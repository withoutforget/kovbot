from __future__ import annotations

import uuid
from datetime import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import User, UserProfile, UserSchedule
from kov.web.deps import get_db_session

router = APIRouter()


class EnsureUserRequest(BaseModel):
    telegram_user_id: str
    timezone: str = "UTC"
    language: str = "ru"


class EnsureUserResponse(BaseModel):
    user_id: str


@router.post("/ensure", response_model=EnsureUserResponse)
async def ensure_user(req: EnsureUserRequest, session: AsyncSession = Depends(get_db_session)) -> EnsureUserResponse:
    """
    Idempotent and concurrency-safe.

    Telegram может прислать несколько апдейтов параллельно для нового пользователя,
    поэтому делаем UPSERT по уникальному `users.telegram_user_id`.
    """
    user_id_res = await session.execute(
        pg_insert(User)
        .values(
            id=uuid.uuid4(),
            telegram_user_id=req.telegram_user_id,
            timezone=req.timezone or "UTC",
            language=req.language or "ru",
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_user_id],
            set_={
                "timezone": req.timezone or "UTC",
                "language": req.language or "ru",
            },
        )
        .returning(User.id)
    )
    user_id = user_id_res.scalar_one()

    # Ensure profile exists (best-effort, concurrency-safe via unique index).
    await session.execute(
        pg_insert(UserProfile)
        .values(id=uuid.uuid4(), user_id=user_id, data={})
        .on_conflict_do_nothing(index_elements=[UserProfile.user_id])
    )

    # Ensure default schedules exist (best-effort, concurrency-safe via unique index).
    await session.execute(
        pg_insert(UserSchedule)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            schedule_key="mood_tracker",
            at_time=time(hour=18, minute=0),
            enabled=True,
        )
        .on_conflict_do_nothing(index_elements=[UserSchedule.user_id, UserSchedule.schedule_key])
    )
    await session.execute(
        pg_insert(UserSchedule)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            schedule_key="habit_tracker",
            at_time=time(hour=21, minute=0),
            enabled=True,
        )
        .on_conflict_do_nothing(index_elements=[UserSchedule.user_id, UserSchedule.schedule_key])
    )

    await session.commit()
    return EnsureUserResponse(user_id=str(user_id))


class ProfileResponse(BaseModel):
    user_id: str
    data: dict[str, Any]


@router.get("/profile/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str, session: AsyncSession = Depends(get_db_session)) -> ProfileResponse:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(UserProfile).where(UserProfile.user_id == user_uuid))
    profile = res.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    return ProfileResponse(user_id=user_id, data=profile.data or {})


class ProfileMergeRequest(BaseModel):
    user_id: str
    data: dict[str, Any]


@router.post("/profile/merge", response_model=dict[str, bool])
async def merge_profile(req: ProfileMergeRequest, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(req.user_id)
    res = await session.execute(select(UserProfile).where(UserProfile.user_id == user_uuid))
    profile = res.scalar_one_or_none()
    if not profile:
        # Safe for concurrent calls thanks to unique index on user_profiles.user_id.
        await session.execute(
            pg_insert(UserProfile)
            .values(id=uuid.uuid4(), user_id=user_uuid, data=req.data or {})
            .on_conflict_do_nothing(index_elements=[UserProfile.user_id])
        )
        await session.commit()
        # If another request created the row first, we still need to merge the incoming data.
        res2 = await session.execute(select(UserProfile).where(UserProfile.user_id == user_uuid))
        profile = res2.scalar_one_or_none()
        if not profile:
            return {"ok": True}
    current = profile.data or {}
    current.update(req.data or {})
    profile.data = current
    await session.commit()
    return {"ok": True}
