"""Вспомогательные утилиты интерфейса бота."""
from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

from aiogram.types import Message

from app.core import llm


def local_today():
    """Сегодняшняя дата в часовом поясе бота (не UTC контейнера)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.config import settings
    return datetime.now(ZoneInfo(settings.tz)).date()


# Разумный диапазон веса тела (кг) — отсекаем опечатки/случайные числа
WEIGHT_MIN, WEIGHT_MAX = 30.0, 300.0


def valid_weight(w: float | None) -> float | None:
    """Возвращает вес, если он в разумном диапазоне, иначе None."""
    if w is None:
        return None
    return w if WEIGHT_MIN <= w <= WEIGHT_MAX else None


async def parse_weight(text: str) -> float | None:
    """Понимает вес: числом из текста, иначе через LLM. Отсекает нереалистичные значения."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if m:
        return valid_weight(float(m.group(1).replace(",", ".")))
    return valid_weight(await llm.extract_weight(text))


@asynccontextmanager
async def typing(message: Message):
    """Показывает статус «печатает…» всё время, пока готовится ответ."""

    async def _loop() -> None:
        try:
            while True:
                await message.bot.send_chat_action(message.chat.id, "typing")
                await asyncio.sleep(4)  # статус в Telegram живёт ~5 c, обновляем заранее
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
