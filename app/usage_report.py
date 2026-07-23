"""Сводка расхода OpenAI из файла логов.

Запуск: docker compose exec bot python -m app.usage_report
Опционально: за последние N дней — python -m app.usage_report 7
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

_LOG_PATH = os.environ.get("USAGE_LOG", "/app/logs/usage.log")
_LINE = re.compile(
    r"\[USAGE\] tag=(?P<tag>\S+) model=(?P<model>\S+) in=(?P<in>\d+) out=(?P<out>\d+) "
    r"reasoning=(?P<r>\d+) ~\$(?P<cost>[0-9.]+)"
)


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    since = datetime.now() - timedelta(days=days) if days else None

    calls: dict[str, int] = defaultdict(int)
    cost: dict[str, float] = defaultdict(float)
    tin: dict[str, int] = defaultdict(int)
    tout: dict[str, int] = defaultdict(int)
    total = 0.0

    for path in (_LOG_PATH, _LOG_PATH + ".1", _LOG_PATH + ".2", _LOG_PATH + ".3"):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if since:
                    ts = line[:19]
                    try:
                        if datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") < since:
                            continue
                    except ValueError:
                        pass
                m = _LINE.search(line)
                if not m:
                    continue
                t = m.group("tag")
                calls[t] += 1
                cost[t] += float(m.group("cost"))
                tin[t] += int(m.group("in"))
                tout[t] += int(m.group("out"))
                total += float(m.group("cost"))

    period = f"за {days} дн." if days else "за всё время"
    print(f"Расход OpenAI {period}:\n")
    print(f"{'ТИП':18} {'вызовов':>8} {'вход':>9} {'выход':>9} {'USD':>9}")
    for t in sorted(cost, key=cost.get, reverse=True):
        print(f"{t:18} {calls[t]:>8} {tin[t]:>9} {tout[t]:>9} {cost[t]:>9.4f}")
    print(f"\nИТОГО: ~${total:.4f}")


if __name__ == "__main__":
    main()
