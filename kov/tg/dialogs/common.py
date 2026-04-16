from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import time
from typing import Any, Iterable

from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram_dialog import DialogManager

from kov.tg.runtime import ensure_user_id, runtime


def get_chat_id(manager: DialogManager) -> int:
    event = manager.event
    if isinstance(event, CallbackQuery):
        if event.message:
            return event.message.chat.id
        return event.from_user.id
    if isinstance(event, Message):
        return event.chat.id
    raise RuntimeError(f"Unsupported event type: {type(event)!r}")


def split_csv(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def parse_hhmm(text: str) -> time | None:
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s*:\s*(\d{2})", t)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return time(hour=hh, minute=mm)


def try_parse_int(text: str) -> int | None:
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(r"-?\d+", t)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def json_file(*, filename: str, data: Any) -> BufferedInputFile:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return BufferedInputFile(payload, filename=filename)


async def profile_get(event: Message | CallbackQuery) -> dict[str, Any]:
    user_id = await ensure_user_id(event)
    try:
        resp = await runtime().api.get(f"/users/profile/{user_id}")
        return resp.get("data") or {}
    except Exception:
        return {}


async def profile_merge(event: Message | CallbackQuery, *, data: dict[str, Any]) -> None:
    user_id = await ensure_user_id(event)
    await runtime().api.post("/users/profile/merge", {"user_id": user_id, "data": data})


@dataclass(frozen=True)
class ListItem:
    id: str
    title: str


def as_list_items(items: Iterable[dict[str, Any]], *, id_key: str, title_key: str) -> list[ListItem]:
    out: list[ListItem] = []
    for it in items:
        out.append(ListItem(id=str(it.get(id_key) or ""), title=str(it.get(title_key) or "")))
    return out
