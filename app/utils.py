"""Вспомогательные утилиты интерфейса бота."""
from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

from aiogram.types import Message, ReactionTypeEmoji

from app.core import llm


async def react(message: Message, emoji: str) -> None:
    """Ставит реакцию-эмодзи на сообщение (метка «получил/прослушал»). Ошибки глушим."""
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except Exception:
        pass


async def parse_weight(text: str) -> float | None:
    """Понимает вес: числом из текста, иначе через LLM (для голоса и слов)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if m:
        return float(m.group(1).replace(",", "."))
    return await llm.extract_weight(text)


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
