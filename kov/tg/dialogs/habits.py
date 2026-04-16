from __future__ import annotations

import json
from datetime import date
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Multiselect, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import parse_hhmm, profile_merge, split_csv
from kov.tg.dialogs.states import HabitsSG, MainMenuSG
from kov.tg.runtime import ensure_user_id, runtime


def _habit_label(h: dict[str, Any]) -> str:
    title = h.get("title") or ""
    archived = bool(h.get("archived"))
    return f"{title}{' (архив)' if archived else ''}".strip()


async def _fetch_habits(user_id: str) -> list[dict[str, Any]]:
    return await runtime().api.get(f"/habits/{user_id}")


async def menu_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    return {}


async def list_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"items": []}
    user_id = await ensure_user_id(event)
    habits = await _fetch_habits(user_id)
    dialog_manager.dialog_data["habits"] = habits
    items = [(h["habit_id"], _habit_label(h), h) for h in habits]
    return {"items": items}


async def detail_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    h = dialog_manager.dialog_data.get("selected_habit") or {}
    title = h.get("title") or "—"
    desc = (h.get("description") or "").strip() or "—"
    archived = "да" if h.get("archived") else "нет"
    return {"title": title, "desc": desc, "archived": archived}


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    event = manager.event
    try:
        if isinstance(event, (Message, CallbackQuery)):
            await profile_merge(event, data={"last_scenario": "habit_tracker"})
    except Exception:
        pass
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_open_list_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(HabitsSG.list)


async def on_pick_habit(
    callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str
) -> None:
    habits = manager.dialog_data.get("habits") or []
    selected = next((h for h in habits if h.get("habit_id") == item_id), None)
    manager.dialog_data["selected_habit"] = selected or {}
    await manager.switch_to(HabitsSG.detail)
    await callback.answer()


async def on_add_clicked(_, __, manager: DialogManager) -> None:
    manager.dialog_data.pop("new_title", None)
    manager.dialog_data.pop("new_desc", None)
    await manager.switch_to(HabitsSG.add_title)


