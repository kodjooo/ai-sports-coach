"""Меню: тренировка-триггеры, статистика, настройки (расписание/план/вес)."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.db import async_session
from app.core import progress
from app.core import repository as repo
from app.handlers.schedule import start_schedule
from app.keyboards import main_menu, settings_menu

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    await message.answer("Меню:", reply_markup=main_menu())


@router.callback_query(F.data == "wk:move")
async def move_workout(cb: CallbackQuery) -> None:
    """Перенос тренировки: фиксируем перенос на завтра."""
    weekday = date.today().weekday()
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        if user:
            template = await repo.get_template_for_weekday(db, user.id, weekday)
            tpl_id = template.id if template else None
            moved = await repo.create_session(db, user.id, tpl_id, date.today(), status="moved")
            await repo.set_session_status(db, moved, "moved")
            await repo.create_session(db, user.id, tpl_id, date.today() + timedelta(days=1))
    await cb.message.answer("Ок, перенёс на завтра. Отдыхай сегодня 🙌")
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
                block.append(f"🔥 Разминка: {tpl.warmup}")
            block += [f"• {r}" for r in rows]
            if tpl.cooldown:
                block.append(f"🧘 Заминка: {tpl.cooldown}")
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


@router.callback_query(F.data == "set:weight")
async def settings_weight(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(expect_weight=True)
    await cb.message.answer("Напиши текущий вес в кг (например 81.3).")
    await cb.answer()
