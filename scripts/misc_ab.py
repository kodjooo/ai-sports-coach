"""A/B прочих вызовов: estimate_burn (mini vs gpt-5) и простой chat/фидбек (gpt-5 vs luna).
Запуск: docker compose exec -T bot python -u - < scripts/misc_ab.py"""
import asyncio
import app.core.llm as llm

# (описание тренировки, вес, пол, ориентир ккал по METs)
BURN = [
    ("разминка: 5 движений; основная: присед с гантелями 3×12, тяга гантелей 3×12, жим гантелей 3×10, "
     "планка 3×40с; заминка: 4 растяжки; общая длительность ~40 мин", 92, "м", 260),
    ("разминка 5 мин; основная: 3 упражнения по 3 подхода, было легко; общая ~25 мин", 70, "ж", 130),
    ("только разминка 5 движений, дальше не пошло", 85, "м", 30),
]

FEEDBACK_PROMPTS = [
    "Клиент завершил тренировку (присед с гантелями было тяжело в колене, остальное ок). "
    "Дай короткий тёплый фидбек тренера (2–4 предложения): похвали, отметь колено, дай 1 совет.",
    "Недельный итог клиента: 2 из 3 тренировок сделаны, вес −0.4 кг, питание в норме 4 из 7 дней. "
    "Дай короткий поддерживающий недельный вывод тренера с 1 фокусом на следующую неделю.",
]

async def main():
    print("===== estimate_burn (mini vs gpt-5) =====", flush=True)
    for summ, w, sx, ref in BURN:
        line = f"ориентир ~{ref}: "
        for model in ("gpt-5-mini", "gpt-5"):
            try:
                k = await llm.estimate_burn(summ, w, sx, model=model)
                line += f"{model}={k}  "
            except Exception as e:
                line += f"{model}=ERR({repr(e)[:40]})  "
        print(f"  «{summ[:50]}…»\n    {line}", flush=True)

    print("\n===== chat/фидбек (gpt-5 vs luna) =====", flush=True)
    sys = "Ты — тёплый персональный фитнес-тренер. Пиши кратко, по-русски, на «ты»."
    for p in FEEDBACK_PROMPTS:
        print(f"\n--- запрос: {p[:60]}… ---", flush=True)
        for model in ("gpt-5", "gpt-5.6-luna"):
            try:
                r = await llm.chat(p, system_prompt=sys, model=model)
                print(f"  [{model}] {r.strip()}", flush=True)
            except Exception as e:
                print(f"  [{model}] ERR {repr(e)[:60]}", flush=True)

asyncio.run(main())
