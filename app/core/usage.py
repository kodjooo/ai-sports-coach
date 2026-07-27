"""Учёт расхода OpenAI: логирует токены и оценку стоимости по каждому типу вызова.

Смотреть: docker compose logs bot | grep USAGE
Агрегировать примерно: grep USAGE | awk … или собрать по tag.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timezone, datetime
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("usage")
logger.setLevel(logging.INFO)

# Пишем расход в файл на volume — переживает пересборку контейнера.
_LOG_PATH = os.environ.get("USAGE_LOG", "/app/logs/usage.log")
try:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        _fh = RotatingFileHandler(_LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(_fh)
except Exception:
    pass

# Цены за 1M токенов (вход, выход). reasoning-токены тарифицируются как выход.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.0),
    "gpt-5.1": (1.25, 10.0),
    "gpt-5.6-luna": (1.0, 6.0),
    "gpt-5-mini": (0.125, 1.0),
    "gpt-5-nano": (0.05, 0.40),
}


def _cost(model: str, prompt: int, completion: int) -> float:
    inp, out = _PRICES.get(model, (1.25, 10.0))
    return prompt / 1_000_000 * inp + completion / 1_000_000 * out


# Глобальный счётчик стоимости за текущий день (в процессе). Служит предохранителем от
# «сжигания» бюджета всплеском трафика/абьюзом. Сбрасывается при смене даты (UTC).
_spend: dict[str, float] = {}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _add_spend(usd: float) -> None:
    k = _today_key()
    if k not in _spend:
        _spend.clear()  # новый день — забываем прошлые
        _spend[k] = 0.0
    _spend[k] += usd


def spent_today_usd() -> float:
    return _spend.get(_today_key(), 0.0)


async def complete(client, tag: str, **params):
    """Вызывает chat.completions.create и логирует расход по метке tag."""
    resp = await client.chat.completions.create(**params)
    try:
        u = resp.usage
        pt = getattr(u, "prompt_tokens", 0) or 0
        ct = getattr(u, "completion_tokens", 0) or 0
        details = getattr(u, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", 0) or 0
        model = params.get("model", "?")
        cost = _cost(model, pt, ct)
        _add_spend(cost)
        logger.info(
            "[USAGE] tag=%s model=%s in=%d out=%d reasoning=%d ~$%.4f день~$%.2f",
            tag, model, pt, ct, reasoning, cost, spent_today_usd(),
        )
    except Exception:
        pass
    return resp
