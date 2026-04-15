from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from kov.config import load_config
from kov.logging import configure_logging, get_logger
from kov.tg.handlers import register_handlers


async def main() -> None:
    config = load_config()
    configure_logging(config.logging.level)
    log = get_logger(component="bot")
    if not config.telegram.bot_token:
        log.warning("telegram_token_missing")
    bot = Bot(token=config.telegram.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp, api_base_url=config.telegram.api_base_url)
    log.info("starting_bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
