"""Голосовые сообщения: транскрипция и маршрутизация по текущему состоянию."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import llm
from app.handlers import chat as chat_handlers
from app.handlers import start as start_handlers
from app.states import Onboarding

router = Router()


@router.message(F.voice | F.audio)
async def on_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    """Скачиваем голос, распознаём и передаём текст в нужный обработчик."""
    voice = message.voice or message.audio
    buf = await bot.download(voice.file_id)
    text = await llm.transcribe(buf.read(), filename="voice.ogg")
    if not text:
        await message.answer("Не разобрал голосовое, повтори текстом, пожалуйста.")
        return

    # Показываем распознанное, чтобы пользователь видел, что понято
    await message.answer(f"🗣 «{text}»")

    current = await state.get_state()
    if current == Onboarding.interview.state:
        await start_handlers.handle_interview(message, state, text)
    elif current == Onboarding.waiting_weight.state:
        await start_handlers.handle_weight(message, state, text)
    else:
        await chat_handlers.handle_chat(message, state, text)
