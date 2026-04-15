from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kov.db.models import User, UserSchedule
from kov.logging import get_logger


class ReminderScheduler:
    def __init__(self, *, sessionmaker: async_sessionmaker[AsyncSession]):
        self.sessionmaker = sessionmaker
        self.log = get_logger(component="scheduler")

    def register(self, scheduler) -> None:
        scheduler.add_job(self.tick, "interval", minutes=1, id="reminders_tick", max_instances=1)

    async def tick(self) -> None:
        now_utc = datetime.now(tz=timezone.utc)
        async with self.sessionmaker() as session:
            res = await session.execute(
                select(UserSchedule, User).join(User, User.id == UserSchedule.user_id).where(UserSchedule.enabled.is_(True))
            )
            rows = res.all()
            due_items: list[UserSchedule] = []
            for sched, user in rows:
                try:
                    tz = ZoneInfo(user.timezone or "UTC")
                except Exception:
                    tz = timezone.utc
                now_local = now_utc.astimezone(tz)
                window_start = (now_local - timedelta(minutes=1)).time()
                window_end = now_local.time()
                if not (window_start <= sched.at_time <= window_end):
                    continue
                if sched.last_time_asked and sched.last_time_asked >= (now_utc - timedelta(hours=4)):
                    continue
                sched.last_time_asked = now_utc
                due_items.append(sched)
                self.log.info(
                    "reminder_due",
                    user_id=str(sched.user_id),
                    schedule_key=sched.schedule_key,
                    at_time=str(sched.at_time),
                    timezone=user.timezone,
                )
            if due_items:
                await session.commit()
