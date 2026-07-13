"""Слой доступа к данным: операции над сущностями и метрики."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
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
