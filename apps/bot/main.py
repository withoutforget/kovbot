from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.token import TokenValidationError
from aiogram_dialog import setup_dialogs

from kov.config import load_config
from kov.logging import configure_logging, get_logger
from kov.tg.dialogs.kb import kb_dialog
from kov.tg.dialogs.menu import main_menu_dialog
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

    dp = Dispatcher(storage=MemoryStorage())
    init_runtime(api_base_url=config.telegram.api_base_url)
    dp.include_router(tg_router)
    dp.include_router(main_menu_dialog)
    dp.include_router(kb_dialog)
    setup_dialogs(dp)
    log.info("starting_bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
