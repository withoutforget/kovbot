from __future__ import annotations

import uuid
from datetime import datetime, time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func
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
    # Concurrency-safe UPSERT (requires unique index on (user_id, schedule_key))
    await session.execute(
        pg_insert(UserSchedule)
        .values(
            id=uuid.uuid4(),
            user_id=user_uuid,
            schedule_key=req.schedule_key,
            at_time=req.at_time,
            enabled=req.enabled,
        )
        .on_conflict_do_update(
            index_elements=[UserSchedule.user_id, UserSchedule.schedule_key],
            set_={"at_time": req.at_time, "enabled": req.enabled, "updated_at": func.now()},
        )
    )
    await session.commit()
    return {"ok": True}


class ScheduleItem(BaseModel):
    schedule_key: str
    at_time: time
    enabled: bool
    last_time_asked: datetime | None
    last_time_answered: datetime | None
    last_time_missed: datetime | None


@router.get("/{user_id}", response_model=list[ScheduleItem])
async def list_schedules(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[ScheduleItem]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(UserSchedule).where(UserSchedule.user_id == user_uuid))
    out: list[ScheduleItem] = []
    for s in res.scalars().all():
        out.append(
            ScheduleItem(
                schedule_key=s.schedule_key,
                at_time=s.at_time,
                enabled=s.enabled,
                last_time_asked=s.last_time_asked,
                last_time_answered=s.last_time_answered,
                last_time_missed=s.last_time_missed,
            )
        )
    return out
