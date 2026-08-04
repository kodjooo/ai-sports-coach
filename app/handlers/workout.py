"""Режим тренировки: пошаговый ввод кнопками, запись сетов, фидбек LLM."""
from __future__ import annotations

import asyncio
import logging
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
    swap_scope_kb,
    warmup_step_kb,
    workout_menu,
)
from app.states import Workout
from app.utils import is_time_based, md_bold_to_html, typing

router = Router()
logger = logging.getLogger(__name__)

def _is_time_based(name: str, muscle_group: str) -> bool:
    # Единый источник в app.utils.is_time_based (чтобы карточка и план недели не расходились)
    return is_time_based(name, muscle_group)


def _equipment_note(item: dict) -> str:
    """Короткая подпись про инвентарь для упражнения (по каталогу)."""
    from app.core import catalog
    hit = catalog.resolve(item.get("name", ""))
    req = (hit.get("equipment_req") if hit else None) or []
    return "нужен инвентарь: " + ", ".join(req) if req else "без инвентаря"


# Признаки упражнения «на каждую сторону» (один подход = обе стороны, подпись это поясняет)
_PER_SIDE_KEYWORDS = (
    "на каждую", "каждый бок", "каждую ног", "каждую стор", "боковая планк", "болгар",
    "выпад", "на одной ног", "одной рук", "попеременн", "разноимённ", "разноименн",
    "пистолет", "сплит-присед", "сплит присед", "бок", "на колене",
)


def _is_per_side(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in _PER_SIDE_KEYWORDS)


def _warmup_dose(name: str, muscle_group: str) -> str:
    """Примерная доза движения разминки/заминки для показа."""
    return "~30 сек" if _is_time_based(name, muscle_group) else "~10 повторов"


def _today() -> date:
    """Сегодняшняя дата в часовом поясе бота (не UTC контейнера)."""
    return datetime.now(ZoneInfo(settings.tz)).date()


def _gif_path(gif: str | None) -> str | None:
    """Полный путь к GIF-анимации, если файл есть на volume."""
    if not gif:
        return None
    path = os.path.join(settings.exercise_gif_dir, gif)
    return path if os.path.exists(path) else None


async def _send_exercise_card(target, item: dict, caption: str, reply_markup=None):
    """Отправляет карточку упражнения с GIF-анимацией техники; если файла нет — текстом.
    Возвращает отправленное сообщение (нужно для компактного режима)."""
    path = _gif_path(item.get("gif"))
    if path:
        try:
            return await target.answer_animation(FSInputFile(path), caption=caption,
                                                 reply_markup=reply_markup)
        except Exception:
            pass
    return await target.answer(caption, reply_markup=reply_markup)


# ---------- Компактный режим: одна активная карточка вместо ленты сообщений ----------

async def _remember(state: FSMContext, msg) -> None:
    """Запоминает id служебного сообщения тренировки, чтобы удалить его на следующем шаге."""
    if not settings.workout_compact or msg is None:
        return
    data = await state.get_data()
    ids = list(data.get("tracked_msgs") or [])
    ids.append(msg.message_id)
    await state.update_data(tracked_msgs=ids[-30:])


async def _purge(target, state: FSMContext) -> None:
    """Удаляет сообщения предыдущего шага (карточку + таймеры/вопросы)."""
    if not settings.workout_compact:
        return
    data = await state.get_data()
    ids = data.get("tracked_msgs") or []
    if not ids:
        return
    bot = getattr(target, "bot", None)
    if bot is None:  # подстраховка: берём бот из текущего контекста aiogram
        from aiogram.client.bot import Bot as _Bot
        bot = _Bot.get_current(no_error=True) if hasattr(_Bot, "get_current") else None
    if bot is None:
        logger.warning("[COMPACT] нет объекта bot — не могу удалить %d сообщений", len(ids))
        await state.update_data(tracked_msgs=[])
        return
    for mid in ids:
        try:
            await bot.delete_message(target.chat.id, mid)
        except Exception as exc:
            logger.warning("[COMPACT] не удалил сообщение %s: %s", mid, exc)
    await state.update_data(tracked_msgs=[])


