"""Генерация GIF-анимаций упражнений из 2 кадров (старт → финиш).

Источник кадров — открытая база free-exercise-db (public domain). Скрипт скачивает
по два кадра на упражнение и склеивает зацикленный GIF (по 1 секунде на кадр).

Запуск (разово, при подготовке медиа):
    python scripts/build_exercise_gifs.py

Куда пишет: каталог из переменной окружения EXERCISE_GIF_DIR (по умолчанию /app/media/exercises).
На проде это Docker volume, поэтому гифки переживают пересборку контейнера.

Манифест источников: scripts/exercise_media_sources.json — список
{"gif": "<имя_файла>.gif", "images": ["Path/0.jpg", "Path/1.jpg"]}.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import requests
from PIL import Image

RAW_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
FRAME_MS = 1000  # длительность каждого кадра
MAX_W = 360      # ширина кадра (компактный размер для Telegram)

OUT_DIR = Path(os.environ.get("EXERCISE_GIF_DIR", "/app/media/exercises"))
MANIFEST = Path(__file__).with_name("exercise_media_sources.json")


def _load_frame(path: str) -> Image.Image:
    resp = requests.get(RAW_BASE + path, timeout=30)
    resp.raise_for_status()
    im = Image.open(io.BytesIO(resp.content)).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)))
    return im


def _build_gif(images: list[str]) -> bytes | None:
    frames = []
    for p in images:
        try:
            frames.append(_load_frame(p))
        except Exception as exc:  # пропускаем битый кадр
            print(f"  ! кадр не скачан {p}: {exc}", file=sys.stderr)
    if not frames:
        return None
    # выравниваем размеры кадров по первому
    base = frames[0]
    frames = [f if f.size == base.size else f.resize(base.size) for f in frames]
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )
    return buf.getvalue()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    done, skipped, failed = 0, 0, 0
    for i, it in enumerate(items, 1):
        out = OUT_DIR / it["gif"]
        if out.exists():
            skipped += 1
            continue
        data = _build_gif(it.get("images") or [])
        if not data:
            failed += 1
            continue
        out.write_bytes(data)
        done += 1
        if i % 50 == 0:
            print(f"  {i}/{len(items)} обработано…")
    print(f"Готово: создано {done}, пропущено (уже есть) {skipped}, без кадров {failed}. "
          f"Каталог: {OUT_DIR}")


if __name__ == "__main__":
    main()
