"""Меню: тренировка-триггеры, статистика, настройки (расписание/план/вес)."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.db import async_session
from app.core import nutrition, progress
from app.core import repository as repo
from app.core import vector
from app.handlers.environment import start_environment
from app.handlers.schedule import start_schedule
from app.keyboards import main_menu, reset_confirm_kb, settings_menu

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


HELP_TEXT = (
    "<b>ℹ️ Что я умею</b>\n\n"
    "🏋️ <b>Тренировки</b>\n"
    "• Персональный план под твою цель, уровень, пол, место и инвентарь.\n"
    "• Кнопка «▶️ Тренировка»: разминка → упражнения (кнопки повторов/секунд, "
    "ручной ввод, пропуск) → таймер отдыха → заминка → итог с фидбеком.\n"
    "• По ходу подсказываю технику, можно заменить упражнение.\n\n"
    "🍎 <b>Питание</b>\n"
    "• Пришли фото еды или напиши текстом («съел рис с курицей») — посчитаю КБЖУ.\n"
    "• С этикетки беру значения напрямую; для обычной еды уточняю по базам (USDA/OpenFoodFacts).\n"
    "• «🍎 Питание»: сколько съедено и сколько осталось до нормы.\n\n"
    "💬 <b>Чат с тренером</b>\n"
    "• Пиши или говори голосом — отвечу с учётом твоих тренировок, веса и питания.\n"
    "• Могу по твоему подтверждению менять план, нагрузку, время, записывать еду/вес.\n\n"
    "📊 <b>Статистика</b> — тренировки, вес, рекорды, потраченные калории; раз в неделю — итоги.\n\n"
    "⚙️ <b>Настройки</b> — дни/время, место и инвентарь, уровень, число упражнений, "
    "цель по питанию, вес, сброс истории.\n\n"
    "Команды: /start, /profile (пересобрать профиль), /menu, /help."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.callback_query(F.data == "set:help")
async def settings_help(cb: CallbackQuery) -> None:
    await cb.message.answer(HELP_TEXT)
    await cb.answer()


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    await message.answer("Меню:", reply_markup=main_menu())


@router.callback_query(F.data == "wk:move")
async def move_workout(cb: CallbackQuery) -> None:
    """Перенос тренировки: спросить, сдвигать ли всё расписание."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Только эту (на завтра)", callback_data="mv:one")],
            [InlineKeyboardButton(text="📅 Сдвинуть всю неделю на день", callback_data="mv:week")],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data="mv:no")],
        ]
    )
    await cb.message.answer("Перенести только сегодняшнюю тренировку или сдвинуть всё расписание?", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "mv:no")
async def move_cancel(cb: CallbackQuery) -> None:
    await cb.message.answer("Ок, расписание без изменений.")
    await cb.answer()


@router.callback_query(F.data == "mv:one")
async def move_one(cb: CallbackQuery) -> None:
    weekday = date.today().weekday()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        if user:
            template = await repo.get_template_for_weekday(db, user.id, weekday)
            tpl_id = template.id if template else None
            moved = await repo.create_session(db, user.id, tpl_id, date.today(), status="moved")
            await repo.set_session_status(db, moved, "moved")
            await repo.create_session(db, user.id, tpl_id, date.today() + timedelta(days=1))
    await cb.message.answer("Ок, перенёс на завтра — напомню завтра. Сегодня отдыхай 🙌")
    await cb.answer()


@router.callback_query(F.data == "mv:week")
async def move_week(cb: CallbackQuery) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        if user:
            await repo.shift_templates_by_day(db, user.id, 1)
    await cb.message.answer("Сдвинул всё расписание на день вперёд 📅")
    await cb.answer()


# ---------- План недели ----------

async def _render_plan(user_id: int) -> str:
    async with async_session() as db:
        templates = await repo.list_templates(db, user_id)
        if not templates:
            return "План пока пуст. Настрой расписание в «⚙️ Настройки»."
        lines = ["📋 <b>План недели</b>"]
        for tpl in templates:
            day = WEEKDAYS[tpl.weekday] if tpl.weekday is not None else "—"
            items = await repo.list_template_items(db, tpl.id)
            rows = []
            for it in items:
                ex = await repo.get_exercise(db, it.exercise_id)
                rest = f", отдых {it.rest_sec} сек" if it.rest_sec else ""
                rows.append(f"{ex.name if ex else '?'} {it.target_sets}×{it.target_reps}{rest}")
            block = [f"\n<b>{tpl.label}</b> ({day}):"]
            if tpl.warmup:
                block.append(f"\n🔥 <b>Разминка</b>\n{tpl.warmup}")
            block.append("\n💪 <b>Основная часть</b>")
            block += [f"• {r}" for r in rows]
            if tpl.cooldown:
                block.append(f"\n🧘 <b>Заминка</b>\n{tpl.cooldown}")
            lines.append("\n".join(block))
        return "\n".join(lines)


@router.callback_query(F.data == "menu:plan")
async def show_plan_cb(cb: CallbackQuery) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
    if user:
        await cb.message.answer(await _render_plan(user.id))
    await cb.answer()


