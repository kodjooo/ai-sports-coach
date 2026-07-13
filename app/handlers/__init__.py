"""Регистрация роутеров бота."""
from aiogram import Router

from app.handlers import chat, menu, nutrition, schedule, start, voice, workout


def get_root_router() -> Router:
    root = Router()
    # Порядок важен: команды/онбординг и конкретные кнопки → голос → чат последним
    root.include_router(start.router)
    root.include_router(schedule.router)
    root.include_router(menu.router)
    root.include_router(workout.router)
    root.include_router(nutrition.router)
    root.include_router(voice.router)
    root.include_router(chat.router)
    return root
