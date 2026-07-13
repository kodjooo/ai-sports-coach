"""Исполнение действий, предложенных тренером в чате (после подтверждения)."""
from __future__ import annotations

from app.core.db import async_session
from app.core import repository as repo


def describe(action: dict) -> str | None:
    """Человеческое описание предложенного действия для подтверждения."""
    name = action.get("name")
    args = action.get("args", {})
    if name == "adjust_load":
        parts = []
        if args.get("target_sets") is not None:
            parts.append(f"{args['target_sets']} подх.")
        if args.get("target_reps") is not None:
            parts.append(f"{args['target_reps']} повт.")
        return f"Изменить «{args.get('exercise_name')}» → {' × '.join(parts) or 'новая нагрузка'}"
    if name == "replace_exercise":
        return f"Заменить «{args.get('old_exercise')}» на «{args.get('new_exercise')}» в плане"
    if name == "set_time":
        return f"Ставить напоминания на {int(args.get('hour', 0)):02d}:{int(args.get('minute', 0)):02d}"
    if name == "log_weight":
        return f"Записать вес {args.get('weight_kg')} кг"
    return None


async def apply(action: dict, tg_id: int) -> str:
    """Применяет действие к данным пользователя. Возвращает текст-результат."""
    name = action.get("name")
    args = action.get("args", {})
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, tg_id)
        if user is None:
            return "Не нашёл профиль. Нажми /start."

        if name == "adjust_load":
            ex = await repo.find_exercise_by_name(db, args.get("exercise_name", ""))
            if not ex:
                return "Не нашёл такое упражнение в плане."
            n = await repo.adjust_load(
                db, user.id, ex.id, args.get("target_sets"), args.get("target_reps")
            )
            return f"Готово, обновил нагрузку «{ex.name}»." if n else "В плане нет этого упражнения."

        if name == "replace_exercise":
            old = await repo.find_exercise_by_name(db, args.get("old_exercise", ""))
            new = await repo.find_exercise_by_name(db, args.get("new_exercise", ""))
            if not old or not new:
                return "Не нашёл одно из упражнений в каталоге."
            n = await repo.replace_exercise_in_plan(db, user.id, old.id, new.id)
            return f"Заменил «{old.name}» на «{new.name}»." if n else "В плане нет исходного упражнения."

        if name == "set_time":
            hour = int(args.get("hour", 8))
            minute = int(args.get("minute", 0))
            await repo.set_train_time(db, user, hour, minute)
            return f"Напоминания теперь на {hour:02d}:{minute:02d}."

        if name == "log_weight":
            weight = float(args.get("weight_kg"))
            await repo.log_weight(db, user.id, weight)
            return f"Записал вес {weight:g} кг."

    return "Не понял действие."
