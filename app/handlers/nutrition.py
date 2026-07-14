"""Учёт питания: фото/текст → разбор КБЖУ → подтверждение → сохранение.

Несколько фото подряд = несколько независимых черновиков (каждый со своим id),
поэтому можно сохранить/исправить любой из них в любом порядке.
"""
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


def _confirm_kb(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data=f"meal:save:{draft_id}"),
                InlineKeyboardButton(text="✏️ Исправить", callback_data=f"meal:edit:{draft_id}"),
            ],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data=f"meal:cancel:{draft_id}")],
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


async def _get_drafts(state: FSMContext) -> dict:
    data = await state.get_data()
    return data.get("meal_drafts") or {}


async def _set_draft(state: FSMContext, draft_id: str, analysis: dict) -> None:
    drafts = await _get_drafts(state)
    drafts[draft_id] = analysis
    await state.update_data(meal_drafts=drafts)


async def _pop_draft(state: FSMContext, draft_id: str) -> dict | None:
    drafts = await _get_drafts(state)
    analysis = drafts.pop(draft_id, None)
    await state.update_data(meal_drafts=drafts)
    return analysis


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

    draft_id = str(message.message_id)  # уникальный id этого фото/черновика
    analysis["photo"] = file_id
    await _set_draft(state, draft_id, analysis)
    await message.answer(_format(analysis), reply_markup=_confirm_kb(draft_id))


@router.callback_query(F.data.startswith("meal:save:"))
async def meal_save(cb: CallbackQuery, state: FSMContext) -> None:
    draft_id = cb.data.split(":", 2)[2]
    analysis = await _pop_draft(state, draft_id)
    if analysis is None:
        await cb.answer("Это блюдо уже сохранено или отменено", show_alert=True)
        return
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        await repo.add_meal(db, user.id, analysis, analysis.get("photo"))
        totals = await repo.today_totals(db, user.id)
        norm = nutrition.daily_norm(user)
    text = "Записал ✅"
    if norm:
        left = norm["kcal"] - totals["kcal"]
        text += (
            f"\nСегодня: {totals['kcal']} / {norm['kcal']} ккал "
            f"(осталось {max(left, 0)}), Б {totals['protein']} Ж {totals['fat']} У {totals['carbs']}"
        )
    try:
        await cb.message.edit_reply_markup(reply_markup=None)  # убираем кнопки у карточки
    except Exception:
        pass
    await cb.message.answer(text)
    await cb.answer()


@router.callback_query(F.data.startswith("meal:cancel:"))
async def meal_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    draft_id = cb.data.split(":", 2)[2]
    await _pop_draft(state, draft_id)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer("Ок, это блюдо не записываю.")
    await cb.answer()


@router.callback_query(F.data.startswith("meal:edit:"))
async def meal_edit(cb: CallbackQuery, state: FSMContext) -> None:
    draft_id = cb.data.split(":", 2)[2]
    drafts = await _get_drafts(state)
    if draft_id not in drafts:
        await cb.answer("Это блюдо уже сохранено или отменено", show_alert=True)
        return
    await state.set_state(Nutrition.correcting)
    await state.update_data(correcting_id=draft_id)
    await cb.message.answer("Что поправить? Напиши, например: «это гречка» или «250 г».")
    await cb.answer()


@router.message(Nutrition.correcting, F.text)
async def meal_correction(message: Message, state: FSMContext) -> None:
    await handle_correction(message, state, message.text.strip())


async def handle_correction(message: Message, state: FSMContext, text: str) -> None:
    """Коррекция черновика (текст или расшифрованный голос)."""
    data = await state.get_data()
    draft_id = data.get("correcting_id")
    drafts = data.get("meal_drafts") or {}
    prev = drafts.get(draft_id)
    if prev is None:
        await state.set_state(None)
        await message.answer("Черновик не найден. Пришли фото ещё раз.")
        return

    async with typing(message):
        analysis = await llm.analyze_food_text(text, prev=prev)
        if analysis.get("items"):
            analysis = await openfoodfacts.refine(analysis)
    if not analysis.get("items"):
        await message.answer("Не понял правку. Опиши блюдо и вес, например «рис 200 г».")
        return

    analysis["photo"] = prev.get("photo")
    await state.set_state(None)
    await _set_draft(state, draft_id, analysis)
    await message.answer(_format(analysis), reply_markup=_confirm_kb(draft_id))