async def _step(target, state: FSMContext, text: str, reply_markup=None):
    """Одно активное сообщение: удаляем предыдущее и отправляем новое."""
    await _purge(target, state)
    sent = await target.answer(text, reply_markup=reply_markup)
    await _remember(state, sent)
    return sent


def _phase_caption(m: dict, idx: int, total: int, dose: str) -> str:
    """Подпись движения разминки/заминки: номер, название, доза (повторы/сек), короткая техника."""
    tech = (m.get("technique") or "").strip()
    side = " · на каждую сторону" if _is_per_side(m.get("name", "")) else ""
    head = f"<b>{m['name']}</b> ({idx + 1}/{total}) — {dose}{side}"
    return head + (f"\n{tech}" if tech else "")


async def _show_warmup_step(target, state: FSMContext) -> None:
    """Показывает одно движение разминки с кнопкой «Далее» (пошагово)."""
    await state.update_data(phase_now="warmup")
    data = await state.get_data()
    items = data.get("warm_items") or []
    idx = data.get("warm_idx", 0)
    m = items[idx]
    dose = _warmup_dose(m.get("name", ""), m.get("muscle_group", ""))
    caption = "🔥 " + _phase_caption(m, idx, len(items), dose)
    await _purge(target, state)
    sent = await _send_exercise_card(target, m, caption,
                                     reply_markup=warmup_step_kb(last=idx + 1 >= len(items)))
    await _remember(state, sent)


async def _show_cooldown_step(target, state: FSMContext) -> None:
    """Показывает одно движение заминки с кнопкой «Далее» (пошагово)."""
    data = await state.get_data()
    items = data.get("cool_items") or []
    idx = data.get("cool_idx", 0)
    m = items[idx]
    caption = "🧘 " + _phase_caption(m, idx, len(items), "~20–30 сек")  # заминка — статичная растяжка
    await _purge(target, state)
    sent = await _send_exercise_card(target, m, caption,
                                     reply_markup=cooldown_step_kb(last=idx + 1 >= len(items)))
    await _remember(state, sent)


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
        equipment=user.equipment,  # нужен для пересборки заминки под доступный инвентарь
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
    await state.update_data(phase_now="main")  # для «Продолжить» и «завершить в конце»
    items = data["items"]
    i = data["cur_item"]
    item = items[i]
    is_time = item.get("is_time", False)
    unit = "сек" if is_time else "повт."
    per_side = " на каждую сторону" if _is_per_side(item.get("name", "")) else ""
    # Цель: подсказка по ощущению прошлого подхода, иначе плановая
    goal = data.get("suggest") or item["target_reps"]
    prompt = (
        f"Сколько секунд продержал{' на сторону' if per_side else ''}?"
        if is_time else f"Сколько повторов{' на сторону' if per_side else ''}?"
    )
    set_body = f"сет {data['cur_set']} из {item['target_sets']} (цель ~{goal} {unit}{per_side})\n{prompt}"
    kb = reps_kb(target=goal, is_time=is_time)
    # Ориентир «где мы»: номер упражнения в основной части
    pos = f"Упражнение {data['cur_item'] + 1} из {len(items)}"
    await _purge(target, state)
    if data["cur_set"] == 1:
        # Первый подход — единая карточка: GIF + название · группа + техника + строка сета + кнопки
        tech = (item.get("technique") or "").strip()
        muscle = item.get("muscle_group") or ""
        head = f"<b>{item['name']}</b>" + (f" · {muscle}" if muscle else "")
        caption = f"{pos}\n" + head + (f"\n{tech}" if tech else "")
        caption += f"\n\n{set_body[0].upper()}{set_body[1:]}"
        sent = await _send_exercise_card(target, item, caption, reply_markup=kb)
    else:
        # Последующие подходы — только строка сета с кнопками (без гифки и описания)
        sent = await target.answer(f"{pos}\n<b>{item['name']}</b> — {set_body}", reply_markup=kb)
    await _remember(state, sent)


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
    data = await state.get_data()
    if data.get("phase_now") == "cooldown":
        # Мы уже на заминке — продолжать нечего, завершаем без переспроса
        await _finish(message, state)
        return
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
    await _step(message, state, "Как ощущение?", reply_markup=effort_kb())


