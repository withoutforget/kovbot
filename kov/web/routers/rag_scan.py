import uuid

from botocore.client import BaseClient
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.rag.scan.service import RagScanService
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


@router.post("/upload", response_model=ScanUploadResponse)
async def upload_pdf(
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
    file: UploadFile = File(...),
) -> ScanUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf is supported")
    pdf_bytes = await file.read()
    service = RagScanService(config=config, session=session, qdrant=qdrant, s3=s3)
    result = await service.ingest_pdf(filename=file.filename, pdf_bytes=pdf_bytes)
    return ScanUploadResponse(document_id=str(result.document_id), status=result.status)


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
