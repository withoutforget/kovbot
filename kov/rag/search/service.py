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
from kov.db.models import RagContext, RagQuery, RagRequest, RagResult
from kov.embeddings.fake import FakeEmbedder
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
        self.embedder = FakeEmbedder(vector_size=config.qdrant.vector_size)

    async def search(
        self,
        *,
        user_query: str,
        user_id: uuid.UUID | None,
        scenario_id: str,
        language: str,
        search_profile: str,
    ) -> RagAnswer:
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
        vectors = self.embedder.embed([q.text for q in plan.queries])
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

        # expand context via neighbor chunks from DB
        expanded_contexts: list[dict[str, Any]] = []
        db_contexts: list[RagContext] = []
        seed_items = reranked[: min(5, len(reranked))]
        for seed in seed_items:
            seed_chunk_uuid = uuid.UUID(seed["chunk_id"])
            seed_payload = seed["payload"]
            chunk_row = await self._get_chunk(seed_chunk_uuid)
            if not chunk_row:
                continue
            text = await self._expand_neighbors(chunk_row.document_id, chunk_row.chunk_no)
            ctx = {
                "seed_chunk_id": str(seed_chunk_uuid),
                "expansion_mode": "neighbors",
                "document_id": str(chunk_row.document_id),
                "chapter_title": chunk_row.chapter_title,
                "subchapter_title": chunk_row.subchapter_title,
                "page_start": chunk_row.page_start,
                "page_end": chunk_row.page_end,
                "text": text,
            }
            expanded_contexts.append(ctx)
            db_contexts.append(
                RagContext(
                    id=uuid.uuid4(),
                    request_id=request_uuid,
                    seed_chunk_id=seed_chunk_uuid,
                    expansion_mode="neighbors",
                    document_id=chunk_row.document_id,
                    chapter_title=chunk_row.chapter_title,
                    subchapter_title=chunk_row.subchapter_title,
                    page_start=chunk_row.page_start,
                    page_end=chunk_row.page_end,
                    context_text=text[:8000],
                    context_token_count=max(1, len(text) // 4),
                )
            )
        self.session.add_all(db_contexts)
        await self.session.flush()
        self._put_s3_json(f"rag/{request_uuid}/contexts.json", expanded_contexts)

        answer_text = self._compose_answer(user_query=user_query, contexts=expanded_contexts)
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

    async def _get_chunk(self, chunk_id: uuid.UUID) -> DbChunk | None:
        res = await self.session.execute(select(DbChunk).where(DbChunk.id == chunk_id))
        return res.scalar_one_or_none()

    async def _expand_neighbors(self, document_id: uuid.UUID, chunk_no: int) -> str:
        nos = [n for n in [chunk_no - 1, chunk_no, chunk_no + 1] if n > 0]
        res = await self.session.execute(
            select(DbChunk)
            .where(DbChunk.document_id == document_id)
            .where(DbChunk.chunk_no.in_(nos))
            .order_by(DbChunk.chunk_no.asc())
        )
        chunks = list(res.scalars().all())
        return "\n\n".join([c.text for c in chunks if c.text])

    def _compose_answer(self, *, user_query: str, contexts: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        lines.append("Коротко: я постараюсь опереться на найденные фрагменты из корпуса.")
        lines.append("")
        lines.append(f"Ваш запрос: {user_query.strip()}")
        lines.append("")
        if not contexts:
            lines.append("Пока не нашлось релевантных фрагментов в корпусе. Попробуйте переформулировать запрос.")
            return "\n".join(lines).strip()
        lines.append("Что можно попробовать (черновой grounded-ответ):")
        for i, ctx in enumerate(contexts[:5], start=1):
            snippet = (ctx["text"] or "").strip().replace("\n", " ")
            snippet = snippet[:240] + ("…" if len(snippet) > 240 else "")
            src = f"Источник: doc={ctx['document_id']} стр. {ctx['page_start']}-{ctx['page_end']}"
            lines.append(f"{i}. {snippet}")
            lines.append(f"   {src}")
        return "\n".join(lines).strip()

    def _put_s3_json(self, key: str, payload: Any) -> None:
        self.s3.put_object(
            Bucket=self.config.s3.bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