# ---------- Статистика ----------

@router.message(F.text == "🍎 Питание")
async def show_nutrition(message: Message) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return
        totals = await repo.today_totals(db, user.id)
        norm = nutrition.daily_norm(user)
        burned_today = await repo.calories_burned(db, user.id, days=1)

    lines = ["🍎 <b>Питание сегодня</b>", ""]
    if norm:
        async with async_session() as db:
            u = await repo.get_user_by_tg(db, message.from_user.id)
            _, mode_label = nutrition.mode_of(u)
        goal_name = dict(nutrition.NUTRITION_LABELS).get(u.nutrition_goal, "авто")
        lines.append(f"Режим: <b>{goal_name}</b> ({mode_label})")
        lines.append(
            f"Калории: <b>{totals['kcal']} / {norm['kcal']}</b> "
            f"(осталось {max(norm['kcal'] - totals['kcal'], 0)})"
        )
        lines.append(
            f"Белки: {totals['protein']} / {norm['protein']} г (осталось {max(norm['protein'] - totals['protein'], 0)})\n"
            f"Жиры: {totals['fat']} / {norm['fat']} г (осталось {max(norm['fat'] - totals['fat'], 0)})\n"
            f"Углеводы: {totals['carbs']} / {norm['carbs']} г (осталось {max(norm['carbs'] - totals['carbs'], 0)})"
        )
    else:
        lines.append(
            f"Съедено: {totals['kcal']} ккал (Б {totals['protein']} Ж {totals['fat']} У {totals['carbs']})"
        )
        lines.append("\n<i>Пройди /profile (пол/возраст/активность) — и посчитаю норму.</i>")
    lines.append(f"\nПриёмов пищи: {totals['meals']}")
    if burned_today:
        lines.append(f"🔥 Потрачено на тренировке: ~{burned_today} ккал (не входит в норму выше)")
    lines.append("\n📷 Пришли фото еды или напиши, что съел — запишу и посчитаю КБЖУ.")
    await message.answer("\n".join(lines))


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return
        report = await progress.full_stats(db, user.id)
    await message.answer(report)


# ---------- Настройки ----------

@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message) -> None:
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_menu())


@router.callback_query(F.data == "set:plan")
async def settings_plan(cb: CallbackQuery) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
    if user:
        await cb.message.answer(await _render_plan(user.id))
    await cb.answer()


@router.callback_query(F.data == "set:schedule")
async def settings_schedule(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await start_schedule(cb.message, state, from_settings=True)


@router.callback_query(F.data == "set:time")
async def settings_time(cb: CallbackQuery, state: FSMContext) -> None:
    from app.handlers.schedule import start_time_only

    await cb.answer()
    await start_time_only(cb.message, state)


@router.callback_query(F.data == "set:env")
async def settings_env(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await start_environment(cb.message, state, from_settings=True)


@router.callback_query(F.data == "set:level")
async def settings_level(cb: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards import level_kb
    from app.states import Onboarding

    await state.set_state(Onboarding.level)
    await state.update_data(from_settings=True)
    await cb.message.answer("Какой у тебя уровень подготовки?", reply_markup=level_kb())
    await cb.answer()


@router.callback_query(F.data == "set:exd")
async def settings_exd(cb: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards import exercises_count_kb
    from app.states import Onboarding

    await state.set_state(Onboarding.exercises)
    await state.update_data(from_settings=True)
    await cb.message.answer("Сколько упражнений в тренировке?", reply_markup=exercises_count_kb())
    await cb.answer()


@router.callback_query(F.data == "set:ngoal")
async def settings_ngoal(cb: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards import nutrition_goal_kb
    from app.states import Onboarding

    await state.set_state(Onboarding.nutrition_goal)
    await state.update_data(from_settings=True)
    await cb.message.answer("Цель по питанию?", reply_markup=nutrition_goal_kb())
    await cb.answer()


@router.callback_query(F.data == "set:weight")
async def settings_weight(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(expect_weight=True)
    await cb.message.answer("Напиши текущий вес в кг (например 81.3).")
    await cb.answer()


@router.callback_query(F.data == "set:reset")
async def settings_reset(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "♻️ Сбросить историю? Удалю профиль, план, тренировки, вес и переписку — "
        "и начнём настройку с нуля. Это необратимо.",
        reply_markup=reset_confirm_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "reset:no")
async def reset_cancel(cb: CallbackQuery) -> None:
    await cb.message.answer("Отменил, всё на месте 👌")
    await cb.answer()


@router.callback_query(F.data == "reset:yes")
async def reset_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        if user is None:
            await cb.message.answer("Нечего сбрасывать. Нажми /start.")
            return
        await repo.reset_user(db, user)
    vector.clear_user(user.id)
    await state.clear()
    await cb.message.answer("Готово, всё сброшено. Начнём заново!")
    # Запускаем онбординг с чистого листа
    from app.handlers.start import _start_interview
    await _start_interview(cb.message, state)
