from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
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
    session.add(Message(id=uuid.uuid4(), dialog_id=dialog.id, role="user", text=req.text, meta={}))
    await session.commit()

    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    answer = await service.search(
        user_query=req.text,
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
