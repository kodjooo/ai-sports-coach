"""Свободный чат с тренером и запись веса текстом."""
from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import context as ctx
from app.core import llm, vector
from app.core import repository as repo
from app.core.db import async_session

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def free_chat(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return

        # Режим ожидания веса (после кнопки «Записать вес»)
        if data.get("expect_weight"):
            raw = text.replace(",", ".")
            try:
                weight = float(raw)
            except ValueError:
                await message.answer("Не похоже на число. Напиши вес, например 81.3")
                return
            await repo.log_weight(db, user.id, weight)
            await state.update_data(expect_weight=False)
            await message.answer(f"Записал вес {weight} кг ⚖️")
            return

        # Свободный вопрос тренеру
        facts, memory = await ctx.build_context(db, user.id, text)
        prompt = ctx.chat_prompt(facts, memory, text)
        answer = await llm.chat(prompt)

    # Реплику пользователя сохраняем в память как заметку
    await vector.add_memory(
        user.id, f"note-{message.message_id}", text, {"type": "user_note", "date": str(date.today())}
    )
    await message.answer(answer)
