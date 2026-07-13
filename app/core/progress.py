"""Расчёт метрик, текстовых сводок и недельных отчётов."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import repository as repo
from app.core.models import Session


async def format_session_summary(db: AsyncSession, session: Session) -> str:
    """Короткий текст-итог сессии для памяти и промпта."""
    logs = await repo.session_set_logs(db, session.id)
    by_ex: dict[int, list] = {}
    for log in logs:
        by_ex.setdefault(log.exercise_id, []).append(log)

    parts: list[str] = []
    for ex_id, rows in by_ex.items():
        ex = await repo.get_exercise(db, ex_id)
        name = ex.name if ex else f"упр.{ex_id}"
        reps = "/".join(str(r.reps) for r in rows)
        effort = rows[-1].effort or "-"
        parts.append(f"{name} {len(rows)}×{reps} (ощущение {effort})")
    label = "тренировка"
    return f"{label}: " + "; ".join(parts) if parts else f"{label}: без записей"


WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


async def plan_text(db: AsyncSession, user_id: int) -> str:
    """Текущий план недели одной строкой-блоком для контекста тренера."""
    templates = await repo.list_templates(db, user_id)
    if not templates:
        return "план не настроен"
    lines = []
    for tpl in templates:
        day = WEEKDAYS[tpl.weekday] if tpl.weekday is not None else "—"
        items = await repo.list_template_items(db, tpl.id)
        parts = []
        for it in items:
            ex = await repo.get_exercise(db, it.exercise_id)
            parts.append(f"{ex.name if ex else '?'} {it.target_sets}×{it.target_reps}")
        lines.append(f"{tpl.label} ({day}): " + ", ".join(parts))
    return "; ".join(lines)


async def build_facts(db: AsyncSession, user_id: int, limit: int = 30) -> str:
    """Текстовая выжимка последних тренировок (до ~2 месяцев) для промпта LLM."""
    sessions = await repo.recent_sessions(db, user_id, limit=limit)
    if not sessions:
        return "Пока нет завершённых тренировок."
    lines: list[str] = []
    for s in sessions:
        summary = await format_session_summary(db, s)
        d = s.finished_at.date().isoformat() if s.finished_at else "?"
        lines.append(f"[{d}] {summary}")
    return "\n".join(lines)


async def full_stats(db: AsyncSession, user_id: int) -> str:
    """Расширенная статистика: всего, неделя, вес, рекорды."""
    total = await repo.total_done_sessions(db, user_id)

    since = date.today() - timedelta(days=7)
    week = await repo.sessions_in_period(db, user_id, since)
    week_done = len([s for s in week if s.status == "done"])
    week_planned = len(week)

    weight = await repo.current_weight(db, user_id)
    dw = await repo.weight_change(db, user_id, days=30)
    records = await repo.exercise_records(db, user_id)

    lines = ["📊 <b>Статистика</b>", ""]
    lines.append(f"🏋️ Всего тренировок: <b>{total}</b>")
    lines.append(f"📅 За неделю: <b>{week_done}</b> из {week_planned}")

    if weight is not None:
        w_line = f"⚖️ Текущий вес: <b>{weight:g} кг</b>"
        if dw is not None:
            sign = "−" if dw < 0 else "+"
            w_line += f" ({sign}{abs(dw):.1f} кг за месяц)"
        lines.append(w_line)
    else:
        lines.append("⚖️ Вес ещё не записан")

    if records:
        lines.append("")
        lines.append("🏆 <b>Рекорды</b> (макс. повторов в подходе):")
        for name, best in records:
            lines.append(f"• {name}: {best}")

    return "\n".join(lines)


async def weekly_report(db: AsyncSession, user_id: int) -> str:
    """Недельный отчёт: тренировки, динамика веса."""
    since = date.today() - timedelta(days=7)
    sessions = await repo.sessions_in_period(db, user_id, since)
    done = [s for s in sessions if s.status == "done"]
    planned = len(sessions)
    dw = await repo.weight_change(db, user_id, days=7)

    parts = [f"Тренировок: {len(done)} из {planned}."]
    if dw is not None:
        sign = "−" if dw < 0 else "+"
        parts.append(f"Вес: {sign}{abs(dw):.1f} кг.")
    if len(done) >= planned and planned > 0:
        parts.append("Держишь темп 💪")
    return " ".join(parts)
