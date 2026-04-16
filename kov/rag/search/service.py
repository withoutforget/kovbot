from __future__ import annotations

import json
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
    ) -> RagAnswer:
        profile_summary = await self._get_profile_summary(user_id=user_id)
        plan = plan_queries(
            config=self.config, user_query=user_query, language=language, search_profile=search_profile
        )
        request_uuid = uuid.UUID(plan.request_id)

        req = RagRequest(
            id=request_uuid,
            user_id=user_id,
            scenario_id=scenario_id,
            source_channel="api",
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

        # rerank (simple heuristic)
        reranked = sorted(candidates.values(), key=lambda x: x["score_retrieval"], reverse=True)
        reranked = reranked[:50]

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
                    score_rerank=item["score_retrieval"],
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
        answer_text = await self._compose_answer_llm(
            user_query=user_query,
            language=language,
            expanded_contexts=expanded_contexts,
            user_profile_summary=profile_summary,
        )
        telegram_parts = split_telegram(
            answer_text,
            safe_limit_chars=self.config.rag_search.telegram.safe_limit_chars,
            max_parts=self.config.rag_search.telegram.max_parts,
        )

        req.status = "completed"
        req.completed_at = datetime.now(tz=timezone.utc)
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
        plan = plan_queries(
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
        reranked = sorted(candidates.values(), key=lambda x: x["score_retrieval"], reverse=True)[:50]
        expanded_contexts = await self._expand_contexts(request_id=request_uuid, reranked=reranked, persist=False)
        return {
            "request_id": str(request_uuid),
            "plan": plan.model_dump(),
            "reranked": reranked[:20],
            "expanded_contexts": expanded_contexts,
        }

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
    ) -> str:
        # final answer should be the LLM answer, without sources/debug content
        ctx_texts = self._dedupe_context_texts(expanded_contexts)
        if not ctx_texts:
            return "Пока не нашлось релевантных фрагментов в корпусе. Попробуйте переформулировать запрос."

        if not (self.config.llm.base_url and self.config.llm.api_key and self.config.llm.model):
            # graceful degradation (no sources, nicer than debug)
            return (
                f"Ваш запрос: {user_query.strip()}\n\n"
                "Коротко: я нашёл фрагменты в корпусе, но генерация ответа LLM сейчас не настроена. "
                "Попробуйте включить LLM (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL) и повторить запрос."
            )

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
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        text = OpenAICompatClient.extract_text(raw).strip()
        return text or "Не удалось сгенерировать ответ. Попробуйте переформулировать запрос."

    async def compose_answer_llm_stream(
        self,
        *,
        user_query: str,
        language: str,
        expanded_contexts: list[dict[str, Any]],
        user_profile_summary: str | None = None,
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
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
        ):
            yield delta

    def _put_s3_json(self, key: str, payload: Any) -> None:
        self.s3.put_object(
            Bucket=self.config.s3.bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
