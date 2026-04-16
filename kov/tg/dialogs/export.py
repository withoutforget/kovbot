from __future__ import annotations

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, SwitchTo
from aiogram_dialog.widgets.text import Const

from kov.logging import get_logger
from kov.tg.dialogs.common import get_chat_id, json_file
from kov.tg.dialogs.states import ExportSG, MainMenuSG
from kov.tg.runtime import ensure_user_id, runtime


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def _get_message(manager: DialogManager) -> Message | None:
    event = manager.event
    if isinstance(event, Message):
        return event
    if isinstance(event, CallbackQuery):
        return event.message
    return None


async def on_export_clicked(_, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        event = manager.event
        if not isinstance(event, (Message, CallbackQuery)):
            return
        user_id = await ensure_user_id(event)
        data = await runtime().api.get(f"/export/{user_id}")
        doc = json_file(filename="kora_export.json", data=data)
        await msg.bot.send_document(chat_id=get_chat_id(manager), document=doc, caption="Экспорт данных")
    except Exception as e:
        log.error("export_failed", error=str(e))
        await msg.answer("Не удалось сделать экспорт. Проверь, что API доступен.")


async def _clear(msg: Message, *, path: str, payload: dict) -> bool:
    await runtime().api.post(path, payload)
    return True


async def on_clear_interview_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        user_id = await ensure_user_id(callback)
        await _clear(msg, path=f"/scenarios/interview/{user_id}/clear", payload={})
        await callback.answer("Интервью очищено")
    except Exception as e:
        log.error("clear_interview_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def on_clear_mood_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        user_id = await ensure_user_id(callback)
        await _clear(msg, path=f"/mood/clear/{user_id}", payload={})
        await callback.answer("Настроение очищено")
    except Exception as e:
        log.error("clear_mood_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def on_clear_habits_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        user_id = await ensure_user_id(callback)
        await _clear(msg, path=f"/habits/clear/{user_id}", payload={})
        await callback.answer("Привычки очищены")
    except Exception as e:
        log.error("clear_habits_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def on_clear_dialog_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        user_id = await ensure_user_id(callback)
        await runtime().api.post("/dialog/clear", {"user_id": user_id, "scenario_key": "dialog"})
        await callback.answer("Диалог очищен")
    except Exception as e:
        log.error("clear_dialog_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


async def on_clear_relationships_clicked(callback: CallbackQuery, __, manager: DialogManager) -> None:
    log = get_logger(component="tg_export")
    msg = await _get_message(manager)
    if not msg:
        return
    try:
        user_id = await ensure_user_id(callback)
        await runtime().api.post("/dialog/clear", {"user_id": user_id, "scenario_key": "relationships"})
        await callback.answer("Отношения очищены")
    except Exception as e:
        log.error("clear_relationships_failed", error=str(e))
        await callback.answer("Не удалось", show_alert=True)


export_dialog = Dialog(
    Window(
        Const(
            "Мои данные\n\n"
            "Можно выгрузить все данные в JSON или очистить отдельные разделы.\n"
            "Очистка необратима."
        ),
        Button(Const("Экспорт JSON"), id="export", on_click=on_export_clicked),
        Button(Const("Очистить интервью"), id="clr_i", on_click=on_clear_interview_clicked),
        Button(Const("Очистить трекер настроения"), id="clr_m", on_click=on_clear_mood_clicked),
        Button(Const("Очистить привычки"), id="clr_h", on_click=on_clear_habits_clicked),
        Button(Const("Очистить диалог"), id="clr_d", on_click=on_clear_dialog_clicked),
        Button(Const("Очистить отношения"), id="clr_r", on_click=on_clear_relationships_clicked),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        state=ExportSG.menu,
    )
)
