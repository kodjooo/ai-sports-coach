"""Каталог упражнений с GIF: палитра для LLM-тренера и поиск по названию.

LLM выбирает упражнения ТОЛЬКО из кандидатов, которые вернёт этот модуль
(это гарантирует наличие GIF), но сам выбор — за тренером с учётом контекста.
Код тут делает лишь механику: фильтр по среде/инвентарю и поиск gif/техники по названию.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_PATH = Path(__file__).with_name("exercises.json")

# Ключевое слово в тексте инвентаря пользователя -> метка equipment в каталоге
_EQUIP_TOKENS: list[tuple[str, str]] = [
    ("гантел", "гантели"),
    ("гир", "гиря"),
    ("штанг", "штанга"),
    ("резин", "резинки"),
    ("эспандер", "резинки"),
    ("турник", "турник"),
    ("перекладин", "турник"),
    ("брус", "брусья"),
    ("скам", "скамья"),
    ("тренаж", "тренажёр"),
    ("блок", "блок/трос"),
    ("трос", "блок/трос"),
    ("кроссовер", "блок/трос"),
    ("медбол", "медбол"),
    ("медицинск", "медбол"),
    ("фитбол", "фитбол"),
    ("швейцарск", "фитбол"),
    ("ez", "EZ-гриф"),
    ("ролик для пресса", "ролик для пресса"),
    ("аб-ролик", "ролик для пресса"),
    ("массажн", "массажный ролик"),
    ("тумб", "тумба"),
    ("степ", "тумба"),
    ("trx", "TRX/петли"),
    ("петл", "TRX/петли"),
    ("канат", "канат"),
    ("сани", "сани"),
    ("салазк", "сани"),
]


def _load() -> list[dict]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


ALL: list[dict] = _load()


def _norm(name: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", " ", (name or "").lower()).strip()


BY_NAME: dict[str, dict] = {_norm(e["name"]): e for e in ALL}


def _tokens(name: str) -> set[str]:
    return set(_norm(name).split())


# Токены названий каталога — для нечёткого поиска
_TOKENS_BY_NAME: list[tuple[set[str], dict]] = [(_tokens(e["name"]), e) for e in ALL]


def resolve_in(name: str, pool: list[dict], fuzzy: bool = True) -> dict | None:
    """Находит упражнение по названию ТОЛЬКО среди pool (отфильтрованной палитры).

    Нужно, чтобы fuzzy-сопоставление не подтягивало вариант с инвентарём, которого нет
    у клиента (напр. «Ягодичный мостик» → «...со штангой»).
    """
    by_name = {_norm(e["name"]): e for e in pool}
    exact = by_name.get(_norm(name))
    if exact or not fuzzy:
        return exact
    want = _tokens(name)
    if not want:
        return None
    best, best_score = None, 0.0
    for e in pool:
        toks = _tokens(e["name"])
        inter = len(want & toks)
        if not inter:
            continue
        score = inter / len(want | toks)
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 0.5 else None


def resolve(name: str, fuzzy: bool = False) -> dict | None:
    """Находит упражнение каталога по названию.

    Сначала — точное совпадение по нормализованному виду. При fuzzy=True и промахе —
    ближайшее по пересечению слов (если модель чуть переиначила название).
    """
    exact = BY_NAME.get(_norm(name))
    if exact or not fuzzy:
        return exact
    want = _tokens(name)
    if not want:
        return None
    best, best_score = None, 0.0
    for toks, e in _TOKENS_BY_NAME:
        if not toks:
            continue
        inter = len(want & toks)
        if not inter:
            continue
        score = inter / len(want | toks)  # коэффициент Жаккара
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 0.5 else None


# Канонический словарь оборудования (совпадает с equipment_req в каталоге и метками чеклиста).
EQUIPMENT_TAGS = [
    "гантели", "штанга", "гиря", "резинки", "турник", "брусья", "скамья", "тренажёр",
    "блок/трос", "медбол", "фитбол", "EZ-гриф", "ролик для пресса", "массажный ролик",
    "тумба", "TRX/петли", "канат", "сани",
]
# «У меня есть всё» — синоним, а не «место»: раскрывает весь словарь оборудования.
_ALL_EQUIP_MARKERS = ("всё оборуд", "все оборуд", "любое оборуд", "полный зал")


def available_equipment(equipment: str | None) -> set[str]:
    """Множество оборудования, доступного клиенту, по его словам/галочкам чеклиста.

    Ось одна — оборудование (не «место»). Упражнение без инвентаря (пустой equipment_req)
    доступно всегда. «Всё оборудование» раскрывает весь словарь.
    """
    text = (equipment or "").lower()
    if any(m in text for m in _ALL_EQUIP_MARKERS):
        return set(EQUIPMENT_TAGS)
    allowed: set[str] = set()
    for token, tag in _EQUIP_TOKENS:
        if token in text:
            allowed.add(tag)
    return allowed


def _feasible(e: dict, allowed: set[str]) -> bool:
    """Упражнение доступно, если ВСЁ необходимое оборудование есть у клиента (пустое — всегда)."""
    return set(e.get("equipment_req") or []).issubset(allowed)


def _round_robin_by_muscle(items: list[dict], limit: int) -> list[dict]:
    """Отбирает до limit упражнений, чередуя группы мышц ради разнообразия палитры."""
    buckets: dict[str, list[dict]] = {}
    for e in items:
        buckets.setdefault(e["muscle_group"], []).append(e)
    order = sorted(buckets)
    out: list[dict] = []
    idx = 0
    while len(out) < limit and any(buckets[g] for g in order):
        g = order[idx % len(order)]
        if buckets[g]:
            out.append(buckets[g].pop(0))
        idx += 1
    return out


def main_candidates(equipment: str | None, limit: int = 130) -> list[dict]:
    """Палитра основных упражнений (силовое/плиометрика/кардио) по доступному инвентарю."""
    allowed = available_equipment(equipment)
    pool = [
        e for e in ALL
        if e.get("kind") in ("силовое", "плиометрика", "кардио")
        and _feasible(e, allowed)
    ]
    return _round_robin_by_muscle(pool, limit)


def warmup_candidates(equipment: str | None, zones: list[str] | None = None) -> list[dict]:
    """Палитра разминки/заминки (растяжка) — при указании zones приоритет зонам."""
    allowed = available_equipment(equipment)
    pool = [e for e in ALL if e.get("kind") == "растяжка" and _feasible(e, allowed)]
    if not zones:
        return pool
    zset = {z.strip().lower() for z in zones if z.strip()}
    def hit(e: dict) -> bool:
        return any(part.strip().lower() in zset for part in e["muscle_group"].split("/"))
    prioritized = [e for e in pool if hit(e)]
    general = [e for e in pool if not hit(e)]
    return prioritized + general


def names_for_prompt(items: list[dict]) -> str:
    """Компактный список для промпта: «Название (зона; оборудование; сложность N/5)»."""
    def eq(e: dict) -> str:
        r = e.get("equipment_req") or []
        return ", ".join(r) if r else "без инвентаря"
    return "\n".join(
        f"- {e['name']} ({e['muscle_group']}; {eq(e)}; сложность {e.get('difficulty', 3)}/5)"
        for e in items
    )
