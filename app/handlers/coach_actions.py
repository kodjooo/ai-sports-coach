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
        line = f"Пересобрать программу: {args.get('wishes') or 'обновить план'}"
        days = args.get("weekdays")
        if days:
            line += "; дни: " + ", ".join(_wd(int(d)) for d in days)
        if args.get("hour") is not None:
            line += f"; напоминания {int(args['hour']):02d}:{int(args.get('minute', 0)):02d}"
        return line
    return None


async def apply(action: dict, tg_id: int) -> tuple[str, int | None]:
    """Применяет действие к данным пользователя. Возвращает (текст-результат, id_записи_еды_для_отмены)."""
    name = action.get("name")
    args = action.get("args", {})
    async with async_session() as db:
        user = await repo.get_user_by_tg(db, tg_id)
        if user is None:
            return "Не нашёл профиль. Нажми /start.", None

        if name == "adjust_load":
            ex = await repo.find_exercise_by_name(db, args.get("exercise_name", ""))
            if not ex:
                return "Не нашёл такое упражнение в плане.", None
            n = await repo.adjust_load(
                db, user.id, ex.id, args.get("target_sets"), args.get("target_reps")
            )
            return (f"Готово, обновил нагрузку «{ex.name}»." if n else "В плане нет этого упражнения."), None

        if name == "replace_exercise":
            from app.core import catalog

            old = await repo.find_exercise_by_name(db, args.get("old_exercise", ""))
            # Новое ищем ТОЛЬКО в палитре каталога под инвентарь/уровень клиента — иначе коуч
            # мог подставить самодельную запись без GIF и техники.
            pool = catalog.main_candidates(user.equipment, user.level, limit=10_000)
            hit = catalog.resolve_in(args.get("new_exercise", ""), pool)
            new = await repo.find_exercise_by_name(db, hit["name"]) if hit else None
            if not old or not new:
                return ("Не нашёл подходящей замены в каталоге под твой инвентарь и уровень.", None)
            n = await repo.replace_exercise_in_plan(db, user.id, old.id, new.id)
            return (f"Заменил «{old.name}» на «{new.name}»." if n else "В плане нет исходного упражнения."), None

        if name == "set_time":
            hour = int(args.get("hour", 8))
            minute = int(args.get("minute", 0))
            await repo.set_train_time(db, user, hour, minute)
            return f"Напоминания теперь на {hour:02d}:{minute:02d}.", None

        if name == "log_weight":
            from app.utils import valid_weight
            try:
                weight = valid_weight(float(args.get("weight_kg")))
            except (TypeError, ValueError):
                weight = None
            if weight is None:
                return "Не понял вес — напиши число в кг (например 82.5).", None
            await repo.log_weight(db, user.id, weight)
            return f"Записал вес {weight:g} кг.", None

        if name == "log_meal":
            from app.core import llm, nutrition, openfoodfacts

            known = await repo.recent_dishes(db, user.id)
            analysis = await llm.analyze_food_text(args.get("description", ""), known=known)
            if not analysis.get("items"):
                return "Не понял, что именно съедено.", None
            analysis = await openfoodfacts.refine(analysis)
            meal = await repo.add_meal(db, user.id, analysis)
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
            return msg, meal.id

        if name == "set_plan":
            # ЕДИНЫЙ генератор: упражнения подбирает generate_plan строго из каталога-палитры
            # (инвентарь + уровень + правила безопасности), а коуч передаёт только ПОЖЕЛАНИЯ.
            from app.core import llm

            wishes = (args.get("wishes") or "").strip()
            days = [int(d) for d in (args.get("weekdays") or []) if 0 <= int(d) <= 6]
            if not days:
                days = sorted({t.weekday for t in await repo.list_templates(db, user.id)
                               if t.weekday is not None}) or [0, 2, 4]
            profile = (user.profile_summary or "")
            if wishes:
                profile = (profile + "\nПОЖЕЛАНИЯ К НОВОЙ ПРОГРАММЕ: " + wishes).strip()
            workouts = await llm.generate_plan(
                profile, user.goal, days, user.environment, user.equipment,
                user.sex, user.level, user.exercises_per_day or 4,
            )
            if not workouts:
                return "Не получилось собрать программу — попробуй ещё раз чуть позже.", None
            n = await repo.build_custom_plan(db, user.id, workouts,
                                             environment=user.environment, equipment=user.equipment)
            if args.get("hour") is not None:
                await repo.set_train_time(db, user, int(args["hour"]), int(args.get("minute", 0)))
            return f"Готово! Собрал новую программу на {n} дн. Загляни в «План недели».", None

    return "Не понял действие.", None