@router.callback_query(Workout.in_progress, F.data.startswith("reps:"))
async def choose_reps(cb: CallbackQuery, state: FSMContext) -> None:
    reps = int(cb.data.split(":")[1])
    await state.update_data(pending_reps=reps)
    await _step(cb.message, state, "Как ощущение?", reply_markup=effort_kb())
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


def _cooldown_for_zones(zones: list[str], n: int = 5, equipment: str | None = None) -> list[dict]:
    """Подбирает движения заминки (статические растяжки) под фактические зоны дня.

    equipment — ИНВЕНТАРЬ КЛИЕНТА: обязателен, иначе в заминку попадут фитбол/палка/скамья,
    которых у него нет (пустая строка = только вес тела).
    """
    from app.core import catalog
    flat = [z.strip() for zg in zones for z in (zg or "").split("/") if z.strip()]
    pool = catalog.cooldown_candidates(equipment or "", zones=flat)
    out, seen = [], set()
    for e in pool:
        if e["name"] in seen:
            continue
        seen.add(e["name"])
        out.append({"name": e["name"], "muscle_group": e["muscle_group"],
                    "technique": e["technique"], "gif": e["gif"]})
        if len(out) >= n:
            break
    return out


async def _show_cooldown(target, state: FSMContext) -> None:
    """Заминка: пошагово движения каталога с GIF; если их нет — старый текст."""
    await state.update_data(phase_now="cooldown")  # дальше «завершить» не переспрашивает
    data = await state.get_data()
    cool_items = data.get("cool_items") or []
    # Если во время тренировки меняли упражнения — пересобираем заминку под фактические мышцы
    if data.get("replaced"):
        zones = [it.get("muscle_group", "") for it in data.get("items", [])]
        rebuilt = _cooldown_for_zones(zones, equipment=data.get("equipment"))
        if rebuilt:
            cool_items = rebuilt
            await state.update_data(cool_items=cool_items)
    if cool_items:
        await state.update_data(cool_idx=0)
        await _step(target, state, "🧘 Финишная прямая — заминка по одному движению.")
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
        await _step(target, state, f"⏱ Отдых {rest} сек — дам сигнал, когда продолжать.")
        await state.update_data(cur_set=data["cur_set"] + 1, pending_reps=None)
        _start_rest(target, rest, state)  # карточку подхода покажем ПОСЛЕ отдыха
    elif i + 1 < len(items):
        rest = item.get("rest_sec") or 60
        nxt = items[i + 1]
        await _step(target, state,
                    f"⏱ Отдых {rest} сек. Дальше: <b>{nxt['name']}</b> — {_equipment_note(nxt)}.")
        await state.update_data(cur_item=i + 1, cur_set=1, pending_reps=None, suggest=None)
        _start_rest(target, rest, state)
    else:
        _cancel_rest(target.chat.id)
        data2 = await state.get_data()
        first_cool = (data2.get("cool_items") or [{}])[0].get("name")
        nxt = f" Дальше: <b>{first_cool}</b> — {_equipment_note({'name': first_cool})}." if first_cool else ""
        await _rest_between_phases(
            target, state=state, text=f"💪 Основная часть готова! Отдышись ~30–60 сек — и лёгкая заминка 🧘{nxt}")
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
    data = await state.get_data()
    if data.get("phase_now") == "cooldown":
        await cb.answer()
        await _finish(cb.message, state)
        return
    await cb.message.answer("Завершить тренировку?", reply_markup=finish_confirm_kb())
    await cb.answer()


