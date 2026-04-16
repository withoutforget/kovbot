import json
import uuid
from typing import Any

from botocore.client import BaseClient
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.db.models import (
    Chunk,
    Dialog,
    Document,
    Message,
    RagContext,
    RagResult,
    RagRequest,
    TokenUsageEvent,
    User,
    UserTokenUsageDay,
)
from kov.embeddings.factory import create_embedder
from kov.rag.search.service import RagSearchService
from kov.web.routers.rag_scan import _run_scan_job


templates = Jinja2Templates(directory="apps/api/templates")

router = APIRouter(route_class=DishkaRoute, default_response_class=HTMLResponse)


def _s3_delete_prefix(*, s3: BaseClient, bucket: str, prefix: str) -> int:
    deleted = 0
    token: str | None = None
    while True:
        kwargs: dict[str, object] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        keys = [{"Key": obj["Key"]} for obj in (resp.get("Contents") or []) if obj.get("Key")]
        if keys:
            # S3 accepts up to 1000 keys per delete_objects call.
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
            deleted += len(keys)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return deleted


def _qdrant_delete_document(*, qdrant: QdrantClient, collection: str, document_id: str) -> None:
    flt = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchValue(value=document_id),
            )
        ]
    )
    qdrant.delete(
        collection_name=collection,
        points_selector=qmodels.FilterSelector(filter=flt),
        wait=True,
    )


@router.get("/")
async def admin_index(request: Request):
    return templates.TemplateResponse("admin/index.html", {"request": request})


@router.get("/rag/documents")
async def rag_documents(
    request: Request, session: FromDishka[AsyncSession]
):
    res = await session.execute(select(Document).order_by(Document.created_at.desc()).limit(200))
    docs = res.scalars().all()
    return templates.TemplateResponse("admin/documents.html", {"request": request, "docs": docs})


@router.get("/rag/documents/{document_id}")
async def rag_document_detail(
    document_id: str, request: Request, session: FromDishka[AsyncSession]
):
    doc_uuid = uuid.UUID(document_id)
    doc_res = await session.execute(select(Document).where(Document.id == doc_uuid))
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    chunks_res = await session.execute(
        select(Chunk).where(Chunk.document_id == doc_uuid).order_by(Chunk.chunk_no.asc())
    )
    chunks = chunks_res.scalars().all()
    return templates.TemplateResponse(
        "admin/document_detail.html", {"request": request, "doc": doc, "chunks": chunks}
    )


@router.post("/rag/documents/{document_id}/delete")
async def rag_document_delete(
    document_id: str,
    request: Request,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
    confirm: str = Form(""),
):
    if confirm.strip() != "1":
        raise HTTPException(status_code=400, detail="Confirmation required")

    doc_uuid = uuid.UUID(document_id)
    doc_res = await session.execute(select(Document).where(Document.id == doc_uuid))
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    # Try external deletes first so we can retry via admin if something fails.
    doc.status = "deleting"
    doc.error_reason = ""
    await session.commit()

    errors: list[str] = []
    try:
        _qdrant_delete_document(qdrant=qdrant, collection=config.qdrant.collection, document_id=str(doc_uuid))
    except Exception as e:
        errors.append(f"qdrant: {e}")

    try:
        prefix = f"documents/{doc_uuid}/"
        _s3_delete_prefix(s3=s3, bucket=config.s3.bucket, prefix=prefix)
    except Exception as e:
        errors.append(f"s3: {e}")

    if errors:
        doc.status = "delete_failed"
        doc.error_reason = "; ".join(errors)[:4000]
        await session.commit()
        raise HTTPException(status_code=500, detail={"errors": errors})

    # Now hard-delete DB rows.
    chunk_ids_res = await session.execute(select(Chunk.id).where(Chunk.document_id == doc_uuid))
    chunk_ids = [row[0] for row in chunk_ids_res.all()]

    if chunk_ids:
        await session.execute(delete(RagResult).where(RagResult.chunk_id.in_(chunk_ids)))
        await session.execute(delete(RagContext).where(RagContext.seed_chunk_id.in_(chunk_ids)))

    await session.execute(delete(RagResult).where(RagResult.document_id == doc_uuid))
    await session.execute(delete(RagContext).where(RagContext.document_id == doc_uuid))
    await session.execute(delete(Chunk).where(Chunk.document_id == doc_uuid))
    await session.execute(delete(Document).where(Document.id == doc_uuid))
    await session.commit()

    # Back to list.
    return RedirectResponse(url="/admin/rag/documents", status_code=303)


@router.get("/rag/upload")
async def rag_upload_form(request: Request):
    return templates.TemplateResponse("admin/rag_upload.html", {"request": request})


