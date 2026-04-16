from __future__ import annotations

import asyncio

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from kov.config import load_config
from kov.db.session import create_engine_and_sessionmaker
from kov.logging import configure_logging, get_logger
from kov.scheduler.reminders import ReminderScheduler


async def main() -> None:
    config = load_config()
    configure_logging(config.logging.level)
    log = get_logger(component="worker")
    engine, sessionmaker = create_engine_and_sessionmaker(config.postgres.dsn)
    bot = Bot(token=config.telegram.bot_token) if config.telegram.bot_token else None
    scheduler = AsyncIOScheduler(timezone="UTC")
    if bot:
        reminder = ReminderScheduler(sessionmaker=sessionmaker, bot=bot)
        reminder.register(scheduler)
        scheduler.start()
        log.info("worker_started")
    else:
        log.warning("telegram_token_missing_worker_reminders_disabled", env=config.env)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if bot:
            await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
