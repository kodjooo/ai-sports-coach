"""Меню: план недели, статистика, запись веса."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.core.db import async_session
from app.core import progress
from app.core import repository as repo
from app.keyboards import main_menu

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    await message.answer("Меню открыто.", reply_markup=main_menu())


@router.message(F.text == "🔽 Свернуть меню")
async def hide_menu(message: Message) -> None:
    await message.answer(
        "Меню свёрнуто. Чтобы открыть снова — команда /menu.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.callback_query(F.data == "wk:move")
async def move_workout(cb: CallbackQuery) -> None:
    """Перенос тренировки: фиксируем перенос на завтра."""
    weekday = date.today().weekday()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        if user:
            template = await repo.get_template_for_weekday(db, user.id, weekday)
            tpl_id = template.id if template else None
            # Помечаем сегодняшнюю как перенесённую и планируем на завтра
            moved = await repo.create_session(db, user.id, tpl_id, date.today(), status="moved")
            await repo.set_session_status(db, moved, "moved")
            await repo.create_session(db, user.id, tpl_id, date.today() + timedelta(days=1))
    await cb.message.answer("Ок, перенёс на завтра. Отдыхай сегодня 🙌")
    await cb.answer()


async def _render_plan(user_id: int) -> str:
    async with async_session() as db:
        templates = await repo.list_templates(db, user_id)
        if not templates:
            return "План пока пуст. Нажми /start, чтобы создать стартовый план."
        lines = ["📊 <b>План недели</b>"]
        for tpl in templates:
            day = WEEKDAYS[tpl.weekday] if tpl.weekday is not None else "—"
            items = await repo.list_template_items(db, tpl.id)
            names = []
            for it in items:
                ex = await repo.get_exercise(db, it.exercise_id)
                names.append(f"{ex.name if ex else '?'} {it.target_sets}×{it.target_reps}")
            lines.append(f"\n<b>{tpl.label}</b> ({day}):\n" + "\n".join(f"• {n}" for n in names))
        return "\n".join(lines)


@router.message(F.text == "📊 План недели")
async def show_plan(message: Message) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start")
        return
    await message.answer(await _render_plan(user.id))


@router.callback_query(F.data == "menu:plan")
async def show_plan_cb(cb: CallbackQuery) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
    if user:
        await cb.message.answer(await _render_plan(user.id))
    await cb.answer()


@router.message(F.text == "📈 Статистика")
async def show_stats(message: Message) -> None:
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return
        report = await progress.weekly_report(db, user.id)
    await message.answer("📈 <b>Итоги недели</b>\n" + report)


@router.message(F.text == "⚖️ Записать вес")
async def ask_weight(message: Message, state: FSMContext) -> None:
    await message.answer("Напиши текущий вес в кг (например 81.3). Или отправь любой вопрос тренеру.")
    await state.update_data(expect_weight=True)