@router.callback_query(Workout.in_progress, F.data == "wk:finish_cont")
async def finish_cont(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Продолжаем")
    # Возвращаем ровно туда, где были: на тот же подход или на тот же шаг заминки
    data = await state.get_data()
    phase = data.get("phase_now", "main")
    if phase == "cooldown":
        await _show_cooldown_step(cb.message, state)
    elif phase == "warmup":
        await _show_warmup_step(cb.message, state)
    else:
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


async def _rest_between_phases(target, text: str, state: FSMContext | None = None) -> None:
    """Короткая пауза-подсказка между фазами (после разминки / перед заминкой)."""
    if state is not None:
        await _step(target, state, text)
    else:
        await target.answer(text)


@router.callback_query(Workout.in_progress, F.data == "wk:warmup_done")
async def warmup_done(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _rest_between_phases(cb.message, state=state, text="🧘 Разминка окончена — переведи дух ~30 сек, и переходим к основной части 💪")
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
        await _rest_between_phases(cb.message, state=state, text="🧘 Разминка окончена — переведи дух ~30 сек, и переходим к основной части 💪")
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


def _start_rest(message, seconds: int, state: FSMContext | None = None) -> None:
    _cancel_rest(message.chat.id)
    _rest_tasks[message.chat.id] = asyncio.create_task(_rest_timer(message, seconds, state))


async def _rest_timer(message, seconds: int, state: FSMContext | None = None) -> None:
    """Отсчёт отдыха: сигнал в середине (для длинных), «время!» в конце — и ТОЛЬКО ПОТОМ
    показываем карточку подхода (чтобы она была внизу, под сигналом «время», а не терялась выше)."""
    try:
        if seconds >= 75:
            await asyncio.sleep(seconds / 2)
            await _step(message, state, f"⏳ Половина отдыха, осталось ~{seconds // 2} сек.")
            await asyncio.sleep(seconds - seconds / 2)
        else:
            await asyncio.sleep(seconds)
        await _step(message, state, "⏱ Время! Следующий подход 💪")
        if state is not None:
            await _show_set(message, state)
    except asyncio.CancelledError:
        return  # отдых отменён (завершение/пропуск) — карточку не показываем
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

        # Оценка калорий — по ФАКТУ, с учётом ВСЕХ фаз (разминка + основная + заминка) и длительности.
        logged = await repo.session_set_logs(db, session.id)
        warm_items = data.get("warm_items") or []
        cool_items = data.get("cool_items") or []
        phase = data.get("phase_now")
        warm_done = len(warm_items) if phase in ("main", "cooldown") else (
            data.get("warm_idx", 0) + 1 if phase == "warmup" else 0
        )
        cool_done = (data.get("cool_idx", 0) + 1) if phase == "cooldown" else 0
        dur_min = None
        if session.started_at and session.finished_at:
            dur_min = max(1, round((session.finished_at - session.started_at).total_seconds() / 60))
        extra = []
        if warm_done:
            extra.append(f"разминка: {warm_done} движений")
        if cool_done:
            extra.append(f"заминка: {cool_done} движений (растяжка)")
        if dur_min:
            extra.append(f"общая длительность ~{dur_min} мин")
        burn_summary = summary + (" | " + "; ".join(extra) if extra else "")
        # Активность была, если сделаны подходы ИЛИ хотя бы разминка
        if logged or warm_done:
            burned = await llm.estimate_burn(
                burn_summary, float(user.weight_kg) if user.weight_kg else None, user.sex
            )
        else:
            burned = 0
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
    msg = md_bold_to_html(feedback) if feedback else "Отличная работа!"
    if burned:
        msg += f"\n\n🔥 Потрачено ~{burned} ккал за тренировку."
    await target.answer(msg, reply_markup=main_menu())

    sid = data.get("session_id")  # state уже очищен — берём id из прочитанных ранее данных
    # Микро-прогрессия: по итогам подходов и ощущений корректируем нагрузку в плане.
    # Правила детерминированные (без LLM), изменение отменяемо кнопкой.
    try:
        async with async_session() as db:
            user2 = await repo.get_user_by_tg(db, target.chat.id)
            changes = await repo.apply_progression(db, user2.id, sid) if (user2 and sid) else []
        if changes:
            lines = ["📈 <b>Обновил нагрузку на следующий раз</b>"]
            for ch in changes:
                lines.append(f"• {ch['name']}: {ch['old_sets']}×{ch['old_reps']} → "
                             f"{ch['new_sets']}×{ch['new_reps']}")
            import json as _json
            from app.core import limits as _lim
            try:  # снимок для отмены (сутки в Redis)
                r = _lim._client()
                await r.set(f"prog_undo:{target.chat.id}", _json.dumps(changes), ex=86400)
            except Exception:
                pass
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="↩️ Оставить как было", callback_data="prog:undo")
            ]])
            await target.answer("\n".join(lines), reply_markup=kb)
    except Exception as exc:
        logger.warning("прогрессия не применена: %s", exc)


