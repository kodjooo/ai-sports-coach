"""Исполнение действий, предложенных тренером в чате (после подтверждения)."""
from __future__ import annotations

from app.core.db import async_session
from app.core import repository as repo

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _wd(i: int) -> str:
    return WEEKDAYS[i] if 0 <= i <= 6 else "?"


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
    if name == "log_meal":
        return f"Записать съеденное: {args.get('description')}"
    if name == "set_plan":
        workouts = args.get("workouts", [])
        parts = [f"{_wd(w.get('weekday', 0))} ({len(w.get('exercises', []))} упр.)" for w in workouts]
        line = f"Новый план на {len(workouts)} дн.: " + ", ".join(parts)
        if args.get("hour") is not None:
            line += f"; напоминания {int(args['hour']):02d}:{int(args.get('minute', 0)):02d}"
        return line
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
            from app.utils import valid_weight
            try:
                weight = valid_weight(float(args.get("weight_kg")))
            except (TypeError, ValueError):
                weight = None
            if weight is None:
                return "Не понял вес — напиши число в кг (например 82.5)."
            await repo.log_weight(db, user.id, weight)
            return f"Записал вес {weight:g} кг."

        if name == "log_meal":
            from app.core import llm, nutrition, openfoodfacts

            known = await repo.recent_dishes(db, user.id)
            analysis = await llm.analyze_food_text(args.get("description", ""), known=known)
            if not analysis.get("items"):
                return "Не понял, что именно съедено."
            analysis = await openfoodfacts.refine(analysis)
            await repo.add_meal(db, user.id, analysis)
            t = analysis.get("total", {})
            dish = analysis.get("dish") or "приём пищи"
            msg = (
                f"Записал: {dish} — {round(t.get('kcal') or 0)} ккал "
                f"(Б{round(t.get('protein') or 0)} Ж{round(t.get('fat') or 0)} У{round(t.get('carbs') or 0)})."
            )
            totals = await repo.today_totals(db, user.id)
            norm = nutrition.daily_norm(user)
            if norm:
                msg += (
                    f"\nСегодня: {totals['kcal']} / {norm['kcal']} ккал\n"
                    f"Осталось добрать: {max(norm['kcal'] - totals['kcal'], 0)} ккал · "
                    f"Б {max(norm['protein'] - totals['protein'], 0)} · "
                    f"Ж {max(norm['fat'] - totals['fat'], 0)} · "
                    f"У {max(norm['carbs'] - totals['carbs'], 0)} г"
                )
            return msg

        if name == "set_plan":
            workouts = args.get("workouts", [])
            if not workouts:
                return "Пустой план — нечего применять."
            n = await repo.build_custom_plan(db, user.id, workouts, environment=user.environment)
            if args.get("hour") is not None:
                await repo.set_train_time(db, user, int(args["hour"]), int(args.get("minute", 0)))
            return f"Готово! Собрал новый план на {n} дн. Загляни в «План недели»."

    return "Не понял действие."
