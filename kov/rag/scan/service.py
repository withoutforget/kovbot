from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.db.models import Chunk as DbChunk
from kov.db.models import Document
from kov.embeddings.factory import create_embedder
from kov.logging import get_logger
from kov.rag.scan.chunking import semantic_chunk_text, simple_chunk_text
from kov.rag.scan.pdf import detect_pdf_type, extract_text_per_page, sha256_bytes


@dataclass(frozen=True)
class ScanResult:
    document_id: uuid.UUID
    status: str


class RagScanService:
    def __init__(self, *, config: AppConfig, session: AsyncSession, qdrant: QdrantClient, s3):
        self.config = config
        self.session = session
        self.qdrant = qdrant
        self.s3 = s3
        self.log = get_logger(component="rag_scan")
        self.embedder = create_embedder(config)

    def _embedding_model_name(self) -> str:
        provider = (self.config.embeddings.provider or "fake").lower()
        if provider in {"openai", "openai_compat", "proxyapi"}:
            return self.config.embeddings.model or "openai-compat"
        return "fake-embedder"

    async def process_document(self, *, document_id: uuid.UUID) -> ScanResult:
        doc = await self.get_document(document_id)
        if not doc:
            raise ValueError("Document not found")
        source_key = f"documents/{document_id}/source.pdf"
        doc.status = "processing"
        doc.error_reason = ""
        await self.session.commit()

        try:
            pdf_bytes = self.s3.get_object(Bucket=self.config.s3.bucket, Key=source_key)["Body"].read()
            sha256 = sha256_bytes(pdf_bytes)
            page_texts = extract_text_per_page(pdf_bytes).page_texts
            pdf_type = detect_pdf_type(page_texts)
            page_count = len(page_texts)

            doc.sha256 = sha256
            doc.size_bytes = len(pdf_bytes)
            doc.page_count = page_count
            doc.pdf_type = pdf_type
            doc.ocr_used = False
            doc.pipeline_version = self.config.rag_scan.pipeline_version
            doc.last_processed_at = datetime.now(tz=timezone.utc)
            doc.status = "parsed"
            await self.session.flush()

            # artifacts: parsed
            self._put_s3_json(
                f"documents/{document_id}/parsed.json",
                {"page_texts": page_texts, "pdf_type": pdf_type, "page_count": page_count},
            )

            chunking_mode = (self.config.rag_scan.chunking.mode or "semantic").lower()
            if chunking_mode == "simple":
                chunks = simple_chunk_text(
                    page_texts=page_texts,
                    max_chars=self.config.rag_scan.chunking.max_chars,
                    overlap_chars=self.config.rag_scan.chunking.overlap_chars,
                )
            else:
                chunks = semantic_chunk_text(
                    page_texts=page_texts,
                    max_chars=self.config.rag_scan.chunking.max_chars,
                    overlap_chars=self.config.rag_scan.chunking.overlap_chars,
                    strip_repeated_headers_footers=bool(
                        self.config.rag_scan.chunking.strip_repeated_headers_footers
                    ),
                    drop_low_signal_paragraphs=bool(self.config.rag_scan.chunking.drop_low_signal_paragraphs),
                    min_alpha_chars=int(self.config.rag_scan.chunking.min_alpha_chars or 20),
                )

            db_chunks: list[DbChunk] = []
            for idx, chunk in enumerate(chunks, start=1):
                db_chunks.append(
                    DbChunk(
                        id=uuid.uuid4(),
                        document_id=document_id,
                        chunk_no=idx,
                        text=chunk.text,
                        content_type=chunk.content_type,
                        heading_path=chunk.heading_path or [],
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        pages=list(range(chunk.page_start, chunk.page_end + 1)),
                        char_count=len(chunk.text),
                        token_count=max(1, len(chunk.text) // 4),
                        ocr_used=False,
                        chunking_version=self.config.rag_scan.pipeline_version,
                        embedding_model=self._embedding_model_name(),
                    )
                )
            self.session.add_all(db_chunks)
            await self.session.flush()

            self._put_s3_json(
                f"documents/{document_id}/chunks.json",
                [
                    {
                        "chunk_id": str(c.id),
                        "chunk_no": c.chunk_no,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "text": c.text,
                    }
                    for c in db_chunks
                ],
            )

            vectors = await self.embedder.embed([c.text for c in db_chunks])
            points: list[qmodels.PointStruct] = []
            for c, v in zip(db_chunks, vectors, strict=False):
                payload: dict[str, Any] = {
                    "document_id": str(document_id),
                    "chunk_id": str(c.id),
                    "text": c.text,
                    "original_filename": doc.original_filename,
                    "language": doc.language,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "chapter_no": c.chapter_no,
                    "chapter_title": c.chapter_title,
                    "subchapter_no": c.subchapter_no,
                    "subchapter_title": c.subchapter_title,
                    "heading_path": c.heading_path,
                    "content_type": c.content_type,
                    "topic_tags": c.topic_tags,
                    "approach_tags": c.approach_tags,
                    "ocr_used": c.ocr_used,
                    "pipeline_version": self.config.rag_scan.pipeline_version,
                }
                points.append(qmodels.PointStruct(id=str(c.id), vector=v, payload=payload))

            batch_size = max(1, int(self.config.qdrant.upsert_batch_size or 64))
            for start in range(0, len(points), batch_size):
                batch = points[start : start + batch_size]
                self.qdrant.upsert(collection_name=self.config.qdrant.collection, points=batch)

            doc.status = "completed"
            await self.session.commit()
            return ScanResult(document_id=document_id, status=doc.status)
        except Exception as e:
            doc.status = "failed"
            doc.error_reason = (str(e) or "unknown error")[:4000]
            await self.session.commit()
            raise

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        res = await self.session.execute(select(Document).where(Document.id == document_id))
        return res.scalar_one_or_none()

    def _put_s3_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(
            Bucket=self.config.s3.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def _put_s3_json(self, key: str, payload: Any) -> None:
        self._put_s3_bytes(key, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")
