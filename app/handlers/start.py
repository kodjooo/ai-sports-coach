"""Онбординг: LLM-интервью → персональный промпт тренера, обязательный вес."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.handlers.schedule import start_schedule
from app.keyboards import main_menu
from app.states import Onboarding
from app.utils import parse_weight, react, typing

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
    async with typing(message):
        result = await llm.interview_step(history, force_finish=force_finish)

    reply = result.get("reply") or "Понял."
    history.append({"role": "assistant", "content": reply})

    if result.get("done"):
        # Первое сообщение — подтверждение, что всё понял
        await message.answer(reply)
        # Второе — что готовит персональную настройку (генерация может занять время)
        await message.answer("Настраиваю тренера под тебя, секунду…")
        async with typing(message):
            system_prompt = await llm.build_system_prompt(
                result.get("profile_summary"), result.get("goal")
            )
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, message.from_user.id)
            await repo.save_personalization(
                db,
                user,
                system_prompt=system_prompt,
                profile_summary=result.get("profile_summary"),
                goal=result.get("goal"),
            )
        # Дальше — выбор расписания (частота/дни/время)
        await start_schedule(message, state)
    else:
        await state.update_data(history=history, clarifications=clarifications + 1)
        await message.answer(reply)


@router.message(Onboarding.interview, F.text)
async def interview_text(message: Message, state: FSMContext) -> None:
    await react(message, "👀")  # метка «прочитал»
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

    await state.clear()
    await message.answer(
        f"Записал вес — {weight:g} кг. Всё готово! Профиль и план настроены.\n"
        "Нажми «▶️ Тренировка», когда будешь готов, или загляни в «⚙️ Настройки».",
        reply_markup=main_menu(),
    )


@router.message(Onboarding.waiting_weight, F.text)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    await handle_weight(message, state, message.text)
