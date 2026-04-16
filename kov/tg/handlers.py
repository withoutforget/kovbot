from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from kov.tg.dialogs.states import MainMenuSG


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)

