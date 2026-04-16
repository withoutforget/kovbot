from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import profile_merge
from kov.tg.dialogs.states import MainMenuSG, TechniquesSG
from kov.tg.runtime import ensure_user_id, runtime


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    event = manager.event
    try:
        if isinstance(event, (Message, CallbackQuery)):
            await profile_merge(event, data={"last_scenario": "techniques"})
    except Exception:
        pass
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_query_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    manager.dialog_data["query"] = text
    await manager.switch_to(TechniquesSG.suggestions)


async def suggestions_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"items": []}
    query = (dialog_manager.dialog_data.get("query") or "").strip()
    if not query:
        return {"items": []}
    user_id = await ensure_user_id(event)
    data = await runtime().api.post("/techniques", {"user_id": user_id, "query": query})
    suggestions = data.get("suggestions") or []
    dialog_manager.dialog_data["suggestions"] = suggestions
    items = [(s.get("title") or "", f"[{s.get('kind')}] {s.get('title')}", s) for s in suggestions]
    return {"items": items, "query": query}


async def on_pick_suggestion(
    callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str
) -> None:
    suggestions = manager.dialog_data.get("suggestions") or []
    selected = next((s for s in suggestions if (s.get("title") or "") == item_id), None)
    manager.dialog_data["selected"] = selected or {}
    await manager.switch_to(TechniquesSG.detail)
    await callback.answer()


async def detail_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    s = dialog_manager.dialog_data.get("selected") or {}
    title = s.get("title") or "—"
    kind = s.get("kind") or "—"
    steps = s.get("steps") or []
    lines = [f"{title} ({kind})", "", *[f"{i+1}. {step}" for i, step in enumerate(steps)]]
    return {"text": "\n".join(lines).strip()[:3800], "title": title}


async def on_alternative_clicked(_, __, manager: DialogManager) -> None:
    # re-enter suggestions to trigger a fresh backend pick
    await manager.switch_to(TechniquesSG.suggestions)


async def on_done_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_techniques")
    msg = callback
    title = (manager.dialog_data.get("selected") or {}).get("title")
    if not title:
        return
    try:
        user_id = await ensure_user_id(msg)
        await runtime().api.post("/techniques/done", {"user_id": user_id, "title": title})
        await callback.answer("Отметил выполнение")
    except Exception as e:
        log.error("technique_done_failed", error=str(e))
        await callback.answer("Не удалось сохранить", show_alert=True)


async def on_save_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_techniques")
    msg = callback
    title = (manager.dialog_data.get("selected") or {}).get("title")
    if not title:
        return
    try:
        user_id = await ensure_user_id(msg)
        await runtime().api.post("/techniques/save", {"user_id": user_id, "title": title})
        await callback.answer("Сохранено")
    except Exception as e:
        log.error("technique_save_failed", error=str(e))
        await callback.answer("Не удалось сохранить", show_alert=True)


techniques_dialog = Dialog(
    Window(
        Const(
            "Техники и упражнения\n\n"
            "Опишите запрос (что сейчас происходит и что вы хотите получить).\n"
            "Я предложу 2 варианта: экспресс и более глубокую практику."
        ),
        MessageInput(on_query_message),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        state=TechniquesSG.ask,
    ),
    Window(
        Format("Запрос: {query}\n\nВыберите технику:"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="s",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_suggestion,
            ),
            id="s_g",
            width=1,
            height=8,
        ),
        Button(Const("Другая подборка"), id="alt", on_click=on_alternative_clicked),
        SwitchTo(Const("Изменить запрос"), id="back", state=TechniquesSG.ask),
        Button(Const("В меню"), id="menu2", on_click=on_to_menu_clicked),
        getter=suggestions_getter,
        state=TechniquesSG.suggestions,
    ),
    Window(
        Format("{text}"),
        Button(Const("Я сделал(а)"), id="done", on_click=on_done_clicked),
        Button(Const("Сохранить в историю"), id="save", on_click=on_save_clicked),
        SwitchTo(Const("Назад"), id="back2", state=TechniquesSG.suggestions),
        Button(Const("В меню"), id="menu3", on_click=on_to_menu_clicked),
        getter=detail_getter,
        state=TechniquesSG.detail,
    ),
)
