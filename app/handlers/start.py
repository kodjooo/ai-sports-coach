"""Онбординг: /start, сбор цели и веса."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core.db import async_session
from app.core import repository as repo
from app.core.seed import ensure_default_templates
from app.keyboards import main_menu
from app.states import Onboarding

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await repo.create_user(db, message.from_user.id, message.from_user.first_name)
            await message.answer(
                "Привет! Я твой виртуальный тренер. Давай познакомимся.\n"
                "Какая у тебя цель? (например: похудеть, набрать силу, подтянуться на турнике)"
            )
            await state.set_state(Onboarding.waiting_goal)
        else:
            await message.answer(
                f"С возвращением, {user.name or 'спортсмен'}! Готов к тренировке?",
                reply_markup=main_menu(),
            )


@router.message(Onboarding.waiting_goal, F.text)
async def onboarding_goal(message: Message, state: FSMContext) -> None:
    await state.update_data(goal=message.text.strip())
    await message.answer("Принял. Какой сейчас вес в кг? (например: 82.5)")
    await state.set_state(Onboarding.waiting_weight)


@router.message(Onboarding.waiting_weight, F.text)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        weight = float(raw)
    except ValueError:
        await message.answer("Не понял вес. Напиши число, например 82.5")
        return

    data = await state.get_data()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        await repo.update_user_profile(db, user, goal=data.get("goal"), weight_kg=weight)
        await ensure_default_templates(db, user.id)

    await state.clear()
    await message.answer(
        "Готово! Я создал стартовый план: День A (Пн) и День B (Ср).\n"
        "Загляни в «План недели» или сразу начинай тренировку.",
        reply_markup=main_menu(),
    )
