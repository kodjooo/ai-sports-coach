"""Учёт питания: фото/текст → разбор КБЖУ → подтверждение → сохранение.

Несколько фото подряд = несколько независимых черновиков (каждый со своим id),
поэтому можно сохранить/исправить любой из них в любом порядке.
"""
from __future__ import annotations

import asyncio
import base64

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
            [  # съел не всё — записать долю порции
                InlineKeyboardButton(text="½ порции", callback_data=f"meal:frac:{draft_id}:1:2"),
                InlineKeyboardButton(text="⅓", callback_data=f"meal:frac:{draft_id}:1:3"),
                InlineKeyboardButton(text="¼", callback_data=f"meal:frac:{draft_id}:1:4"),
            ],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data=f"meal:cancel:{draft_id}")],
        ]
    )


def _scale_analysis(analysis: dict, factor: float) -> dict:
    """Масштабирует граммы и КБЖУ на долю (для «съел половину/треть/четверть»)."""
    a = dict(analysis)
    keys = ("grams", "kcal", "protein", "fat", "carbs")
    a["items"] = [
        {**it, **{k: round((it.get(k) or 0) * factor, 1) for k in keys if k in it}}
        for it in analysis.get("items", [])
    ]
    t = analysis.get("total", {})
    a["total"] = {**t, **{k: round((t.get(k) or 0) * factor) for k in ("kcal", "protein", "fat", "carbs")}}
    return a


def _format(analysis: dict) -> str:
    t = analysis.get("total", {})
    dish = analysis.get("dish")
    lines = [f"🍽 <b>{dish}</b>" if dish else "🍽 <b>Разбор блюда</b>", "Состав:"]
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
        names = {"usda": "USDA", "off": "OpenFoodFacts", "label": "этикетка на упаковке"}
        lines.append("<i>Уточнено по базе: " + ", ".join(names.get(s, s) for s in sources) + ".</i>")
    return "\n".join(lines)


async def _get_drafts(state: FSMContext) -> dict:
    data = await state.get_data()
    return data.get("meal_drafts") or {}


_MAX_DRAFTS = 10  # не копим черновики бесконечно в Redis (если не сохранять/не отменять)


async def _set_draft(state: FSMContext, draft_id: str, analysis: dict) -> None:
    drafts = await _get_drafts(state)
    drafts[draft_id] = analysis
    # Оставляем только последние N (draft_id — message_id, растёт со временем → сортируем по нему)
    if len(drafts) > _MAX_DRAFTS:
        for old in sorted(drafts, key=lambda k: int(k) if k.isdigit() else 0)[:-_MAX_DRAFTS]:
            drafts.pop(old, None)
    await state.update_data(meal_drafts=drafts)


# Замок от двойного тапа: пока сохранение по draft_id идёт, повторные нажатия отбрасываем
_saving: set[str] = set()


