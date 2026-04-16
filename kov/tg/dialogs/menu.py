from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.tg.dialogs.states import (
    DataSG,
    ExportSG,
    HabitsSG,
    InterviewSG,
    KnowledgeBaseSG,
    MainMenuSG,
    MoodSG,
    ReportsSG,
    SupportChatSG,
    TechniquesSG,
)
from kov.tg.runtime import ensure_user_id, runtime

from kov.tg.dialogs.common import profile_get
from kov.tg.dialogs.common import profile_merge


async def _start(manager: DialogManager, state) -> None:
    await manager.start(state, mode=StartMode.RESET_STACK)


async def on_scenarios_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(MainMenuSG.scenarios)


async def on_reports_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(ReportsSG.list, mode=StartMode.RESET_STACK)


async def on_data_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, DataSG.menu)


async def on_reminders_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(MainMenuSG.reminders)


async def on_kb_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, KnowledgeBaseSG.chat)


async def on_interview_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, InterviewSG.start)


async def on_mood_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, MoodSG.menu)


async def on_techniques_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, TechniquesSG.ask)


async def on_dialog_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(SupportChatSG.chat, mode=StartMode.RESET_STACK, data={"scenario_key": "dialog"})


async def on_relationships_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(
        SupportChatSG.chat,
        mode=StartMode.RESET_STACK,
        data={"scenario_key": "relationships"},
    )


async def on_habits_clicked(_, __, manager: DialogManager) -> None:
    await _start(manager, HabitsSG.menu)


async def scenarios_getter(dialog_manager: DialogManager, **_) -> dict:
    try:
        if isinstance(dialog_manager.event, (Message, CallbackQuery)):
            await ensure_user_id(dialog_manager.event)
    except Exception:
        pass
    scenarios = await runtime().api.get("/scenarios")
    enabled = [s for s in scenarios if s.get("enabled")]
    items = [(s.get("key") or "", s.get("title") or "", s.get("description") or "") for s in enabled]
    return {"items": items}


async def on_pick_scenario(callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str) -> None:
    key = item_id
    try:
        await profile_merge(callback, data={"last_scenario": key})
    except Exception:
        pass
    if key == "interview":
        await _start(manager, InterviewSG.start)
    elif key == "mood_tracker":
        await _start(manager, MoodSG.menu)
    elif key == "habit_tracker":
        await _start(manager, HabitsSG.menu)
    elif key == "techniques":
        await _start(manager, TechniquesSG.ask)
    elif key in ("dialog", "relationships"):
        await manager.start(SupportChatSG.chat, mode=StartMode.RESET_STACK, data={"scenario_key": key})
    else:
        await callback.answer("Сценарий есть в API, но UI ещё не реализован", show_alert=True)
        return
    await callback.answer()


async def on_timezone_clicked(_, __, manager: DialogManager) -> None:
    await manager.switch_to(MainMenuSG.timezone)


async def on_continue_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    data = await profile_get(callback)
    key = data.get("last_scenario")
    if not key:
        # fallback: если профиль по какой-то причине пуст, попробуем продолжить последний диалог
        try:
            user_id = await ensure_user_id(callback)
            dialogs = await runtime().api.get(f"/dialog/list/{user_id}")
            if dialogs:
                key = dialogs[0].get("scenario_key") or "dialog"
        except Exception:
            key = None
    if not key:
        await callback.answer("Нет незавершённого сценария", show_alert=True)
        return
    if key == "interview":
        await _start(manager, InterviewSG.start)
    elif key == "mood_tracker":
        await _start(manager, MoodSG.menu)
    elif key == "techniques":
        await _start(manager, TechniquesSG.ask)
    elif key in ("dialog", "relationships"):
        await manager.start(SupportChatSG.chat, mode=StartMode.RESET_STACK, data={"scenario_key": key})
    elif key == "habit_tracker":
        await _start(manager, HabitsSG.menu)
    elif key == "knowledge_base":
        await _start(manager, KnowledgeBaseSG.chat)
    else:
        await callback.answer("Не знаю, как продолжить этот сценарий", show_alert=True)


async def on_timezone_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    tz = (message.text or "").strip()
    if not tz:
        return
    try:
        ZoneInfo(tz)
    except Exception:
        await message.answer("Не похоже на IANA timezone. Пример: Europe/Moscow или America/New_York.")
        return
    await ensure_user_id(message, timezone=tz)
    await message.answer(f"Сохранил часовой пояс: {tz}")
    await manager.switch_to(MainMenuSG.menu)


main_menu_dialog = Dialog(
    Window(
        Const(
            "Кора — ассистент психологической поддержки.\n"
            "Внутри: интервью для профиля, трекеры, техники, диалоги и база знаний.\n\n"
            "Выберите раздел:"
        ),
        Button(Const("Продолжить"), id="continue", on_click=on_continue_clicked),
        Button(Const("Сценарии"), id="scenarios", on_click=on_scenarios_clicked),
        Button(Const("Отчёты и аналитика"), id="reports", on_click=on_reports_clicked),
        Button(Const("Мои данные"), id="data", on_click=on_data_clicked),
        Button(Const("Напоминания"), id="reminders", on_click=on_reminders_clicked),
        Button(Const("Часовой пояс"), id="tz", on_click=on_timezone_clicked),
        state=MainMenuSG.menu,
    )
    ,
    Window(
        Const("Сценарии\n\nВыберите сценарий:"),
        ScrollingGroup(
            Select(
                Format("{item[1]} — {item[2]}"),
                id="sc",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_scenario,
            ),
            id="sc_g",
            width=1,
            height=8,
        ),
        Button(Const("Поиск по базе знаний (RAG)"), id="kb", on_click=on_kb_clicked),
        SwitchTo(Const("Назад"), id="back_menu", state=MainMenuSG.menu),
        getter=scenarios_getter,
        state=MainMenuSG.scenarios,
    ),
    Window(
        Const(
            "Отчёты и аналитика\n\n"
            "Сейчас отчёты доступны внутри трекеров:\n"
            "• Трекер настроения → Недельная/Месячная\n"
            "• Трекер привычек → Недельная/Месячная"
        ),
        Button(Const("Открыть трекер настроения"), id="go_mood", on_click=on_mood_clicked),
        Button(Const("Открыть трекер привычек"), id="go_habits", on_click=on_habits_clicked),
        SwitchTo(Const("Назад"), id="back_menu2", state=MainMenuSG.menu),
        state=MainMenuSG.reports,
    ),
    Window(
        Const(
            "Напоминания\n\n"
            "Настройки напоминаний находятся внутри трекеров:\n"
            "• Трекер настроения → Настройки\n"
            "• Трекер привычек → Настройки"
        ),
        Button(Const("Настроить настроение"), id="rem_mood", on_click=on_mood_clicked),
        Button(Const("Настроить привычки"), id="rem_hab", on_click=on_habits_clicked),
        SwitchTo(Const("Назад"), id="back_menu3", state=MainMenuSG.menu),
        state=MainMenuSG.reminders,
    ),
    Window(
        Const(
            "Часовой пояс\n\n"
            "Введите ваш часовой пояс в формате IANA.\n"
            "Примеры: Europe/Moscow, Asia/Almaty, America/New_York"
        ),
        MessageInput(on_timezone_message),
        SwitchTo(Const("Назад"), id="back_menu4", state=MainMenuSG.menu),
        state=MainMenuSG.timezone,
    ),
)
