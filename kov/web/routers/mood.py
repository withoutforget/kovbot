from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import MoodTrackerEntry, ReminderEvent, UserSchedule
from kov.web.deps import get_db_session

router = APIRouter()


class MoodEntryRequest(BaseModel):
    user_id: str
    entry_date: date | None = None
    mood_score: int | None = None
    notes: str = ""
    factors_down: list[str] = []
    factors_up: list[str] = []


class MoodEntryResponse(BaseModel):
    ok: bool


@router.post("/entry", response_model=MoodEntryResponse)
async def upsert_mood_entry(
    req: MoodEntryRequest, session: AsyncSession = Depends(get_db_session)
) -> MoodEntryResponse:
    user_uuid = uuid.UUID(req.user_id)
    d = req.entry_date or date.today()
    # Concurrency-safe UPSERT (unique: uq_mood_user_date)
    await session.execute(
        pg_insert(MoodTrackerEntry)
        .values(
            id=uuid.uuid4(),
            user_id=user_uuid,
            entry_date=d,
            mood_score=req.mood_score,
            notes=req.notes,
            factors_down=req.factors_down,
            factors_up=req.factors_up,
        )
        .on_conflict_do_update(
            constraint="uq_mood_user_date",
            set_={
                "mood_score": req.mood_score,
                "notes": req.notes,
                "factors_down": req.factors_down,
                "factors_up": req.factors_up,
                "updated_at": func.now(),
            },
        )
    )

    # mark reminder as answered (best-effort)
    sched_res = await session.execute(
        select(UserSchedule).where(and_(UserSchedule.user_id == user_uuid, UserSchedule.schedule_key == "mood_tracker"))
    )
    sched = sched_res.scalar_one_or_none()
    if sched:
        sched.last_time_answered = datetime.now(tz=timezone.utc)

    # mark latest reminder event as answered (best-effort)
    ev_res = await session.execute(
        select(ReminderEvent)
        .where(and_(ReminderEvent.user_id == user_uuid, ReminderEvent.schedule_key == "mood_tracker"))
        .where(ReminderEvent.status == "asked")
        .order_by(ReminderEvent.asked_at.desc())
        .limit(1)
    )
    ev = ev_res.scalar_one_or_none()
    if ev:
        ev.status = "answered"
        ev.answered_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return MoodEntryResponse(ok=True)


class MoodEntry(BaseModel):
    entry_date: date
    mood_score: int | None
    notes: str
    factors_down: list[str]
    factors_up: list[str]


@router.get("/history/{user_id}", response_model=list[MoodEntry])
async def mood_history(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[MoodEntry]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(
        select(MoodTrackerEntry).where(MoodTrackerEntry.user_id == user_uuid).order_by(MoodTrackerEntry.entry_date.asc())
    )
    out: list[MoodEntry] = []
    for e in res.scalars().all():
        out.append(
            MoodEntry(
                entry_date=e.entry_date,
                mood_score=e.mood_score,
                notes=e.notes,
                factors_down=e.factors_down,
                factors_up=e.factors_up,
            )
        )
    return out


@router.post("/entry/{user_id}/{entry_date}/delete")
async def delete_entry(user_id: str, entry_date: date, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(
        select(MoodTrackerEntry).where(and_(MoodTrackerEntry.user_id == user_uuid, MoodTrackerEntry.entry_date == entry_date))
    )
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(entry)
    await session.commit()
    return {"ok": True}


@router.post("/clear/{user_id}")
async def clear_history(user_id: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(MoodTrackerEntry).where(MoodTrackerEntry.user_id == user_uuid))
    for e in res.scalars().all():
        await session.delete(e)
    await session.commit()
    return {"ok": True}
