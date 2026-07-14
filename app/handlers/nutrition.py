"""Учёт питания: фото/текст → разбор КБЖУ → подтверждение → сохранение."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core import llm, nutrition, openfoodfacts
from app.core import repository as repo
from app.core.db import async_session
from app.states import Nutrition
from app.utils import typing

router = Router()


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="meal:save"),
                InlineKeyboardButton(text="✏️ Исправить", callback_data="meal:edit"),
            ],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data="meal:cancel")],
        ]
    )


def _format(analysis: dict) -> str:
    t = analysis.get("total", {})
    lines = ["🍽 <b>Разбор блюда</b>"]
    for it in analysis.get("items", []):
        lines.append(
            f"• {it.get('name', '?')} ~{round(it.get('grams') or 0)} г — "
            f"{round(it.get('kcal') or 0)} ккал"
        )
    lines.append(
        f"\n<b>Итого:</b> {round(t.get('kcal') or 0)} ккал, "
        f"Б {round(t.get('protein') or 0)} / Ж {round(t.get('fat') or 0)} / "
        f"У {round(t.get('carbs') or 0)}"
    )
    sources = {it.get("source") for it in analysis.get("items", []) if it.get("source")}
    if sources:
        names = {"usda": "USDA", "off": "OpenFoodFacts"}
        lines.append("<i>Уточнено по базе: " + ", ".join(names.get(s, s) for s in sources) + ".</i>")
    return "\n".join(lines)


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    image_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

    async with typing(message):
        analysis = await llm.analyze_food_photo(image_url)
        if analysis.get("is_food"):
            analysis = await openfoodfacts.refine(analysis)

    if not analysis.get("is_food"):
        await message.answer("Это не похоже на еду 🤔 Пришли фото блюда.")
        return

    await state.set_state(Nutrition.confirming)
    await state.update_data(meal=analysis, meal_photo=file_id)
    await message.answer(_format(analysis), reply_markup=_confirm_kb())


@router.callback_query(Nutrition.confirming, F.data == "meal:save")
async def meal_save(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    analysis = data.get("meal") or {}
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        await repo.add_meal(db, user.id, analysis, data.get("meal_photo"))
        totals = await repo.today_totals(db, user.id)
        norm = nutrition.daily_norm(user)
    await state.clear()
    text = "Записал ✅"
    if norm:
        left = norm["kcal"] - totals["kcal"]
        text += (
            f"\nСегодня: {totals['kcal']} / {norm['kcal']} ккал "
            f"(осталось {max(left, 0)}), Б {totals['protein']} Ж {totals['fat']} У {totals['carbs']}"
        )
    await cb.message.answer(text)
    await cb.answer()


@router.callback_query(Nutrition.confirming, F.data == "meal:edit")
async def meal_edit(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Nutrition.correcting)
    await cb.message.answer("Что поправить? Напиши, например: «паста 250 г» или «без масла».")
    await cb.answer()


@router.callback_query(Nutrition.confirming, F.data == "meal:cancel")
async def meal_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.answer("Ок, не записываю.")
    await cb.answer()


@router.message(Nutrition.correcting, F.text)
async def meal_correction(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    prev = data.get("meal") or {}
    async with typing(message):
        analysis = await llm.analyze_food_text(message.text.strip(), prev=prev)
        if analysis.get("items"):
            analysis = await openfoodfacts.refine(analysis)
    if not analysis.get("items"):
        await message.answer("Не понял правку. Опиши блюдо и вес, например «рис 200 г, курица 150 г».")
        return
    await state.set_state(Nutrition.confirming)
    await state.update_data(meal=analysis)
    await message.answer(_format(analysis), reply_markup=_confirm_kb())
