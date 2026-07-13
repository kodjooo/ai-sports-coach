"""Свободный чат с тренером (персональный промпт) и запись веса текстом."""
from __future__ import annotations

import re
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import context as ctx
from app.core import llm, vector
from app.core import repository as repo
from app.core.db import async_session
from app.utils import parse_weight, typing

router = Router()


async def handle_chat(message: Message, state: FSMContext, text: str) -> None:
    """Обработка свободного сообщения (текст или расшифрованный голос)."""
    text = text.strip()
    data = await state.get_data()

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return

        # Режим ожидания веса (после кнопки «Записать вес»)
        if data.get("expect_weight"):
            async with typing(message):
                weight = await parse_weight(text)
            if weight is None:
                await message.answer("Не уловил вес. Напиши, например «81.3».")
                return
            await repo.log_weight(db, user.id, weight)
            await state.update_data(expect_weight=False)
            await message.answer(f"Записал вес — {weight:g} кг ⚖️")
            return

        # Одинокое число (например, ответ на недельный вопрос о весе) → запись веса
        if re.fullmatch(r"\d{2,3}([.,]\d)?\s*(кг|kg)?", text):
            weight = float(re.sub(r"[^\d.,]", "", text).replace(",", "."))
            await repo.log_weight(db, user.id, weight)
            await message.answer(f"Записал вес — {weight:g} кг ⚖️")
            return

        # Свободный вопрос тренеру с персональным системным промптом
        facts, memory = await ctx.build_context(db, user.id, text)
        prompt = ctx.chat_prompt(facts, memory, text)
        async with typing(message):
            answer = await llm.chat(prompt, system_prompt=user.system_prompt)

    # Реплику пользователя сохраняем в память как заметку
    await vector.add_memory(
        user.id, f"note-{message.message_id}", text, {"type": "user_note", "date": str(date.today())}
    )
    await message.answer(answer)


@router.message(F.text & ~F.text.startswith("/"))
async def free_chat(message: Message, state: FSMContext) -> None:
    await handle_chat(message, state, message.text)
