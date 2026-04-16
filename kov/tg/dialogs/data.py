from __future__ import annotations

import json
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import get_chat_id, json_file
from kov.tg.dialogs.states import DataSG, MainMenuSG
from kov.tg.runtime import ensure_user_id, runtime


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def _event_user_id(manager: DialogManager) -> str | None:
    event = manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return None
    return await ensure_user_id(event)


async def on_export_clicked(_, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_data")
    uid = await _event_user_id(manager)
    if not uid:
        return
    try:
        data = await runtime().api.get(f"/export/{uid}")
        doc = json_file(filename="kora_export.json", data=data)
        await manager.event.bot.send_document(  # type: ignore[attr-defined]
            chat_id=get_chat_id(manager), document=doc, caption="Экспорт данных"
        )
    except Exception as e:
        log.error("export_failed", error=str(e))


async def interview_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    uid = await _event_user_id(dialog_manager)
    if not uid:
        return {"text": "—"}
    data = await runtime().api.get(f"/scenarios/interview/{uid}")
    answers = data.get("answers") or {}
    lines = ["Интервью", ""]
    for k, v in answers.items():
        lines.append(f"• {k}: {v}")
    if not answers:
        lines.append("Пока нет ответов.")
    return {"text": "\n".join(lines).strip()[:3800]}


async def mood_list_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    uid = await _event_user_id(dialog_manager)
    if not uid:
        return {"items": []}
    entries: list[dict[str, Any]] = await runtime().api.get(f"/mood/history/{uid}")
    entries = list(reversed(entries))[:30]
    items = [(str(e.get("entry_date")), f"{e.get('entry_date')} (оценка: {e.get('mood_score')})", e) for e in entries]
    dialog_manager.dialog_data["mood_items"] = items
    return {"items": items}


async def on_pick_mood(callback: CallbackQuery, _w: Select, manager: DialogManager, item_id: str) -> None:
    items = manager.dialog_data.get("mood_items") or []
    selected = next((x[2] for x in items if x[0] == item_id), None)
    manager.dialog_data["mood_selected"] = selected or {}
    await manager.switch_to(DataSG.mood_view)
    await callback.answer()


async def mood_view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    e = dialog_manager.dialog_data.get("mood_selected") or {}
    d = e.get("entry_date") or "—"
    score = e.get("mood_score")
    score_s = "—" if score is None else str(score)
    notes = (e.get("notes") or "").strip() or "—"
    down = ", ".join(e.get("factors_down") or []) or "—"
    up = ", ".join(e.get("factors_up") or []) or "—"
    text = f"Настроение за {d}\n\nОценка: {score_s}\nЗаметки: {notes}\nСпад: {down}\nПоддержка: {up}"
    return {"text": text[:3800], "date": str(d)}


async def on_delete_mood(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_data")
    try:
        uid = await ensure_user_id(callback)
        e = manager.dialog_data.get("mood_selected") or {}
        d = str(e.get("entry_date") or "")
        if not d:
            await callback.answer("Нет даты", show_alert=True)
            return
        await runtime().api.post(f"/mood/entry/{uid}/{d}/delete", {})
        await callback.answer("Удалено")
        await manager.switch_to(DataSG.mood_list)
    except Exception as e:
        log.error("delete_mood_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def habits_list_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    uid = await _event_user_id(dialog_manager)
    if not uid:
        return {"items": []}
    habits = await runtime().api.get(f"/habits/{uid}")
    items = [(h.get("habit_id") or "", h.get("title") or "", h) for h in habits]
    dialog_manager.dialog_data["habits_items"] = items
    return {"items": items}


async def on_pick_habit(callback: CallbackQuery, _w: Select, manager: DialogManager, item_id: str) -> None:
    items = manager.dialog_data.get("habits_items") or []
    selected = next((x[2] for x in items if x[0] == item_id), None)
    manager.dialog_data["habit_selected"] = selected or {}
    await manager.switch_to(DataSG.habit_view)
    await callback.answer()


async def habit_view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    h = dialog_manager.dialog_data.get("habit_selected") or {}
    title = h.get("title") or "—"
    desc = (h.get("description") or "").strip() or "—"
    archived = "да" if h.get("archived") else "нет"
    return {"text": f"Привычка: {title}\n\nОписание: {desc}\nАрхив: {archived}"[:3800]}


async def habit_logs_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    uid = await _event_user_id(dialog_manager)
    h = dialog_manager.dialog_data.get("habit_selected") or {}
    hid = h.get("habit_id")
    if not uid or not hid:
        return {"items": []}
    logs = await runtime().api.get(f"/habits/logs/{uid}?habit_id={hid}&limit=60")
    items = [
        (str(l.get("log_date")), f"{l.get('log_date')} — {'✅' if l.get('done') else '❌'}", l) for l in logs
    ]
    dialog_manager.dialog_data["habit_logs"] = items
    return {"items": items}


async def on_pick_habit_log(callback: CallbackQuery, _w: Select, manager: DialogManager, item_id: str) -> None:
    items = manager.dialog_data.get("habit_logs") or []
    selected = next((x[2] for x in items if x[0] == item_id), None)
    manager.dialog_data["log_selected"] = selected or {}
    await manager.switch_to(DataSG.habit_log_view)
    await callback.answer()


async def habit_log_view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    l = dialog_manager.dialog_data.get("log_selected") or {}
    d = l.get("log_date") or "—"
    done = "✅" if l.get("done") else "❌"
    notes = (l.get("notes") or "").strip()
    helped = []
    hindered = []
    if notes:
        try:
            payload = json.loads(notes)
            helped = payload.get("helped") or []
            hindered = payload.get("hindered") or []
        except Exception:
            pass
    text = (
        f"Лог за {d}\n\nСтатус: {done}\n"
        f"Помогло: {', '.join(helped) or '—'}\n"
        f"Мешало: {', '.join(hindered) or '—'}"
    )
    return {"text": text[:3800], "date": str(d)}


async def on_delete_habit_log(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_data")
    try:
        h = manager.dialog_data.get("habit_selected") or {}
        hid = h.get("habit_id")
        l = manager.dialog_data.get("log_selected") or {}
        d = l.get("log_date")
        if not hid or not d:
            await callback.answer("Нет данных", show_alert=True)
            return
        await runtime().api.post(f"/habits/log/{hid}/{d}/delete", {})
        await callback.answer("Удалено")
        await manager.switch_to(DataSG.habit_logs)
    except Exception as e:
        log.error("delete_habit_log_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def dialogs_list_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    uid = await _event_user_id(dialog_manager)
    if not uid:
        return {"items": []}
    dialogs = await runtime().api.get(f"/dialog/list/{uid}")
    items = [(d.get("dialog_id") or "", f"{d.get('scenario_key') or 'dialog'}", d) for d in dialogs]
    dialog_manager.dialog_data["dialogs"] = items
    return {"items": items}


async def on_pick_dialog(callback: CallbackQuery, _w: Select, manager: DialogManager, item_id: str) -> None:
    manager.dialog_data["dialog_id"] = item_id
    await manager.switch_to(DataSG.dialog_view)
    await callback.answer()


async def dialog_view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    did = dialog_manager.dialog_data.get("dialog_id")
    if not did:
        return {"text": "—"}
    data = await runtime().api.get(f"/dialog/{did}")
    msgs = data.get("messages") or []
    tail = msgs[-12:]
    lines = [f"Диалог: {data.get('title') or ''}", ""]
    for m in tail:
        role = "Вы" if m.get("role") == "user" else "Кора"
        text = (m.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return {"text": "\n".join(lines).strip()[:3800]}


data_dialog = Dialog(
    Window(
        Const("Мои данные\n\nВыберите раздел:"),
        SwitchTo(Const("Интервью"), id="i", state=DataSG.interview),
        SwitchTo(Const("Настроение"), id="m", state=DataSG.mood_list),
        SwitchTo(Const("Привычки"), id="h", state=DataSG.habits_list),
        SwitchTo(Const("Диалоги"), id="d", state=DataSG.dialogs_list),
        Button(Const("Экспорт JSON"), id="ex", on_click=on_export_clicked),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        state=DataSG.menu,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back", state=DataSG.menu),
        getter=interview_getter,
        state=DataSG.interview,
    ),
    Window(
        Const("Записи настроения (последние 30):"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="ml",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_mood,
            ),
            id="ml_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back2", state=DataSG.menu),
        getter=mood_list_getter,
        state=DataSG.mood_list,
    ),
    Window(
        Format("{text}"),
        Button(Const("Удалить запись"), id="del_m", on_click=on_delete_mood),
        SwitchTo(Const("Назад"), id="back3", state=DataSG.mood_list),
        getter=mood_view_getter,
        state=DataSG.mood_view,
    ),
    Window(
        Const("Привычки:"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="hl",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_habit,
            ),
            id="hl_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back4", state=DataSG.menu),
        getter=habits_list_getter,
        state=DataSG.habits_list,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Логи"), id="logs", state=DataSG.habit_logs),
        SwitchTo(Const("Назад"), id="back5", state=DataSG.habits_list),
        getter=habit_view_getter,
        state=DataSG.habit_view,
    ),
    Window(
        Const("Логи привычки (последние 60):"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="lg",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_habit_log,
            ),
            id="lg_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back6", state=DataSG.habit_view),
        getter=habit_logs_getter,
        state=DataSG.habit_logs,
    ),
    Window(
        Format("{text}"),
        Button(Const("Удалить лог"), id="del_l", on_click=on_delete_habit_log),
        SwitchTo(Const("Назад"), id="back7", state=DataSG.habit_logs),
        getter=habit_log_view_getter,
        state=DataSG.habit_log_view,
    ),
    Window(
        Const("Диалоги:"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="dl",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_dialog,
            ),
            id="dl_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back8", state=DataSG.menu),
        getter=dialogs_list_getter,
        state=DataSG.dialogs_list,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back9", state=DataSG.dialogs_list),
        getter=dialog_view_getter,
        state=DataSG.dialog_view,
    ),
)
