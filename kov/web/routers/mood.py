from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import MoodTrackerEntry
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
    res = await session.execute(
        select(MoodTrackerEntry).where(and_(MoodTrackerEntry.user_id == user_uuid, MoodTrackerEntry.entry_date == d))
    )
    entry = res.scalar_one_or_none()
    if not entry:
        entry = MoodTrackerEntry(id=uuid.uuid4(), user_id=user_uuid, entry_date=d)
        session.add(entry)
    entry.mood_score = req.mood_score
    entry.notes = req.notes
    entry.factors_down = req.factors_down
    entry.factors_up = req.factors_up
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
