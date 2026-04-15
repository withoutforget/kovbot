from __future__ import annotations

import uuid
from datetime import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
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
    res = await session.execute(select(User).where(User.telegram_user_id == req.telegram_user_id))
    user = res.scalar_one_or_none()
    if not user:
        user = User(id=uuid.uuid4(), telegram_user_id=req.telegram_user_id, timezone=req.timezone, language=req.language)
        session.add(user)
        session.add(UserProfile(id=uuid.uuid4(), user_id=user.id, data={}))
        await session.flush()

        # defaults: mood 18:00, habits 21:00 (local user time)
        session.add(
            UserSchedule(
                id=uuid.uuid4(),
                user_id=user.id,
                schedule_key="mood_tracker",
                at_time=time(hour=18, minute=0),
                enabled=True,
            )
        )
        session.add(
            UserSchedule(
                id=uuid.uuid4(),
                user_id=user.id,
                schedule_key="habit_tracker",
                at_time=time(hour=21, minute=0),
                enabled=True,
            )
        )
        await session.commit()
    else:
        # update timezone/language if provided changes
        user.timezone = req.timezone or user.timezone
        user.language = req.language or user.language
        await session.commit()
    return EnsureUserResponse(user_id=str(user.id))
