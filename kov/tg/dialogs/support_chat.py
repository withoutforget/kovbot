from __future__ import annotations

from typing import Any

import random
import time

from aiogram.methods.send_message_draft import SendMessageDraft
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import profile_merge
from kov.tg.dialogs.states import MainMenuSG, SupportChatSG
from kov.tg.runtime import ensure_user_id, runtime


async def chat_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    scenario_key = (dialog_manager.start_data or {}).get("scenario_key") or "dialog"
    title = "Диалог" if scenario_key == "dialog" else "Отношения"
    dialog_manager.dialog_data["scenario_key"] = scenario_key
    try:
        if isinstance(dialog_manager.event, (Message, CallbackQuery)):
            await profile_merge(dialog_manager.event, data={"last_scenario": scenario_key})
    except Exception:
        pass
    return {"title": title}


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    scenario_key = manager.dialog_data.get("scenario_key") or "dialog"
    event = manager.event
    try:
        if isinstance(event, (Message, CallbackQuery)):
            await profile_merge(event, data={"last_scenario": scenario_key})
    except Exception:
        pass
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_user_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_support_chat")
    text = (message.text or "").strip()
    if not text:
        return
    scenario_key = manager.dialog_data.get("scenario_key") or "dialog"
    try:
        user_id = await ensure_user_id(message)
        payload = {"user_id": user_id, "scenario_key": scenario_key, "text": text}

        progress = await message.answer("Думаю…")
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

        async for delta in runtime().api.stream_text("/dialog/message/stream", payload):
            if not delta:
                continue
            full += delta
            drafts[current]["text"] += delta
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
    except Exception as e:
        log.error("support_chat_failed", error=str(e))
        await message.answer("Не удалось получить ответ. Проверь, что API доступен и LLM настроен.")


support_chat_dialog = Dialog(
    Window(
        Format(
            "{title}\n\n"
            "Напишите сообщение. Я отвечу бережно и по делу.\n"
            "Можно продолжать диалог — контекст сохраняется на бэкенде."
        ),
        MessageInput(on_user_message),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        getter=chat_getter,
        state=SupportChatSG.chat,
    )
)
