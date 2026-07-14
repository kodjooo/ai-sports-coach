"""Тест склейки сообщений (дебаунс)."""
import asyncio

from app import debounce


def test_multiple_messages_flushed_once():
    debounce.DELAY = 0.05
    calls: list[str] = []

    async def scenario() -> None:
        async def flush(text: str) -> None:
            calls.append(text)

        # Три сообщения подряд — одна обработка со склейкой
        await debounce.push("k1", "привет", flush)
        await debounce.push("k1", "вешу 80", flush)
        await debounce.push("k1", "рост 180", flush)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert calls == ["привет\nвешу 80\nрост 180"]


def test_separate_keys_independent():
    debounce.DELAY = 0.05
    calls: list[str] = []

    async def scenario() -> None:
        async def flush(text: str) -> None:
            calls.append(text)

        await debounce.push("a", "один", flush)
        await debounce.push("b", "два", flush)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert sorted(calls) == ["два", "один"]
