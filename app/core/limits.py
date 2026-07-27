"""Лимиты дорогих LLM-действий: триал для новичков, суточные лимиты, глобальный
предохранитель по стоимости и байпас для админов.

- Дешёвый/кнопочный функционал (тренировки, дневник, GIF, статистика) НЕ ограничивается —
  лимиты только для дорогих вызовов (фото еды, чат).
- Счётчики в Redis: суточный ключ с TTL и пожизненный триал-ключ.
- При недоступности Redis — «fail open» (пропускаем), чтобы инфра-сбой не ломал бота;
  бюджет при этом всё равно прикрыт глобальным предохранителем (in-memory в usage.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import settings
from app.core import usage

logger = logging.getLogger(__name__)

# action -> (лимит триала суммарно, суточный лимит после активации)
_LIMITS = {
    "food": (settings.limit_food_trial, settings.limit_food_daily),
    "chat": (settings.limit_chat_trial, settings.limit_chat_daily),
}

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


def fuse_state() -> str:
    """Состояние глобального предохранителя: 'ok' | 'soft' | 'hard'."""
    spent = usage.spent_today_usd()
    if spent >= settings.daily_cost_hard_usd:
        return "hard"
    if spent >= settings.daily_cost_soft_usd:
        return "soft"
    return "ok"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def check_and_consume(tg_id: int, action: str, activated: bool) -> tuple[bool, str | None]:
    """Проверяет и списывает единицу лимита для дорогого действия.

    Возвращает (разрешено, причина_отказа|None). Причины: 'fuse' (предохранитель),
    'quota' (исчерпан триал/суточный лимит). Админы — всегда разрешено, без списания.
    """
    if is_admin(tg_id):
        return True, None

    # Глобальный предохранитель: при хард-пороге дорогие LLM-функции временно выключены.
    if fuse_state() == "hard":
        logger.warning("[LIMITS] предохранитель HARD ($%.2f) — отказ %s для %s",
                       usage.spent_today_usd(), action, tg_id)
        return False, "fuse"

    trial_limit, daily_limit = _LIMITS.get(action, (10, 15))
    try:
        r = _client()
        if activated:
            key = f"lim:{tg_id}:{action}:{_today()}"
            new = await r.incr(key)
            if new == 1:
                await r.expire(key, 172800)  # 2 суток, чтобы точно пережить смену дня
            limit = daily_limit
        else:
            key = f"trial:{tg_id}:{action}"
            new = await r.incr(key)
            limit = trial_limit
        if new > limit:
            await r.decr(key)  # не копим заблокированные попытки
            return False, "quota"
        return True, None
    except Exception as exc:
        logger.warning("[LIMITS] Redis недоступен (%s) — пропускаю без списания", exc)
        return True, None


def deny_message(reason: str | None, action: str) -> str:
    """Дружелюбное сообщение при отказе."""
    if reason == "fuse":
        return (
            "Сервис сейчас под высокой нагрузкой — умные функции (распознавание еды и чат) "
            "ненадолго на паузе и вернутся позже сегодня. Тренировки, дневник и статистика "
            "работают как обычно 💪"
        )
    # quota
    what = "распознаваний еды" if action == "food" else "сообщений тренеру"
    return (
        f"На сегодня лимит {what} исчерпан 🙂 Он обнулится завтра.\n"
        "Хочешь больше уже сейчас — пригласи друга (скоро добавим кнопку), "
        "а пока доступны тренировки, дневник и статистика."
    )
