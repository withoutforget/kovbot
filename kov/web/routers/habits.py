from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Habit, HabitLog, ReminderEvent, UserSchedule
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


class HabitUpdateRequest(BaseModel):
    title: str
    description: str = ""


@router.post("/{habit_id}/update")
async def update_habit(
    habit_id: str, req: HabitUpdateRequest, session: AsyncSession = Depends(get_db_session)
) -> dict[str, bool]:
    hid = uuid.UUID(habit_id)
    res = await session.execute(select(Habit).where(Habit.id == hid))
    habit = res.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Not found")
    habit.title = req.title
    habit.description = req.description
    await session.commit()
    return {"ok": True}


@router.post("/{habit_id}/delete")
async def delete_habit(habit_id: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    hid = uuid.UUID(habit_id)
    res = await session.execute(select(Habit).where(Habit.id == hid))
    habit = res.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Not found")
    # delete logs first (hard delete for simplicity)
    logs_res = await session.execute(select(HabitLog).where(HabitLog.habit_id == hid))
    for l in logs_res.scalars().all():
        await session.delete(l)
    await session.delete(habit)
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
    # Concurrency-safe UPSERT (unique: uq_habit_date)
    await session.execute(
        pg_insert(HabitLog)
        .values(
            id=uuid.uuid4(),
            user_id=user_uuid,
            habit_id=habit_uuid,
            log_date=d,
            done=req.done,
            notes=req.notes,
        )
        .on_conflict_do_update(
            constraint="uq_habit_date",
            set_={
                "done": req.done,
                "notes": req.notes,
                "updated_at": func.now(),
            },
        )
    )

    # mark reminder as answered (best-effort)
    sched_res = await session.execute(
        select(UserSchedule).where(
            and_(UserSchedule.user_id == user_uuid, UserSchedule.schedule_key == "habit_tracker")
        )
    )
    sched = sched_res.scalar_one_or_none()
    if sched:
        sched.last_time_answered = datetime.now(tz=timezone.utc)

    # mark latest reminder event as answered (best-effort)
    ev_res = await session.execute(
        select(ReminderEvent)
        .where(and_(ReminderEvent.user_id == user_uuid, ReminderEvent.schedule_key == "habit_tracker"))
        .where(ReminderEvent.status == "asked")
        .order_by(ReminderEvent.asked_at.desc())
        .limit(1)
    )
    ev = ev_res.scalar_one_or_none()
    if ev:
        ev.status = "answered"
        ev.answered_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"ok": True}


class HabitLogItem(BaseModel):
    habit_id: str
    log_date: date
    done: bool
    notes: str


@router.get("/logs/{user_id}", response_model=list[HabitLogItem])
async def list_logs(
    user_id: str,
    habit_id: str | None = None,
    limit: int = 60,
    session: AsyncSession = Depends(get_db_session),
) -> list[HabitLogItem]:
    user_uuid = uuid.UUID(user_id)
    q = select(HabitLog).where(HabitLog.user_id == user_uuid)
    if habit_id:
        q = q.where(HabitLog.habit_id == uuid.UUID(habit_id))
    q = q.order_by(HabitLog.log_date.desc()).limit(max(1, min(int(limit or 60), 365)))
    res = await session.execute(q)
    out: list[HabitLogItem] = []
    for l in res.scalars().all():
        out.append(
            HabitLogItem(
                habit_id=str(l.habit_id),
                log_date=l.log_date,
                done=bool(l.done),
                notes=l.notes or "",
            )
        )
    return out


@router.post("/log/{habit_id}/{log_date}/delete")
async def delete_log(
    habit_id: str, log_date: date, session: AsyncSession = Depends(get_db_session)
) -> dict[str, bool]:
    hid = uuid.UUID(habit_id)
    res = await session.execute(select(HabitLog).where(and_(HabitLog.habit_id == hid, HabitLog.log_date == log_date)))
    log_row = res.scalar_one_or_none()
    if not log_row:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(log_row)
    await session.commit()
    return {"ok": True}


@router.post("/clear/{user_id}")
async def clear_habits(user_id: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(user_id)
    logs_res = await session.execute(select(HabitLog).where(HabitLog.user_id == user_uuid))
    for l in logs_res.scalars().all():
        await session.delete(l)
    habits_res = await session.execute(select(Habit).where(Habit.user_id == user_uuid))
    for h in habits_res.scalars().all():
        await session.delete(h)
    await session.commit()
    return {"ok": True}
