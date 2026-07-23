"""Склейка нескольких сообщений подряд (дебаунс), чтобы обрабатывать их вместе.

Пользователь часто шлёт 2–3 сообщения (в т.ч. голосовых) подряд. Без склейки они
обрабатываются по отдельности и вызывают гонки/задвоение (особенно в интервью).
Здесь мы копим текст по ключу (чат+пользователь) и запускаем обработку один раз —
через DELAY секунд после последнего сообщения.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

DELAY = 3.0  # сколько ждём новых сообщений перед обработкой

_buffers: dict[str, list[str]] = {}
_tasks: dict[str, asyncio.Task] = {}


async def push(key: str, text: str, flush: Callable[[str], Awaitable[None]]) -> None:
    """Добавляет текст в буфер и (пере)запускает таймер обработки."""
    _buffers.setdefault(key, []).append(text)
    old = _tasks.get(key)
    if old and not old.done():
        old.cancel()
    _tasks[key] = asyncio.create_task(_run(key, flush))


async def _run(key: str, flush: Callable[[str], Awaitable[None]]) -> None:
    try:
        await asyncio.sleep(DELAY)
    except asyncio.CancelledError:
        return  # пришло новое сообщение — этот таймер отменён
    texts = _buffers.pop(key, [])
    _tasks.pop(key, None)
    if texts:
        # flush выполняется вне пайплайна aiogram — ловим ошибки сами, иначе они теряются молча
        try:
            await flush("\n".join(texts))
        except Exception:
            logger.exception("Ошибка обработки склеенных сообщений (key=%s)", key)
