from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kov.db.models import ReminderEvent, User, UserSchedule
from kov.logging import get_logger


class ReminderScheduler:
    def __init__(self, *, sessionmaker: async_sessionmaker[AsyncSession], bot: Bot):
        self.sessionmaker = sessionmaker
        self.bot = bot
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
            due_items: list[tuple[UserSchedule, User]] = []
            changed = False
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
                due_items.append((sched, user))
                changed = True
                self.log.info(
                    "reminder_due",
                    user_id=str(sched.user_id),
                    schedule_key=sched.schedule_key,
                    at_time=str(sched.at_time),
                    timezone=user.timezone,
                )
                session.add(
                    ReminderEvent(
                        id=uuid.uuid4(),
                        user_id=sched.user_id,
                        schedule_key=sched.schedule_key,
                        asked_at=now_utc,
                        answered_at=None,
                        status="asked",
                        meta={"timezone": user.timezone or "UTC", "at_time": str(sched.at_time)},
                    )
                )
            if changed:
                await session.commit()

        # Mark missed (best-effort) in a separate pass
        grace = timedelta(hours=6)
        async with self.sessionmaker() as session:
            missed_res = await session.execute(
                select(ReminderEvent)
                .where(ReminderEvent.status == "asked")
                .where(ReminderEvent.asked_at <= (now_utc - grace))
                .limit(500)
            )
            events = missed_res.scalars().all()
            if events:
                for ev in events:
                    ev.status = "missed"
                await session.commit()

        # send notifications outside of DB transaction
        for sched, user in due_items:
            try:
                chat_id = int(user.telegram_user_id)
            except Exception:
                self.log.warning("reminder_bad_chat_id", telegram_user_id=user.telegram_user_id)
                continue
            if sched.schedule_key == "mood_tracker":
                text = "Напоминание: заполнить трекер настроения.\n\nОткройте бота и выберите «Трекер настроения»."
            elif sched.schedule_key == "habit_tracker":
                text = "Напоминание: отметить привычки за сегодня.\n\nОткройте бота и выберите «Трекер привычек»."
            else:
                text = f"Напоминание: {sched.schedule_key}"
            try:
                await self.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                self.log.error(
                    "reminder_send_failed",
                    error=str(e),
                    telegram_user_id=user.telegram_user_id,
                    schedule_key=sched.schedule_key,
                )
