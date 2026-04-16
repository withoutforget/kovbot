from __future__ import annotations

from datetime import date
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import parse_hhmm, profile_merge, split_csv, try_parse_int
from kov.tg.dialogs.states import MainMenuSG, MoodSG
from kov.tg.runtime import ensure_user_id, runtime


def _fmt_entry(e: dict[str, Any]) -> str:
    d = str(e.get("entry_date") or "")
    score = e.get("mood_score")
    score_s = "—" if score is None else str(score)
    return f"{d} (оценка: {score_s})"


async def menu_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    # show last saved values (local, for current run)
    score = dialog_manager.dialog_data.get("mood_score")
    return {"last_score": "—" if score is None else str(score)}


async def history_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"items": []}
    user_id = await ensure_user_id(event)
    entries: list[dict[str, Any]] = await runtime().api.get(f"/mood/history/{user_id}")
    entries = list(reversed(entries))[:30]  # newest first, limit for UI
    items = [(str(e.get("entry_date")), _fmt_entry(e), e) for e in entries]
    return {"items": items}


async def history_view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    e = dialog_manager.dialog_data.get("selected_entry") or {}
    d = e.get("entry_date") or "—"
    score = e.get("mood_score")
    notes = (e.get("notes") or "").strip()
    down = ", ".join(e.get("factors_down") or []) or "—"
    up = ", ".join(e.get("factors_up") or []) or "—"
    score_s = "—" if score is None else str(score)
    text = f"Запись за {d}\n\nОценка: {score_s}\nЗаметки: {notes or '—'}\nСпад: {down}\nПоддержка: {up}"
    return {"text": text[:3800]}


async def weekly_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"text": "—"}
    user_id = await ensure_user_id(event)
    data = await runtime().api.get(f"/reports/mood/weekly/{user_id}")
    avg = data.get("avg_mood")
    avg_s = "—" if avg is None else f"{avg:.2f}"
    down = data.get("top_down_factors") or []
    up = data.get("top_up_factors") or []
    daily = data.get("daily_scores") or []
    lines = [
        f"Отчёт по настроению (неделя {data.get('period_start')} → {data.get('period_end')})",
        "",
        f"Среднее настроение: {avg_s}",
        "",
        "Дневные оценки:",
        *(f"• {d}: {s}" for d, s in daily),
        "",
        "Частые факторы спада:",
        *(f"• {k} — {n}" for k, n in down[:10]),
        "",
        "Частые факторы поддержки:",
        *(f"• {k} — {n}" for k, n in up[:10]),
    ]
    return {"text": "\n".join(lines).strip()[:3800]}


async def monthly_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"text": "—"}
    user_id = await ensure_user_id(event)
    data = await runtime().api.get(f"/reports/mood/monthly/{user_id}")
    avg = data.get("avg_mood")
    avg_s = "—" if avg is None else f"{avg:.2f}"
    down = data.get("top_down_factors") or []
    up = data.get("top_up_factors") or []
    daily = data.get("daily_scores") or []
    lines = [
        f"Отчёт по настроению (месяц {data.get('period_start')} → {data.get('period_end')})",
        "",
        f"Среднее настроение: {avg_s}",
        "",
        "Дневные оценки:",
        *(f"• {d}: {s}" for d, s in daily[-14:]),  # keep compact
        "",
        "Частые факторы спада:",
        *(f"• {k} — {n}" for k, n in down[:10]),
        "",
        "Частые факторы поддержки:",
        *(f"• {k} — {n}" for k, n in up[:10]),
    ]
    return {"text": "\n".join(lines).strip()[:3800]}


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    event = manager.event
    try:
        if isinstance(event, (Message, CallbackQuery)):
            await profile_merge(event, data={"last_scenario": "mood_tracker"})
    except Exception:
        pass
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_fill_today_clicked(_, __, manager: DialogManager) -> None:
    manager.dialog_data.pop("mood_score", None)
    manager.dialog_data.pop("notes", None)
    manager.dialog_data.pop("factors_down", None)
    manager.dialog_data.pop("factors_up", None)
    await manager.switch_to(MoodSG.q_score)


