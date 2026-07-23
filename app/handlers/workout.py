"""Режим тренировки: пошаговый ввод кнопками, запись сетов, фидбек LLM."""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.config import settings
from app.core import context as ctx
from app.core import llm, progress, vector, warmup
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import Session, User
from app.keyboards import (
    cooldown_done_kb,
    cooldown_step_kb,
    effort_kb,
    finish_confirm_kb,
    main_menu,
    reps_kb,
    replace_scope_kb,
    warmup_done_kb,
    warmup_step_kb,
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


def _today() -> date:
    """Сегодняшняя дата в часовом поясе бота (не UTC контейнера)."""
    return datetime.now(ZoneInfo(settings.tz)).date()


def _gif_path(gif: str | None) -> str | None:
    """Полный путь к GIF-анимации, если файл есть на volume."""
    if not gif:
        return None
    path = os.path.join(settings.exercise_gif_dir, gif)
    return path if os.path.exists(path) else None


async def _send_exercise_card(target, item: dict, caption: str, reply_markup=None) -> None:
    """Отправляет карточку упражнения с GIF-анимацией техники; если файла нет — текстом."""
    path = _gif_path(item.get("gif"))
    if path:
        try:
            await target.answer_animation(FSInputFile(path), caption=caption, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await target.answer(caption, reply_markup=reply_markup)


def _phase_caption(m: dict, idx: int, total: int) -> str:
    """Подпись движения разминки/заминки: номер, название, короткая техника."""
    tech = (m.get("technique") or "").strip()
    head = f"<b>{m['name']}</b> ({idx + 1}/{total})"
    return head + (f"\n{tech}" if tech else "")


async def _show_warmup_step(target, state: FSMContext) -> None:
    """Показывает одно движение разминки с кнопкой «Далее» (пошагово)."""
    data = await state.get_data()
    items = data.get("warm_items") or []
    idx = data.get("warm_idx", 0)
    m = items[idx]
    caption = "🔥 " + _phase_caption(m, idx, len(items))
    await _send_exercise_card(target, m, caption, reply_markup=warmup_step_kb(last=idx + 1 >= len(items)))


async def _show_cooldown_step(target, state: FSMContext) -> None:
    """Показывает одно движение заминки с кнопкой «Далее» (пошагово)."""
    data = await state.get_data()
    items = data.get("cool_items") or []
    idx = data.get("cool_idx", 0)
    m = items[idx]
    caption = "🧘 " + _phase_caption(m, idx, len(items))
    await _send_exercise_card(target, m, caption, reply_markup=cooldown_step_kb(last=idx + 1 >= len(items)))


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
                "howto": (ex.howto if ex else None),
                "gif": (ex.gif if ex else None),
                "phase": getattr(it, "phase", None) or "main",
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
        weekday = _today().weekday()
        template = await repo.get_template_for_weekday(db, user.id, weekday)
        if template is None:
            templates = await repo.list_templates(db, user.id)
            if not templates:
                await target.answer("План пуст. Нажми /start, чтобы создать план.")
                return
            template = templates[0]  # если на сегодня нет — берём первый доступный
        all_items = await _load_items(db, template.id)
        if not all_items:
            await target.answer("В плане нет упражнений.")
            return
        session = await repo.create_session(db, user.id, template.id, _today())
        await repo.start_session(db, session)
        stored_warmup = template.warmup
        stored_cooldown = template.cooldown

    # Разбиваем по фазам: разминка → основная часть → заминка
    warm_items = [it for it in all_items if it["phase"] == "warmup"]
    main_items = [it for it in all_items if it["phase"] == "main"]
    cool_items = [it for it in all_items if it["phase"] == "cooldown"]
    if not main_items:  # старые планы без фаз — все элементы считаем основными
        main_items = all_items

    groups = [it["muscle_group"] for it in main_items]
    await state.set_state(Workout.in_progress)
    await state.update_data(
        session_id=session.id,
        items=main_items,
        warm_items=warm_items,
        warm_idx=0,
        cool_items=cool_items,
        cool_idx=0,
        cur_item=0,
        cur_set=1,
        pending_reps=None,
        groups=groups,
        warmup=stored_warmup or warmup.warmup_text(groups),
        cooldown=stored_cooldown,
    )
    # Прячем главное меню на время тренировки (чтобы случайно не начать новую)
    await target.answer("🏋️ Поехали! Начнём с разминки — по одному движению.", reply_markup=workout_menu())
    # Разминка пошагово: движения каталога с GIF; если их нет — старый текст
    if warm_items:
        await _show_warmup_step(target, state)
    else:
        warmup_msg = f"🔥 <b>Разминка</b>\n{stored_warmup}" if stored_warmup else warmup.warmup_text(groups)
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
    set_line = (
        f"<b>{item['name']}</b> — сет {data['cur_set']} из {item['target_sets']} "
        f"(цель ~{goal} {unit})\n{prompt}"
    )
    kb = reps_kb(target=goal, is_time=is_time)
    if data["cur_set"] == 1:
        # Первый подход — единая карточка: GIF + название · группа + техника + строка сета + кнопки
        tech = (item.get("technique") or "").strip()
        muscle = item.get("muscle_group") or ""
        head = f"<b>{item['name']}</b>" + (f" · {muscle}" if muscle else "")
        caption = head + (f"\n{tech}" if tech else "")
        caption += (
            f"\n\nСет {data['cur_set']} из {item['target_sets']} (цель ~{goal} {unit})\n{prompt}"
        )
        await _send_exercise_card(target, item, caption, reply_markup=kb)
    else:
        # Последующие подходы — только строка сета с кнопками (без гифки и описания)
        await target.answer(set_line, reply_markup=kb)


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
    # Та же страховка, что и при старте из меню: не начинаем вторую тренировку поверх идущей
    if await state.get_state() in (Workout.in_progress.state, Workout.manual_reps.state):
        await cb.answer("Тренировка уже идёт", show_alert=True)
        return
    await cb.answer()
    await _begin(cb.message, cb.from_user.id, state)


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
    # Сразу «съедаем» результат — повторный тап по ощущению не запишет второй подход
    await state.update_data(pending_reps=None)

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


async def _show_cooldown(target, state: FSMContext) -> None:
    """Заминка: пошагово движения каталога с GIF; если их нет — старый текст."""
    data = await state.get_data()
    cool_items = data.get("cool_items") or []
    if cool_items:
        await state.update_data(cool_idx=0)
        await target.answer("🧘 Финишная прямая — заминка по одному движению.")
        await _show_cooldown_step(target, state)
    else:
        cooldown = data.get("cooldown")
        text = f"🧘 <b>Заминка</b>\n{cooldown}" if cooldown else warmup.cooldown_text(data.get("groups", []))
        await target.answer(text, reply_markup=cooldown_done_kb())


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
        await _show_cooldown(target, state)


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
        await _show_cooldown(cb.message, state)


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


@router.callback_query(Workout.in_progress, F.data == "wk:warm_next")
async def warm_next(cb: CallbackQuery, state: FSMContext) -> None:
    """Следующее движение разминки; после последнего — к основным упражнениям."""
    await cb.answer()
    data = await state.get_data()
    items = data.get("warm_items") or []
    idx = data.get("warm_idx", 0) + 1
    if idx < len(items):
        await state.update_data(warm_idx=idx)
        await _show_warmup_step(cb.message, state)
    else:
        await _show_set(cb.message, state)


@router.callback_query(Workout.in_progress, F.data == "wk:cool_next")
async def cool_next(cb: CallbackQuery, state: FSMContext) -> None:
    """Следующее движение заминки; после последнего — завершение тренировки."""
    await cb.answer()
    data = await state.get_data()
    items = data.get("cool_items") or []
    idx = data.get("cool_idx", 0) + 1
    if idx < len(items):
        await state.update_data(cool_idx=idx)
        await _show_cooldown_step(cb.message, state)
    else:
        await _finish(cb.message, state)


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

# Чаты, для которых завершение уже идёт — от двойного тапа (двойные платные LLM-вызовы, двойная прогрессия)
_finishing: set[int] = set()


async def _finish(target, state: FSMContext) -> None:
    if target.chat.id in _finishing:
        return
    _finishing.add(target.chat.id)
    try:
        await _finish_inner(target, state)
    finally:
        _finishing.discard(target.chat.id)


async def _finish_inner(target, state: FSMContext) -> None:
    _cancel_rest(target.chat.id)
    data = await state.get_data()
    if not data.get("session_id"):
        return  # уже завершено/сброшено
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
        user.id, f"session-{session.id}", summary, {"type": "session_summary", "date": str(_today())}
    )
    if feedback:
        await vector.add_memory(
            user.id,
            f"feedback-{session.id}",
            feedback,
            {"type": "coach_feedback", "date": str(_today())},
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
    # Готовое описание из каталога (быстро, без затрат). LLM — только фолбэк, если поля нет.
    text = (item.get("howto") or "").strip()
    if not text:
        async with typing(cb.message):
            text = await llm.exercise_howto(item["name"], item.get("is_time", False))
        text = text or item.get("technique") or "Техника не описана."
    await cb.message.answer(f"<b>Как правильно — {item['name']}</b>\n{text}")


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
        equip = (user.equipment if user else None)
        res = await db.execute(select(Exercise).where(Exercise.id != cur_ex_id))
        others = list(res.scalars().all())

    # Фильтр по ДОСТУПНОМУ ОБОРУДОВАНИЮ (единая ось): предлагаем только выполнимое.
    from app.core import catalog
    avail = catalog.available_equipment(equip)

    def feasible(ex) -> bool:
        hit = catalog.resolve(ex.name)
        if not hit:
            return True  # нет в каталоге — не отсекаем (напр. кастомные)
        return set(hit.get("equipment_req") or []).issubset(avail)

    suitable = [ex for ex in others if feasible(ex)]
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
            "gif": ex.gif,
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
        user.id, f"change-{cb.id}", note, {"type": "change", "date": str(_today())}
    )
    unit = "сек" if is_time else "повт."
    await cb.message.answer(f"Готово: теперь {ex.name} — {load['sets']}×{load['reps']} {unit}.")
    await cb.answer()
    await _show_set(cb.message, state)
