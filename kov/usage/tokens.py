from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import TokenUsageEvent, User, UserTokenUsageDay


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


async def record_token_usage(
    *,
    session: AsyncSession,
    user_id: uuid.UUID | None,
    source: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    occurred_at = occurred_at or _now_utc()
    total_tokens = int(prompt_tokens) + int(completion_tokens)

    telegram_user_id = ""
    telegram_username = ""
    if user_id:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()
        if user:
            telegram_user_id = user.telegram_user_id or ""
            telegram_username = user.telegram_username or ""

    event = TokenUsageEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        source=source,
        model=model or "",
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        total_tokens=int(total_tokens),
        request_id=request_id,
        meta=meta or {},
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    session.add(event)

    if user_id:
        day = occurred_at.date()
        stmt = (
            pg_insert(UserTokenUsageDay)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                day=day,
                prompt_tokens=int(prompt_tokens),
                completion_tokens=int(completion_tokens),
                total_tokens=int(total_tokens),
            )
            .on_conflict_do_update(
                index_elements=[UserTokenUsageDay.user_id, UserTokenUsageDay.day],
                set_={
                    "prompt_tokens": UserTokenUsageDay.prompt_tokens + int(prompt_tokens),
                    "completion_tokens": UserTokenUsageDay.completion_tokens + int(completion_tokens),
                    "total_tokens": UserTokenUsageDay.total_tokens + int(total_tokens),
                    "updated_at": occurred_at,
                },
            )
        )
        await session.execute(stmt)

