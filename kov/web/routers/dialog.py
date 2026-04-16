from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.db.models import Dialog, Message, Scenario
from kov.rag.search.service import RagSearchService
from kov.rag.types import RagAnswer
from kov.web.deps import get_config, get_db_session, get_qdrant, get_s3

router = APIRouter()


class DialogMessageRequest(BaseModel):
    user_id: str
    scenario_key: str = "dialog"  # dialog/relationships
    text: str


class DialogMessageResponse(BaseModel):
    dialog_id: str
    answer: RagAnswer


def _build_query_with_history(*, history: list[dict[str, str]], user_text: str) -> str:
    if not history:
        return user_text
    tail = history[-12:]
    lines: list[str] = ["Контекст диалога:"]
    for item in tail:
        role = item.get("role") or "user"
        text = (item.get("text") or "").strip()
        if not text:
            continue
        prefix = "Пользователь" if role == "user" else "Ассистент"
        lines.append(f"{prefix}: {text}")
    lines.append("")
    lines.append("Текущее сообщение:")
    lines.append(user_text)
    return "\n".join(lines).strip()


async def _load_dialog_history(session: AsyncSession, *, dialog_id: uuid.UUID, limit: int = 24) -> list[dict[str, str]]:
    # load last N messages, keep chronological order
    res = await session.execute(
        select(Message)
        .where(Message.dialog_id == dialog_id)
        .order_by(Message.created_at.desc())
        .limit(max(1, min(int(limit), 100)))
    )
    msgs = list(reversed(res.scalars().all()))
    return [{"role": m.role, "text": m.text} for m in msgs]


@router.post("/message", response_model=DialogMessageResponse)
async def dialog_message(
    req: DialogMessageRequest,
    config: AppConfig = Depends(get_config),
    session: AsyncSession = Depends(get_db_session),
    qdrant: QdrantClient = Depends(get_qdrant),
    s3=Depends(get_s3),
) -> DialogMessageResponse:
    user_uuid = uuid.UUID(req.user_id)
    scenario_res = await session.execute(select(Scenario).where(Scenario.key == req.scenario_key))
    scenario = scenario_res.scalar_one_or_none()
    scenario_id = scenario.id if scenario else None
    dialog_res = await session.execute(
        select(Dialog).where(Dialog.user_id == user_uuid).where(Dialog.scenario_id == scenario_id)
    )
    dialog = dialog_res.scalar_one_or_none()
    if not dialog:
        dialog = Dialog(id=uuid.uuid4(), user_id=user_uuid, scenario_id=scenario_id, title=req.scenario_key)
        session.add(dialog)
        await session.flush()
    history = await _load_dialog_history(session, dialog_id=dialog.id, limit=24)
    session.add(Message(id=uuid.uuid4(), dialog_id=dialog.id, role="user", text=req.text, meta={}))
    await session.commit()

    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    llm_query = _build_query_with_history(history=history, user_text=req.text)
    answer = await service.search(
        user_query=llm_query,
        user_id=user_uuid,
        scenario_id=req.scenario_key,
        language="ru",
        search_profile="quick_advice" if req.scenario_key == "dialog" else "relationship_support",
    )
    session.add(
        Message(
            id=uuid.uuid4(),
            dialog_id=dialog.id,
            role="assistant",
            text="\n\n".join([p.text for p in answer.telegram_messages]),
            meta={"request_id": answer.request_id},
        )
    )
    await session.commit()
    return DialogMessageResponse(dialog_id=str(dialog.id), answer=answer)


