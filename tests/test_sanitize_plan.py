"""Тесты _sanitize_plan: сверка с палитрой, восстановление дней, добивка до per_day."""
from app.core.llm import _sanitize_plan


def _ex(name, group, equipment="без инвентаря"):
    return {
        "name": name, "muscle_group": group, "technique": "т",
        "environment": "везде", "equipment": equipment, "gif": "x.gif",
    }


MAIN_POOL = [
    _ex("Отжимания", "грудь"),
    _ex("Приседания", "ноги"),
    _ex("Планка", "пресс"),
    _ex("Подтягивания", "спина"),
    _ex("Выпады", "ноги"),
]
WARM_POOL = [_ex("Растяжка груди", "грудь"), _ex("Растяжка ног", "ноги")]


def _day(weekday, names, warmup=None, cooldown=None):
    return {
        "weekday": weekday,
        "exercises": [{"name": n, "sets": 3, "reps": 10, "rest_sec": 60} for n in names],
        "warmup": warmup or [],
        "cooldown": cooldown or [],
    }


def test_unknown_names_dropped():
    plan = _sanitize_plan([_day(0, ["Отжимания", "Выдуманное упражнение XYZ"])],
                          MAIN_POOL, WARM_POOL)
    names = [e["name"] for e in plan[0]["exercises"]]
    assert names == ["Отжимания"]


def test_all_exercises_from_pool_only():
    plan = _sanitize_plan([_day(0, ["Отжимания", "Приседания"])], MAIN_POOL, WARM_POOL)
    pool_names = {e["name"] for e in MAIN_POOL}
    assert all(e["name"] in pool_names for d in plan for e in d["exercises"])


def test_missing_weekday_restored_and_backfilled():
    # Модель «потеряла» день 2 (все названия вне палитры) — он должен вернуться
    # пустым каркасом и добиться до per_day из одобренных групп.
    raw = [_day(0, ["Отжимания", "Приседания"]), _day(2, ["Ерунда", "Чушь"])]
    plan = _sanitize_plan(raw, MAIN_POOL, WARM_POOL, per_day=2, weekdays=[0, 2])
    assert [d["weekday"] for d in plan] == [0, 2]
    assert all(len(d["exercises"]) == 2 for d in plan)


def test_backfill_only_from_approved_groups():
    # Модель выбрала только грудь и пресс — добивка не должна втащить ноги/спину.
    raw = [_day(0, ["Отжимания"]), _day(2, ["Планка"])]
    plan = _sanitize_plan(raw, MAIN_POOL, WARM_POOL, per_day=2, weekdays=[0, 2])
    groups = {e["muscle_group"] for d in plan for e in d["exercises"]}
    assert groups <= {"грудь", "пресс"}


def test_backfill_respects_per_day_exact():
    raw = [_day(0, ["Отжимания", "Приседания", "Планка", "Подтягивания"])]
    plan = _sanitize_plan(raw, MAIN_POOL, WARM_POOL, per_day=4, weekdays=[0])
    assert len(plan[0]["exercises"]) == 4


def test_warmup_cooldown_donor_copied_to_restored_day():
    raw = [_day(0, ["Отжимания"], warmup=["Растяжка груди"], cooldown=["Растяжка ног"])]
    plan = _sanitize_plan(raw, MAIN_POOL, WARM_POOL, per_day=1, weekdays=[0, 3])
    restored = next(d for d in plan if d["weekday"] == 3)
    assert restored["warmup"] and restored["cooldown"]


def test_empty_plan_returns_empty():
    plan = _sanitize_plan([_day(0, ["Полная чушь"])], MAIN_POOL, WARM_POOL,
                          per_day=3)
    # Все дни выпали, weekdays не передан — восстанавливать нечего, добивать не из чего
    assert plan == []
