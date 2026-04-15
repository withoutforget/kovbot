from __future__ import annotations

import asyncio

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
    scheduler = AsyncIOScheduler(timezone="UTC")
    reminder = ReminderScheduler(sessionmaker=sessionmaker)
    reminder.register(scheduler)
    scheduler.start()
    log.info("worker_started")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

