"""Тесты ThrottleMiddleware: лимит действий на пользователя в окне."""
import asyncio

from aiogram.types import Chat, Message, User

from app.middlewares import ThrottleMiddleware


def _msg(uid: int) -> Message:
    return Message.model_construct(
        message_id=1, date=None,
        chat=Chat.model_construct(id=uid, type="private"),
        from_user=User.model_construct(id=uid, is_bot=False, first_name="T"),
    )


def _run(coro):
    return asyncio.run(coro)


def test_limit_blocks_excess_actions():
    mw = ThrottleMiddleware()
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1

    async def scenario():
        for _ in range(mw.LIMIT + 5):
            await mw(handler, _msg(1), {})

    _run(scenario())
    assert calls["n"] == mw.LIMIT  # сверх лимита — в обработчик не пускаем


def test_limits_are_per_user():
    mw = ThrottleMiddleware()
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1

    async def scenario():
        for _ in range(mw.LIMIT):
            await mw(handler, _msg(1), {})
        # Другой пользователь не задет лимитом первого
        await mw(handler, _msg(2), {})

    _run(scenario())
    assert calls["n"] == mw.LIMIT + 1


def test_event_without_user_passes():
    mw = ThrottleMiddleware()
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1

    class Dummy:  # не Message/CallbackQuery
        pass

    _run(mw(handler, Dummy(), {}))
    assert calls["n"] == 1