async def _pop_draft(state: FSMContext, draft_id: str) -> dict | None:
    drafts = await _get_drafts(state)
    analysis = drafts.pop(draft_id, None)
    await state.update_data(meal_drafts=drafts)
    return analysis


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    # Скачиваем фото и передаём в OpenAI как data:base64 — НЕ светим токен бота в URL
    buf = await bot.download_file(file.file_path)
    image_url = "data:image/jpeg;base64," + base64.b64encode(buf.read()).decode()

    async with typing(message):
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, message.from_user.id)
            known = await repo.recent_dishes(db, user.id) if user else []
        analysis = await llm.analyze_food_photo(image_url, known=known)
        # Само-консистентность ТОЛЬКО для крупной оценочной еды: если вес прикинут на глаз
        # (нет весов/этикетки) и порция калорийная (>500 ккал) — модель между прогонами сильно
        # шумит по объёму (выброс вроде суши 3118). Делаем 2 доп. прохода ПАРАЛЛЕЛЬНО (латентность
        # как +1 вызов) и берём разбор с МЕДИАННЫМ итогом по ккал — устойчиво к выбросу.
        # Весы/этикетки и мелкие порции (банан/яблоко/йогурт) второй проход НЕ трогает.
        if (analysis.get("is_food") and analysis.get("portion_basis") == "estimate"
                and ((analysis.get("total") or {}).get("kcal") or 0) > 500):
            extra = await asyncio.gather(
                llm.analyze_food_photo(image_url, known=known),
                llm.analyze_food_photo(image_url, known=known),
                return_exceptions=True,
            )
            cands = [analysis] + [
                e for e in extra if isinstance(e, dict) and e.get("is_food")
            ]
            cands.sort(key=lambda a: (a.get("total") or {}).get("kcal") or 0)
            analysis = cands[len(cands) // 2]  # медиана по итоговым ккал
        if analysis.get("is_food"):
            analysis = await openfoodfacts.refine(analysis)

    if not analysis.get("is_food"):
        await message.answer("Это не похоже на еду 🤔 Пришли фото блюда.")
        return

    draft_id = str(message.message_id)  # уникальный id этого фото/черновика
    analysis["photo"] = file_id
    await _set_draft(state, draft_id, analysis)
    await message.answer(_format(analysis), reply_markup=_confirm_kb(draft_id))


async def _save_draft(cb: CallbackQuery, state: FSMContext, draft_id: str, factor: float = 1.0) -> None:
    """Сохраняет черновик приёма (опц. долю порции factor) и показывает остаток до нормы."""
    key = f"{cb.from_user.id}:{draft_id}"
    if key in _saving:
        await cb.answer("Уже сохраняю…")
        return
    _saving.add(key)
    try:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        analysis = await _pop_draft(state, draft_id)
        if analysis is None:
            await cb.answer("Это блюдо уже сохранено или отменено", show_alert=True)
            return
        if factor != 1.0:
            analysis = _scale_analysis(analysis, factor)
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, cb.from_user.id)
            meal = await repo.add_meal(db, user.id, analysis, analysis.get("photo"))
            totals = await repo.today_totals(db, user.id)
            norm = nutrition.daily_norm(user)
    finally:
        _saving.discard(key)
    frac_note = {0.5: " (½ порции)", 1/3: " (⅓ порции)", 0.25: " (¼ порции)"}.get(round(factor, 4), "")
    dish = analysis.get("dish") or "приём пищи"
    t = analysis.get("total", {}) or {}
    text = f"Записал: {dish}{frac_note} — {round(t.get('kcal') or 0)} ккал ✅"
    if norm:
        left_k = max(norm["kcal"] - totals["kcal"], 0)
        left_p = max(norm["protein"] - totals["protein"], 0)
        left_f = max(norm["fat"] - totals["fat"], 0)
        left_c = max(norm["carbs"] - totals["carbs"], 0)
        text += (
            f"\nСегодня: {totals['kcal']} / {norm['kcal']} ккал\n"
            f"Осталось добрать: {left_k} ккал · Б {left_p} · Ж {left_f} · У {left_c} г"
        )
    # Кнопка отмены прямо у сообщения «Записал» (а не в меню) — на случай ошибочной записи
    undo_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Убрать эту запись", callback_data=f"meal:del:{meal.id}")
    ]])
    await cb.message.answer(text, reply_markup=undo_kb)
    await cb.answer()


@router.callback_query(F.data.startswith("meal:frac:"))
async def meal_frac(cb: CallbackQuery, state: FSMContext) -> None:
    parts = cb.data.split(":")  # meal:frac:<draft_id>:<n>:<d>
    draft_id, n, d = parts[2], int(parts[3]), int(parts[4])
    await _save_draft(cb, state, draft_id, factor=n / d)


@router.callback_query(F.data.startswith("meal:save:"))
async def meal_save(cb: CallbackQuery, state: FSMContext) -> None:
    draft_id = cb.data.split(":", 2)[2]
    await _save_draft(cb, state, draft_id, factor=1.0)


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
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, message.from_user.id)
            known = await repo.recent_dishes(db, user.id) if user else []
        analysis = await llm.analyze_food_text(text, prev=prev, known=known)
        if analysis.get("items"):
            analysis = await openfoodfacts.refine(analysis)
    if not analysis.get("items"):
        await message.answer("Не понял правку. Опиши блюдо и вес, например «рис 200 г».")
        return

    analysis["photo"] = prev.get("photo")
    await state.set_state(None)
    await _set_draft(state, draft_id, analysis)
    await message.answer(_format(analysis), reply_markup=_confirm_kb(draft_id))
