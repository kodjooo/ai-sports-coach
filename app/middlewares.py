"""Middleware для логирования входящих и исходящих сообщений."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Message, TelegramObject

from app import dialoglog


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
