from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import CallbackQuery, Message

from kov.logging import get_logger
from kov.tg.api import ApiClient


@dataclass(frozen=True)
class TgRuntime:
    api: ApiClient


_RUNTIME: TgRuntime | None = None


def init_runtime(*, api_base_url: str) -> None:
    global _RUNTIME
    _RUNTIME = TgRuntime(api=ApiClient(api_base_url))


def runtime() -> TgRuntime:
    if _RUNTIME is None:
        raise RuntimeError("Tg runtime is not initialized")
    return _RUNTIME


async def ensure_user_id(event: Message | CallbackQuery, *, timezone: str = "UTC") -> str:
    log = get_logger(component="tg_runtime")
    api = runtime().api
    user = event.from_user
    if user is None:
        raise RuntimeError("Telegram event has no from_user")
    try:
        data = await api.post(
            "/users/ensure",
            {
                "telegram_user_id": str(user.id),
                "telegram_username": (user.username or ""),
                "timezone": timezone or "UTC",
                "language": user.language_code or "ru",
            },
        )
        return data["user_id"]
    except Exception as e:
        log.error("ensure_user_failed", error=str(e))
        raise
