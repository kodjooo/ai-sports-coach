"""Расчёт метрик, текстовых сводок и недельных отчётов."""
from __future__ import annotations

from datetime import timedelta

from app.utils import local_today

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nutrition
from app.core import repository as repo
from app.core.models import Session, User


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
    """Расширенная статистика: всего, текущая неделя (с понедельника), вес."""
    total = await repo.total_done_sessions(db, user_id)

    today = local_today()
    since = today - timedelta(days=today.weekday())  # понедельник текущей недели
    days_win = today.weekday() + 1                    # Пн..сегодня включительно
    # Считаем только реальные тренировки (с подходами); пустые сессии не в счёт
    week_done = await repo.count_workouts_in_period(db, user_id, since)
    # План на неделю = число тренировочных дней (активных шаблонов)
    week_planned = len(await repo.list_templates(db, user_id))

    weight = await repo.current_weight(db, user_id)
    dw = await repo.weight_change(db, user_id, days=30)

    burned_week = await repo.calories_burned(db, user_id, days=days_win)

    lines = ["📊 <b>Статистика</b>", ""]
    lines.append(f"🏋️ Всего тренировок: <b>{total}</b>")
    lines.append(f"📅 На этой неделе: <b>{week_done}</b> из {week_planned}")
    if burned_week:
        lines.append(f"🔥 Потрачено за неделю: <b>~{burned_week}</b> ккал")

    if weight is not None:
        w_line = f"⚖️ Текущий вес: <b>{weight:g} кг</b>"
        if dw is not None:
            sign = "−" if dw < 0 else "+"
            w_line += f" ({sign}{abs(dw):.1f} кг за месяц)"
        lines.append(w_line)
    else:
        lines.append("⚖️ Вес ещё не записан")

    return "\n".join(lines)


async def weekly_report(db: AsyncSession, user_id: int) -> str:
    """Недельный отчёт: тренировки, динамика веса."""
    today = local_today()
    since = today - timedelta(days=today.weekday())  # с понедельника текущей недели
    sessions = await repo.sessions_in_period(db, user_id, since)
    done = [s for s in sessions if s.status == "done"]
    # План на неделю = число тренировочных дней (активных шаблонов)
    planned = len(await repo.list_templates(db, user_id))
    dw = await repo.weight_change(db, user_id, days=7)

    parts = [f"🏋️ Тренировок: {len(done)} из {planned}."]
    if dw is not None:
        sign = "−" if dw < 0 else "+"
        parts.append(f"Вес: {sign}{abs(dw):.1f} кг.")
    if len(done) >= planned and planned > 0:
        parts.append("Держишь темп 💪")

    nutri = await nutrition_week(db, user_id)
    text = " ".join(parts)
    if nutri:
        text += "\n\n" + nutri
    return text


async def nutrition_week(db: AsyncSession, user_id: int) -> str:
    """Недельная аналитика питания: средние КБЖУ, дни в норме, сравнение с нормой."""
    rows = await repo.meals_by_day(db, user_id, days=7)
    if not rows:
        return ""
    n = len(rows)
    avg_kcal = round(sum(r["kcal"] for r in rows) / n)
    avg_prot = round(sum(r["protein"] for r in rows) / n)
    avg_fat = round(sum(r["fat"] for r in rows) / n)
    avg_carb = round(sum(r["carbs"] for r in rows) / n)

    lines = ["🍎 <b>Питание за неделю</b>"]
    lines.append(f"Дней с записями: {n} из 7")
    lines.append(f"В среднем: {avg_kcal} ккал/день (Б{avg_prot} Ж{avg_fat} У{avg_carb})")

    user = await db.get(User, user_id)
    norm = nutrition.daily_norm(user) if user else None
    if norm:
        ok = over = under = 0
        for r in rows:
            if r["kcal"] > norm["kcal"] * 1.1:
                over += 1
            elif r["kcal"] < norm["kcal"] * 0.9:
                under += 1
            else:
                ok += 1
        diff = avg_kcal - norm["kcal"]
        sign = "+" if diff >= 0 else "−"
        lines.append(f"Норма: {norm['kcal']} ккал; в среднем {sign}{abs(diff)} ккал/день")
        lines.append(f"В норме: {ok} · перебор: {over} · недобор: {under}")
        if avg_prot < norm["protein"] * 0.9:
            lines.append("⚠️ Белка в среднем маловато — добавь источники белка.")
    return "\n".join(lines)


