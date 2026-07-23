"""Режим тренировки: пошаговый ввод кнопками, запись сетов, фидбек LLM."""
from __future__ import annotations

import asyncio
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import context as ctx
from app.core import llm, progress, vector, warmup
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import Session, User
from app.keyboards import (
    cooldown_done_kb,
    effort_kb,
    finish_confirm_kb,
    main_menu,
    reps_kb,
    replace_scope_kb,
    warmup_done_kb,
    workout_menu,
)
from app.states import Workout
from app.utils import typing

router = Router()

# Ключевые слова «временных» упражнений (результат в секундах, а не повторах)
_TIME_KEYWORDS = ("планк", "вис", "изометр", "hold", "статич", "уголок", "удержан")


def _is_time_based(name: str, muscle_group: str) -> bool:
    text = f"{name} {muscle_group}".lower()
    return any(k in text for k in _TIME_KEYWORDS)


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
                "muscle_group": (ex.muscle_group if ex else "") or "",
                "technique": (ex.technique if ex else "") or "Техника не описана.",
                "target_sets": it.target_sets or 3,
                "target_reps": it.target_reps or 10,
                "rest_sec": it.rest_sec or 60,
                "is_time": _is_time_based(ex.name if ex else "", (ex.muscle_group if ex else "") or ""),
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
        stored_warmup = template.warmup
        stored_cooldown = template.cooldown

    groups = [it["muscle_group"] for it in items]
    await state.set_state(Workout.in_progress)
    await state.update_data(
        session_id=session.id,
        items=items,
        cur_item=0,
        cur_set=1,
        pending_reps=None,
        groups=groups,
        warmup=stored_warmup or warmup.warmup_text(groups),
        cooldown=stored_cooldown,
    )
    # Прячем главное меню на время тренировки (чтобы случайно не начать новую)
    await target.answer("🏋️ Поехали! Начнём с разминки.", reply_markup=workout_menu())
    # Разминка (хранимая или собранная по группам мышц)
    if stored_warmup:
        warmup_msg = f"🔥 <b>Разминка</b>\n{stored_warmup}"
    else:
        warmup_msg = warmup.warmup_text(groups)
    await target.answer(warmup_msg, reply_markup=warmup_done_kb())


async def _show_set(target, state: FSMContext) -> None:
    data = await state.get_data()
    items = data["items"]
    i = data["cur_item"]
    item = items[i]
    is_time = item.get("is_time", False)
    unit = "сек" if is_time else "повт."
    # Цель: подсказка по ощущению прошлого подхода, иначе плановая
    goal = data.get("suggest") or item["target_reps"]
    prompt = "Сколько секунд продержал?" if is_time else "Выбери число повторов:"
    text = (
        f"<b>{item['name']}</b> — сет {data['cur_set']} из {item['target_sets']} "
        f"(цель ~{goal} {unit})\n{prompt}"
    )
    await target.answer(text, reply_markup=reps_kb(target=goal, is_time=is_time))


@router.message(F.text == "▶️ Тренировка")
async def start_from_menu(message: Message, state: FSMContext) -> None:
    if await state.get_state() in (Workout.in_progress.state, Workout.manual_reps.state):
        await message.answer("Тренировка уже идёт. Заверши её кнопкой «🏁 Завершить тренировку».")
        return
    await _begin(message, message.from_user.id, state)


@router.message(Workout.in_progress, F.text == "🏁 Завершить тренировку")
@router.message(Workout.manual_reps, F.text == "🏁 Завершить тренировку")
async def finish_from_menu(message: Message, state: FSMContext) -> None:
    _cancel_rest(message.chat.id)
    await state.set_state(Workout.in_progress)
    await message.answer("Завершить тренировку?", reply_markup=finish_confirm_kb())


@router.callback_query(F.data == "wk:start")
async def start_from_reminder(cb: CallbackQuery, state: FSMContext) -> None:
    await _begin(cb.message, cb.from_user.id, state)
    await cb.answer()


# ---------- Ввод повторов и ощущения ----------

@router.callback_query(Workout.in_progress, F.data == "wk:manual")
async def manual_reps(cb: CallbackQuery, state: FSMContext) -> None:
    """Ручной ввод результата, если нужной кнопки нет."""
    data = await state.get_data()
    is_time = data["items"][data["cur_item"]].get("is_time", False)
    await state.set_state(Workout.manual_reps)
    await cb.message.answer("Напиши число " + ("секунд." if is_time else "повторов."))
    await cb.answer()


