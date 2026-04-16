from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from aiogram import Bot
from aiogram.methods.send_message_draft import SendMessageDraft
from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const

from kov.logging import get_logger
from kov.tg.dialogs.states import KnowledgeBaseSG, MainMenuSG
from kov.tg.runtime import ensure_user_id, runtime


def _build_query_with_history(*, history: list[dict[str, str]], user_text: str) -> str:
    if not history:
        return user_text
    # keep it compact: last 10 messages
    tail = history[-10:]
    lines: list[str] = ["Контекст диалога:"]
    for item in tail:
        role = item.get("role") or "user"
        text = (item.get("text") or "").strip()
        if not text:
            continue
        prefix = "Пользователь" if role == "user" else "Ассистент"
        lines.append(f"{prefix}: {text}")
    lines.append("")
    lines.append("Текущий вопрос:")
    lines.append(user_text)
    return "\n".join(lines).strip()


async def _send_streaming_text(
    bot: Bot, *, chat_id: int, text: str, chunk_size: int = 1200, delay_s: float = 0.15, max_chunks: int = 10
) -> None:
    t = (text or "").strip()
    if not t:
        return
    chunks: list[str] = []
    for i in range(0, len(t), chunk_size):
        chunks.append(t[i : i + chunk_size])
        if len(chunks) >= max_chunks:
            break
    for c in chunks:
        await bot.send_message(chat_id=chat_id, text=c)
        await asyncio.sleep(delay_s)
    rest = t[len("".join(chunks)) :].strip()
    if rest:
        await bot.send_message(chat_id=chat_id, text=rest)


async def on_end_clicked(_, __, manager: DialogManager) -> None:
    manager.dialog_data.pop("history", None)
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_kb_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_kb_dialog")
    text = (message.text or "").strip()
    if not text:
        return

    history: list[dict[str, str]] = manager.dialog_data.get("history") or []
    history.append({"role": "user", "text": text})
    manager.dialog_data["history"] = history

    progress = await message.answer("Поиск по базе знаний…")
    try:
        user_id = await ensure_user_id(message)
        api = runtime().api
        payload: dict[str, Any] = {
            "user_query": _build_query_with_history(history=history, user_text=text),
            "user_id": user_id,
            "scenario_id": "knowledge_base",
            "language": "ru",
            "search_profile": "quick_advice",
        }
        # Draft streaming: updates a message draft in-place.
        # If the answer is longer than the Telegram limit, we continue in a new draft.
        draft_limit = 3500
        min_interval_s = 0.6
        min_delta_chars = 80

        drafts: list[dict[str, Any]] = [{"id": random.randint(1, 2_147_483_647), "text": ""}]
        current = 0
        last_sent_at = 0.0
        last_sent_len = 0
        full = ""
        progress_deleted = False

        async def send_current(force: bool = False) -> None:
            nonlocal last_sent_at, last_sent_len, progress_deleted
            now = time.monotonic()
            t = drafts[current]["text"]
            if not t.strip():
                return
            if not force:
                if (now - last_sent_at) < min_interval_s and (len(t) - last_sent_len) < min_delta_chars:
                    return
            await message.bot(
                SendMessageDraft(chat_id=message.chat.id, draft_id=int(drafts[current]["id"]), text=t)
            )
            last_sent_at = now
            last_sent_len = len(t)
            if not progress_deleted:
                progress_deleted = True
                try:
                    await progress.delete()
                except Exception:
                    pass

        async for delta in api.stream_text("/rag/search/stream", payload):
            if not delta:
                continue
            full += delta
            drafts[current]["text"] += delta
            # split into multiple drafts if longer than safe limit
            while len(drafts[current]["text"]) > draft_limit:
                overflow = drafts[current]["text"][draft_limit:]
                drafts[current]["text"] = drafts[current]["text"][:draft_limit]
                await send_current(force=True)
                drafts.append({"id": random.randint(1, 2_147_483_647), "text": overflow})
                current += 1
                last_sent_at = 0.0
                last_sent_len = 0
            await send_current()

        await send_current(force=True)
        # Finalize: send the completed message so it's stored in chat history.
        # Telegram enforces 4096 chars, so we do a soft split if needed.
        final_text = full.strip()
        if final_text:
            limit = 3900
            for i in range(0, len(final_text), limit):
                await message.answer(final_text[i : i + limit])

        if not progress_deleted:
            try:
                await progress.delete()
            except Exception:
                pass

        history.append({"role": "assistant", "text": full.strip()})
        manager.dialog_data["history"] = history
    except Exception as e:
        log.error("kb_rag_failed", error=str(e))
        await message.answer("Не удалось выполнить поиск. Проверь, что API доступен и ключи LLM настроены.")
    finally:
        # progress is deleted on first draft update (or here on failure)
        try:
            await progress.delete()
        except Exception:
            pass


kb_dialog = Dialog(
    Window(
        Const(
            "Поиск по базе знаний\n\n"
            "Задай мне любой вопрос и напиши побольше вводных.\n"
            "Дальше можешь продолжать диалог — я буду учитывать контекст."
        ),
        MessageInput(on_kb_message),
        Button(Const("Закончить диалог"), id="end", on_click=on_end_clicked),
        state=KnowledgeBaseSG.chat,
    )
)
