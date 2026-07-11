"""Точка входа: миграции, сид, планировщик, запуск бота (long polling)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from alembic import command
from alembic.config import Config

from app.config import settings
from app.core.db import async_session
from app.core.seed import seed_exercises
from app.handlers import get_root_router
from app.scheduler.reminders import setup_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Применяем миграции Alembic до старта бота."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


async def prepare_data() -> None:
    """Наполняем справочник упражнений."""
    async with async_session() as db:
        await seed_exercises(db)


async def main() -> None:
    await prepare_data()

    bot = Bot(
        token=settings.tg_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(get_root_router())

    scheduler = setup_scheduler(bot)
    scheduler.start()

    logger.info("Бот запущен (long polling)")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    # Миграции выполняем синхронно до старта event loop (env.py сам поднимает loop)
    run_migrations()
    asyncio.run(main())