@router.message(Workout.manual_reps, F.text)
async def manual_reps_input(message: Message, state: FSMContext) -> None:
    import re

    m = re.search(r"\d+", message.text)
    if not m:
        await message.answer("Не понял число. Напиши, например 12.")
        return
    await state.set_state(Workout.in_progress)
    await state.update_data(pending_reps=int(m.group()))
    await message.answer("Как ощущение?", reply_markup=effort_kb())


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
        await cb.answer("Сначала выбери число")
        return

    item = data["items"][data["cur_item"]]
    async with async_session() as db:
        await repo.log_set(
            db, data["session_id"], item["exercise_id"], data["cur_set"], reps, effort
        )
    # Автокоррекция: подсказка на следующий подход по ощущению
    step = 5 if item.get("is_time") else 2
    if effort == "easy":
        suggest = reps + step
    elif effort == "hard":
        suggest = max(1, reps - step)
    else:
        suggest = reps
    await state.update_data(suggest=suggest)
    await cb.answer("Записал ✅")
    await _advance(cb.message, state)


async def _advance(target, state: FSMContext) -> None:
    """Переход к следующему подходу/упражнению/заминке."""
    data = await state.get_data()
    items = data["items"]
    i = data["cur_item"]
    item = items[i]
    if data["cur_set"] < item["target_sets"]:
        rest = item.get("rest_sec") or 60
        await target.answer(f"⏱ Отдых {rest} сек — дам сигнал, когда продолжать.")
        await state.update_data(cur_set=data["cur_set"] + 1, pending_reps=None)
        await _show_set(target, state)
        _start_rest(target, rest)
    elif i + 1 < len(items):
        rest = item.get("rest_sec") or 60
        await target.answer(f"⏱ Отдых {rest} сек перед следующим упражнением.")
        await state.update_data(cur_item=i + 1, cur_set=1, pending_reps=None, suggest=None)
        await _show_set(target, state)
        _start_rest(target, rest)
    else:
        _cancel_rest(target.chat.id)
        cooldown = data.get("cooldown")
        text = f"🧘 <b>Заминка</b>\n{cooldown}" if cooldown else warmup.cooldown_text(data.get("groups", []))
        await target.answer(text, reply_markup=cooldown_done_kb())