@router.post("/rag/upload")
async def rag_upload_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf is supported")
    pdf_bytes = await file.read()
    document_id = uuid.uuid4()
    source_key = f"documents/{document_id}/source.pdf"
    s3.put_object(Bucket=config.s3.bucket, Key=source_key, Body=pdf_bytes, ContentType="application/pdf")

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
    return RedirectResponse(url=f"/admin/rag/documents/{document_id}", status_code=303)


@router.get("/qdrant/search")
async def qdrant_search_form(request: Request):
    return templates.TemplateResponse("admin/qdrant_search.html", {"request": request, "results": None})


@router.post("/qdrant/search")
async def qdrant_search_submit(
    request: Request,
    config: FromDishka[AppConfig],
    qdrant: FromDishka[QdrantClient],
    query_text: str = Form(""),
    top_k: int = Form(10),
    score_threshold: float = Form(0.0),
    filter_json: str = Form(""),
):
    embedder = create_embedder(config)
    vectors = await embedder.embed([query_text])
    query_vector = vectors[0]

    q_filter: qmodels.Filter | None = None
    if filter_json.strip():
        try:
            raw = json.loads(filter_json)
            q_filter = qmodels.Filter(**raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid filter_json: {e}") from e

    hits = qdrant.search(
        collection_name=config.qdrant.collection,
        query_vector=query_vector,
        limit=int(top_k),
        score_threshold=float(score_threshold),
        query_filter=q_filter,
        with_payload=True,
    )
    results: list[dict[str, Any]] = []
    for h in hits:
        payload = h.payload or {}
        results.append(
            {
                "id": str(h.id),
                "score": float(h.score or 0.0),
                "document_id": payload.get("document_id"),
                "chunk_no": payload.get("chunk_no"),
                "content_type": payload.get("content_type"),
                "page_start": payload.get("page_start"),
                "page_end": payload.get("page_end"),
                "heading_path": payload.get("heading_path"),
                "text_snippet": (payload.get("text") or "")[:240],
            }
        )
    return templates.TemplateResponse(
        "admin/qdrant_search.html",
        {
            "request": request,
            "results": results,
            "query_text": query_text,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "filter_json": filter_json,
        },
    )


@router.get("/rag/search")
async def rag_search_form(request: Request):
    return templates.TemplateResponse("admin/rag_search.html", {"request": request, "result": None})


@router.post("/rag/search")
async def rag_search_submit(
    request: Request,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
    user_query: str = Form(""),
    user_id: str = Form(""),
    scenario_id: str = Form(""),
    language: str = Form("ru"),
    search_profile: str = Form("quick_advice"),
    retrieval_top_k_per_query: int = Form(10),
    retrieval_min_score: float = Form(0.0),
    llm_model: str = Form(""),
    llm_temperature: float = Form(0.2),
    llm_max_tokens: int = Form(2500),
    mode: str = Form("answer"),
):
    user_uuid = uuid.UUID(user_id) if user_id.strip() else None

    cfg = config.model_copy(deep=True)
    cfg.rag_search.retrieval.top_k_per_query = int(retrieval_top_k_per_query)
    cfg.rag_search.retrieval.min_score = float(retrieval_min_score)

    llm_overrides: dict[str, Any] = {
        "model": llm_model.strip() or None,
        "temperature": float(llm_temperature),
        "max_tokens": int(llm_max_tokens),
    }
    llm_overrides = {k: v for k, v in llm_overrides.items() if v is not None}

    service = RagSearchService(config=cfg, session=session, qdrant=qdrant, s3=s3)
    if mode == "debug":
        payload = await service.search_debug(
            user_query=user_query,
            user_id=user_uuid,
            scenario_id=scenario_id,
            language=language,
            search_profile=search_profile,
        )
        result = {"mode": "debug", "payload": payload}
    else:
        answer = await service.search(
            user_query=user_query,
            user_id=user_uuid,
            scenario_id=scenario_id,
            language=language,
            search_profile=search_profile,
            llm_overrides=llm_overrides,
        )
        result = {"mode": "answer", "payload": answer.model_dump()}

    return templates.TemplateResponse(
        "admin/rag_search.html",
        {
            "request": request,
            "result": result,
            "user_query": user_query,
            "user_id": user_id,
            "scenario_id": scenario_id,
            "language": language,
            "search_profile": search_profile,
            "retrieval_top_k_per_query": retrieval_top_k_per_query,
            "retrieval_min_score": retrieval_min_score,
            "llm_model": llm_model,
            "llm_temperature": llm_temperature,
            "llm_max_tokens": llm_max_tokens,
        },
    )


@router.get("/users")
async def users_list(request: Request, session: FromDishka[AsyncSession]):
    totals_subq = (
        select(
            UserTokenUsageDay.user_id.label("user_id"),
            func.coalesce(func.sum(UserTokenUsageDay.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UserTokenUsageDay.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(UserTokenUsageDay.total_tokens), 0).label("total_tokens"),
        )
        .group_by(UserTokenUsageDay.user_id)
        .subquery()
    )

    res = await session.execute(
        select(User, totals_subq.c.prompt_tokens, totals_subq.c.completion_tokens, totals_subq.c.total_tokens)
        .outerjoin(totals_subq, totals_subq.c.user_id == User.id)
        .order_by(User.created_at.desc())
        .limit(200)
    )
    rows = res.all()
    items: list[dict[str, Any]] = []
    for u, pt, ct, tt in rows:
        items.append(
            {
                "id": str(u.id),
                "telegram_user_id": u.telegram_user_id,
                "telegram_username": u.telegram_username,
                "prompt_tokens": int(pt or 0),
                "completion_tokens": int(ct or 0),
                "total_tokens": int(tt or 0),
                "created_at": u.created_at,
            }
        )
    return templates.TemplateResponse("admin/users.html", {"request": request, "users": items})


@router.get("/users/{user_id}")
async def user_detail(user_id: str, request: Request, session: FromDishka[AsyncSession]):
    user_uuid = uuid.UUID(user_id)
    u_res = await session.execute(select(User).where(User.id == user_uuid))
    u = u_res.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Not found")

    usage_res = await session.execute(
        select(UserTokenUsageDay)
        .where(UserTokenUsageDay.user_id == user_uuid)
        .order_by(UserTokenUsageDay.day.desc())
        .limit(60)
    )
    usage_days = usage_res.scalars().all()

    rag_res = await session.execute(
        select(RagRequest)
        .where(RagRequest.user_id == user_uuid)
        .order_by(RagRequest.created_at.desc())
        .limit(50)
    )
    rag_requests = rag_res.scalars().all()

    msg_res = await session.execute(
        select(Message)
        .join(Dialog, Dialog.id == Message.dialog_id)
        .where(Dialog.user_id == user_uuid)
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    messages = msg_res.scalars().all()

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "u": u,
            "usage_days": usage_days,
            "rag_requests": rag_requests,
            "messages": messages,
        },
    )


@router.get("/users/{user_id}/export", response_class=JSONResponse)
async def user_export(user_id: str, session: FromDishka[AsyncSession]) -> dict[str, Any]:
    user_uuid = uuid.UUID(user_id)
    u_res = await session.execute(select(User).where(User.id == user_uuid))
    u = u_res.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Not found")

    usage_days_res = await session.execute(
        select(UserTokenUsageDay).where(UserTokenUsageDay.user_id == user_uuid).order_by(UserTokenUsageDay.day.asc())
    )
    usage_days = usage_days_res.scalars().all()

    events_res = await session.execute(
        select(TokenUsageEvent)
        .where(TokenUsageEvent.user_id == user_uuid)
        .order_by(TokenUsageEvent.created_at.desc())
        .limit(2000)
    )
    events = events_res.scalars().all()

    rag_res = await session.execute(
        select(RagRequest).where(RagRequest.user_id == user_uuid).order_by(RagRequest.created_at.desc()).limit(1000)
    )
    rag_requests = rag_res.scalars().all()

    msg_res = await session.execute(
        select(Message)
        .join(Dialog, Dialog.id == Message.dialog_id)
        .where(Dialog.user_id == user_uuid)
        .order_by(Message.created_at.desc())
        .limit(2000)
    )
    messages = msg_res.scalars().all()

    return {
        "user": {
            "id": str(u.id),
            "telegram_user_id": u.telegram_user_id,
            "telegram_username": u.telegram_username,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        },
        "token_usage_by_day": [
            {
                "day": d.day.isoformat(),
                "prompt_tokens": d.prompt_tokens,
                "completion_tokens": d.completion_tokens,
                "total_tokens": d.total_tokens,
            }
            for d in usage_days
        ],
        "token_usage_events": [
            {
                "id": str(e.id),
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "source": e.source,
                "model": e.model,
                "prompt_tokens": e.prompt_tokens,
                "completion_tokens": e.completion_tokens,
                "total_tokens": e.total_tokens,
                "request_id": str(e.request_id) if e.request_id else None,
                "meta": e.meta or {},
            }
            for e in events
        ],
        "rag_requests": [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "scenario_id": r.scenario_id,
                "source_channel": r.source_channel,
                "search_profile": r.search_profile,
                "status": r.status,
                "user_query": r.user_query,
            }
            for r in rag_requests
        ],
        "messages": [
            {
                "id": str(m.id),
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "role": m.role,
                "text": m.text,
                "meta": m.meta or {},
            }
            for m in messages
        ],
    }
