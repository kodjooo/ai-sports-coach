"""Настройка расписания: частота → дни → время. Используется в онбординге и настройках."""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.core.seed import create_templates
from app.keyboards import WEEKDAYS_SHORT, days_kb, freq_kb, main_menu, time_kb
from app.states import Onboarding
from app.utils import typing

router = Router()


def _days_str(days: list[int]) -> str:
    return "/".join(WEEKDAYS_SHORT[d] for d in sorted(days))


async def start_schedule(message: Message, state: FSMContext, from_settings: bool = False) -> None:
    """Запускает выбор расписания."""
    await state.set_state(Onboarding.schedule)
    await state.update_data(from_settings=from_settings)
    await message.answer(
        "Сколько раз в неделю удобно тренироваться?", reply_markup=freq_kb()
    )


@router.callback_query(Onboarding.schedule, F.data.startswith("sf:"))
async def pick_freq(cb: CallbackQuery, state: FSMContext) -> None:
    freq = int(cb.data.split(":")[1])
    await state.update_data(freq=freq)
    await cb.message.answer("В какие дни удобнее?", reply_markup=days_kb(freq))
    await cb.answer()


@router.callback_query(Onboarding.schedule, F.data.startswith("sd:"))
async def pick_days(cb: CallbackQuery, state: FSMContext) -> None:
    days = [int(x) for x in cb.data.split(":")[1].split(",")]
    await state.update_data(days=days)
    await cb.message.answer("Во сколько напоминать о тренировке?", reply_markup=time_kb())
    await cb.answer()


@router.callback_query(Onboarding.schedule, F.data.startswith("st:"))
async def pick_time(cb: CallbackQuery, state: FSMContext) -> None:
    val = cb.data.split(":", 1)[1]
    if val == "other":
        await state.set_state(Onboarding.custom_time)
        await cb.message.answer("Напиши время в формате ЧЧ:ММ, например 07:30")
        await cb.answer()
        return
    await _apply_time(cb.message, cb.from_user.id, state, int(val), 0)
    await cb.answer()


@router.message(Onboarding.custom_time, F.text)
async def custom_time(message: Message, state: FSMContext) -> None:
    m = re.match(r"^(\d{1,2})[:.\s](\d{2})$", message.text.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        await message.answer("Не понял время. Формат ЧЧ:ММ, например 07:30")
        return
    await _apply_time(message, message.from_user.id, state, int(m.group(1)), int(m.group(2)))


async def _apply_time(message: Message, tg_id: int, state: FSMContext, hour: int, minute: int) -> None:
    data = await state.get_data()
    days = data.get("days", [0, 2, 4])
    from_settings = data.get("from_settings")

    await message.answer("Составляю персональную программу под тебя, секунду…")
    async with typing(message):
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, tg_id)
            await repo.set_train_time(db, user, hour, minute)
            profile, goal, env, equip, uid = (
                user.profile_summary, user.goal, user.environment, user.equipment, user.id
            )
        # Генерируем план под профиль и среду; при сбое — базовые шаблоны
        workouts = await llm.generate_plan(profile, goal, days, env, equip)
        async with async_session() as db:
            if workouts:
                await repo.build_custom_plan(db, uid, workouts, environment=env)
            else:
                await create_templates(db, uid, days)

    schedule_line = f"дни {_days_str(days)}, время {hour:02d}:{minute:02d}"
    if from_settings:
        await state.clear()
        await message.answer(
            f"Готово! Обновил расписание: {schedule_line}. Напомню за 30 минут и в момент старта.",
            reply_markup=main_menu(),
        )
    else:
        # Онбординг: дальше вес/рост — только если их ещё нет
        await message.answer(f"Отлично, расписание: {schedule_line}.")
        from app.handlers.start import after_schedule
        await after_schedule(message, tg_id, state)
