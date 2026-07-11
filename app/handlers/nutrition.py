"""Фаза 3 — учёт питания: фото блюда + вес → оценка калорийности (GPT-4 Vision)."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import llm
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import Meal
from app.states import Nutrition

router = Router()


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    """Пользователь прислал фото еды — запоминаем file_id и спрашиваем вес."""
    file_id = message.photo[-1].file_id
    await state.set_state(Nutrition.waiting_grams)
    await state.update_data(meal_photo=file_id)
    await message.answer("Сколько примерно граммов? Напиши число или «-», если не знаешь.")


@router.message(Nutrition.waiting_grams, F.text)
async def on_grams(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    file_id = data.get("meal_photo")
    raw = message.text.strip().replace(",", ".")
    grams = None
    if raw not in ("-", ""):
        try:
            grams = float(raw)
        except ValueError:
            grams = None

    # Получаем прямую ссылку на файл для Vision
    file = await bot.get_file(file_id)
    image_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

    estimate = await llm.vision_estimate_kcal(image_url, grams)

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user:
            db.add(Meal(user_id=user.id, photo_file_id=file_id, grams=grams, note=estimate))
            await db.commit()

    await state.clear()
    await message.answer(f"🍽 {estimate}")