async def on_score_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    score = try_parse_int(message.text or "")
    if score is None or not (0 <= score <= 10):
        await message.answer("Пожалуйста, укажи число от 0 до 10.")
        return
    manager.dialog_data["mood_score"] = score
    await manager.switch_to(MoodSG.q_notes)


async def on_notes_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    manager.dialog_data["notes"] = (message.text or "").strip()
    await manager.switch_to(MoodSG.q_down)


async def on_down_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    manager.dialog_data["factors_down"] = split_csv(message.text or "")
    await manager.switch_to(MoodSG.q_up)


async def on_up_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_mood")
    manager.dialog_data["factors_up"] = split_csv(message.text or "")
    try:
        user_id = await ensure_user_id(message)
        payload = {
            "user_id": user_id,
            "entry_date": str(date.today()),
            "mood_score": manager.dialog_data.get("mood_score"),
            "notes": manager.dialog_data.get("notes") or "",
            "factors_down": manager.dialog_data.get("factors_down") or [],
            "factors_up": manager.dialog_data.get("factors_up") or [],
        }
        await runtime().api.post("/mood/entry", payload)
        await message.answer("Запись сохранена.")
        await manager.switch_to(MoodSG.menu)
    except Exception as e:
        log.error("mood_save_failed", error=str(e))
        await message.answer("Не удалось сохранить запись. Проверь, что API доступен.")


async def on_pick_entry(
    callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str
) -> None:
    items = (await history_getter(manager)).get("items") or []
    selected = next((x[2] for x in items if x[0] == item_id), None)
    manager.dialog_data["selected_entry"] = selected or {}
    await manager.switch_to(MoodSG.history_view)
    await callback.answer()


async def on_settings_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(MoodSG.settings)


async def on_set_time_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(MoodSG.set_time)


async def _persist_settings(event: Message | CallbackQuery, manager: DialogManager) -> None:
    # store enabled + time (best-effort). If time wasn't set in UI, keep defaults.
    enabled = bool(manager.dialog_data.get("enabled", True))
    at_time_s = (manager.dialog_data.get("at_time") or "18:00").strip()
    # normalize HH:MM to HH:MM:SS
    if len(at_time_s) == 5:
        at_time_s = at_time_s + ":00"
    user_id = await ensure_user_id(event)
    await runtime().api.post(
        "/schedule",
        {"user_id": user_id, "schedule_key": "mood_tracker", "at_time": at_time_s, "enabled": enabled},
    )


async def on_enable_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    manager.dialog_data["enabled"] = True
    try:
        await _persist_settings(callback, manager)
    except Exception:
        pass
    await manager.switch_to(MoodSG.settings)


async def on_disable_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    manager.dialog_data["enabled"] = False
    try:
        await _persist_settings(callback, manager)
    except Exception:
        pass
    await manager.switch_to(MoodSG.settings)


async def on_time_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_mood")
    tm = parse_hhmm(message.text or "")
    if not tm:
        await message.answer("Формат времени: HH:MM (например 18:00).")
        return
    try:
        user_id = await ensure_user_id(message)
        enabled = bool(manager.dialog_data.get("enabled", True))
        await runtime().api.post(
            "/schedule",
            {"user_id": user_id, "schedule_key": "mood_tracker", "at_time": tm.isoformat(), "enabled": enabled},
        )
        manager.dialog_data["at_time"] = tm.isoformat(timespec="minutes")
        await message.answer("Сохранил время напоминания.")
        await manager.switch_to(MoodSG.settings)
    except Exception as e:
        log.error("mood_schedule_failed", error=str(e))
        await message.answer("Не удалось сохранить настройки напоминаний.")


