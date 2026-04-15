from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Habit, HabitLog
from kov.web.deps import get_db_session

router = APIRouter()


class HabitCreateRequest(BaseModel):
    user_id: str
    title: str
    description: str = ""


class HabitResponse(BaseModel):
    habit_id: str


@router.post("", response_model=HabitResponse)
async def create_habit(req: HabitCreateRequest, session: AsyncSession = Depends(get_db_session)) -> HabitResponse:
    habit = Habit(id=uuid.uuid4(), user_id=uuid.UUID(req.user_id), title=req.title, description=req.description)
    session.add(habit)
    await session.commit()
    return HabitResponse(habit_id=str(habit.id))


class HabitItem(BaseModel):
    habit_id: str
    title: str
    description: str
    archived: bool


@router.get("/{user_id}", response_model=list[HabitItem])
async def list_habits(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[HabitItem]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(Habit).where(Habit.user_id == user_uuid).order_by(Habit.created_at.asc()))
    return [
        HabitItem(habit_id=str(h.id), title=h.title, description=h.description, archived=h.archived)
        for h in res.scalars().all()
    ]


class HabitArchiveRequest(BaseModel):
    archived: bool = True


@router.post("/{habit_id}/archive")
async def archive_habit(
    habit_id: str, req: HabitArchiveRequest, session: AsyncSession = Depends(get_db_session)
) -> dict[str, bool]:
    hid = uuid.UUID(habit_id)
    res = await session.execute(select(Habit).where(Habit.id == hid))
    habit = res.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Not found")
    habit.archived = req.archived
    await session.commit()
    return {"ok": True}


class HabitLogRequest(BaseModel):
    user_id: str
    habit_id: str
    log_date: date | None = None
    done: bool = False
    notes: str = ""


@router.post("/log")
async def log_habit(req: HabitLogRequest, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(req.user_id)
    habit_uuid = uuid.UUID(req.habit_id)
    d = req.log_date or date.today()
    res = await session.execute(
        select(HabitLog).where(and_(HabitLog.habit_id == habit_uuid, HabitLog.log_date == d))
    )
    log = res.scalar_one_or_none()
    if not log:
        log = HabitLog(id=uuid.uuid4(), user_id=user_uuid, habit_id=habit_uuid, log_date=d)
        session.add(log)
    log.done = req.done
    log.notes = req.notes
    await session.commit()
    return {"ok": True}
