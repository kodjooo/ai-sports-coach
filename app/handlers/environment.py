"""Сбор места тренировок и инвентаря. Используется в онбординге и настройках."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.keyboards import EQUIPMENT_OPTIONS, equipment_kb, main_menu
from app.states import Onboarding
from app.utils import typing

logger = logging.getLogger(__name__)

router = Router()


async def ask_equipment(message: Message, state: FSMContext, from_settings: bool = False) -> None:
    """Чеклист инвентаря (мультивыбор). Место тренировки НЕ спрашиваем — фильтр только по инвентарю."""
    await state.set_state(Onboarding.equipment)
    await state.update_data(from_settings=from_settings, equip_sel=[])
    await message.answer(
        "Отметь, что у тебя есть из инвентаря (можно несколько), и нажми «Готово»:",
        reply_markup=equipment_kb(set()),
    )


# Совместимость: старт сбора инвентаря в онбординге/настройках (место больше не спрашиваем)
async def start_environment(message: Message, state: FSMContext, from_settings: bool = False) -> None:
    await ask_equipment(message, state, from_settings=from_settings)


@router.callback_query(Onboarding.equipment, F.data.startswith("eq:t:"))
async def toggle_equipment(cb: CallbackQuery, state: FSMContext) -> None:
    idx = int(cb.data.split(":")[2])
    data = await state.get_data()
    sel = set(data.get("equip_sel", []))
    sel.symmetric_difference_update({idx})
    await state.update_data(equip_sel=sorted(sel))
    try:
        await cb.message.edit_reply_markup(reply_markup=equipment_kb(sel))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(Onboarding.equipment, F.data == "eq:done")
async def equipment_done(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    sel = set(data.get("equip_sel", []))
    labels = [EQUIPMENT_OPTIONS[i] for i in sorted(sel)]
    equipment = ", ".join(labels) if labels else "без инвентаря"
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        await repo.set_environment(db, user, user.environment, equipment)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(f"Записал инвентарь: {equipment}.")
    await cb.answer()
    if data.get("from_settings"):
        await _regenerate(cb.message, cb.from_user.id, state)
    else:
        from app.handlers.start import _ask_next_profile
        await _ask_next_profile(cb.message, cb.from_user.id, state)


async def _regenerate(message: Message, tg_id: int, state: FSMContext) -> None:
    """Пересобирает план под новую среду (из настроек), сохраняя дни."""
    await message.answer("Пересобираю программу под новые настройки…")
    async with typing(message):
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, tg_id)
            days = await repo.active_weekdays(db, user.id)
            profile, goal, env, equip, sex, level, per_day, uid = (
                user.profile_summary, user.goal, user.environment, user.equipment,
                user.sex, user.level, user.exercises_per_day or 4, user.id,
            )
        days = days or [0, 2, 4]
        workouts = await llm.generate_plan(profile, goal, days, env, equip, sex, level, per_day)
        if workouts:
            async with async_session() as db:
                await repo.build_custom_plan(db, uid, workouts, environment=env)
    await state.clear()
    if not workouts:
        logger.error("Не удалось пересобрать план: user=%s env=%s equip=%s", uid, env, equip)
        await message.answer(
            "Не получилось пересобрать программу 😕 Попробуй ещё раз или напиши мне в чат.",
            reply_markup=main_menu(),
        )
        return
    await message.answer("Готово! Пересобрал программу под новые настройки 💪", reply_markup=main_menu())
