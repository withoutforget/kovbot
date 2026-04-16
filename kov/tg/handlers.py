from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from kov.tg.dialogs.states import MainMenuSG
from kov.tg.keyboards import main_reply_kb


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, dialog_manager: DialogManager) -> None:
    await message.answer(
        "Привет! Я Кора — ассистент психологической поддержки.\n"
        "Я умею: интервью для профиля, трекеры (настроение/привычки), техники и диалоги.\n\n"
        "Нажмите «Меню» снизу или используйте /menu.",
        reply_markup=main_reply_kb(),
    )
    await dialog_manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


@router.message(Command("menu"))
async def cmd_menu(message: Message, dialog_manager: DialogManager) -> None:
    await message.answer("Открываю меню.", reply_markup=main_reply_kb())
    await dialog_manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


@router.message(F.text.casefold() == "меню")
async def txt_menu(message: Message, dialog_manager: DialogManager) -> None:
    await message.answer("Открываю меню.", reply_markup=main_reply_kb())
    await dialog_manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Кора — ассистент психологической поддержки.\n\n"
        "Что внутри:\n"
        "• Интервью — базовые вопросы для персонализации\n"
        "• Трекер настроения — ежедневные записи + отчёты\n"
        "• Трекер привычек — список привычек + статистика\n"
        "• Техники — 2 упражнения по запросу\n"
        "• Диалог/Отношения — бережный чат\n"
        "• База знаний — поиск по документам (RAG)\n\n"
        "Чтобы открыть меню — нажмите «Меню» снизу или /menu.",
        reply_markup=main_reply_kb(),
    )
