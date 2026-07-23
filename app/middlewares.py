"""Middleware: логирование входящих/исходящих сообщений и троттлинг от спама."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Message, TelegramObject

from app import dialoglog


class ThrottleMiddleware(BaseMiddleware):
    """Ограничение частоты действий на пользователя — защита от выжигания бюджета OpenAI.

    Покрывает и сообщения, и нажатия кнопок. Не более LIMIT действий за WINDOW секунд;
    сверх лимита действие игнорируется, один раз за окно предупреждаем пользователя.
    """

    LIMIT = 20
    WINDOW = 60.0
    _MAX_USERS = 5000  # backstop от неограниченного роста словарей

    def __init__(self) -> None:
        self._hits: dict[int, list[float]] = {}
        self._warned: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uid = event.from_user.id if isinstance(event, (Message, CallbackQuery)) and event.from_user else None
        if uid is not None:
            now = time.monotonic()
            if len(self._hits) > self._MAX_USERS:  # редкая уборка
                self._hits.clear()
                self._warned.clear()
            hits = [t for t in self._hits.get(uid, []) if now - t < self.WINDOW]
            if len(hits) >= self.LIMIT:
                self._hits[uid] = hits
                if now - self._warned.get(uid, 0) > self.WINDOW:
                    self._warned[uid] = now
                    try:
                        if isinstance(event, CallbackQuery):
                            await event.answer("Слишком часто 🙂 Секунду.", show_alert=False)
                        else:
                            await event.answer("Слишком часто 🙂 Дай мне секунду и продолжим.")
                    except Exception:
                        pass
                return  # не пускаем в обработчик
            hits.append(now)
            self._hits[uid] = hits
        return await handler(event, data)


class IncomingLogMiddleware(BaseMiddleware):
    """Логирует входящие текстовые сообщения (голос логируется после расшифровки)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text and event.from_user:
            dialoglog.log_in(event.from_user.id, event.text)
        return await handler(event, data)


class OutgoingLogMiddleware(BaseRequestMiddleware):
    """Логирует исходящие сообщения бота (ответы)."""

    async def __call__(self, make_request, bot, method: TelegramMethod) -> Any:
        if isinstance(method, SendMessage):
            dialoglog.log_out(method.chat_id, method.text)
        return await make_request(bot, method)
