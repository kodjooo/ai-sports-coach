"""Режим тренировки: пошаговый ввод кнопками, запись сетов, фидбек LLM."""
from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import context as ctx
from app.core import llm, progress, vector
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import Session, User
from app.keyboards import effort_kb, reps_kb, replace_scope_kb
from app.states import Workout

router = Router()


# ---------- Запуск тренировки ----------

async def _load_items(db, template_id: int) -> list[dict]:
    items = await repo.list_template_items(db, template_id)
    result: list[dict] = []
    for it in items:
        ex = await repo.get_exercise(db, it.exercise_id)
        result.append(
            {
                "item_id": it.id,
                "exercise_id": it.exercise_id,
                "name": ex.name if ex else "Упражнение",
                "technique": (ex.technique if ex else "") or "Техника не описана.",
                "target_sets": it.target_sets or 3,
                "target_reps": it.target_reps or 10,
            }
        )
    return result


async def _begin(target, user_tg: int, state: FSMContext) -> None:
    """target — Message или объект с .answer для вывода."""
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, user_tg)
        if user is None:
            await target.answer("Сначала нажми /start")
            return
        weekday = date.today().weekday()
        template = await repo.get_template_for_weekday(db, user.id, weekday)
        if template is None:
            templates = await repo.list_templates(db, user.id)
            if not templates:
                await target.answer("План пуст. Нажми /start, чтобы создать план.")
                return
            template = templates[0]  # если на сегодня нет — берём первый доступный
        items = await _load_items(db, template.id)
        if not items:
            await target.answer("В плане нет упражнений.")
            return
        session = await repo.create_session(db, user.id, template.id, date.today())
        await repo.start_session(db, session)

    await state.set_state(Workout.in_progress)
    await state.update_data(session_id=session.id, items=items, cur_item=0, cur_set=1, pending_reps=None)
    await _show_set(target, state)


async def _show_set(target, state: FSMContext) -> None:
    data = await state.get_data()
    items = data["items"]
    i = data["cur_item"]
    item = items[i]
    text = (
        f"<b>{item['name']}</b> — сет {data['cur_set']} из {item['target_sets']} "
        f"(цель ~{item['target_reps']})\nВыбери число повторов:"
    )
    await target.answer(text, reply_markup=reps_kb())


@router.message(F.text == "▶️ Начать тренировку")
async def start_from_menu(message: Message, state: FSMContext) -> None:
    await _begin(message, message.from_user.id, state)


@router.callback_query(F.data == "wk:start")
async def start_from_reminder(cb: CallbackQuery, state: FSMContext) -> None:
    await _begin(cb.message, cb.from_user.id, state)
    await cb.answer()


# ---------- Ввод повторов и ощущения ----------

@router.callback_query(Workout.in_progress, F.data.startswith("reps:"))
async def choose_reps(cb: CallbackQuery, state: FSMContext) -> None:
    reps = int(cb.data.split(":")[1])
    await state.update_data(pending_reps=reps)
    await cb.message.answer("Как ощущение?", reply_markup=effort_kb())
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data.startswith("eff:"))
async def choose_effort(cb: CallbackQuery, state: FSMContext) -> None:
    effort = cb.data.split(":")[1]
    data = await state.get_data()
    reps = data.get("pending_reps")
    if reps is None:
        await cb.answer("Сначала выбери повторы")
        return

    items = data["items"]
    i = data["cur_item"]
    item = items[i]

    # Немедленная запись сета в БД
    async with async_session() as db:
        await repo.log_set(
            db, data["session_id"], item["exercise_id"], data["cur_set"], reps, effort
        )

    # Переход к следующему сету/упражнению
    if data["cur_set"] < item["target_sets"]:
        await state.update_data(cur_set=data["cur_set"] + 1, pending_reps=None)
        await _show_set(cb.message, state)
    elif i + 1 < len(items):
        await state.update_data(cur_item=i + 1, cur_set=1, pending_reps=None)
        await _show_set(cb.message, state)
    else:
        await _finish(cb.message, state)
    await cb.answer("Записал ✅")


# ---------- Завершение и фидбек ----------

async def _finish(target, state: FSMContext) -> None:
    data = await state.get_data()
    await target.answer("Тренировка завершена! Считаю итоги…")
    async with async_session() as db:
        session = await db.get(Session, data["session_id"])
        user = await db.get(User, session.user_id)
        await repo.finish_session(db, session)

        summary = await progress.format_session_summary(db, session)
        facts, memory = await ctx.build_context(db, user.id, summary)
        prompt = ctx.feedback_prompt(facts, memory, summary)
        feedback = await llm.chat(prompt)

    # Пишем итог и фидбек в векторную память
    await vector.add_memory(
        user.id, f"session-{session.id}", summary, {"type": "session_summary", "date": str(date.today())}
    )
    if feedback:
        await vector.add_memory(
            user.id,
            f"feedback-{session.id}",
            feedback,
            {"type": "coach_feedback", "date": str(date.today())},
        )
    await state.clear()
    await target.answer(feedback or "Отличная работа!")


# ---------- Техника и замена ----------

@router.callback_query(Workout.in_progress, F.data == "wk:howto")
async def show_howto(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    item = data["items"][data["cur_item"]]
    await cb.message.answer(f"<b>Техника — {item['name']}</b>\n{item['technique']}")
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data == "wk:replace")
async def replace_start(cb: CallbackQuery, state: FSMContext) -> None:
    """Показываем варианты замены — другие упражнения каталога."""
    data = await state.get_data()
    cur_ex_id = data["items"][data["cur_item"]]["exercise_id"]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    async with async_session() as db:
        from sqlalchemy import select
        from app.core.models import Exercise

        res = await db.execute(select(Exercise).where(Exercise.id != cur_ex_id))
        others = list(res.scalars().all())
    rows = [
        [InlineKeyboardButton(text=ex.name, callback_data=f"repex:{ex.id}")] for ex in others[:8]
    ]
    await cb.message.answer(
        "На что заменить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data.startswith("repex:"))
async def replace_pick(cb: CallbackQuery, state: FSMContext) -> None:
    new_ex_id = int(cb.data.split(":")[1])
    await state.update_data(replace_to=new_ex_id)
    await cb.message.answer("Заменить на сегодня или в плане навсегда?", reply_markup=replace_scope_kb())
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data.startswith("rep:"))
async def replace_apply(cb: CallbackQuery, state: FSMContext) -> None:
    scope = cb.data.split(":")[1]
    data = await state.get_data()
    if scope == "keep":
        await cb.message.answer("Оставляем как есть.")
        await cb.answer()
        await _show_set(cb.message, state)
        return

    new_ex_id = data.get("replace_to")
    items = data["items"]
    i = data["cur_item"]
    item = items[i]

    async with async_session() as db:
        ex = await repo.get_exercise(db, new_ex_id)
        item.update(
            {
                "exercise_id": new_ex_id,
                "name": ex.name,
                "technique": (ex.technique or "Техника не описана."),
            }
        )
        note = f"Заменили {item['name']}"
        if scope == "forever":
            await repo.replace_template_item_exercise(db, item["item_id"], new_ex_id)
            note = f"Заменили упражнение в плане навсегда на {ex.name}"
        user = await repo.get_user_by_tg(db, cb.from_user.id)

    items[i] = item
    await state.update_data(items=items)
    # Факт замены — в память
    await vector.add_memory(
        user.id, f"change-{cb.id}", note, {"type": "change", "date": str(date.today())}
    )
    await cb.message.answer(f"Готово: теперь {ex.name}.")
    await cb.answer()
    await _show_set(cb.message, state)
