"""Онбординг: LLM-интервью → персональный промпт тренера, обязательный вес."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.core.seed import ensure_default_templates
from app.keyboards import main_menu
from app.states import Onboarding
from app.utils import parse_weight, typing

router = Router()

# Максимум уточняющих вопросов, чтобы интервью не длилось бесконечно
MAX_CLARIFICATIONS = 4

INTRO = (
    "Привет! Я твой виртуальный тренер. Чтобы вести именно тебя, расскажи "
    "своими словами (можно голосом): чего хочешь добиться, какой сейчас статус "
    "(опыт, ограничения), как часто готов тренироваться, что нравится и что "
    "не нравится в тренировках."
)


async def _start_interview(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.interview)
    await state.update_data(history=[{"role": "assistant", "content": INTRO}], clarifications=0)
    await message.answer(INTRO)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await repo.create_user(db, message.from_user.id, message.from_user.first_name)
            await _start_interview(message, state)
        else:
            await message.answer(
                f"С возвращением, {user.name or 'спортсмен'}! Готов к тренировке?\n"
                "Хочешь обновить профиль — команда /profile.",
                reply_markup=main_menu(),
            )


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext) -> None:
    """Повторное прохождение интервью для обновления персонального промпта."""
    await state.clear()
    async with async_session() as db:
        await repo.get_or_create_user(db, message.from_user.id, message.from_user.first_name)
    await message.answer("Обновим профиль. Расскажи, что изменилось или чего хочешь теперь.")
    await _start_interview(message, state)


async def handle_interview(message: Message, state: FSMContext, text: str) -> None:
    """Обработка ответа пользователя в интервью (текст или расшифрованный голос)."""
    data = await state.get_data()
    history = data.get("history", [])
    clarifications = data.get("clarifications", 0)
    history.append({"role": "user", "content": text})

    # Достигли лимита уточнений — просим модель завершить
    force_finish = clarifications >= MAX_CLARIFICATIONS
    if force_finish:
        await message.answer("Секунду, собираю твой персональный профиль…")
    async with typing(message):
        result = await llm.interview_step(history, force_finish=force_finish)

    reply = result.get("reply") or "Понял."
    history.append({"role": "assistant", "content": reply})

    if result.get("done"):
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, message.from_user.id)
            await repo.save_personalization(
                db,
                user,
                system_prompt=result.get("system_prompt"),
                profile_summary=result.get("profile_summary"),
                goal=result.get("goal"),
            )
        await message.answer(reply)
        # Обязательный вопрос про вес числом
        await state.set_state(Onboarding.waiting_weight)
        await state.update_data(history=history)
        await message.answer("И последнее: какой сейчас вес в кг? (например 82.5)")
    else:
        await state.update_data(history=history, clarifications=clarifications + 1)
        await message.answer(reply)


@router.message(Onboarding.interview, F.text)
async def interview_text(message: Message, state: FSMContext) -> None:
    await handle_interview(message, state, message.text.strip())


async def handle_weight(message: Message, state: FSMContext, text: str) -> None:
    """Приём веса (текст или расшифрованный голос) в конце онбординга."""
    async with typing(message):
        weight = await parse_weight(text)
    if weight is None:
        await message.answer("Не уловил вес. Напиши, сколько сейчас весишь, например «76 кг».")
        return

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        await repo.update_user_profile(db, user, weight_kg=weight)
        await ensure_default_templates(db, user.id)

    await state.clear()
    await message.answer(
        f"Записал вес — {weight:g} кг. Профиль настроен, стартовый план создан: "
        "День A (Пн) и День B (Ср).\n"
        "Загляни в «План недели» или сразу начинай тренировку.",
        reply_markup=main_menu(),
    )


@router.message(Onboarding.waiting_weight, F.text)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    await handle_weight(message, state, message.text)
