"""Точка входа: миграции, сид, планировщик, запуск бота (long polling)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent
from alembic import command
from alembic.config import Config

from app.config import settings
from app.core.db import async_session
from app.core.seed import seed_exercises
from app.handlers import get_root_router
from app.middlewares import IncomingLogMiddleware, OutgoingLogMiddleware, ThrottleMiddleware
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
    # Логирование переписки (если включено)
    bot.session.middleware(OutgoingLogMiddleware())

    # FSM в Redis — состояние диалога переживает перезапуск бота
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)
    dp.message.outer_middleware(ThrottleMiddleware())  # троттлинг раньше логирования/обработки
    dp.message.outer_middleware(IncomingLogMiddleware())
    dp.include_router(get_root_router())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        # Устаревшие callback после простоя бота — проглатываем без трейсбека
        if isinstance(event.exception, TelegramBadRequest) and "query is too old" in str(
            event.exception
        ):
            return True
        logger.exception("Необработанная ошибка: %s", event.exception)
        # Сообщаем пользователю, чтобы бот не «молчал» при сбое хендлера
        msg = getattr(event.update, "message", None) or getattr(
            getattr(event.update, "callback_query", None), "message", None
        )
        if msg is not None:
            try:
                await msg.answer("Ой, что-то пошло не так 😕 Попробуй ещё раз или напиши иначе.")
            except Exception:
                pass
        return True

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
