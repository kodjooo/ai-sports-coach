"""Prompt-eval учёта еды по тексту: набор блюд с ориентиром ккал → analyze_food_text + refine →
ошибка калорий. САМОДОСТАТОЧЕН, запуск в контейнере с реальным ключом:
  docker compose exec -T bot python -u - < tests/prompt_eval/run_food_eval.py
Критерий: медианная |ошибка| ≤ 25%, и НЕТ систематического занижения
(медиана со знаком не ниже -15%) — для похудения занижать опаснее."""
import asyncio, copy, statistics
import app.core.llm as llm
from app.core import openfoodfacts

# (описание, ориентир ккал)
CASES = [
    ("Тарелка варёного белого риса, 250 г", 325),
    ("Один банан", 105),
    ("Куриная грудка гриль 200 г и гречка варёная 150 г", 480),
    ("Два бутерброда: белый хлеб, варёная колбаса, сыр", 420),
    ("Овсянка на молоке 250 г с бананом и ложкой мёда", 450),
    ("Протеиновый батончик 60 г", 230),
    ("Греческий салат, стандартная порция", 350),
    ("Американо 270 мл с 1 ложкой сахара", 25),
]


async def kcal_of(desc):
    a = await llm.analyze_food_text(desc)
    a = await openfoodfacts.refine(copy.deepcopy(a))
    return round((a.get("total") or {}).get("kcal") or 0)


async def main():
    rows, errs, signed = [], [], []
    for desc, ref in CASES:
        try:
            k = await kcal_of(desc)
            e = (k - ref) / ref * 100
            errs.append(abs(e)); signed.append(e)
            rows.append((desc, ref, k, e))
        except Exception as ex:
            rows.append((desc, ref, None, None))
    print("\n===== PROMPT-EVAL: ЕДА (текст) =====")
    for desc, ref, k, e in rows:
        s = f"{k} ккал ({e:+.0f}%)" if k is not None else "ERR"
        print(f"  «{desc[:44]:44}» ориентир {ref:>4} → {s}")
    med_abs = statistics.median(errs) if errs else 999
    med_signed = statistics.median(signed) if signed else -999
    ok = med_abs <= 25 and med_signed >= -15
    print(f"\nИТОГ: медиана |ошибки|={med_abs:.0f}% (порог 25), медиана со знаком="
          f"{med_signed:+.0f}% (не ниже -15) → {'PASS ✅' if ok else 'FAIL ❌'}")


asyncio.run(main())
