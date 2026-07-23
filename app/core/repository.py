"""Слой доступа к данным: операции над сущностями и метрики."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


def _local_day_start(days_ago: int = 0) -> datetime:
    """Начало локального дня (по TZ бота) N дней назад, в UTC для сравнения с logged_at."""
    tz = ZoneInfo(settings.tz)
    start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return (start_local - timedelta(days=days_ago)).astimezone(timezone.utc)

from app.core.models import (
    ChatMessage,
    Exercise,
    Meal,
    MealItem,
    Session,
    SetLog,
    TemplateItem,
    User,
    WeightLog,
    WorkoutTemplate,
)


# ---------- Пользователи ----------

async def get_user_by_tg(db: AsyncSession, tg_id: int) -> User | None:
    res = await db.execute(select(User).where(User.tg_id == tg_id))
    return res.scalar_one_or_none()


async def create_user(db: AsyncSession, tg_id: int, name: str | None = None) -> User:
    user = User(tg_id=tg_id, name=name)
    db.add(user)
    await db.commit()
    return user


async def reset_user(db: AsyncSession, user: User) -> None:
    """Полный сброс: удаляет все данные пользователя и очищает профиль (кроме tg_id)."""
    # id тренировок пользователя — для удаления связанных сетов
    sess_ids = (
        await db.execute(select(Session.id).where(Session.user_id == user.id))
    ).scalars().all()
    if sess_ids:
        await db.execute(delete(SetLog).where(SetLog.session_id.in_(sess_ids)))
    await db.execute(delete(Session).where(Session.user_id == user.id))

    tpl_ids = (
        await db.execute(select(WorkoutTemplate.id).where(WorkoutTemplate.user_id == user.id))
    ).scalars().all()
    if tpl_ids:
        await db.execute(delete(TemplateItem).where(TemplateItem.template_id.in_(tpl_ids)))
    await db.execute(delete(WorkoutTemplate).where(WorkoutTemplate.user_id == user.id))

    await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    await db.execute(delete(WeightLog).where(WeightLog.user_id == user.id))
    # Сначала ингредиенты (FK meal_items.meal_id без каскада), потом сами блюда
    meal_ids = (
        await db.execute(select(Meal.id).where(Meal.user_id == user.id))
    ).scalars().all()
    if meal_ids:
        await db.execute(delete(MealItem).where(MealItem.meal_id.in_(meal_ids)))
    await db.execute(delete(Meal).where(Meal.user_id == user.id))

    # Обнуляем профиль (строка пользователя остаётся, tg_id сохраняется)
    user.goal = None
    user.weight_kg = None
    user.system_prompt = None
    user.profile_summary = None
    user.train_hour = None
    user.train_minute = None
    user.chat_summary = None
    user.environment = None
    user.equipment = None
    user.sex = None
    user.age = None
    user.activity = None
    user.level = None
    user.exercises_per_day = None
    user.nutrition_goal = None
    await db.commit()


async def get_or_create_user(db: AsyncSession, tg_id: int, name: str | None = None) -> User:
    user = await get_user_by_tg(db, tg_id)
    if user is None:
        user = await create_user(db, tg_id, name)
    return user


async def update_user_profile(
    db: AsyncSession, user: User, goal: str | None = None, weight_kg: float | None = None
) -> User:
    if goal is not None:
        user.goal = goal
    if weight_kg is not None:
        user.weight_kg = weight_kg
        db.add(WeightLog(user_id=user.id, weight_kg=weight_kg))
    await db.commit()
    return user


# ---------- Память диалога (окно + резюме) ----------

async def add_chat_message(db: AsyncSession, user_id: int, role: str, content: str) -> None:
    db.add(ChatMessage(user_id=user_id, role=role, content=content))
    await db.commit()


async def get_chat_window(db: AsyncSession, user_id: int, limit: int = 12) -> list[dict]:
    """Последние сообщения диалога в хронологическом порядке."""
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    rows = list(res.scalars().all())
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


async def count_chat_messages(db: AsyncSession, user_id: int) -> int:
    res = await db.execute(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.user_id == user_id)
    )
    return int(res.scalar_one())


async def pop_oldest_chat_messages(db: AsyncSession, user_id: int, count: int) -> list[dict]:
    """Забирает и удаляет `count` самых старых сообщений (для суммаризации)."""
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at)
        .limit(count)
    )
    rows = list(res.scalars().all())
    out = [{"role": r.role, "content": r.content} for r in rows]
    for r in rows:
        await db.delete(r)
    await db.commit()
    return out


async def set_chat_summary(db: AsyncSession, user_id: int, summary: str) -> None:
    user = await db.get(User, user_id)
    if user:
        user.chat_summary = summary
        await db.commit()


# ---------- Исполнители действий тренера ----------

async def find_exercise_by_name(db: AsyncSession, name: str) -> Exercise | None:
    res = await db.execute(select(Exercise).where(Exercise.name.ilike(f"%{name}%")).limit(1))
    return res.scalar_one_or_none()


async def find_or_create_exercise(
    db: AsyncSession,
    name: str,
    muscle_group: str | None = None,
    technique: str | None = None,
    environment: str | None = None,
    equipment: str | None = None,
) -> Exercise:
    """Находит упражнение по названию или создаёт новое (автопополнение каталога)."""
    name = name.strip()
    ex = await find_exercise_by_name(db, name)
    if ex:
        return ex
    ex = Exercise(
        name=name,
        muscle_group=muscle_group,
        technique=technique or "Техника не описана.",
        environment=environment,
        equipment=equipment,
    )
    db.add(ex)
    await db.flush()
    return ex


async def set_environment(
    db: AsyncSession, user: User, environment: str | None, equipment: str | None
) -> User:
    """Сохраняет место тренировок и инвентарь пользователя."""
    if environment is not None:
        user.environment = environment
    if equipment is not None:
        user.equipment = equipment
    await db.commit()
    return user


async def shift_templates_by_day(db: AsyncSession, user_id: int, days: int = 1) -> None:
    """Сдвигает дни недели всех активных шаблонов на `days` вперёд (по модулю 7)."""
    res = await db.execute(
        select(WorkoutTemplate).where(
            WorkoutTemplate.user_id == user_id, WorkoutTemplate.active.is_(True)
        )
    )
    for tpl in res.scalars().all():
        if tpl.weekday is not None:
            tpl.weekday = (tpl.weekday + days) % 7
    await db.commit()


async def active_weekdays(db: AsyncSession, user_id: int) -> list[int]:
    """Дни недели активного плана (для перегенерации из настроек)."""
    res = await db.execute(
        select(WorkoutTemplate.weekday).where(
            WorkoutTemplate.user_id == user_id, WorkoutTemplate.active.is_(True)
        )
    )
    return sorted({w for w in res.scalars().all() if w is not None})


async def build_custom_plan(
    db: AsyncSession, user_id: int, workouts: list[dict], environment: str | None = None
) -> int:
    """Пересобирает план из структуры тренера.

    workouts: [{"weekday", "warmup":[{name,...}], "cooldown":[{name,...}],
                "exercises":[{name,sets,reps,rest_sec,muscle_group,technique,gif,...}]}]
    Разминка/заминка сохраняются как элементы плана с фазой (phase). Возвращает число дней.
    """
    # Деактивируем прежний план
    old = await db.execute(select(WorkoutTemplate).where(WorkoutTemplate.user_id == user_id))
    for tpl in old.scalars().all():
        tpl.active = False

    for i, w in enumerate(sorted(workouts, key=lambda x: x.get("weekday", 0))):
        warm = w.get("warmup") or []
        cool = w.get("cooldown") or []
        # Обратная совместимость: если разминка/заминка пришла строкой (старый формат) —
        # сохраняем как текст, фазовых элементов не создаём
        warm_text = warm if isinstance(warm, str) else "\n".join(f"• {m['name']}" for m in warm)
        cool_text = cool if isinstance(cool, str) else "\n".join(f"• {m['name']}" for m in cool)
        if isinstance(warm, str):
            warm = []
        if isinstance(cool, str):
            cool = []
        template = WorkoutTemplate(
            user_id=user_id,
            label=f"День {i + 1}",
            weekday=w.get("weekday", 0),
            # Текстовая сводка — для показа плана и обратной совместимости
            warmup=warm_text or None,
            cooldown=cool_text or None,
        )
        db.add(template)
        await db.flush()

        order = 0
        for m in warm:
            exo = await find_or_create_exercise(
                db, m.get("name", "Разминка"), m.get("muscle_group"), m.get("technique"),
                environment=m.get("environment") or environment, equipment=m.get("equipment"),
            )
            db.add(TemplateItem(template_id=template.id, exercise_id=exo.id,
                                order_idx=order, phase="warmup"))
            order += 1
        for ex in w.get("exercises", []):
            exo = await find_or_create_exercise(
                db, ex.get("name", "Упражнение"), ex.get("muscle_group"), ex.get("technique"),
                environment=ex.get("environment") or environment, equipment=ex.get("equipment"),
            )
            db.add(TemplateItem(template_id=template.id, exercise_id=exo.id,
                                target_sets=ex.get("sets") or 3, target_reps=ex.get("reps") or 10,
                                rest_sec=ex.get("rest_sec") or 60, order_idx=order, phase="main"))
            order += 1
        for m in cool:
            exo = await find_or_create_exercise(
                db, m.get("name", "Заминка"), m.get("muscle_group"), m.get("technique"),
                environment=m.get("environment") or environment, equipment=m.get("equipment"),
            )
            db.add(TemplateItem(template_id=template.id, exercise_id=exo.id,
                                order_idx=order, phase="cooldown"))
            order += 1
    await db.commit()
    return len(workouts)


async def _active_items_by_exercise(db: AsyncSession, user_id: int, exercise_id: int) -> list[TemplateItem]:
    res = await db.execute(
        select(TemplateItem)
        .join(WorkoutTemplate, WorkoutTemplate.id == TemplateItem.template_id)
        .where(
            WorkoutTemplate.user_id == user_id,
            WorkoutTemplate.active.is_(True),
            TemplateItem.exercise_id == exercise_id,
        )
    )
    return list(res.scalars().all())


async def adjust_load(
    db: AsyncSession, user_id: int, exercise_id: int, sets: int | None, reps: int | None
) -> int:
    """Меняет цель подходов/повторов упражнения во всех активных шаблонах. Возвращает число правок."""
    items = await _active_items_by_exercise(db, user_id, exercise_id)
    for it in items:
        if sets is not None:
            it.target_sets = sets
        if reps is not None:
            it.target_reps = reps
    await db.commit()
    return len(items)


async def replace_exercise_in_plan(
    db: AsyncSession, user_id: int, old_exercise_id: int, new_exercise_id: int
) -> int:
    """Заменяет упражнение во всех активных шаблонах пользователя."""
    items = await _active_items_by_exercise(db, user_id, old_exercise_id)
    for it in items:
        it.exercise_id = new_exercise_id
    await db.commit()
    return len(items)


async def set_train_time(db: AsyncSession, user: User, hour: int, minute: int) -> User:
    """Сохраняет время тренировки для напоминаний."""
    user.train_hour = hour
    user.train_minute = minute
    await db.commit()
    return user


async def save_personalization(
    db: AsyncSession,
    user: User,
    system_prompt: str | None,
    profile_summary: str | None,
    goal: str | None,
) -> User:
    """Сохраняет результаты интервью: персональный промпт и профиль."""
    if system_prompt:
        user.system_prompt = system_prompt
    if profile_summary:
        user.profile_summary = profile_summary
    if goal:
        user.goal = goal
    await db.commit()
    return user


# ---------- Упражнения и шаблоны ----------

async def list_templates(db: AsyncSession, user_id: int) -> list[WorkoutTemplate]:
    res = await db.execute(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.user_id == user_id, WorkoutTemplate.active.is_(True))
        .order_by(WorkoutTemplate.weekday)
    )
    return list(res.scalars().all())


async def get_template_for_weekday(
    db: AsyncSession, user_id: int, weekday: int
) -> WorkoutTemplate | None:
    res = await db.execute(
        select(WorkoutTemplate).where(
            WorkoutTemplate.user_id == user_id,
            WorkoutTemplate.weekday == weekday,
            WorkoutTemplate.active.is_(True),
        )
    )
    return res.scalar_one_or_none()


async def get_template(db: AsyncSession, template_id: int) -> WorkoutTemplate | None:
    return await db.get(WorkoutTemplate, template_id)


async def list_template_items(db: AsyncSession, template_id: int) -> list[TemplateItem]:
    res = await db.execute(
        select(TemplateItem)
        .where(TemplateItem.template_id == template_id)
        .order_by(TemplateItem.order_idx)
    )
    return list(res.scalars().all())


async def get_exercise(db: AsyncSession, exercise_id: int) -> Exercise | None:
    return await db.get(Exercise, exercise_id)


async def replace_template_item_exercise(
    db: AsyncSession, item_id: int, new_exercise_id: int
) -> None:
    """Замена упражнения в плане «навсегда»."""
    item = await db.get(TemplateItem, item_id)
    if item is not None:
        item.exercise_id = new_exercise_id
        await db.commit()


# ---------- Сессии тренировок ----------

async def create_session(
    db: AsyncSession,
    user_id: int,
    template_id: int | None,
    planned_date: date | None = None,
    status: str = "planned",
) -> Session:
    session = Session(
        user_id=user_id,
        template_id=template_id,
        planned_date=planned_date,
        status=status,
    )
    db.add(session)
    await db.commit()
    return session


async def start_session(db: AsyncSession, session: Session) -> Session:
    session.status = "in_progress"
    session.started_at = datetime.now(timezone.utc)
    await db.commit()
    return session


async def finish_session(db: AsyncSession, session: Session) -> Session:
    session.status = "done"
    session.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return session


async def set_session_status(db: AsyncSession, session: Session, status: str) -> Session:
    session.status = status
    await db.commit()
    return session


async def delete_session(db: AsyncSession, session_id: int) -> None:
    """Полностью удаляет сессию и её подходы (досрочная отмена тренировки)."""
    await db.execute(delete(SetLog).where(SetLog.session_id == session_id))
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()


# ---------- Логи сетов ----------

async def log_set(
    db: AsyncSession,
    session_id: int,
    exercise_id: int,
    set_idx: int,
    reps: int,
    effort: str,
) -> SetLog:
    """Немедленная запись сета по клику кнопки."""
    row = SetLog(
        session_id=session_id,
        exercise_id=exercise_id,
        set_idx=set_idx,
        reps=reps,
        effort=effort,
    )
    db.add(row)
    await db.commit()
    return row


async def apply_progression(db: AsyncSession, user_id: int, session_id: int) -> None:
    """Прогрессия плана: по ощущениям сессии двигаем целевые повторы в шаблонах.

    Преобладало 'easy' → +1 повтор, 'hard' → −1 (в активных шаблонах пользователя).
    """
    logs = await session_set_logs(db, session_id)
    by_ex: dict[int, list[str]] = {}
    for log in logs:
        by_ex.setdefault(log.exercise_id, []).append(log.effort or "ok")
    for ex_id, efforts in by_ex.items():
        easy = efforts.count("easy")
        hard = efforts.count("hard")
        delta = 1 if easy > hard and easy >= len(efforts) / 2 else (-1 if hard > easy else 0)
        if delta == 0:
            continue
        items = await _active_items_by_exercise(db, user_id, ex_id)
        for it in items:
            if it.target_reps:
                it.target_reps = max(1, it.target_reps + delta)
    await db.commit()


async def session_set_logs(db: AsyncSession, session_id: int) -> list[SetLog]:
    res = await db.execute(
        select(SetLog).where(SetLog.session_id == session_id).order_by(SetLog.logged_at)
    )
    return list(res.scalars().all())


# ---------- Вес ----------

async def log_weight(db: AsyncSession, user_id: int, weight_kg: float) -> WeightLog:
    row = WeightLog(user_id=user_id, weight_kg=weight_kg)
    db.add(row)
    await db.commit()
    return row


# ---------- Питание ----------

async def add_meal(
    db: AsyncSession, user_id: int, analysis: dict, photo_file_id: str | None = None
) -> Meal:
    """Сохраняет приём пищи: итоговые БЖУ + ингредиенты.

    analysis: {"items":[{name,grams,kcal,protein,fat,carbs}], "total":{kcal,protein,fat,carbs}}
    """
    total = analysis.get("total", {})
    meal = Meal(
        user_id=user_id,
        photo_file_id=photo_file_id,
        kcal=total.get("kcal"),
        protein=total.get("protein"),
        fat=total.get("fat"),
        carbs=total.get("carbs"),
        note=analysis.get("dish") or analysis.get("note"),
    )
    db.add(meal)
    await db.flush()
    for it in analysis.get("items", []):
        db.add(
            MealItem(
                meal_id=meal.id,
                name=it.get("name", "?"),
                grams=it.get("grams"),
                kcal=it.get("kcal"),
                protein=it.get("protein"),
                fat=it.get("fat"),
                carbs=it.get("carbs"),
            )
        )
    await db.commit()
    return meal


async def meals_by_day(db: AsyncSession, user_id: int, days: int = 7) -> list[dict]:
    """Суммы БЖУ/ккал по дням за последние `days` дней (только дни с записями)."""
    since = _local_day_start(days - 1)
    # Группируем по локальному дню (по TZ бота), а не по UTC
    day = func.date_trunc("day", func.timezone(settings.tz, Meal.logged_at))
    res = await db.execute(
        select(
            day.label("d"),
            func.coalesce(func.sum(Meal.kcal), 0),
            func.coalesce(func.sum(Meal.protein), 0),
            func.coalesce(func.sum(Meal.fat), 0),
            func.coalesce(func.sum(Meal.carbs), 0),
        )
        .where(Meal.user_id == user_id, Meal.logged_at >= since)
        .group_by(day)
        .order_by(day)
    )
    return [
        {
            "date": d,
            "kcal": round(float(k)),
            "protein": round(float(p)),
            "fat": round(float(f)),
            "carbs": round(float(c)),
        }
        for d, k, p, f, c in res.all()
    ]


async def recent_dishes(db: AsyncSession, user_id: int, limit: int = 20) -> list[dict]:
    """Недавно записанные блюда (для консистентности разбора): dish + суммарные КБЖУ."""
    res = await db.execute(
        select(Meal.note, Meal.kcal, Meal.protein, Meal.fat, Meal.carbs)
        .where(Meal.user_id == user_id, Meal.note.isnot(None))
        .order_by(Meal.logged_at.desc())
        .limit(limit)
    )
    seen: set[str] = set()
    out: list[dict] = []
    for note, kcal, protein, fat, carbs in res.all():
        name = (note or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "dish": name,
                "kcal": round(float(kcal or 0)),
                "protein": round(float(protein or 0)),
                "fat": round(float(fat or 0)),
                "carbs": round(float(carbs or 0)),
            }
        )
    return out


async def today_totals(db: AsyncSession, user_id: int) -> dict:
    """Суммарные БЖУ/ккал за сегодня (по локальной дате сервера)."""
    since = _local_day_start()  # начало сегодняшнего дня по TZ бота
    res = await db.execute(
        select(
            func.coalesce(func.sum(Meal.kcal), 0),
            func.coalesce(func.sum(Meal.protein), 0),
            func.coalesce(func.sum(Meal.fat), 0),
            func.coalesce(func.sum(Meal.carbs), 0),
            func.count(Meal.id),
        ).where(Meal.user_id == user_id, Meal.logged_at >= since)
    )
    kcal, protein, fat, carbs, count = res.one()
    return {
        "kcal": round(float(kcal)),
        "protein": round(float(protein)),
        "fat": round(float(fat)),
        "carbs": round(float(carbs)),
        "meals": int(count),
    }


# ---------- Метрики для контекста LLM и отчётов ----------

async def planned_session_on(db: AsyncSession, user_id: int, day: date) -> Session | None:
    """Явно запланированная (перенесённая) сессия на дату — статус 'planned'."""
    res = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.planned_date == day,
            Session.status == "planned",
        )
    )
    return res.scalars().first()


async def has_session_status_on(db: AsyncSession, user_id: int, day: date, status: str) -> bool:
    res = await db.execute(
        select(func.count())
        .select_from(Session)
        .where(Session.user_id == user_id, Session.planned_date == day, Session.status == status)
    )
    return int(res.scalar_one()) > 0


async def recent_sessions(db: AsyncSession, user_id: int, limit: int = 5) -> list[Session]:
    res = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.status == "done")
        .order_by(Session.finished_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def sessions_in_period(
    db: AsyncSession, user_id: int, since: date
) -> list[Session]:
    res = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.planned_date >= since,
        )
    )
    return list(res.scalars().all())


async def weight_change(db: AsyncSession, user_id: int, days: int = 7) -> float | None:
    """Разница веса за период (последний минус первый в окне)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    res = await db.execute(
        select(WeightLog)
        .where(WeightLog.user_id == user_id, WeightLog.logged_at >= since)
        .order_by(WeightLog.logged_at)
    )
    rows = list(res.scalars().all())
    if len(rows) < 2:
        return None
    return float(rows[-1].weight_kg) - float(rows[0].weight_kg)


