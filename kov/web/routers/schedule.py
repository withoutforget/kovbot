from __future__ import annotations

import uuid
from datetime import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import UserSchedule
from kov.web.deps import get_db_session

router = APIRouter()


class ScheduleUpsertRequest(BaseModel):
    user_id: str
    schedule_key: str
    at_time: time
    enabled: bool = True


@router.post("", response_model=dict[str, bool])
async def upsert_schedule(
    req: ScheduleUpsertRequest, session: AsyncSession = Depends(get_db_session)
) -> dict[str, bool]:
    user_uuid = uuid.UUID(req.user_id)
    res = await session.execute(
        select(UserSchedule).where(
            and_(UserSchedule.user_id == user_uuid, UserSchedule.schedule_key == req.schedule_key)
        )
    )
    sched = res.scalar_one_or_none()
    if not sched:
        sched = UserSchedule(
            id=uuid.uuid4(), user_id=user_uuid, schedule_key=req.schedule_key, at_time=req.at_time
        )
        session.add(sched)
    sched.at_time = req.at_time
    sched.enabled = req.enabled
    await session.commit()
    return {"ok": True}
