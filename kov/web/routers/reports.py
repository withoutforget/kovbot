from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Habit, HabitLog, MoodTrackerEntry, Report
from kov.web.deps import get_db_session

router = APIRouter()


class MoodReport(BaseModel):
    period_start: date
    period_end: date
    avg_mood: float | None
    top_down_factors: list[tuple[str, int]]
    top_up_factors: list[tuple[str, int]]
    daily_scores: list[tuple[date, int | None]]
    insights: list[str] = []


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
    insights: list[str] = []
    if avg is not None:
        if avg <= 3:
            insights.append("Неделя была тяжёлой: среднее настроение низкое. Поддержка и маленькие шаги важнее всего.")
        elif avg >= 7:
            insights.append("В целом неделя прошла стабильно: среднее настроение высокое.")
        else:
            insights.append("Среднее настроение в середине диапазона: возможно, были и сложные, и поддерживающие дни.")
    if down:
        insights.append(f"Чаще всего ухудшало: {', '.join([k for k, _ in down.most_common(3)])}.")
    if up:
        insights.append(f"Чаще всего поддерживало: {', '.join([k for k, _ in up.most_common(3)])}.")

    report = MoodReport(
        period_start=start,
        period_end=end,
        avg_mood=avg,
        top_down_factors=down.most_common(10),
        top_up_factors=up.most_common(10),
        daily_scores=[(e.entry_date, e.mood_score) for e in sorted(entries, key=lambda x: x.entry_date)],
        insights=insights,
    )
    await _store_report(
        session,
        user_id=user_id,
        report_type="mood_weekly",
        period_start=start,
        period_end=end,
        content=report.model_dump(mode="json"),
    )
    return report


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
    insights: list[str] = []
    if avg is not None:
        if avg <= 3:
            insights.append("Месяц был тяжёлым: среднее настроение низкое.")
        elif avg >= 7:
            insights.append("Месяц в целом устойчивый: среднее настроение высокое.")
        else:
            insights.append("Среднее настроение за месяц в середине диапазона.")
    if down:
        insights.append(f"Чаще всего ухудшало: {', '.join([k for k, _ in down.most_common(3)])}.")
    if up:
        insights.append(f"Чаще всего поддерживало: {', '.join([k for k, _ in up.most_common(3)])}.")

    report = MoodReport(
        period_start=start,
        period_end=end,
        avg_mood=avg,
        top_down_factors=down.most_common(10),
        top_up_factors=up.most_common(10),
        daily_scores=[(e.entry_date, e.mood_score) for e in sorted(entries, key=lambda x: x.entry_date)],
        insights=insights,
    )
    await _store_report(
        session,
        user_id=user_id,
        report_type="mood_monthly",
        period_start=start,
        period_end=end,
        content=report.model_dump(mode="json"),
    )
    return report


