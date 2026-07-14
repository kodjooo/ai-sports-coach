"""Голосовые сообщения: транскрипция и маршрутизация по текущему состоянию."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import debounce, dialoglog
from app.core import llm
from app.handlers import chat as chat_handlers
from app.handlers import environment as env_handlers
from app.handlers import start as start_handlers
from app.states import Onboarding
from app.utils import typing

router = Router()


@router.message(F.voice | F.audio)
async def on_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    """Скачиваем голос, распознаём и передаём текст в нужный обработчик."""
    voice = message.voice or message.audio
    async with typing(message):
        buf = await bot.download(voice.file_id)
        text = await llm.transcribe(buf.read(), filename="voice.ogg")
    if not text:
        await message.answer("Не разобрал голосовое, повтори текстом, пожалуйста.")
        return
    dialoglog.log_in(message.from_user.id, f"[голос] {text}")

    current = await state.get_state()
    key = f"{message.chat.id}:{message.from_user.id}"

    # Интервью и свободный чат — склеиваем несколько голосовых/сообщений подряд
    if current == Onboarding.interview.state:
        async def flush(t: str) -> None:
            await start_handlers.handle_interview(message, state, t)
        await debounce.push(key, text, flush)
    elif current == Onboarding.equipment.state:
        await env_handlers.handle_equipment(message, state, text)
    elif current == Onboarding.waiting_weight.state:
        await start_handlers.handle_weight(message, state, text)
    elif current == Onboarding.waiting_height.state:
        await start_handlers.handle_height(message, state, text)
    else:
        async def flush_chat(t: str) -> None:
            await chat_handlers.handle_chat(message, state, t)
        await debounce.push(key, text, flush_chat)
