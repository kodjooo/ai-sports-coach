"""A/B чат-тренера: gpt-5 vs gpt-5.1 vs luna на типовых репликах.
Для каждой реплики печатает ответ модели + предложенное действие (tool).
Запуск: docker compose exec -T bot python -u - < scripts/chat_ab.py"""
import asyncio
import app.core.llm as llm
from app.config import settings

# (модель, reasoning) — luna требует 'none' при function tools
MODELS = [("gpt-5", "low"), ("gpt-5.6-luna", "none")]

TOOLS_HINT = (
    "Если уместно, предлагай изменения через функции: нагрузка (adjust_load), замена (replace_exercise), "
    "время (set_time), вес (log_weight), полный план (set_plan). Если клиент говорит, что съел что-то — "
    "используй log_meal с описанием как есть. Изменения применяются ТОЛЬКО после подтверждения кнопкой. "
    "Предлагая изменение — сначала КРАТКО объясни почему, потом действие. Отвечай кратко."
)
PERSONA = (
    "Ты — Алекс, персональный фитнес-тренер клиента Марка. Тёплый, краткий, поддерживающий стиль, обращение на «ты». "
    "Цель клиента: похудение. Уровень: новичок. Ограничение: болит правое колено. Тренируется дома с гантелями."
)
CONTEXT = (
    "КОНТЕКСТ: вес 92 кг (−1.2 за месяц); съедено сегодня 1400/2000 ккал; план на Пн/Ср/Пт; "
    "последняя тренировка: присед с гантелями было тяжело в колене."
)
SYS = PERSONA + "\n\n" + TOOLS_HINT + "\n\n" + CONTEXT

MSGS = [
    ("мотивация", "Что-то нет сил заниматься, всё лень, вес встал"),
    ("техника", "Как правильно дышать в приседаниях?"),
    ("боль", "После вчерашней тренировки болит колено сильнее, что делать?"),
    ("отчёт", "Сделал сегодня всю тренировку, было тяжело но осилил"),
    ("еда", "Съел два бутерброда с колбасой и сыром и выпил американо с сахаром"),
    ("правка плана", "Мне тяжело приседать из-за колена, можно заменить?"),
    ("вес", "Сегодня взвесился — 91.3"),
]

async def main():
    settings.openai_reasoning_effort = "low"
    for tag, msg in MSGS:
        print(f"\n===== [{tag}] «{msg}» =====", flush=True)
        for model, reasoning in MODELS:
            try:
                r = await llm.chat_with_tools([{"role": "user", "content": msg}], SYS,
                                              model=model, reasoning=reasoning)
                act = r.get("action")
                act_s = f"  →ДЕЙСТВИЕ: {act['name']}({act.get('args')})" if act else "  →действие: нет"
                print(f"--- {model}({reasoning}) ---\n{r.get('text','').strip()}{act_s}", flush=True)
            except Exception as e:
                print(f"--- {model} --- ERR {repr(e)[:80]}", flush=True)

asyncio.run(main())
