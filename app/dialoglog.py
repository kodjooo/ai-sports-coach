"""Логирование переписки пользователя для последующего анализа.

Включается флагом LOG_DIALOG. Можно ограничить конкретными tg_id через
LOG_DIALOG_USERS (пусто = все пользователи). Пишет в отдельный логгер `dialog`
(видно в `docker compose logs bot`, фильтр по префиксу [DIALOG]).
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("dialog")


def _enabled(tg_id: int) -> bool:
    if not settings.log_dialog:
        return False
    ids = settings.log_dialog_user_ids
    return (not ids) or (tg_id in ids)


def log_in(tg_id: int, text: str) -> None:
    if _enabled(tg_id):
        logger.info("[DIALOG] user=%s IN: %s", tg_id, text.replace("\n", " ⏎ "))


def log_out(tg_id: int, text: str) -> None:
    if _enabled(tg_id):
        logger.info("[DIALOG] user=%s OUT: %s", tg_id, (text or "").replace("\n", " ⏎ "))
