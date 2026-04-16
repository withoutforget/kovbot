from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.types import MenuButtonCommands
from aiogram.utils.token import TokenValidationError
from aiogram_dialog import setup_dialogs

from kov.config import load_config
from kov.logging import configure_logging, get_logger
from kov.tg.dialogs.export import export_dialog
from kov.tg.dialogs.habits import habits_dialog
from kov.tg.dialogs.interview import interview_dialog
from kov.tg.dialogs.kb import kb_dialog
from kov.tg.dialogs.data import data_dialog
from kov.tg.dialogs.menu import main_menu_dialog
from kov.tg.dialogs.mood import mood_dialog
from kov.tg.dialogs.reports import reports_dialog
from kov.tg.dialogs.support_chat import support_chat_dialog
from kov.tg.dialogs.techniques import techniques_dialog
from kov.tg.handlers import router as tg_router
from kov.tg.runtime import init_runtime


async def main() -> None:
    config = load_config()
    configure_logging(config.logging.level)
    log = get_logger(component="bot")
    if not config.telegram.bot_token:
        log.warning("telegram_token_missing_bot_disabled", env=config.env)
        await asyncio.Event().wait()

    try:
        bot = Bot(token=config.telegram.bot_token)
    except TokenValidationError:
        log.warning("telegram_token_invalid_bot_disabled", env=config.env)
        await asyncio.Event().wait()

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Запуск и главное меню"),
                BotCommand(command="menu", description="Открыть меню"),
                BotCommand(command="help", description="Что умеет бот"),
            ]
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        log.warning("telegram_commands_setup_failed", error=str(e))

    dp = Dispatcher(storage=MemoryStorage())
    init_runtime(api_base_url=config.telegram.api_base_url)
    dp.include_router(tg_router)
    dp.include_router(main_menu_dialog)
    dp.include_router(kb_dialog)
    dp.include_router(interview_dialog)
    dp.include_router(mood_dialog)
    dp.include_router(techniques_dialog)
    dp.include_router(support_chat_dialog)
    dp.include_router(habits_dialog)
    dp.include_router(export_dialog)
    dp.include_router(reports_dialog)
    dp.include_router(data_dialog)
    setup_dialogs(dp)
    log.info("starting_bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
