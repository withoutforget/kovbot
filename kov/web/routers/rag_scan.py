import uuid

from botocore.client import BaseClient
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.db.models import Document
from kov.db.session import create_engine_and_sessionmaker
from kov.qdrant.client import create_qdrant_client, ensure_collection
from kov.rag.scan.service import RagScanService
from kov.s3.client import create_s3_client, ensure_bucket
router = APIRouter(route_class=DishkaRoute)


class ScanUploadResponse(BaseModel):
    document_id: str
    status: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: str
    pdf_type: str
    page_count: int
    error_reason: str = ""


async def _run_scan_job(*, config: AppConfig, document_id: uuid.UUID) -> None:
    engine, sessionmaker = create_engine_and_sessionmaker(config.postgres.dsn)
    qdrant = create_qdrant_client(config.qdrant.url, timeout_seconds=config.qdrant.timeout_seconds)
    ensure_collection(qdrant, config.qdrant.collection, config.qdrant.vector_size)
    s3 = create_s3_client(
        endpoint_url=config.s3.endpoint_url,
        access_key=config.s3.access_key,
        secret_key=config.s3.secret_key,
        region=config.s3.region,
    )
    ensure_bucket(s3, config.s3.bucket)
    try:
        async with sessionmaker() as session:
            service = RagScanService(config=config, session=session, qdrant=qdrant, s3=s3)
            await service.process_document(document_id=document_id)
    finally:
        await engine.dispose()


@router.post("/upload", response_model=ScanUploadResponse, status_code=202)
async def upload_pdf(
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> ScanUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf is supported")
    pdf_bytes = await file.read()

    document_id = uuid.uuid4()
    source_key = f"documents/{document_id}/source.pdf"
    s3.put_object(
        Bucket=config.s3.bucket, Key=source_key, Body=pdf_bytes, ContentType="application/pdf"
    )

    doc = Document(
        id=document_id,
        original_filename=file.filename,
        source_uri=f"s3://{config.s3.bucket}/{source_key}",
        sha256="",
        size_bytes=len(pdf_bytes),
        page_count=0,
        pdf_type="unknown",
        ocr_used=False,
        pipeline_version=config.rag_scan.pipeline_version,
        status="queued",
        error_reason="",
    )
    session.add(doc)
    await session.commit()

    background_tasks.add_task(_run_scan_job, config=config, document_id=document_id)
    return ScanUploadResponse(document_id=str(document_id), status="queued")


@router.get("/documents/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
) -> DocumentStatusResponse:
    service = RagScanService(config=config, session=session, qdrant=qdrant, s3=s3)
    doc = await service.get_document(uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return DocumentStatusResponse(
        document_id=str(doc.id),
        status=doc.status,
        pdf_type=doc.pdf_type,
        page_count=doc.page_count,
        error_reason=doc.error_reason,
    )
