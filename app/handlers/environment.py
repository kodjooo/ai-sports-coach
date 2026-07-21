"""Сбор места тренировок и инвентаря. Используется в онбординге и настройках."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.keyboards import env_kb, main_menu
from app.states import Onboarding
from app.utils import typing

router = Router()


async def start_environment(message: Message, state: FSMContext, from_settings: bool = False) -> None:
    await state.set_state(Onboarding.environment)
    await state.update_data(from_settings=from_settings)
    await message.answer("Где чаще всего тренируешься?", reply_markup=env_kb())


async def ask_equipment(message: Message, state: FSMContext) -> None:
    """Спросить только инвентарь (место уже известно)."""
    await state.set_state(Onboarding.equipment)
    await message.answer(
        "Что есть из инвентаря? Напиши через запятую (турник, гантели, резинки, скамья…) "
        "или «ничего»."
    )


@router.callback_query(Onboarding.environment, F.data.startswith("env:"))
async def pick_env(cb: CallbackQuery, state: FSMContext) -> None:
    env = cb.data.split(":", 1)[1]
    await state.update_data(environment=env)
    await state.set_state(Onboarding.equipment)
    await cb.message.answer(
        "Что есть из инвентаря? Напиши через запятую (турник, гантели, резинки, скамья…) "
        "или «ничего»."
    )
    await cb.answer()


async def handle_equipment(message: Message, state: FSMContext, text: str) -> None:
    equipment = text.strip()
    data = await state.get_data()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        await repo.set_environment(db, user, data.get("environment"), equipment)

    if data.get("from_settings"):
        await _regenerate(message, message.from_user.id, state)
    else:
        # Онбординг: дальше собираем профиль (пол/возраст/уровень/вес/рост/активность),
        # и только потом расписание — чтобы план учитывал всё это
        from app.handlers.start import _ask_next_profile
        await _ask_next_profile(message, message.from_user.id, state)


@router.message(Onboarding.equipment, F.text)
async def equipment_text(message: Message, state: FSMContext) -> None:
    await handle_equipment(message, state, message.text)


async def _regenerate(message: Message, tg_id: int, state: FSMContext) -> None:
    """Пересобирает план под новую среду (из настроек), сохраняя дни."""
    await message.answer("Пересобираю программу под новое место и инвентарь…")
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
        async with async_session() as db:
            if workouts:
                await repo.build_custom_plan(db, uid, workouts, environment=env)
    await state.clear()
    await message.answer("Готово! Обновил план под твоё место и инвентарь 💪", reply_markup=main_menu())