class HabitReport(BaseModel):
    period_start: date
    period_end: date
    habits: list[dict]
    top_helped_factors: list[tuple[str, int]] = []
    top_hindered_factors: list[tuple[str, int]] = []
    recommendations: list[str] = []


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
    helped_counter: Counter[str] = Counter()
    hindered_counter: Counter[str] = Counter()
    for l in logs:
        if not l.notes:
            continue
        try:
            payload = json.loads(l.notes)
        except Exception:
            continue
        for x in (payload.get("helped") or []):
            if isinstance(x, str) and x.strip():
                helped_counter[x.strip()] += 1
        for x in (payload.get("hindered") or []):
            if isinstance(x, str) and x.strip():
                hindered_counter[x.strip()] += 1
    out = []
    for h in habits:
        hlogs = by_habit.get(h.id, [])
        done = sum(1 for l in hlogs if l.done)
        total = len(hlogs)
        out.append(
            {
                "habit_id": str(h.id),
                "title": h.title,
                "done": done,
                "total": total,
                "rate": (done / total) if total else None,
                "daily": [{"date": str(l.log_date), "done": bool(l.done)} for l in sorted(hlogs, key=lambda x: x.log_date)],
            }
        )
    recommendations = []
    if hindered_counter:
        top = [k for k, _ in hindered_counter.most_common(3)]
        recommendations = [f"Подумайте, как уменьшить влияние «{t}» (маленький шаг, план 'если-то')." for t in top]
    report = HabitReport(
        period_start=start,
        period_end=end,
        habits=out,
        top_helped_factors=helped_counter.most_common(10),
        top_hindered_factors=hindered_counter.most_common(10),
        recommendations=recommendations,
    )
    await _store_report(
        session,
        user_id=user_id,
        report_type="habits_weekly",
        period_start=start,
        period_end=end,
        content=report.model_dump(mode="json"),
    )
    return report


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
    helped_counter: Counter[str] = Counter()
    hindered_counter: Counter[str] = Counter()
    for l in logs:
        if not l.notes:
            continue
        try:
            payload = json.loads(l.notes)
        except Exception:
            continue
        for x in (payload.get("helped") or []):
            if isinstance(x, str) and x.strip():
                helped_counter[x.strip()] += 1
        for x in (payload.get("hindered") or []):
            if isinstance(x, str) and x.strip():
                hindered_counter[x.strip()] += 1
    out = []
    for h in habits:
        hlogs = by_habit.get(h.id, [])
        done = sum(1 for l in hlogs if l.done)
        total = len(hlogs)
        out.append(
            {
                "habit_id": str(h.id),
                "title": h.title,
                "done": done,
                "total": total,
                "rate": (done / total) if total else None,
                "daily": [{"date": str(l.log_date), "done": bool(l.done)} for l in sorted(hlogs, key=lambda x: x.log_date)],
            }
        )
    recommendations = []
    if hindered_counter:
        top = [k for k, _ in hindered_counter.most_common(3)]
        recommendations = [f"Подумайте, как уменьшить влияние «{t}» (маленький шаг, план 'если-то')." for t in top]
    report = HabitReport(
        period_start=start,
        period_end=end,
        habits=out,
        top_helped_factors=helped_counter.most_common(10),
        top_hindered_factors=hindered_counter.most_common(10),
        recommendations=recommendations,
    )
    await _store_report(
        session,
        user_id=user_id,
        report_type="habits_monthly",
        period_start=start,
        period_end=end,
        content=report.model_dump(mode="json"),
    )
    return report


async def _store_report(
    session: AsyncSession,
    *,
    user_id: str,
    report_type: str,
    period_start: date,
    period_end: date,
    content: dict,
) -> None:
    user_uuid = uuid.UUID(user_id)
    existing_res = await session.execute(
        select(Report)
        .where(and_(Report.user_id == user_uuid, Report.report_type == report_type))
        .where(and_(Report.period_start == period_start, Report.period_end == period_end))
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        existing.content = content
    else:
        session.add(
            Report(
                id=uuid.uuid4(),
                user_id=user_uuid,
                report_type=report_type,
                period_start=period_start,
                period_end=period_end,
                content=content,
            )
        )
    await session.commit()


class ReportInfo(BaseModel):
    id: str
    report_type: str
    period_start: date
    period_end: date


@router.get("/list/{user_id}", response_model=list[ReportInfo])
async def list_reports(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[ReportInfo]:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(
        select(Report)
        .where(Report.user_id == user_uuid)
        .order_by(Report.created_at.desc())
        .limit(50)
    )
    return [
        ReportInfo(
            id=str(r.id),
            report_type=r.report_type,
            period_start=r.period_start,
            period_end=r.period_end,
        )
        for r in res.scalars().all()
    ]


@router.get("/{report_id}")
async def get_report(report_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    rid = uuid.UUID(report_id)
    res = await session.execute(select(Report).where(Report.id == rid))
    report = res.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": report_id, "report_type": report.report_type, "content": report.content}
