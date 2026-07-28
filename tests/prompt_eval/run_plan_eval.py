"""Prompt-eval генерации плана: 5 профилей → generate_plan → авто-проверки нарушений.
САМОДОСТАТОЧЕН (профили инлайн) — запуск в контейнере с реальным API-ключом:
  docker compose exec -T bot python -u - < tests/prompt_eval/run_plan_eval.py
Критерий прохождения: 0 КРИТИЧЕСКИХ нарушений (инвентарь/травма/вне палитры) у всех,
и ≥4/5 профилей без НИКАКИХ нарушений. Печатает таблицу и итог PASS/FAIL."""
import asyncio
import app.core.llm as llm
from app.core import catalog

PROFILES = [
    dict(label="Новичок, зал, м, общая форма", goal="общая форма", sex="м", level="новичок",
         equip="всё оборудование зала", per_day=4, note="30 лет, здоров", injury=None),
    dict(label="Средний, дом гантели+резинки, ж, похудение", goal="похудение", sex="ж", level="средний",
         equip="гантели, резинки", per_day=4, note="34 года, сбросить вес", injury=None),
    dict(label="Продвинутый, зал, м, масса", goal="набор массы", sex="м", level="продвинутый",
         equip="всё оборудование зала", per_day=5, note="28 лет, 3 года стажа", injury=None),
    dict(label="Новичок, коврик, ж, тонус, болит колено", goal="тонус и осанка", sex="ж", level="новичок",
         equip="коврик", per_day=3, note="40 лет, болит правое колено", injury="колено"),
    dict(label="Средний, улица турник/брусья, м, рельеф", goal="рельеф", sex="м", level="средний",
         equip="турник, брусья", per_day=4, note="26 лет", injury=None),
]
WEEKDAYS = [0, 2, 4]
KNEE_BAD = ("прыж", "выпад", "присед", "зашагив", "пистолет", "джамп")
BACK_HINT = ("спина", "поясница", "широч", "трапеци", "тяга", "подтяг", "супермен", "разгибание спины")


def check(p, plan):
    """Возвращает (violations, critical) — списки строк."""
    v, crit = [], []
    allowed = catalog.available_equipment(p["equip"])
    pool = {e["name"]: e for e in catalog.main_candidates(p["equip"], p["level"], limit=400)}
    days = {w["weekday"]: w for w in plan}
    for wd in WEEKDAYS:
        if wd not in days:
            crit.append(f"нет дня weekday={wd}")
            continue
        exs = days[wd]["exercises"]
        if len(exs) != p["per_day"]:
            v.append(f"д{wd}: {len(exs)} упр. вместо {p['per_day']}")
        for e in exs:
            name = e["name"] if isinstance(e, dict) else e
            cat = pool.get(name)
            if not cat:
                crit.append(f"д{wd}: «{name}» вне палитры")
                continue
            if not set(cat.get("equipment_req") or []).issubset(allowed):
                crit.append(f"д{wd}: «{name}» требует инвентарь вне доступного")
            if p["level"] == "новичок" and cat.get("kind") == "плиометрика":
                crit.append(f"д{wd}: новичку плиометрика «{name}»")
            if p["injury"] == "колено" and any(k in name.lower() for k in KNEE_BAD):
                crit.append(f"д{wd}: при боли в колене «{name}»")
    # есть ли работа спины хоть где-то
    allnames = " ".join((e["name"] if isinstance(e, dict) else e)
                        for w in plan for e in w["exercises"]).lower()
    allgroups = " ".join((e.get("muscle_group", "") if isinstance(e, dict) else "")
                         for w in plan for e in w["exercises"]).lower()
    if not any(h in (allnames + " " + allgroups) for h in BACK_HINT):
        v.append("нет работы спины/тяги за неделю")
    return v, crit


async def main():
    clean, results = 0, []
    total_crit = 0
    for p in PROFILES:
        try:
            plan = await llm.generate_plan(
                profile_summary=p["note"], goal=p["goal"], weekdays=WEEKDAYS,
                environment=None, equipment=p["equip"], sex=p["sex"],
                level=p["level"], per_day=p["per_day"])
            v, crit = check(p, plan)
        except Exception as e:
            v, crit = [], [f"исключение: {repr(e)[:80]}"]
        total_crit += len(crit)
        if not v and not crit:
            clean += 1
        results.append((p["label"], v, crit))

    print("\n===== PROMPT-EVAL: ПЛАН =====")
    for label, v, crit in results:
        status = "✅" if not v and not crit else ("❌" if crit else "⚠️")
        print(f"{status} {label}")
        for c in crit:
            print(f"    КРИТ: {c}")
        for x in v:
            print(f"    warn: {x}")
    ok = total_crit == 0 and clean >= 4
    print(f"\nИТОГ: чистых {clean}/{len(PROFILES)}, критических {total_crit} → "
          f"{'PASS ✅' if ok else 'FAIL ❌'}")


asyncio.run(main())
