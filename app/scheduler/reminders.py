"""APScheduler: утренние напоминания в день тренировки и недельный отчёт."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import settings
from app.core import progress
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import User
from app.keyboards import reminder_kb

logger = logging.getLogger(__name__)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


async def _morning_reminder(bot: Bot) -> None:
    """Шлём напоминание тем, у кого сегодня есть тренировка по плану."""
    weekday = date.today().weekday()
    async with async_session() as db:
        res = await db.execute(select(User))
        users = list(res.scalars().all())
        for user in users:
            template = await repo.get_template_for_weekday(db, user.id, weekday)
            if template is None:
                continue
            items = await repo.list_template_items(db, template.id)
            names = []
            for it in items:
                ex = await repo.get_exercise(db, it.exercise_id)
                if ex:
                    names.append(ex.name)
            text = (
                f"Доброе утро! Сегодня <b>{template.label}</b>: "
                f"{', '.join(names)}. Начнём?"
            )
            try:
                await bot.send_message(user.tg_id, text, reply_markup=reminder_kb())
            except Exception as exc:
                logger.warning("Не удалось отправить напоминание %s: %s", user.tg_id, exc)


async def _weekly_report(bot: Bot) -> None:
    """Раз в неделю шлём сводку прогресса."""
    async with async_session() as db:
        res = await db.execute(select(User))
        users = list(res.scalars().all())
        for user in users:
            report = await progress.weekly_report(db, user.id)
            try:
                await bot.send_message(user.tg_id, "📈 <b>Итоги недели</b>\n" + report)
            except Exception as exc:
                logger.warning("Не удалось отправить отчёт %s: %s", user.tg_id, exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    # Утреннее напоминание каждый день; внутри отфильтруем по расписанию пользователя
    scheduler.add_job(
        _morning_reminder,
        CronTrigger(hour=settings.reminder_hour, minute=settings.reminder_minute),
        args=[bot],
    )
    # Недельный отчёт — воскресенье вечером
    scheduler.add_job(_weekly_report, CronTrigger(day_of_week="sun", hour=20, minute=0), args=[bot])
    return scheduler
