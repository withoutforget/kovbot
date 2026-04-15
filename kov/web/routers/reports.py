from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Habit, HabitLog, MoodTrackerEntry
from kov.web.deps import get_db_session

router = APIRouter()


class MoodReport(BaseModel):
    period_start: date
    period_end: date
    avg_mood: float | None
    top_down_factors: list[tuple[str, int]]
    top_up_factors: list[tuple[str, int]]


@router.get("/mood/weekly/{user_id}", response_model=MoodReport)
async def mood_weekly(user_id: str, session: AsyncSession = Depends(get_db_session)) -> MoodReport:
    user_uuid = uuid.UUID(user_id)
    end = date.today()
    start = end - timedelta(days=6)
    res = await session.execute(
        select(MoodTrackerEntry).where(
            and_(MoodTrackerEntry.user_id == user_uuid, MoodTrackerEntry.entry_date >= start)
        )
    )
    entries = res.scalars().all()
    scores = [e.mood_score for e in entries if e.mood_score is not None]
    avg = (sum(scores) / len(scores)) if scores else None
    down = Counter([x for e in entries for x in (e.factors_down or [])])
    up = Counter([x for e in entries for x in (e.factors_up or [])])
    return MoodReport(
        period_start=start,
        period_end=end,
        avg_mood=avg,
        top_down_factors=down.most_common(10),
        top_up_factors=up.most_common(10),
    )


@router.get("/mood/monthly/{user_id}", response_model=MoodReport)
async def mood_monthly(user_id: str, session: AsyncSession = Depends(get_db_session)) -> MoodReport:
    user_uuid = uuid.UUID(user_id)
    end = date.today()
    start = end - timedelta(days=29)
    res = await session.execute(
        select(MoodTrackerEntry).where(
            and_(MoodTrackerEntry.user_id == user_uuid, MoodTrackerEntry.entry_date >= start)
        )
    )
    entries = res.scalars().all()
    scores = [e.mood_score for e in entries if e.mood_score is not None]
    avg = (sum(scores) / len(scores)) if scores else None
    down = Counter([x for e in entries for x in (e.factors_down or [])])
    up = Counter([x for e in entries for x in (e.factors_up or [])])
    return MoodReport(
        period_start=start,
        period_end=end,
        avg_mood=avg,
        top_down_factors=down.most_common(10),
        top_up_factors=up.most_common(10),
    )


class HabitReport(BaseModel):
    period_start: date
    period_end: date
    habits: list[dict]


@router.get("/habits/weekly/{user_id}", response_model=HabitReport)
async def habits_weekly(user_id: str, session: AsyncSession = Depends(get_db_session)) -> HabitReport:
    user_uuid = uuid.UUID(user_id)
    end = date.today()
    start = end - timedelta(days=6)
    habits_res = await session.execute(select(Habit).where(Habit.user_id == user_uuid))
    habits = habits_res.scalars().all()
    logs_res = await session.execute(
        select(HabitLog).where(and_(HabitLog.user_id == user_uuid, HabitLog.log_date >= start))
    )
    logs = logs_res.scalars().all()
    by_habit: dict[uuid.UUID, list[HabitLog]] = {}
    for l in logs:
        by_habit.setdefault(l.habit_id, []).append(l)
    out = []
    for h in habits:
        hlogs = by_habit.get(h.id, [])
        done = sum(1 for l in hlogs if l.done)
        total = len(hlogs)
        out.append({"habit_id": str(h.id), "title": h.title, "done": done, "total": total})
    return HabitReport(period_start=start, period_end=end, habits=out)


@router.get("/habits/monthly/{user_id}", response_model=HabitReport)
async def habits_monthly(user_id: str, session: AsyncSession = Depends(get_db_session)) -> HabitReport:
    user_uuid = uuid.UUID(user_id)
    end = date.today()
    start = end - timedelta(days=29)
    habits_res = await session.execute(select(Habit).where(Habit.user_id == user_uuid))
    habits = habits_res.scalars().all()
    logs_res = await session.execute(
        select(HabitLog).where(and_(HabitLog.user_id == user_uuid, HabitLog.log_date >= start))
    )
    logs = logs_res.scalars().all()
    by_habit: dict[uuid.UUID, list[HabitLog]] = {}
    for l in logs:
        by_habit.setdefault(l.habit_id, []).append(l)
    out = []
    for h in habits:
        hlogs = by_habit.get(h.id, [])
        done = sum(1 for l in hlogs if l.done)
        total = len(hlogs)
        out.append({"habit_id": str(h.id), "title": h.title, "done": done, "total": total})
    return HabitReport(period_start=start, period_end=end, habits=out)
