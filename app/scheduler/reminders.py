"""APScheduler: персональные напоминания (за 30 мин и в старт) и недельный отчёт с весом."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

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


def _now_hm() -> tuple[int, int]:
    """Текущее время в часовом поясе бота (часы, минуты, округлённые до 5)."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.tz))
    return now.hour, (now.minute // 5) * 5


async def _training_today(db, user, today):
    """Есть ли тренировка сегодня и по какому шаблону.

    Учитывает перенос: явно запланированная сессия на сегодня → тренировка есть;
    плановый день недели → есть, если сессию с этого дня не перенесли (moved).
    """
    weekday = today.weekday()
    tpl = await repo.get_template_for_weekday(db, user.id, weekday)
    planned = await repo.planned_session_on(db, user.id, today)
    if planned:
        ptpl = await repo.get_template(db, planned.template_id) if planned.template_id else None
        return True, (ptpl or tpl)
    if tpl and not await repo.has_session_status_on(db, user.id, today, "moved"):
        return True, tpl
    return False, None


async def _tick(bot: Bot) -> None:
    """Раз в 5 минут проверяем, кому пора напомнить о тренировке."""
    hour, minute = _now_hm()
    today = date.today()
    async with async_session() as db:
        res = await db.execute(select(User))
        users = list(res.scalars().all())
        for user in users:
            if user.train_hour is None:
                continue
            train_today, template = await _training_today(db, user, today)
            if not train_today or template is None:
                continue

            start_dt = datetime(2000, 1, 1, user.train_hour, user.train_minute or 0)
            pre_dt = start_dt - timedelta(minutes=30)

            text = None
            if (hour, minute) == (start_dt.hour, start_dt.minute):
                names = await _exercise_names(db, template.id)
                text = f"Время тренировки! Сегодня <b>{template.label}</b>: {names}. Начнём?"
            elif (hour, minute) == (pre_dt.hour, pre_dt.minute):
                text = f"Через 30 минут тренировка (<b>{template.label}</b>). Готовься 💪"

            if text:
                try:
                    await bot.send_message(user.tg_id, text, reply_markup=reminder_kb())
                except Exception as exc:
                    logger.warning("Не удалось отправить напоминание %s: %s", user.tg_id, exc)


async def _exercise_names(db, template_id: int) -> str:
    items = await repo.list_template_items(db, template_id)
    names = []
    for it in items:
        ex = await repo.get_exercise(db, it.exercise_id)
        if ex:
            names.append(ex.name)
    return ", ".join(names)


async def _weekly_report(bot: Bot) -> None:
    """Недельная сводка + просьба обновить вес."""
    async with async_session() as db:
        res = await db.execute(select(User))
        users = list(res.scalars().all())
        for user in users:
            report = await progress.weekly_report(db, user.id)
            # Короткий вывод тренера по данным недели
            takeaway = await llm.chat(
                f"Данные клиента за неделю:\n{report}\n\n"
                "Дай 1–2 предложения вывода и один конкретный совет на следующую неделю.",
                system_prompt=user.system_prompt,
            )
            body = "📈 <b>Итоги недели</b>\n" + report
            if takeaway:
                body += "\n\n💬 " + takeaway
            body += "\n\nНапиши текущий вес числом, чтобы я отслеживал динамику."
            try:
                await bot.send_message(user.tg_id, body)
            except Exception as exc:
                logger.warning("Не удалось отправить отчёт %s: %s", user.tg_id, exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    # Тик каждые 5 минут — проверка персональных напоминаний
    scheduler.add_job(_tick, CronTrigger(minute="*/5"), args=[bot])
    # Недельный отчёт — воскресенье вечером
    scheduler.add_job(_weekly_report, CronTrigger(day_of_week="sun", hour=20, minute=0), args=[bot])
    return scheduler