@router.callback_query(F.data == "prog:undo")
async def progression_undo(cb: CallbackQuery) -> None:
    """Откат автоматической прогрессии нагрузки."""
    import json as _json
    from app.core import limits as _lim

    changes = []
    try:
        r = _lim._client()
        raw = await r.get(f"prog_undo:{cb.from_user.id}")
        changes = _json.loads(raw) if raw else []
    except Exception:
        pass
    if not changes:
        await cb.answer("Уже нечего откатывать", show_alert=True)
        return
    async with async_session() as db:
        n = await repo.revert_progression(db, changes)
    try:
        r = _lim._client()
        await r.delete(f"prog_undo:{cb.from_user.id}")
    except Exception:
        pass
    await cb.answer("Вернул прежнюю нагрузку")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(f"↩️ Оставил нагрузку как была ({n} упр.).")


# ---------- Техника и замена ----------

@router.callback_query(Workout.in_progress, F.data == "wk:howto")
async def show_howto(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    item = data["items"][data["cur_item"]]
    # Готовый разбор из каталога (ошибки + легче/тяжелее), быстро и без затрат.
    text = (item.get("howto") or "").strip()
    if not text:
        text = (item.get("technique") or "Нет подсказок по этому упражнению.").strip()
    await cb.message.answer(f"<b>Ошибки и варианты — {item['name']}</b>\n{text}")


@router.callback_query(Workout.in_progress, F.data == "wk:replace")
async def replace_start(cb: CallbackQuery, state: FSMContext) -> None:
    """Показываем варианты замены — приоритет той же группе мышц, с указанием группы."""
    data = await state.get_data()
    cur = data["items"][data["cur_item"]]
    cur_ex_id = cur["exercise_id"]
    cur_group = (cur.get("muscle_group") or "").split("/")[0].strip().lower()
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from app.core import catalog

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        equip = (user.equipment if user else None)
        level = (user.level if user else None)
        # Кандидаты замены — из ТОЙ ЖЕ палитры, что и генерация плана: уже отфильтрованы
        # по инвентарю И уровню (новичку — без плиометрики и сложного). Единый источник правды.
        pool = catalog.main_candidates(equip, level, limit=400)
        # Резолвим названия каталога в упражнения БД (для callback по id)
        opts = []
        for e in pool:
            if e["name"] == cur["name"]:
                continue
            ex = await repo.find_exercise_by_name(db, e["name"])
            if ex:
                opts.append((ex, e.get("muscle_group") or "—"))

    # Сначала — та же группа мышц (равнозначная замена), потом остальные из палитры
    def same_group(mg: str) -> bool:
        return bool(cur_group) and cur_group in (mg or "").lower()

    opts.sort(key=lambda t: (not same_group(t[1]), t[0].name))
    if not opts:
        await cb.message.answer("Не нашёл подходящих замен под твой инвентарь и уровень 🤔")
        await cb.answer()
        return
    rows = [
        [InlineKeyboardButton(text=f"{ex.name} · {mg}", callback_data=f"repex:{ex.id}")]
        for ex, mg in opts[:8]
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
    # Новое упражнение начинаем с 1-го подхода → покажется карточка с GIF и описанием.
    # Флаг replaced → заминку в конце пересоберём под фактические мышцы.
    await state.update_data(items=items, suggest=None, cur_set=1, pending_reps=None, replaced=True)
    await vector.add_memory(
        user.id, f"change-{cb.id}", note, {"type": "change", "date": str(_today())}
    )
    unit = "сек" if is_time else "повт."
    await cb.message.answer(f"Готово: теперь {ex.name} — {load['sets']}×{load['reps']} {unit}.")
    await cb.answer()
    await _show_set(cb.message, state)


# ---------- Замена движения разминки/заминки ----------

def _disliked_set(user) -> set[str]:
    return {x.strip() for x in (user.disliked or "").split(",") if x.strip()}


async def _pick_phase_alt(phase: str, cur: dict, equipment: str | None,
                          used: set[str], disliked: set[str]) -> dict | None:
    """Каталожная альтернатива движению разминки/заминки: та же группа мышц, доступный
    инвентарь, есть GIF, не использована сегодня и не в «нелюбимых»."""
    from app.core import catalog
    zone = (cur.get("muscle_group") or "").split("/")[0].strip().lower()
    pool = (catalog.warmup_candidates(equipment or "", zones=[zone] if zone else None)
            if phase == "warmup" else
            catalog.cooldown_candidates(equipment or "", zones=[zone] if zone else None))
    for e in pool:
        if not e.get("gif") or e["name"] in used or e["name"] in disliked:
            continue
        if e["name"] == cur.get("name"):
            continue
        return {"name": e["name"], "muscle_group": e["muscle_group"],
                "technique": e["technique"], "gif": e["gif"]}
    return None


@router.callback_query(Workout.in_progress, F.data.startswith("wk:swap:"))
async def swap_ask(cb: CallbackQuery, state: FSMContext) -> None:
    """Спрашиваем: заменить только сейчас или больше не предлагать это движение."""
    phase = cb.data.split(":")[2]
    data = await state.get_data()
    idx = data.get("warm_idx", 0) if phase == "warmup" else data.get("cool_idx", 0)
    await cb.answer()
    await cb.message.answer("Заменить это движение:", reply_markup=swap_scope_kb(phase, idx))


@router.callback_query(Workout.in_progress, F.data == "wk:swapc")
async def swap_cancel(cb: CallbackQuery) -> None:
    await cb.answer("Оставляем как есть")
    try:
        await cb.message.delete()
    except Exception:
        pass


async def _do_swap(cb: CallbackQuery, state: FSMContext, phase: str, idx: int, forever: bool) -> None:
    data = await state.get_data()
    key_items = "warm_items" if phase == "warmup" else "cool_items"
    items = list(data.get(key_items) or [])
    if not items or idx >= len(items):
        await cb.answer("Движение не найдено", show_alert=True)
        return
    cur = items[idx]
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, cb.from_user.id)
        disliked = _disliked_set(user) if user else set()
        if forever and user:
            disliked.add(cur.get("name", ""))
            user.disliked = ",".join(sorted(x for x in disliked if x))
            await db.commit()
    used = {it.get("name", "") for it in items}
    alt = await _pick_phase_alt(phase, cur, data.get("equipment"), used, disliked)
    if not alt:
        await cb.answer("Нет подходящей замены под твой инвентарь 🤔", show_alert=True)
        return
    items[idx] = alt
    await state.update_data(**{key_items: items})
    await cb.answer("Заменил" + (" и больше не предложу" if forever else ""))
    try:
        await cb.message.delete()  # убираем сообщение с выбором
    except Exception:
        pass
    if phase == "warmup":
        await _show_warmup_step(cb.message, state)
    else:
        await _show_cooldown_step(cb.message, state)


@router.callback_query(Workout.in_progress, F.data.startswith("wk:swapn:"))
async def swap_now(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, phase, idx = cb.data.split(":")
    await _do_swap(cb, state, phase, int(idx), forever=False)


@router.callback_query(Workout.in_progress, F.data.startswith("wk:swapf:"))
async def swap_forever(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, phase, idx = cb.data.split(":")
    await _do_swap(cb, state, phase, int(idx), forever=True)
