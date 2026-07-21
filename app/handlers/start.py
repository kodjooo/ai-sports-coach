"""Онбординг: LLM-интервью → персональный промпт тренера, обязательный вес."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import debounce
from app.core import llm
from app.core.db import async_session
from app.core import repository as repo
from app.handlers import environment as env_handlers
from app.keyboards import (
    activity_kb,
    exercises_count_kb,
    level_kb,
    main_menu,
    nutrition_goal_kb,
    sex_kb,
)
from app.states import Onboarding
from app.utils import parse_weight, typing

router = Router()

# Максимум уточняющих вопросов, чтобы интервью не длилось бесконечно
MAX_CLARIFICATIONS = 4

INTRO = (
    "Привет! Я твой виртуальный тренер 💪 Веду тренировки и считаю питание.\n\n"
    "Чтобы настроить всё под тебя, расскажи своими словами (можно голосом): "
    "чего хочешь добиться, какой сейчас статус (опыт, ограничения/травмы), что "
    "нравится и что не нравится. Можешь сразу назвать возраст, рост, вес и где "
    "тренируешься — тогда не буду переспрашивать.\n\n"
    "Питание потом — просто пришлёшь фото еды, и я посчитаю калории и БЖУ."
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
        # Второе — что готовим программу (генерация может занять время)
        await message.answer("Отлично! Составлю программу под тебя — ещё пара уточнений 👇")
        async with typing(message):
            system_prompt = await llm.build_system_prompt(
                result.get("profile_summary"), result.get("goal")
            )
        async with async_session() as db:
            user = await repo.get_user_by_tg(db, message.from_user.id)
            # Сохраняем то, что клиент сам назвал в интервью (чтобы не переспрашивать)
            w, h = result.get("weight_kg"), result.get("height_cm")
            if w:
                user.weight_kg = w
            if h:
                user.height_cm = int(h)
            if result.get("age"):
                user.age = int(result["age"])
            if result.get("sex"):
                user.sex = result["sex"]
            if result.get("level"):
                user.level = result["level"]
            if result.get("environment"):
                user.environment = result["environment"]
            if result.get("equipment"):
                user.equipment = result["equipment"]
            await repo.save_personalization(
                db,
                user,
                system_prompt=system_prompt,
                profile_summary=result.get("profile_summary"),
                goal=result.get("goal"),
            )
            if w:
                await repo.log_weight(db, user.id, float(w))
        # Дальше — только недостающие шаги
        await _continue_after_persona(message, message.from_user.id, state)
    else:
        await state.update_data(history=history, clarifications=clarifications + 1)
        await message.answer(reply)


async def _continue_after_persona(message: Message, tg_id: int, state: FSMContext) -> None:
    """Спрашиваем место/инвентарь только если их ещё нет."""
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, tg_id)
        env, equip = user.environment, user.equipment
    if not env:
        await env_handlers.start_environment(message, state)
    elif not equip:
        await env_handlers.ask_equipment(message, state)
    else:
        from app.handlers.schedule import start_schedule
        await start_schedule(message, state)


@router.message(Onboarding.interview, F.text)
async def interview_text(message: Message, state: FSMContext) -> None:
    # Склеиваем несколько сообщений подряд и обрабатываем один раз
    key = f"{message.chat.id}:{message.from_user.id}"

    async def flush(text: str) -> None:
        await handle_interview(message, state, text)

    await debounce.push(key, message.text.strip(), flush)


async def after_schedule(message: Message, tg_id: int, state: FSMContext) -> None:
    # Профиль уже собран до расписания, поэтому здесь просто финиш
    await _finish_onboarding(message, state)


async def _ask_next_profile(message: Message, tg_id: int, state: FSMContext) -> None:
    """Спрашивает по очереди только недостающие данные профиля, затем финиш."""
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, tg_id)
        weight, height, sex, age, activity, level = (
            user.weight_kg, user.height_cm, user.sex, user.age, user.activity, user.level
        )
        exd, ngoal = user.exercises_per_day, user.nutrition_goal
    if level is None:
        await state.set_state(Onboarding.level)
        await message.answer("Какой у тебя уровень подготовки?", reply_markup=level_kb())
        return
    if exd is None:
        await state.set_state(Onboarding.exercises)
        await message.answer("Сколько упражнений в одной тренировке?", reply_markup=exercises_count_kb())
        return
    if ngoal is None:
        await state.set_state(Onboarding.nutrition_goal)
        await message.answer(
            "Цель по питанию (как считать калории)?", reply_markup=nutrition_goal_kb()
        )
        return
    if weight is None:
        await state.set_state(Onboarding.waiting_weight)
        await message.answer("Какой сейчас вес в кг? (например 82.5)")
    elif height is None:
        await state.set_state(Onboarding.waiting_height)
        await message.answer("А какой рост в см? (например 178)")
    elif sex is None:
        await state.set_state(Onboarding.sex)
        await message.answer("Укажи пол — для расчёта нормы калорий:", reply_markup=sex_kb())
    elif age is None:
        await state.set_state(Onboarding.waiting_age)
        await message.answer("Сколько тебе лет?")
    elif activity is None:
        await state.set_state(Onboarding.activity)
        await message.answer(
            "Какой у тебя <b>образ жизни вне тренировок</b> (работа, быт)? "
            "Тренировки я уже учёл отдельно.",
            reply_markup=activity_kb(),
        )
    else:
        # Профиль собран — переходим к расписанию (там сгенерируется план под всё это)
        from app.handlers.schedule import start_schedule
        await start_schedule(message, state)


async def _finish_onboarding(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Всё готово! Профиль и план настроены.\n"
        "Нажми «▶️ Тренировка», когда будешь готов, или загляни в «⚙️ Настройки».",
        reply_markup=main_menu(),
    )


async def handle_weight(message: Message, state: FSMContext, text: str) -> None:
    """Приём веса (текст или расшифрованный голос)."""
    async with typing(message):
        weight = await parse_weight(text)
    if weight is None:
        await message.answer("Не уловил вес. Напиши, сколько сейчас весишь, например «76 кг».")
        return
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        await repo.update_user_profile(db, user, weight_kg=weight)
    await message.answer(f"Записал вес — {weight:g} кг.")
    await _ask_next_profile(message, message.from_user.id, state)


async def handle_height(message: Message, state: FSMContext, text: str) -> None:
    """Приём роста (текст или расшифрованный голос)."""
    import re

    m = re.search(r"(\d{2,3})", text)
    if not m:
        await message.answer("Не уловил рост. Напиши число в см, например 178.")
        return
    height = int(m.group(1))
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        user.height_cm = height
        await db.commit()
    await message.answer(f"Записал рост — {height} см.")
    await _ask_next_profile(message, message.from_user.id, state)


async def handle_age(message: Message, state: FSMContext, text: str) -> None:
    import re

    m = re.search(r"(\d{1,3})", text)
    if not m or not (10 <= int(m.group(1)) <= 100):
        await message.answer("Не уловил возраст. Напиши число, например 30.")
        return
    age = int(m.group(1))
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        user.age = age
        await db.commit()
    await _ask_next_profile(message, message.from_user.id, state)


@router.message(Onboarding.waiting_weight, F.text)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    await handle_weight(message, state, message.text)


@router.message(Onboarding.waiting_height, F.text)
async def onboarding_height(message: Message, state: FSMContext) -> None:
    await handle_height(message, state, message.text)


@router.message(Onboarding.waiting_age, F.text)
async def onboarding_age(message: Message, state: FSMContext) -> None:
    await handle_age(message, state, message.text)


@router.callback_query(Onboarding.sex, F.data.startswith("sex:"))
async def onboarding_sex(cb: CallbackQuery, state: FSMContext) -> None:
    sex = cb.data.split(":", 1)[1]
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        user.sex = sex
        await db.commit()
    await cb.answer()
    await _ask_next_profile(cb.message, cb.from_user.id, state)


@router.callback_query(Onboarding.activity, F.data.startswith("actlvl:"))
async def onboarding_activity(cb: CallbackQuery, state: FSMContext) -> None:
    activity = cb.data.split(":", 1)[1]
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        user.activity = activity
        await db.commit()
    await cb.answer()
    await _ask_next_profile(cb.message, cb.from_user.id, state)


@router.callback_query(Onboarding.level, F.data.startswith("lvl:"))
async def onboarding_level(cb: CallbackQuery, state: FSMContext) -> None:
    level = cb.data.split(":", 1)[1]
    data = await state.get_data()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        user.level = level
        await db.commit()
    await cb.answer()
    if data.get("from_settings"):
        from app.handlers.environment import _regenerate
        await _regenerate(cb.message, cb.from_user.id, state)
    else:
        await _ask_next_profile(cb.message, cb.from_user.id, state)


@router.callback_query(Onboarding.exercises, F.data.startswith("exd:"))
async def onboarding_exercises(cb: CallbackQuery, state: FSMContext) -> None:
    n = int(cb.data.split(":", 1)[1])
    data = await state.get_data()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        user.exercises_per_day = n
        await db.commit()
    await cb.answer()
    if data.get("from_settings"):
        # Меняли из настроек — пересобираем план под новое число
        from app.handlers.environment import _regenerate
        await _regenerate(cb.message, cb.from_user.id, state)
    else:
        await _ask_next_profile(cb.message, cb.from_user.id, state)


@router.callback_query(Onboarding.nutrition_goal, F.data.startswith("ngoal:"))
async def onboarding_nutrition_goal(cb: CallbackQuery, state: FSMContext) -> None:
    ngoal = cb.data.split(":", 1)[1]
    data = await state.get_data()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        user.nutrition_goal = ngoal
        await db.commit()
    await cb.answer()
    if data.get("from_settings"):
        from app.core.nutrition import NUTRITION_LABELS

        label = dict(NUTRITION_LABELS).get(ngoal, ngoal)
        await state.set_state(None)
        await cb.message.answer(f"Готово, режим питания: {label}. Норма пересчитана.")
    else:
        await _ask_next_profile(cb.message, cb.from_user.id, state)