async def settings_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    enabled = dialog_manager.dialog_data.get("enabled", True)
    at_time = dialog_manager.dialog_data.get("at_time") or "18:00"
    event = dialog_manager.event
    if isinstance(event, (Message, CallbackQuery)):
        try:
            user_id = await ensure_user_id(event)
            schedules = await runtime().api.get(f"/schedule/{user_id}")
            item = next((x for x in schedules if x.get("schedule_key") == "mood_tracker"), None) or {}
            enabled = bool(item.get("enabled", enabled))
            tm = (item.get("at_time") or "").strip()
            if tm:
                at_time = tm[:5]
            dialog_manager.dialog_data["enabled"] = enabled
            dialog_manager.dialog_data["at_time"] = at_time
        except Exception:
            pass
    return {"enabled": "включены" if enabled else "выключены", "at_time": at_time}


mood_dialog = Dialog(
    Window(
        Format("Трекер настроения\n\nПоследняя оценка (в этом сеансе): {last_score}"),
        Button(Const("Заполнить за сегодня"), id="fill", on_click=on_fill_today_clicked),
        SwitchTo(Const("История"), id="hist", state=MoodSG.history_list),
        SwitchTo(Const("Недельная аналитика"), id="w", state=MoodSG.weekly),
        SwitchTo(Const("Месячная аналитика"), id="m", state=MoodSG.monthly),
        Button(Const("Настройки напоминаний"), id="settings", on_click=on_settings_clicked),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        getter=menu_getter,
        state=MoodSG.menu,
    ),
    Window(
        Const("Оцените настроение от 0 до 10 (0 — совсем плохо, 10 — отлично):"),
        MessageInput(on_score_message),
        Button(Const("В меню"), id="menu2", on_click=on_to_menu_clicked),
        state=MoodSG.q_score,
    ),
    Window(
        Const("Какие события повлияли на состояние? (Можно коротко)"),
        MessageInput(on_notes_message),
        Button(Const("В меню"), id="menu3", on_click=on_to_menu_clicked),
        state=MoodSG.q_notes,
    ),
    Window(
        Const("Что вызвало спад? Перечислите через запятую (или напишите «нет»)."),
        MessageInput(on_down_message),
        Button(Const("В меню"), id="menu4", on_click=on_to_menu_clicked),
        state=MoodSG.q_down,
    ),
    Window(
        Const("Что помогало и поддерживало? Перечислите через запятую (или напишите «нет»)."),
        MessageInput(on_up_message),
        Button(Const("В меню"), id="menu5", on_click=on_to_menu_clicked),
        state=MoodSG.q_up,
    ),
    Window(
        Const("История (последние 30 записей):"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="h",
                item_id_getter=lambda item: item[0],
                items="items",
                on_click=on_pick_entry,
            ),
            id="h_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back_menu", state=MoodSG.menu),
        getter=history_getter,
        state=MoodSG.history_list,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад к списку"), id="back_list", state=MoodSG.history_list),
        SwitchTo(Const("В меню"), id="back_menu2", state=MoodSG.menu),
        getter=history_view_getter,
        state=MoodSG.history_view,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back_menu3", state=MoodSG.menu),
        getter=weekly_getter,
        state=MoodSG.weekly,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back_menu4", state=MoodSG.menu),
        getter=monthly_getter,
        state=MoodSG.monthly,
    ),
    Window(
        Format("Настройки напоминаний\n\nСтатус: {enabled}\nВремя: {at_time}\n\nЧтобы изменить время, напишите его в формате HH:MM."),
        Button(Const("Изменить время"), id="set_time", on_click=on_set_time_clicked),
        Button(Const("Включить"), id="en", on_click=on_enable_clicked),
        Button(Const("Выключить"), id="dis", on_click=on_disable_clicked),
        SwitchTo(Const("Назад"), id="back_menu5", state=MoodSG.menu),
        getter=settings_getter,
        state=MoodSG.settings,
    ),
    Window(
        Const("Введите время в формате HH:MM (например 18:00):"),
        MessageInput(on_time_message),
        SwitchTo(Const("Назад"), id="back_settings", state=MoodSG.settings),
        state=MoodSG.set_time,
    ),
)
