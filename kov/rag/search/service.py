from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.db.models import Chunk as DbChunk
from kov.db.models import UserProfile
from kov.db.models import RagContext, RagQuery, RagRequest, RagResult
from kov.embeddings.factory import create_embedder
from kov.llm.openai_compat import OpenAICompatClient
from kov.logging import get_logger
from kov.rag.search.planner import plan_queries
from kov.rag.search.telegram import split_telegram
from kov.rag.types import RagAnswer
from kov.usage.tokens import record_token_usage


class RagSearchService:
    def __init__(self, *, config: AppConfig, session: AsyncSession, qdrant: QdrantClient, s3):
        self.config = config
        self.session = session
        self.qdrant = qdrant
        self.s3 = s3
        self.log = get_logger(component="rag_search")
        self.embedder = create_embedder(config)
        self.llm = OpenAICompatClient(config.llm)

    async def search(
        self,
        *,
        user_query: str,
        user_id: uuid.UUID | None,
        scenario_id: str,
        language: str,
        search_profile: str,
        llm_overrides: dict[str, Any] | None = None,
        source_channel: str = "api",
    ) -> RagAnswer:
        profile_summary = await self._get_profile_summary(user_id=user_id)
        plan = await plan_queries(
            config=self.config, user_query=user_query, language=language, search_profile=search_profile
        )
        request_uuid = uuid.UUID(plan.request_id)

        req = RagRequest(
            id=request_uuid,
            user_id=user_id,
            scenario_id=scenario_id,
            source_channel=source_channel,
            user_query=user_query,
            normalized_state=plan.normalized_state.model_dump(),
            search_profile=plan.search_profile,
            status="retrieval",
            pipeline_version=self.config.rag_search.pipeline_version,
        )
        self.session.add(req)
        await self.session.flush()

        self._put_s3_json(f"rag/{request_uuid}/plan.json", plan.model_dump())

        # persist queries
        db_queries: list[RagQuery] = []
        for q in plan.queries:
            db_queries.append(
                RagQuery(
                    id=uuid.uuid4(),
                    request_id=request_uuid,
                    query_id=q.query_id,
                    text=q.text,
                    intent_type=q.intent_type,
                    weight=q.weight,
                    topic_tags=q.topic_tags,
                    approach_tags=q.approach_tags,
                    preferred_content_types=q.preferred_content_types,
                    expected_granularity=q.expected_granularity,
                )
            )
        self.session.add_all(db_queries)
        await self.session.flush()

        # retrieval
        candidates: dict[str, dict[str, Any]] = {}
        vectors = await self.embedder.embed([q.text for q in plan.queries])
        for q, vector in zip(plan.queries, vectors, strict=False):
            hits = self.qdrant.search(
                collection_name=self.config.qdrant.collection,
                query_vector=vector,
                limit=self.config.rag_search.retrieval.top_k_per_query,
                score_threshold=self.config.rag_search.retrieval.min_score,
            )
            for hit in hits:
                chunk_id = str(hit.id)
                prev = candidates.get(chunk_id)
                score = float(hit.score or 0.0) * float(q.weight)
                if not prev or score > prev["score_retrieval"]:
                    candidates[chunk_id] = {
                        "query_id": q.query_id,
                        "chunk_id": chunk_id,
                        "document_id": (hit.payload or {}).get("document_id", ""),
                        "score_retrieval": score,
                        "payload": hit.payload or {},
                    }

        self.log.info(
            "rag_retrieval_completed",
            queries=len(plan.queries),
            candidates=len(candidates),
            top_k_per_query=self.config.rag_search.retrieval.top_k_per_query,
        )

        retrieved = sorted(candidates.values(), key=lambda x: x["score_retrieval"], reverse=True)
        reranked = await self._rerank_candidates(
            user_query=user_query,
            retrieved=retrieved,
        )

        # persist results
        db_results: list[RagResult] = []
        for rank, item in enumerate(reranked, start=1):
            payload = item["payload"]
            doc_id_str = payload.get("document_id") or ""
            if not doc_id_str:
                continue
            db_results.append(
                RagResult(
                    id=uuid.uuid4(),
                    request_id=request_uuid,
                    query_id=item["query_id"],
                    document_id=uuid.UUID(doc_id_str),
                    chunk_id=uuid.UUID(item["chunk_id"]),
                    score_retrieval=item["score_retrieval"],
                    score_rerank=float(item.get("score_rerank") or item["score_retrieval"]),
                    rank_final=rank,
                    content_type=payload.get("content_type", "text"),
                    heading_path=payload.get("heading_path", []),
                    page_start=int(payload.get("page_start") or 0),
                    page_end=int(payload.get("page_end") or 0),
                    ocr_used=bool(payload.get("ocr_used") or False),
                    text_snippet=(payload.get("text") or "")[:240],
                )
            )
        self.session.add_all(db_results)
        await self.session.flush()
        self._put_s3_json(f"rag/{request_uuid}/candidates.json", reranked)

        expanded_contexts = await self._expand_contexts(request_id=request_uuid, reranked=reranked, persist=True)
        answer_text, usage, model_used = await self._compose_answer_llm(
            user_query=user_query,
            language=language,
            expanded_contexts=expanded_contexts,
            user_profile_summary=profile_summary,
            llm_overrides=llm_overrides,
        )
        telegram_parts = split_telegram(
            answer_text,
            safe_limit_chars=self.config.rag_search.telegram.safe_limit_chars,
            max_parts=self.config.rag_search.telegram.max_parts,
        )

        req.status = "completed"
        req.completed_at = datetime.now(tz=timezone.utc)

        if user_id:
            pt = int((usage or {}).get("prompt_tokens") or max(1, len(user_query) // 4))
            ct = int((usage or {}).get("completion_tokens") or max(1, len(answer_text) // 4))
            await record_token_usage(
                session=self.session,
                user_id=user_id,
                source="rag_search",
                model=(model_used or self.config.llm.model or ""),
                prompt_tokens=pt,
                completion_tokens=ct,
                request_id=request_uuid,
                meta={"scenario_id": scenario_id, "source_channel": source_channel, "search_profile": search_profile},
            )

        await self.session.commit()

        answer = RagAnswer(
            request_id=str(request_uuid),
            answer_type=plan.search_profile,
            summary=plan.normalized_state.summary,
            advice_items=[],
            telegram_messages=telegram_parts,
        )
        self._put_s3_json(f"rag/{request_uuid}/answer.json", answer.model_dump())
        return answer

    async def search_stream(
        self,
        *,
        user_query: str,
        user_id: uuid.UUID | None,
        scenario_id: str,
        language: str,
        search_profile: str,
        llm_overrides: dict[str, Any] | None = None,
        source_channel: str = "api",
    ):
        """
        Streaming variant of `search()`:
        - persists the same pipeline artifacts (plan/results/contexts) into DB + S3
        - streams only the final LLM output
        """
        profile_summary = await self._get_profile_summary(user_id=user_id)
        plan = await plan_queries(
            config=self.config, user_query=user_query, language=language, search_profile=search_profile
        )
        request_uuid = uuid.UUID(plan.request_id)

        req = RagRequest(
            id=request_uuid,
            user_id=user_id,
            scenario_id=scenario_id,
            source_channel=source_channel,
            user_query=user_query,
            normalized_state=plan.normalized_state.model_dump(),
            search_profile=plan.search_profile,
            status="retrieval",
            pipeline_version=self.config.rag_search.pipeline_version,
        )
        self.session.add(req)
        await self.session.flush()

        self._put_s3_json(f"rag/{request_uuid}/plan.json", plan.model_dump())

        db_queries: list[RagQuery] = []
        for q in plan.queries:
            db_queries.append(
                RagQuery(
                    id=uuid.uuid4(),
                    request_id=request_uuid,
                    query_id=q.query_id,
                    text=q.text,
                    intent_type=q.intent_type,
                    weight=q.weight,
                    topic_tags=q.topic_tags,
                    approach_tags=q.approach_tags,
                    preferred_content_types=q.preferred_content_types,
                    expected_granularity=q.expected_granularity,
                )
            )
        self.session.add_all(db_queries)
        await self.session.flush()

        candidates: dict[str, dict[str, Any]] = {}
        vectors = await self.embedder.embed([q.text for q in plan.queries])
        for q, vector in zip(plan.queries, vectors, strict=False):
            hits = self.qdrant.search(
                collection_name=self.config.qdrant.collection,
                query_vector=vector,
                limit=self.config.rag_search.retrieval.top_k_per_query,
                score_threshold=self.config.rag_search.retrieval.min_score,
            )
            for hit in hits:
                chunk_id = str(hit.id)
                prev = candidates.get(chunk_id)
                score = float(hit.score or 0.0) * float(q.weight)
                if not prev or score > prev["score_retrieval"]:
                    candidates[chunk_id] = {
                        "query_id": q.query_id,
                        "chunk_id": chunk_id,
                        "document_id": (hit.payload or {}).get("document_id", ""),
                        "score_retrieval": score,
                        "payload": hit.payload or {},
                    }

        self.log.info(
            "rag_retrieval_completed",
            mode="stream",
            queries=len(plan.queries),
            candidates=len(candidates),
            top_k_per_query=self.config.rag_search.retrieval.top_k_per_query,
        )

        retrieved = sorted(candidates.values(), key=lambda x: x["score_retrieval"], reverse=True)
        reranked = await self._rerank_candidates(user_query=user_query, retrieved=retrieved)
        db_results: list[RagResult] = []
        for rank, item in enumerate(reranked, start=1):
            payload = item["payload"]
            doc_id_str = payload.get("document_id") or ""
            if not doc_id_str:
                continue
            db_results.append(
                RagResult(
                    id=uuid.uuid4(),
                    request_id=request_uuid,
                    query_id=item["query_id"],
                    document_id=uuid.UUID(doc_id_str),
                    chunk_id=uuid.UUID(item["chunk_id"]),
                    score_retrieval=item["score_retrieval"],
                    score_rerank=float(item.get("score_rerank") or item["score_retrieval"]),
                    rank_final=rank,
                    content_type=payload.get("content_type", "text"),
                    heading_path=payload.get("heading_path", []),
                    page_start=int(payload.get("page_start") or 0),
                    page_end=int(payload.get("page_end") or 0),
                    ocr_used=bool(payload.get("ocr_used") or False),
                    text_snippet=(payload.get("text") or "")[:240],
                )
            )
        self.session.add_all(db_results)
        await self.session.flush()
        self._put_s3_json(f"rag/{request_uuid}/candidates.json", reranked)

        expanded_contexts = await self._expand_contexts(request_id=request_uuid, reranked=reranked, persist=True)

        usage_out: dict[str, int] = {}
        full = ""
        async for delta in self.compose_answer_llm_stream(
            user_query=user_query,
            language=language,
            expanded_contexts=expanded_contexts,
            user_profile_summary=profile_summary,
            llm_overrides=llm_overrides,
            usage_out=usage_out,
        ):
            if not delta:
                continue
            full += delta
            yield delta

        req.status = "completed"
        req.completed_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

        if user_id:
            pt = int(usage_out.get("prompt_tokens") or max(1, len(user_query) // 4))
            ct = int(usage_out.get("completion_tokens") or max(1, len(full) // 4))
            await record_token_usage(
                session=self.session,
                user_id=user_id,
                source="rag_search_stream",
                model=(self.config.llm.model or ""),
                prompt_tokens=pt,
                completion_tokens=ct,
                request_id=request_uuid,
                meta={"scenario_id": scenario_id, "source_channel": source_channel, "search_profile": search_profile},
            )

        await self.session.commit()

        answer = RagAnswer(
            request_id=str(request_uuid),
            answer_type=plan.search_profile,
            summary=plan.normalized_state.summary,
            advice_items=[],
            telegram_messages=split_telegram(
                full,
                safe_limit_chars=self.config.rag_search.telegram.safe_limit_chars,
                max_parts=self.config.rag_search.telegram.max_parts,
            ),
        )
        self._put_s3_json(f"rag/{request_uuid}/answer.json", answer.model_dump())

    async def search_debug(
        self,
        *,
        user_query: str,
        user_id: uuid.UUID | None,
        scenario_id: str,
        language: str,
        search_profile: str,
    ) -> dict[str, Any]:
        """
        Debug endpoint: returns pipeline artifacts (plan, candidates, expanded contexts).
        """
        plan = await plan_queries(
            config=self.config, user_query=user_query, language=language, search_profile=search_profile
        )
        request_uuid = uuid.UUID(plan.request_id)

        # Run the same pipeline steps but without DB persistence requirements for the response payload.
        vectors = await self.embedder.embed([q.text for q in plan.queries])
        candidates: dict[str, dict[str, Any]] = {}
        for q, vector in zip(plan.queries, vectors, strict=False):
            hits = self.qdrant.search(
                collection_name=self.config.qdrant.collection,
                query_vector=vector,
                limit=self.config.rag_search.retrieval.top_k_per_query,
                score_threshold=self.config.rag_search.retrieval.min_score,
            )
            for hit in hits:
                chunk_id = str(hit.id)
                prev = candidates.get(chunk_id)
                score = float(hit.score or 0.0) * float(q.weight)
                if not prev or score > prev["score_retrieval"]:
                    candidates[chunk_id] = {
                        "query_id": q.query_id,
                        "chunk_id": chunk_id,
                        "document_id": (hit.payload or {}).get("document_id", ""),
                        "score_retrieval": score,
                        "payload": hit.payload or {},
                    }
        retrieved = sorted(candidates.values(), key=lambda x: x["score_retrieval"], reverse=True)
        reranked = await self._rerank_candidates(user_query=user_query, retrieved=retrieved)
        expanded_contexts = await self._expand_contexts(request_id=request_uuid, reranked=reranked, persist=False)
        return {
            "request_id": str(request_uuid),
            "plan": plan.model_dump(),
            "reranked": reranked[:20],
            "expanded_contexts": expanded_contexts,
        }

    async def _rerank_candidates(self, *, user_query: str, retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Takes retrieval results (sorted by vector score) and (optionally) reranks them with an LLM-based reranker.

        Behavior:
        - Always caps the list to `rag_search.reranker.final_k` (default 100).
        - If LLM is not configured or reranker is disabled, falls back to retrieval ordering.
        """
        cfg = self.config.rag_search.reranker
        top_n = max(1, int(cfg.top_n or 100))
        final_k = max(1, int(cfg.final_k or 100))
        retrieved_top = retrieved[:top_n]

        enabled = bool(cfg.enabled)
        llm_ready = bool(self.config.llm.base_url and self.config.llm.api_key and self.config.llm.model)
        if not (enabled and llm_ready) or not retrieved_top:
            return retrieved_top[:final_k]

        mode = (cfg.mode or "list").strip().lower()
        if mode == "full":
            scored = await self._score_with_llm(user_query=user_query, candidates=retrieved_top)
            scored_sorted = sorted(
                scored,
                key=lambda x: (float(x.get("score_rerank") or 0.0), float(x.get("score_retrieval") or 0.0)),
                reverse=True,
            )
            out = scored_sorted[:final_k]
            self.log.info(
                "rag_rerank_completed",
                mode="full",
                retrieved=len(retrieved),
                rerank_in=len(retrieved_top),
                rerank_out=len(out),
            )
            return out

        try:
            order = await self._rerank_with_llm(
                user_query=user_query,
                candidates=retrieved_top,
            )
            by_id = {c["chunk_id"]: c for c in retrieved_top if c.get("chunk_id")}
            reranked: list[dict[str, Any]] = []
            for cid in order:
                item = by_id.get(cid)
                if item:
                    reranked.append(item)
            # append missing (shouldn't happen often) in retrieval order
            for item in retrieved_top:
                if item.get("chunk_id") and item["chunk_id"] not in set(order):
                    reranked.append(item)
            # keep a deterministic rerank score for visibility (descending from 1.0)
            if reranked:
                denom = max(1, len(reranked) - 1)
                for idx, it in enumerate(reranked):
                    it["score_rerank"] = float(1.0 - (idx / denom))
            out = reranked[:final_k]
            self.log.info(
                "rag_rerank_completed",
                mode="list",
                retrieved=len(retrieved),
                rerank_in=len(retrieved_top),
                rerank_out=len(out),
            )
            return out
        except Exception as e:
            self.log.warning("rerank_failed_fallback_to_retrieval", error=str(e))
            return retrieved_top[:final_k]

    _JSON_ARRAY_RE = re.compile(r"\\[[\\s\\S]*\\]")

    def _extract_json_array(self, text: str) -> list[Any] | None:
        if not text:
            return None
        m = self._JSON_ARRAY_RE.search(text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    async def _rerank_with_llm(
        self,
        *,
        user_query: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        cfg = self.config.rag_search.reranker
        passage_max_chars = max(100, int(cfg.passage_max_chars or 800))
        model = (cfg.model or "").strip() or self.config.llm.model

        passages: list[dict[str, str]] = []
        for c in candidates:
            cid = str(c.get("chunk_id") or "")
            payload = c.get("payload") or {}
            t = str(payload.get("text") or payload.get("text_snippet") or "")
            t = t.strip().replace("\u00a0", " ")
            if len(t) > passage_max_chars:
                t = t[:passage_max_chars]
            if cid and t:
                passages.append({"id": cid, "text": t})

        system = (
            "Ты — SOTA reranker. Твоя задача: упорядочить passages по полезности для ответа на query. "
            "Выведи только JSON-массив ids в порядке убывания релевантности. Без пояснений. "
            "Если passages пустые — верни []."
        )
        user = json.dumps({"query": user_query, "passages": passages}, ensure_ascii=False)

        raw = await self.llm.chat_completions(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            temperature=0.0,
            max_tokens=600,
        )
        txt = OpenAICompatClient.extract_text(raw).strip()
        arr = self._extract_json_array(txt)
        if not isinstance(arr, list):
            raise RuntimeError("reranker returned non-json-array")

        ordered: list[str] = []
        seen: set[str] = set()
        for item in arr:
            if isinstance(item, str) and item in {p["id"] for p in passages} and item not in seen:
                ordered.append(item)
                seen.add(item)
        # if model returned nothing usable, fallback to retrieval ids
        if not ordered:
            return [str(c.get("chunk_id")) for c in candidates if c.get("chunk_id")]
        return ordered

    _JSON_OBJ_RE = re.compile(r"\\{[\\s\\S]*\\}")
    _JSON_NUM_RE = re.compile(r"(?<![0-9.])-?(?:0(?:\\.\\d+)?|1(?:\\.0+)?)")

    def _extract_score(self, text: str) -> float | None:
        """
        Accepts either:
        - JSON object: {"score": 0.73}
        - JSON number: 0.73
        """
        t = (text or "").strip()
        if not t:
            return None
        # First try full parse
        try:
            parsed = json.loads(t)
            if isinstance(parsed, (int, float)):
                val = float(parsed)
                return min(1.0, max(0.0, val))
            if isinstance(parsed, dict) and isinstance(parsed.get("score"), (int, float)):
                val = float(parsed["score"])
                return min(1.0, max(0.0, val))
        except Exception:
            pass

        m = self._JSON_OBJ_RE.search(t)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict) and isinstance(obj.get("score"), (int, float)):
                    val = float(obj["score"])
                    return min(1.0, max(0.0, val))
            except Exception:
                pass

        m2 = self._JSON_NUM_RE.search(t)
        if m2:
            try:
                val = float(m2.group(0))
                return min(1.0, max(0.0, val))
            except Exception:
                return None
        return None

    async def _score_with_llm(
        self,
        *,
        user_query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Full mode: score each passage independently with a JSON score in [0,1].
        """
        cfg = self.config.rag_search.reranker
        passage_max_chars = max(100, int(cfg.passage_max_chars or 800))
        model = (cfg.model or "").strip() or self.config.llm.model
        concurrency = max(1, int(cfg.concurrency or 8))
        sem = asyncio.Semaphore(concurrency)

        async def score_one(item: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                payload = item.get("payload") or {}
                t = str(payload.get("text") or payload.get("text_snippet") or "").strip().replace("\u00a0", " ")
                if len(t) > passage_max_chars:
                    t = t[:passage_max_chars]

                system = (
                    "Оцени релевантность passage к query. "
                    "Верни строго JSON: {\"score\": <float 0..1>}. "
                    "0 — совсем не относится, 1 — идеально относится. "
                    "Без текста, без пояснений, только JSON."
                )
                user = json.dumps({"query": user_query, "passage": t}, ensure_ascii=False)
                try:
                    raw = await self.llm.chat_completions(
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                        model=model,
                        temperature=0.0,
                        max_tokens=500,
                    )
                    txt = OpenAICompatClient.extract_text(raw).strip()
                    score = self._extract_score(txt)
                    if score is None:
                        # Some models (notably reasoning-only variants) may return empty content.
                        # Retry once with an even simpler output format (a single JSON number).
                        raw2 = await self.llm.chat_completions(
                            messages=[
                                {"role": "system", "content": "Верни одно число 0..1 в JSON (например 0.37). Только JSON."},
                                {"role": "user", "content": user},
                            ],
                            model=model,
                            temperature=0.0,
                            max_tokens=500,
                        )
                        txt2 = OpenAICompatClient.extract_text(raw2).strip()
                        score = self._extract_score(txt2)
                except Exception as e:
                    self.log.warning("full_rerank_item_failed", error=str(e))
                    score = None

                out = dict(item)
                out["score_rerank"] = float(score) if score is not None else 0.0
                return out

        scored = await asyncio.gather(*(score_one(i) for i in candidates))
        self.log.info(
            "full_rerank_completed",
            candidates=len(candidates),
            concurrency=concurrency,
            model=model,
        )
        return list(scored)

    async def _get_profile_summary(self, *, user_id: uuid.UUID | None) -> str | None:
        if not user_id:
            return None
        res = await self.session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        prof = res.scalar_one_or_none()
        summary = (prof.interview_summary or "").strip() if prof else ""
        return summary or None

    async def _get_chunk(self, chunk_id: uuid.UUID) -> DbChunk | None:
        res = await self.session.execute(select(DbChunk).where(DbChunk.id == chunk_id))
        return res.scalar_one_or_none()

    async def _expand_window(self, document_id: uuid.UUID, chunk_no: int, window: int) -> list[DbChunk]:
        lo = max(1, chunk_no - window)
        hi = chunk_no + window
        res = await self.session.execute(
            select(DbChunk)
            .where(DbChunk.document_id == document_id)
            .where(DbChunk.chunk_no.between(lo, hi))
            .order_by(DbChunk.chunk_no.asc())
        )
        return list(res.scalars().all())

    async def _expand_contexts(
        self, *, request_id: uuid.UUID, reranked: list[dict[str, Any]], persist: bool
    ) -> list[dict[str, Any]]:
        expanded_contexts: list[dict[str, Any]] = []
        db_contexts: list[RagContext] = []

        seed_top_n = max(1, int(self.config.rag_search.expander.seed_top_n or 10))
        window = max(0, int(self.config.rag_search.expander.neighbor_window or 5))
        max_total = max(2000, int(self.config.rag_search.expander.max_context_chars or 24000))

        # take top-N seeds and expand by larger window of neighbor chunks
        total_chars = 0
        seed_items = reranked[: min(seed_top_n, len(reranked))]
        for seed in seed_items:
            if total_chars >= max_total:
                break
            seed_chunk_uuid = uuid.UUID(seed["chunk_id"])
            chunk_row = await self._get_chunk(seed_chunk_uuid)
            if not chunk_row:
                continue
            chunks = await self._expand_window(chunk_row.document_id, chunk_row.chunk_no, window)
            text = "\n\n".join([c.text for c in chunks if c.text]).strip()
            if not text:
                continue

            ctx = {
                "seed_chunk_id": str(seed_chunk_uuid),
                "expansion_mode": "window",
                "document_id": str(chunk_row.document_id),
                "chunk_no": int(chunk_row.chunk_no),
                "page_start": int(min([c.page_start for c in chunks] or [chunk_row.page_start])),
                "page_end": int(max([c.page_end for c in chunks] or [chunk_row.page_end])),
                "text": text,
            }
            expanded_contexts.append(ctx)
            db_contexts.append(
                RagContext(
                    id=uuid.uuid4(),
                    request_id=request_id,
                    seed_chunk_id=seed_chunk_uuid,
                    expansion_mode="window",
                    document_id=chunk_row.document_id,
                    chapter_title=chunk_row.chapter_title,
                    subchapter_title=chunk_row.subchapter_title,
                    page_start=ctx["page_start"],
                    page_end=ctx["page_end"],
                    context_text=text[:8000],
                    context_token_count=max(1, len(text) // 4),
                )
            )
            total_chars += len(text)

        if persist:
            self.session.add_all(db_contexts)
            await self.session.flush()
            self._put_s3_json(f"rag/{request_id}/contexts.json", expanded_contexts)
        return expanded_contexts

    def _dedupe_context_texts(self, expanded_contexts: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for ctx in expanded_contexts:
            t = (ctx.get("text") or "").strip()
            key = " ".join(t.split())[:400]
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(t)
        return unique

    async def _compose_answer_llm(
        self,
        *,
        user_query: str,
        language: str,
        expanded_contexts: list[dict[str, Any]],
        user_profile_summary: str | None = None,
        llm_overrides: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, int] | None, str]:
        # final answer should be the LLM answer, without sources/debug content
        ctx_texts = self._dedupe_context_texts(expanded_contexts)
        if not ctx_texts:
            return (
                "Пока не нашлось релевантных фрагментов в корпусе. Попробуйте переформулировать запрос.",
                None,
                "",
            )

        if not (self.config.llm.base_url and self.config.llm.api_key and self.config.llm.model):
            # graceful degradation (no sources, nicer than debug)
            return (
                f"Ваш запрос: {user_query.strip()}\n\n"
                "Коротко: я нашёл фрагменты в корпусе, но генерация ответа LLM сейчас не настроена. "
                "Попробуйте включить LLM (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL) и повторить запрос."
            ), None, ""

        joined = "\n\n---\n\n".join(ctx_texts)
        # keep prompt bounded
        joined = joined[: max(4000, int(self.config.rag_search.expander.max_context_chars or 24000))]

        system = (
            "Ты — психологический ассистент. Отвечай бережно, структурированно и практично. "
            "Основные объяснения/рекомендации опирай на предоставленные фрагменты (RAG context). "
            "Не упоминай document_id/страницы/источники, не делай ссылок на книги. "
            "Не выдумывай факты, которых нет в контексте. "
            "Не используй Markdown, заголовки и спецразметку. "
            "Формат: 1) короткое объяснение 2) 3–7 конкретных шагов/рекомендаций (нумерованным списком) "
            "3) (опционально) одно короткое упражнение. "
            "В конце (опционально) предложи ОДИН уместный следующий сценарий бота: "
            "«Интервью», «Техники», «Трекер настроения», «Трекер привычек», «Диалог», «Отношения». "
            "Формат одной строки: 'Если хотите, можно перейти в: <сценарий> — <почему>'. "
            "Язык ответа: " + (language or "ru")
        )
        profile_block = ""
        if user_profile_summary:
            profile_block = f"Короткая справка о пользователе (из интервью):\n{user_profile_summary.strip()}\n\n"
        user = f"{profile_block}Запрос пользователя:\n{user_query.strip()}\n\nФрагменты из корпуса:\n{joined}"

        raw = await self.llm.chat_completions(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **(llm_overrides or {}),
        )
        text = OpenAICompatClient.extract_text(raw).strip()
        usage = OpenAICompatClient.extract_usage(raw)
        model_used = str(raw.get("model") or "") if isinstance(raw, dict) else ""
        return text or "Не удалось сгенерировать ответ. Попробуйте переформулировать запрос.", usage, model_used

    async def compose_answer_llm_stream(
        self,
        *,
        user_query: str,
        language: str,
        expanded_contexts: list[dict[str, Any]],
        user_profile_summary: str | None = None,
        llm_overrides: dict[str, Any] | None = None,
        usage_out: dict[str, int] | None = None,
    ):
        """
        Async generator yielding answer text deltas.
        """
        ctx_texts = self._dedupe_context_texts(expanded_contexts)
        if not ctx_texts:
            yield "Пока не нашлось релевантных фрагментов в корпусе. Попробуйте переформулировать запрос."
            return

        if not (self.config.llm.base_url and self.config.llm.api_key and self.config.llm.model):
            yield (
                f"Ваш запрос: {user_query.strip()}\n\n"
                "Коротко: я нашёл фрагменты в корпусе, но генерация ответа LLM сейчас не настроена. "
                "Попробуйте включить LLM (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL) и повторить запрос."
            )
            return

        joined = "\n\n---\n\n".join(ctx_texts)
        joined = joined[: max(4000, int(self.config.rag_search.expander.max_context_chars or 24000))]

        system = (
            "Ты — психологический ассистент. Отвечай бережно, структурированно и практично. "
            "Основные объяснения/рекомендации опирай на предоставленные фрагменты (RAG context). "
            "Не упоминай document_id/страницы/источники, не делай ссылок на книги. "
            "Не выдумывай факты, которых нет в контексте. "
            "Не используй Markdown, заголовки и спецразметку. "
            "Формат: 1) короткое объяснение 2) 3–7 конкретных шагов/рекомендаций (нумерованным списком) "
            "3) (опционально) одно короткое упражнение. "
            "В конце (опционально) предложи ОДИН уместный следующий сценарий бота: "
            "«Интервью», «Техники», «Трекер настроения», «Трекер привычек», «Диалог», «Отношения». "
            "Формат одной строки: 'Если хотите, можно перейти в: <сценарий> — <почему>'. "
            "Язык ответа: " + (language or "ru")
        )
        profile_block = ""
        if user_profile_summary:
            profile_block = f"Короткая справка о пользователе (из интервью):\n{user_profile_summary.strip()}\n\n"
        user = f"{profile_block}Запрос пользователя:\n{user_query.strip()}\n\nФрагменты из корпуса:\n{joined}"

        async for delta in self.llm.chat_completions_stream(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            usage_out=usage_out,
            **(llm_overrides or {}),
        ):
            yield delta

    def _put_s3_json(self, key: str, payload: Any) -> None:
        self.s3.put_object(
            Bucket=self.config.s3.bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