@router.post("/message/stream")
async def dialog_message_stream(
    req: DialogMessageRequest,
    config: AppConfig = Depends(get_config),
    session: AsyncSession = Depends(get_db_session),
    qdrant: QdrantClient = Depends(get_qdrant),
    s3=Depends(get_s3),
):
    """
    Streams the final LLM answer as plain text, while still persisting dialog history in DB.
    """
    user_uuid = uuid.UUID(req.user_id)
    scenario_res = await session.execute(select(Scenario).where(Scenario.key == req.scenario_key))
    scenario = scenario_res.scalar_one_or_none()
    scenario_id = scenario.id if scenario else None
    dialog_res = await session.execute(
        select(Dialog).where(Dialog.user_id == user_uuid).where(Dialog.scenario_id == scenario_id)
    )
    dialog = dialog_res.scalar_one_or_none()
    if not dialog:
        dialog = Dialog(id=uuid.uuid4(), user_id=user_uuid, scenario_id=scenario_id, title=req.scenario_key)
        session.add(dialog)
        await session.flush()
    history = await _load_dialog_history(session, dialog_id=dialog.id, limit=24)
    session.add(Message(id=uuid.uuid4(), dialog_id=dialog.id, role="user", text=req.text, meta={}))
    await session.commit()

    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    search_profile = "quick_advice" if req.scenario_key == "dialog" else "relationship_support"
    llm_query = _build_query_with_history(history=history, user_text=req.text)

    async def gen():
        full = ""
        try:
            plan = await service.search_debug(
                user_query=llm_query,
                user_id=user_uuid,
                scenario_id=req.scenario_key,
                language="ru",
                search_profile=search_profile,
            )
            expanded = plan.get("expanded_contexts") or []
            profile_summary = await service._get_profile_summary(user_id=user_uuid)
            async for delta in service.compose_answer_llm_stream(
                user_query=llm_query,
                language="ru",
                expanded_contexts=expanded,
                user_profile_summary=profile_summary,
            ):
                if not delta:
                    continue
                full += delta
                yield delta.encode("utf-8")
        finally:
            text = full.strip()
            if text:
                session.add(
                    Message(
                        id=uuid.uuid4(),
                        dialog_id=dialog.id,
                        role="assistant",
                        text=text,
                        meta={},
                    )
                )
                await session.commit()

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


class DialogClearRequest(BaseModel):
    user_id: str
    scenario_key: str = "dialog"


@router.post("/clear", response_model=dict[str, bool])
async def dialog_clear(req: DialogClearRequest, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(req.user_id)
    scenario_res = await session.execute(select(Scenario).where(Scenario.key == req.scenario_key))
    scenario = scenario_res.scalar_one_or_none()
    scenario_id = scenario.id if scenario else None
    res = await session.execute(
        select(Dialog).where(Dialog.user_id == user_uuid).where(Dialog.scenario_id == scenario_id)
    )
    dialog = res.scalar_one_or_none()
    if not dialog:
        raise HTTPException(status_code=404, detail="Not found")
    msg_res = await session.execute(select(Message).where(Message.dialog_id == dialog.id))
    for m in msg_res.scalars().all():
        await session.delete(m)
    await session.delete(dialog)
    await session.commit()
    return {"ok": True}


class DialogInfo(BaseModel):
    dialog_id: str
    scenario_key: str | None
    title: str


@router.get("/list/{user_id}", response_model=list[DialogInfo])
async def list_dialogs(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[DialogInfo]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(Dialog).where(Dialog.user_id == user_uuid).order_by(Dialog.created_at.desc()))
    dialogs = res.scalars().all()
    # map scenario_id -> key
    scen_res = await session.execute(select(Scenario))
    scen_map = {s.id: s.key for s in scen_res.scalars().all()}
    out: list[DialogInfo] = []
    for d in dialogs:
        out.append(
            DialogInfo(
                dialog_id=str(d.id),
                scenario_key=scen_map.get(d.scenario_id) if d.scenario_id else None,
                title=d.title,
            )
        )
    return out


@router.get("/{dialog_id}")
async def get_dialog(dialog_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    did = uuid.UUID(dialog_id)
    res = await session.execute(select(Dialog).where(Dialog.id == did))
    dialog = res.scalar_one_or_none()
    if not dialog:
        raise HTTPException(status_code=404, detail="Not found")
    msg_res = await session.execute(select(Message).where(Message.dialog_id == did).order_by(Message.created_at.asc()))
    messages = [{"role": m.role, "text": m.text, "created_at": m.created_at.isoformat()} for m in msg_res.scalars().all()]
    return {"dialog_id": dialog_id, "title": dialog.title, "messages": messages}