async def progress_report(db: AsyncSession, user_id: int) -> str:
    """Экран «Прогресс»: динамика объёма, веса, питания и рост по упражнениям."""
    vol = await repo.volume_by_week(db, user_id, weeks=4)
    weights = await repo.weight_by_week(db, user_id, weeks=6)
    kcals = await repo.kcal_by_week(db, user_id, weeks=4)
    growth = await repo.exercise_progress(db, user_id)

    lines = ["📈 <b>Прогресс</b>", ""]

    if vol:
        cur = vol[-1]
        prev = vol[-2] if len(vol) > 1 else None
        lines.append("<b>Объём нагрузки</b> (подходы × повторы)")
        line = f"• Эта неделя: {cur['sets']} подх. / {cur['reps']} повт."
        if prev and prev["reps"]:
            d = round((cur["reps"] - prev["reps"]) / prev["reps"] * 100)
            line += f" ({'+' if d >= 0 else ''}{d}% к прошлой)"
        lines.append(line)
        top = sorted(cur["groups"].items(), key=lambda x: -x[1])[:3]
        if top:
            lines.append("• Больше всего: " + ", ".join(f"{g} ({r})" for g, r in top))
    else:
        lines.append("Пока нет записанных подходов — начни тренировку 💪")

    if len(weights) >= 2:
        lines.append("")
        lines.append("<b>Вес по неделям</b>")
        lines.append("• " + " → ".join(f"{w:g}" for _, w in weights[-4:]) + " кг")
        delta = weights[-1][1] - weights[0][1]
        lines.append(f"• За период: {'−' if delta < 0 else '+'}{abs(delta):.1f} кг")

    if kcals:
        lines.append("")
        lines.append("<b>Питание</b>")
        for wk, avg, days in kcals[-2:]:
            lines.append(f"• Неделя с {wk.strftime('%d.%m')}: ~{avg} ккал/день, записей {days} дн.")

    if growth:
        lines.append("")
        lines.append("<b>Рост по упражнениям</b> (за месяц)")
        for g in growth:
            sign = "📈" if g["delta"] > 0 else "📉"
            lines.append(f"{sign} {g['name']}: {g['from']} → {g['to']}")

    return "\n".join(lines)


async def macro_advice(db: AsyncSession, user_id: int) -> dict | None:
    """Макро-коррекция (уровень B): раз в неделю смотрим 3 недели истории и решаем,
    нужно ли перестраивать программу.

    ПРИОРИТЕТ: сначала питание, потом нагрузка — если вес стоит из-за несоблюдения калорий,
    НЕ утяжеляем тренировки (иначе перетрен вместо результата).
    Возвращает {"reason": текст для пользователя, "wishes": пожелания генератору} или None.
    """
    user = await db.get(User, user_id)
    if user is None:
        return None
    today = local_today()
    since = today - timedelta(days=21)
    done = await repo.count_workouts_in_period(db, user_id, since)
    planned = len(await repo.list_templates(db, user_id)) * 3 or 1
    weights = await repo.weight_by_week(db, user_id, weeks=4)
    kcals = await repo.kcal_by_week(db, user_id, weeks=3)
    norm = nutrition.daily_norm(user)

    # Данных мало — не советуем ничего (нужна хотя бы пара недель истории)
    if done < 3 or len(weights) < 2:
        return None

    goal = (user.nutrition_goal or user.goal or "").lower()
    losing = "похуд" in goal or "снизить" in goal
    weight_delta = weights[-1][1] - weights[0][1]
    stalled = abs(weight_delta) < 0.4  # вес практически стоит за период

    # Соблюдение калорий: сколько дней записано и средний перебор
    days_logged = sum(d for _, _, d in kcals) if kcals else 0
    avg_kcal = round(sum(a for _, a, _ in kcals) / len(kcals)) if kcals else 0
    over_norm = bool(norm and avg_kcal > norm["kcal"] * 1.05)
    poor_tracking = days_logged < 10  # меньше половины дней за 3 недели

    skipping = done < planned * 0.6

    # 1) ПИТАНИЕ — приоритетнее нагрузки
    if losing and stalled and (over_norm or poor_tracking):
        why = ("ешь в среднем выше нормы" if over_norm else "мало дней с записями еды")
        return {
            "reason": (f"За 3 недели вес почти не изменился ({weight_delta:+.1f} кг), и при этом {why}. "
                       "Программу усложнять не будем — сначала наладим питание. "
                       "Тренировки оставлю в текущем объёме, чуть добавлю активности."),
            "wishes": ("Сохранить текущий уровень сложности, не увеличивать объём; добавить немного "
                       "лёгкой активности/кардио. Причина: вес стоит из-за питания, не из-за тренировок."),
        }

    # 2) Пропуски — упрощаем, чтобы вернуть регулярность
    if skipping:
        return {
            "reason": (f"За 3 недели сделано {done} тренировок из ~{planned} по плану. "
                       "Сделаю программу короче и проще — важнее регулярность, чем объём."),
            "wishes": "Сделать программу проще и короче (меньше упражнений, умеренная нагрузка), "
                      "чтобы её было легко выполнять регулярно.",
        }

    # 3) Всё соблюдается, но вес стоит при цели похудения — меняем стимул нагрузки
    if losing and stalled:
        return {
            "reason": (f"Тренировки идёшь стабильно ({done} за 3 недели), питание в норме, "
                       "но вес встал. Обновлю программу: сменю акценты и добавлю объёма на большие "
                       "группы мышц — это подтолкнёт расход."),
            "wishes": "Обновить программу: сменить упражнения на большие группы мышц, немного "
                      "увеличить общий объём, добавить кардио-элемент.",
        }

    # 4) Прогресс есть — ничего не трогаем
    return None