@router.callback_query(Workout.in_progress, F.data == "wk:skipset")
async def skip_set(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Подход пропущен")
    await state.update_data(pending_reps=None)
    await _advance(cb.message, state)


@router.callback_query(Workout.in_progress, F.data == "wk:skipex")
async def skip_exercise(cb: CallbackQuery, state: FSMContext) -> None:
    """Пропуск упражнения целиком — сразу к следующему/заминке."""
    _cancel_rest(cb.message.chat.id)
    data = await state.get_data()
    items = data["items"]
    i = data["cur_item"]
    await cb.answer("Упражнение пропущено")
    if i + 1 < len(items):
        await state.update_data(cur_item=i + 1, cur_set=1, pending_reps=None, suggest=None)
        await _show_set(cb.message, state)
    else:
        cooldown = data.get("cooldown")
        text = f"🧘 <b>Заминка</b>\n{cooldown}" if cooldown else warmup.cooldown_text(data.get("groups", []))
        await cb.message.answer(text, reply_markup=cooldown_done_kb())


@router.callback_query(Workout.in_progress, F.data == "wk:finishask")
async def finish_ask(cb: CallbackQuery, state: FSMContext) -> None:
    _cancel_rest(cb.message.chat.id)
    await cb.message.answer("Завершить тренировку?", reply_markup=finish_confirm_kb())
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data == "wk:finish_cont")
async def finish_cont(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Продолжаем")
    await _show_set(cb.message, state)


@router.callback_query(Workout.in_progress, F.data == "wk:finish_save")
async def finish_save(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _finish(cb.message, state)


@router.callback_query(Workout.in_progress, F.data == "wk:finish_discard")
async def finish_discard(cb: CallbackQuery, state: FSMContext) -> None:
    _cancel_rest(cb.message.chat.id)
    data = await state.get_data()
    async with async_session() as db:
        await repo.delete_session(db, data["session_id"])
    await state.clear()
    await cb.message.answer("Тренировка отменена, прогресс сброшен.", reply_markup=main_menu())
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data == "wk:warmup_done")
async def warmup_done(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _show_set(cb.message, state)


@router.callback_query(Workout.in_progress, F.data == "wk:cooldown_done")
async def cooldown_done(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _finish(cb.message, state)


# Активные таймеры отдыха по чату — чтобы отменять при завершении/пропуске/отмене
_rest_tasks: dict[int, asyncio.Task] = {}


def _cancel_rest(chat_id: int) -> None:
    task = _rest_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _start_rest(message, seconds: int) -> None:
    _cancel_rest(message.chat.id)
    _rest_tasks[message.chat.id] = asyncio.create_task(_rest_timer(message, seconds))


async def _rest_timer(message, seconds: int) -> None:
    """Отсчёт отдыха: для длинных пауз — сигнал в середине, и «время!» в конце."""
    try:
        if seconds >= 75:
            await asyncio.sleep(seconds / 2)
            await message.answer(f"⏳ Половина отдыха, осталось ~{seconds // 2} сек.")
            await asyncio.sleep(seconds - seconds / 2)
        else:
            await asyncio.sleep(seconds)
        await message.answer("⏱ Время! Следующий подход 💪")
    except Exception:
        pass


# ---------- Завершение и фидбек ----------

async def _finish(target, state: FSMContext) -> None:
    _cancel_rest(target.chat.id)
    data = await state.get_data()
    await target.answer("Тренировка завершена! Считаю итоги…")
    async with typing(target), async_session() as db:
        session = await db.get(Session, data["session_id"])
        user = await db.get(User, session.user_id)
        await repo.finish_session(db, session)

        summary = await progress.format_session_summary(db, session)
        # Прогрессия плана на следующий раз по ощущениям
        await repo.apply_progression(db, user.id, session.id)
        # Оценка потраченных калорий
        burned = await llm.estimate_burn(summary, float(user.weight_kg) if user.weight_kg else None, user.sex)
        session.kcal_burned = burned
        await db.commit()
        facts, memory = await ctx.build_context(db, user.id, summary)
        prompt = ctx.feedback_prompt(facts, memory, summary)
        feedback = await llm.chat(prompt, system_prompt=user.system_prompt)

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
    msg = feedback or "Отличная работа!"
    if burned:
        msg += f"\n\n🔥 Потрачено ~{burned} ккал за тренировку."
    await target.answer(msg, reply_markup=main_menu())


# ---------- Техника и замена ----------

@router.callback_query(Workout.in_progress, F.data == "wk:howto")
async def show_howto(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    item = data["items"][data["cur_item"]]
    async with typing(cb.message):
        detailed = await llm.exercise_howto(item["name"], item.get("is_time", False))
    text = detailed or item["technique"]
    await cb.message.answer(f"<b>Техника — {item['name']}</b>\n{text}")


@router.callback_query(Workout.in_progress, F.data == "wk:replace")
async def replace_start(cb: CallbackQuery, state: FSMContext) -> None:
    """Показываем варианты замены — приоритет той же группе мышц, с указанием группы."""
    data = await state.get_data()
    cur = data["items"][data["cur_item"]]
    cur_ex_id = cur["exercise_id"]
    cur_group = (cur.get("muscle_group") or "").split("/")[0].strip().lower()
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    async with async_session() as db:
        from sqlalchemy import select
        from app.core.models import Exercise

        user = await repo.get_user_by_tg(db, cb.from_user.id)
        env = (user.environment if user else None)
        res = await db.execute(select(Exercise).where(Exercise.id != cur_ex_id))
        others = list(res.scalars().all())

    # Фильтр по среде пользователя (не предлагать зал/улицу без них)
    if env and env != "микс":
        suitable = [ex for ex in others if not ex.environment or ex.environment == env]
        others = suitable or others

    # Сначала — упражнения на ту же группу мышц (равнозначная замена)
    def same_group(ex) -> bool:
        return cur_group and cur_group in (ex.muscle_group or "").lower()

    others.sort(key=lambda ex: (not same_group(ex), ex.name))
    rows = [
        [InlineKeyboardButton(text=f"{ex.name} · {ex.muscle_group or '—'}", callback_data=f"repex:{ex.id}")]
        for ex in others[:8]
    ]
    rows.append([InlineKeyboardButton(text="↩️ Отмена замены", callback_data="wk:replace_cancel")])
    await cb.message.answer(
        f"На что заменить? (сейчас: {cur['name']} · {cur.get('muscle_group') or '—'})\n"
        "Сверху — на ту же группу мышц:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data == "wk:replace_cancel")
async def replace_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Замена отменена")
    await _show_set(cb.message, state)


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
    old_name = item["name"]
    old_sets = item["target_sets"]
    old_reps = item["target_reps"]

    async with async_session() as db:
        ex = await repo.get_exercise(db, new_ex_id)
        is_time = _is_time_based(ex.name, ex.muscle_group or "")
        user = await repo.get_user_by_tg(db, cb.from_user.id)

    # Подбираем равнозначную нагрузку под новое упражнение
    async with typing(cb.message):
        load = await llm.equivalent_load(old_name, old_sets, old_reps, ex.name, is_time)

    item.update(
        {
            "exercise_id": new_ex_id,
            "name": ex.name,
            "muscle_group": (ex.muscle_group or ""),
            "technique": (ex.technique or "Техника не описана."),
            "is_time": is_time,
            "target_sets": load["sets"],
            "target_reps": load["reps"],
        }
    )
    note = f"Заменили на {ex.name}"
    if scope == "forever":
        async with async_session() as db:
            await repo.replace_template_item_exercise(db, item["item_id"], new_ex_id)
        note = f"Заменили упражнение в плане навсегда на {ex.name}"

    items[i] = item
    await state.update_data(items=items, suggest=None)
    await vector.add_memory(
        user.id, f"change-{cb.id}", note, {"type": "change", "date": str(date.today())}
    )
    unit = "сек" if is_time else "повт."
    await cb.message.answer(f"Готово: теперь {ex.name} — {load['sets']}×{load['reps']} {unit}.")
    await cb.answer()
    await _show_set(cb.message, state)
