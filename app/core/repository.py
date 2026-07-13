"""Слой доступа к данным: операции над сущностями и метрики."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    ChatMessage,
    Exercise,
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

    workouts: [{"weekday": int, "exercises": [{"name","sets","reps","muscle_group","technique"}]}]
    Недостающие упражнения автоматически заводятся в каталог. Возвращает число дней.
    """
    # Деактивируем прежний план
    old = await db.execute(select(WorkoutTemplate).where(WorkoutTemplate.user_id == user_id))
    for tpl in old.scalars().all():
        tpl.active = False

    for i, w in enumerate(sorted(workouts, key=lambda x: x.get("weekday", 0))):
        template = WorkoutTemplate(
            user_id=user_id,
            label=f"День {i + 1}",
            weekday=w.get("weekday", 0),
            warmup=w.get("warmup"),
            cooldown=w.get("cooldown"),
        )
        db.add(template)
        await db.flush()
        for idx, ex in enumerate(w.get("exercises", [])):
            exo = await find_or_create_exercise(
                db,
                ex.get("name", "Упражнение"),
                ex.get("muscle_group"),
                ex.get("technique"),
                environment=ex.get("environment") or environment,
                equipment=ex.get("equipment"),
            )
            db.add(
                TemplateItem(
                    template_id=template.id,
                    exercise_id=exo.id,
                    target_sets=ex.get("sets") or 3,
                    target_reps=ex.get("reps") or 10,
                    rest_sec=ex.get("rest_sec") or 60,
                    order_idx=idx,
                )
            )
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


# ---------- Метрики для контекста LLM и отчётов ----------

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