async def calories_burned(db: AsyncSession, user_id: int, days: int = 7) -> int:
    """Суммарно потрачено ккал за тренировки за период (дней)."""
    since = _local_day_start(days - 1)
    res = await db.execute(
        select(func.coalesce(func.sum(Session.kcal_burned), 0)).where(
            Session.user_id == user_id,
            Session.status == "done",
            Session.finished_at >= since,
        )
    )
    return int(res.scalar_one())


async def total_done_sessions(db: AsyncSession, user_id: int) -> int:
    """Всего завершённых тренировок."""
    res = await db.execute(
        select(func.count()).select_from(Session).where(
            Session.user_id == user_id, Session.status == "done"
        )
    )
    return int(res.scalar_one())


async def exercise_records(db: AsyncSession, user_id: int) -> list[tuple[str, int]]:
    """Личные рекорды по повторам в одном сете для каждого упражнения."""
    res = await db.execute(
        select(SetLog.exercise_id, func.max(SetLog.reps))
        .join(Session, Session.id == SetLog.session_id)
        .where(Session.user_id == user_id)
        .group_by(SetLog.exercise_id)
    )
    records: list[tuple[str, int]] = []
    for ex_id, best in res.all():
        if best is None:
            continue
        ex = await get_exercise(db, ex_id)
        records.append((ex.name if ex else f"упр.{ex_id}", int(best)))
    return records


async def current_weight(db: AsyncSession, user_id: int) -> float | None:
    """Последний записанный вес."""
    res = await db.execute(
        select(WeightLog.weight_kg)
        .where(WeightLog.user_id == user_id)
        .order_by(WeightLog.logged_at.desc())
        .limit(1)
    )
    val = res.scalar_one_or_none()
    return float(val) if val is not None else None


async def exercise_record(db: AsyncSession, user_id: int, exercise_id: int) -> int | None:
    """Личный рекорд по повторам в одном сете упражнения."""
    res = await db.execute(
        select(func.max(SetLog.reps))
        .join(Session, Session.id == SetLog.session_id)
        .where(Session.user_id == user_id, SetLog.exercise_id == exercise_id)
    )
    return res.scalar_one_or_none()
