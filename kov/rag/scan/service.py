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
from kov.embeddings.fake import FakeEmbedder
from kov.logging import get_logger
from kov.rag.scan.chunking import simple_chunk_text
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
        self.embedder = FakeEmbedder(vector_size=config.qdrant.vector_size)

    async def ingest_pdf(self, *, filename: str, pdf_bytes: bytes) -> ScanResult:
        document_id = uuid.uuid4()
        sha256 = sha256_bytes(pdf_bytes)
        page_texts = extract_text_per_page(pdf_bytes).page_texts
        pdf_type = detect_pdf_type(page_texts)
        page_count = len(page_texts)

        doc = Document(
            id=document_id,
            original_filename=filename,
            sha256=sha256,
            size_bytes=len(pdf_bytes),
            page_count=page_count,
            pdf_type=pdf_type,
            ocr_used=False,
            pipeline_version=self.config.rag_scan.pipeline_version,
            status="parsed",
            last_processed_at=datetime.now(tz=timezone.utc),
        )
        self.session.add(doc)
        await self.session.flush()

        # store source PDF
        self._put_s3_bytes(f"documents/{document_id}/source.pdf", pdf_bytes, "application/pdf")

        # artifacts: parsed
        self._put_s3_json(
            f"documents/{document_id}/parsed.json",
            {"page_texts": page_texts, "pdf_type": pdf_type, "page_count": page_count},
        )

        chunks = simple_chunk_text(
            page_texts=page_texts,
            max_chars=self.config.rag_scan.chunking.max_chars,
            overlap_chars=self.config.rag_scan.chunking.overlap_chars,
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
                    embedding_model="fake-embedder",
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

        vectors = self.embedder.embed([c.text for c in db_chunks])
        points: list[qmodels.PointStruct] = []
        for c, v in zip(db_chunks, vectors, strict=False):
            payload: dict[str, Any] = {
                "document_id": str(document_id),
                "chunk_id": str(c.id),
                "text": c.text,
                "original_filename": filename,
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

        self.qdrant.upsert(collection_name=self.config.qdrant.collection, points=points)
        doc.status = "completed"
        await self.session.commit()
        return ScanResult(document_id=document_id, status=doc.status)

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

