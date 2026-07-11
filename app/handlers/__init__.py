"""Регистрация роутеров бота."""
from aiogram import Router

from app.handlers import chat, menu, nutrition, start, workout


def get_root_router() -> Router:
    root = Router()
    # Порядок важен: сначала команды/онбординг и конкретные кнопки, чат — последним
    root.include_router(start.router)
    root.include_router(menu.router)
    root.include_router(workout.router)
    root.include_router(nutrition.router)
    root.include_router(chat.router)
    return root