async def on_add_title(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    t = (message.text or "").strip()
    if not t:
        return
    manager.dialog_data["new_title"] = t
    await manager.switch_to(HabitsSG.add_desc)


async def on_add_desc(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    d = (message.text or "").strip()
    title = manager.dialog_data.get("new_title")
    if not title:
        await manager.switch_to(HabitsSG.menu)
        return
    try:
        user_id = await ensure_user_id(message)
        await runtime().api.post("/habits", {"user_id": user_id, "title": title, "description": d})
        await message.answer("Привычка добавлена.")
        await manager.switch_to(HabitsSG.menu)
    except Exception as e:
        log.error("habit_create_failed", error=str(e))
        await message.answer("Не удалось добавить привычку.")


async def on_edit_clicked(_, __, manager: DialogManager) -> None:
    h = manager.dialog_data.get("selected_habit") or {}
    manager.dialog_data["edit_habit_id"] = h.get("habit_id")
    manager.dialog_data["new_title"] = h.get("title") or ""
    manager.dialog_data["new_desc"] = h.get("description") or ""
    await manager.switch_to(HabitsSG.edit_title)


async def on_edit_title(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    t = (message.text or "").strip()
    if not t:
        return
    manager.dialog_data["new_title"] = t
    await manager.switch_to(HabitsSG.edit_desc)


async def on_edit_desc(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    habit_id = manager.dialog_data.get("edit_habit_id")
    if not habit_id:
        await manager.switch_to(HabitsSG.menu)
        return
    desc = (message.text or "").strip()
    title = manager.dialog_data.get("new_title") or ""
    try:
        await runtime().api.post(f"/habits/{habit_id}/update", {"title": title, "description": desc})
        await message.answer("Сохранил изменения.")
        await manager.switch_to(HabitsSG.menu)
    except Exception as e:
        log.error("habit_update_failed", error=str(e))
        await message.answer("Не удалось обновить привычку.")


async def on_toggle_archive_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    h = manager.dialog_data.get("selected_habit") or {}
    habit_id = h.get("habit_id")
    if not habit_id:
        return
    try:
        archived = not bool(h.get("archived"))
        await runtime().api.post(f"/habits/{habit_id}/archive", {"archived": archived})
        h["archived"] = archived
        manager.dialog_data["selected_habit"] = h
        await callback.answer("Ок")
        await manager.switch_to(HabitsSG.detail)
    except Exception as e:
        log.error("habit_archive_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def on_delete_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    h = manager.dialog_data.get("selected_habit") or {}
    habit_id = h.get("habit_id")
    if not habit_id:
        return
    try:
        await runtime().api.post(f"/habits/{habit_id}/delete", {})
        await callback.answer("Удалено")
        await manager.switch_to(HabitsSG.menu)
    except Exception as e:
        log.error("habit_delete_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def today_pick_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"items": []}
    user_id = await ensure_user_id(event)
    habits = await _fetch_habits(user_id)
    active = [h for h in habits if not h.get("archived")]
    items = [(h["habit_id"], h["title"]) for h in active]
    return {"items": items}


async def on_today_next_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(HabitsSG.today_done)


async def today_done_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    # Selected ids are stored in Multiselect widget state, we derive items from it via manager.dialog().find.
    # We still need items list to render, take from last fetch in today_pick_getter.
    data = await today_pick_getter(dialog_manager)
    return {"items": data.get("items") or []}


async def on_helped_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    manager.dialog_data["helped"] = split_csv(message.text or "")
    await manager.switch_to(HabitsSG.log_hindered)


async def on_hindered_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    helped = manager.dialog_data.get("helped") or []
    hindered = split_csv(message.text or "")
    try:
        user_id = await ensure_user_id(message)
        # retrieve multiselect states
        pick = manager.find("pick")
        done = manager.find("done")
        picked_ids = set(pick.get_checked())
        done_ids = set(done.get_checked())
        if not picked_ids:
            await message.answer("Вы не выбрали ни одной привычки.")
            await manager.switch_to(HabitsSG.menu)
            return
        notes = json.dumps({"helped": helped, "hindered": hindered}, ensure_ascii=False)
        for hid in picked_ids:
            await runtime().api.post(
                "/habits/log",
                {
                    "user_id": user_id,
                    "habit_id": str(hid),
                    "log_date": str(date.today()),
                    "done": str(hid) in {str(x) for x in done_ids},
                    "notes": notes,
                },
            )
        await message.answer("Отметки сохранены.")
        await manager.switch_to(HabitsSG.menu)
    except Exception as e:
        log.error("habit_log_failed", error=str(e))
        await message.answer("Не удалось сохранить отметки.")


async def weekly_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"text": "—"}
    user_id = await ensure_user_id(event)
    data = await runtime().api.get(f"/reports/habits/weekly/{user_id}")
    lines = [
        f"Отчёт по привычкам (неделя {data.get('period_start')} → {data.get('period_end')})",
        "",
    ]
    for h in data.get("habits") or []:
        lines.append(f"• {h.get('title')}: {h.get('done')}/{h.get('total')}")
    helped = data.get("top_helped_factors") or []
    hindered = data.get("top_hindered_factors") or []
    recs = data.get("recommendations") or []
    if helped:
        lines += ["", "Чаще помогало:", *[f"• {k} — {n}" for k, n in helped[:10]]]
    if hindered:
        lines += ["", "Чаще мешало:", *[f"• {k} — {n}" for k, n in hindered[:10]]]
    if recs:
        lines += ["", "Рекомендации:", *[f"• {r}" for r in recs[:5]]]
    return {"text": "\n".join(lines).strip()[:3800]}


async def monthly_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"text": "—"}
    user_id = await ensure_user_id(event)
    data = await runtime().api.get(f"/reports/habits/monthly/{user_id}")
    lines = [
        f"Отчёт по привычкам (месяц {data.get('period_start')} → {data.get('period_end')})",
        "",
    ]
    for h in data.get("habits") or []:
        lines.append(f"• {h.get('title')}: {h.get('done')}/{h.get('total')}")
    helped = data.get("top_helped_factors") or []
    hindered = data.get("top_hindered_factors") or []
    recs = data.get("recommendations") or []
    if helped:
        lines += ["", "Чаще помогало:", *[f"• {k} — {n}" for k, n in helped[:10]]]
    if hindered:
        lines += ["", "Чаще мешало:", *[f"• {k} — {n}" for k, n in hindered[:10]]]
    if recs:
        lines += ["", "Рекомендации:", *[f"• {r}" for r in recs[:5]]]
    return {"text": "\n".join(lines).strip()[:3800]}


async def settings_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    enabled = dialog_manager.dialog_data.get("enabled", True)
    at_time = dialog_manager.dialog_data.get("at_time") or "21:00"
    event = dialog_manager.event
    if isinstance(event, (Message, CallbackQuery)):
        try:
            user_id = await ensure_user_id(event)
            schedules = await runtime().api.get(f"/schedule/{user_id}")
            item = next((x for x in schedules if x.get("schedule_key") == "habit_tracker"), None) or {}
            enabled = bool(item.get("enabled", enabled))
            tm = (item.get("at_time") or "").strip()
            if tm:
                at_time = tm[:5]
            dialog_manager.dialog_data["enabled"] = enabled
            dialog_manager.dialog_data["at_time"] = at_time
        except Exception:
            pass
    return {"enabled": "включены" if enabled else "выключены", "at_time": at_time}


async def on_settings_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(HabitsSG.settings)


async def on_time_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_habits")
    tm = parse_hhmm(message.text or "")
    if not tm:
        await message.answer("Формат времени: HH:MM (например 21:00).")
        return
    try:
        user_id = await ensure_user_id(message)
        enabled = bool(manager.dialog_data.get("enabled", True))
        await runtime().api.post(
            "/schedule",
            {"user_id": user_id, "schedule_key": "habit_tracker", "at_time": tm.isoformat(), "enabled": enabled},
        )
        manager.dialog_data["at_time"] = tm.isoformat(timespec="minutes")
        await message.answer("Сохранил время напоминания.")
        await manager.switch_to(HabitsSG.settings)
    except Exception as e:
        log.error("habit_schedule_failed", error=str(e))
        await message.answer("Не удалось сохранить настройки напоминаний.")


async def _persist_settings(event: Message | CallbackQuery, manager: DialogManager) -> None:
    enabled = bool(manager.dialog_data.get("enabled", True))
    at_time_s = (manager.dialog_data.get("at_time") or "21:00").strip()
    if len(at_time_s) == 5:
        at_time_s = at_time_s + ":00"
    user_id = await ensure_user_id(event)
    await runtime().api.post(
        "/schedule",
        {"user_id": user_id, "schedule_key": "habit_tracker", "at_time": at_time_s, "enabled": enabled},
    )


async def on_enable_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    manager.dialog_data["enabled"] = True
    try:
        await _persist_settings(callback, manager)
    except Exception:
        pass
    await manager.switch_to(HabitsSG.settings)


async def on_disable_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    manager.dialog_data["enabled"] = False
    try:
        await _persist_settings(callback, manager)
    except Exception:
        pass
    await manager.switch_to(HabitsSG.settings)


habits_dialog = Dialog(
    Window(
        Const("Трекер привычек"),
        Button(Const("Список привычек"), id="list", on_click=on_open_list_clicked),
        Button(Const("Добавить привычку"), id="add", on_click=on_add_clicked),
        SwitchTo(Const("Заполнить сегодня"), id="today", state=HabitsSG.today_pick),
        SwitchTo(Const("Недельная статистика"), id="w", state=HabitsSG.weekly),
        SwitchTo(Const("Месячная статистика"), id="m", state=HabitsSG.monthly),
        Button(Const("Настройки напоминаний"), id="settings", on_click=on_settings_clicked),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        getter=menu_getter,
        state=HabitsSG.menu,
    ),
    Window(
        Const("Привычки:"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="h",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_habit,
            ),
            id="h_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back", state=HabitsSG.menu),
        getter=list_getter,
        state=HabitsSG.list,
    ),
    Window(
        Format("Привычка: {title}\n\nОписание: {desc}\nАрхив: {archived}"),
        Button(Const("Изменить"), id="edit", on_click=on_edit_clicked),
        Button(Const("Архивировать / вернуть"), id="arch", on_click=on_toggle_archive_clicked),
        Button(Const("Удалить"), id="del", on_click=on_delete_clicked),
        SwitchTo(Const("Назад"), id="back2", state=HabitsSG.list),
        getter=detail_getter,
        state=HabitsSG.detail,
    ),
    Window(
        Const("Название привычки:"),
        MessageInput(on_add_title),
        SwitchTo(Const("Назад"), id="back3", state=HabitsSG.menu),
        state=HabitsSG.add_title,
    ),
    Window(
        Const("Описание (можно пусто):"),
        MessageInput(on_add_desc),
        SwitchTo(Const("Назад"), id="back4", state=HabitsSG.add_title),
        state=HabitsSG.add_desc,
    ),
    Window(
        Const("Новое название:"),
        MessageInput(on_edit_title),
        SwitchTo(Const("Назад"), id="back5", state=HabitsSG.detail),
        state=HabitsSG.edit_title,
    ),
    Window(
        Const("Новое описание:"),
        MessageInput(on_edit_desc),
        SwitchTo(Const("Назад"), id="back6", state=HabitsSG.edit_title),
        state=HabitsSG.edit_desc,
    ),
    Window(
        Const("Выберите привычки для отметки сегодня:"),
        ScrollingGroup(
            Multiselect(
                checked_text=Format("✅ {item[1]}"),
                unchecked_text=Format("⬜️ {item[1]}"),
                id="pick",
                items="items",
                item_id_getter=lambda item: item[0],
            ),
            id="pick_g",
            width=1,
            height=8,
        ),
        Button(Const("Далее"), id="next", on_click=on_today_next_clicked),
        SwitchTo(Const("Назад"), id="back7", state=HabitsSG.menu),
        getter=today_pick_getter,
        state=HabitsSG.today_pick,
    ),
    Window(
        Const("Отметьте выполненные привычки (✅ = выполнено):"),
        ScrollingGroup(
            Multiselect(
                checked_text=Format("✅ {item[1]}"),
                unchecked_text=Format("⬜️ {item[1]}"),
                id="done",
                items="items",
                item_id_getter=lambda item: item[0],
            ),
            id="done_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Далее"), id="next2", state=HabitsSG.log_helped),
        SwitchTo(Const("Назад"), id="back8", state=HabitsSG.today_pick),
        getter=today_done_getter,
        state=HabitsSG.today_done,
    ),
    Window(
        Const("Что помогло сегодня выполнить привычки? (через запятую или «нет»)"),
        MessageInput(on_helped_message),
        SwitchTo(Const("Назад"), id="back9", state=HabitsSG.today_done),
        state=HabitsSG.log_helped,
    ),
    Window(
        Const("Что мешало/останавливало? (через запятую или «нет»)"),
        MessageInput(on_hindered_message),
        SwitchTo(Const("Назад"), id="back9b", state=HabitsSG.log_helped),
        state=HabitsSG.log_hindered,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back10", state=HabitsSG.menu),
        getter=weekly_getter,
        state=HabitsSG.weekly,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back11", state=HabitsSG.menu),
        getter=monthly_getter,
        state=HabitsSG.monthly,
    ),
    Window(
        Format(
            "Настройки напоминаний\n\nСтатус: {enabled}\nВремя: {at_time}\n\n"
            "Чтобы изменить время, напишите его в формате HH:MM."
        ),
        Button(Const("Включить"), id="en", on_click=on_enable_clicked),
        Button(Const("Выключить"), id="dis", on_click=on_disable_clicked),
        MessageInput(on_time_message),
        SwitchTo(Const("Назад"), id="back12", state=HabitsSG.menu),
        getter=settings_getter,
        state=HabitsSG.settings,
    ),
)
