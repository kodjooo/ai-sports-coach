"""Тесты лимитов дорогих LLM-действий: триал, суточный, предохранитель, fail-open.
Redis подменяем простым in-memory стабом, стоимость дня — монипатчем usage."""
import asyncio

import pytest

from app.core import limits
from app.config import settings


class FakeRedis:
    """Минимальный асинхронный стаб под incr/decr/expire (как в check_and_consume)."""
    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    async def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key):
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    async def expire(self, key, seconds):
        self.ttl[key] = seconds
        return True


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(limits, "_client", lambda: fake)
    # по умолчанию предохранитель «ok»
    monkeypatch.setattr(limits.usage, "spent_today_usd", lambda: 0.0)
    # известные лимиты, чтобы тест не зависел от .env
    monkeypatch.setattr(settings, "limit_food_trial", 3, raising=False)
    monkeypatch.setattr(settings, "limit_food_daily", 5, raising=False)
    monkeypatch.setattr(settings, "daily_cost_soft_usd", 5.0, raising=False)
    monkeypatch.setattr(settings, "daily_cost_hard_usd", 10.0, raising=False)
    monkeypatch.setattr(settings, "admin_ids", {999}, raising=False)
    limits._LIMITS["food"] = (3, 5)
    return fake


def test_admin_bypass():
    ok, reason = _run(limits.check_and_consume(999, "food", activated=True))
    assert ok and reason is None


def test_trial_quota_then_deny():
    # новичок (activated=False): триал = 3, четвёртая попытка — отказ
    results = [_run(limits.check_and_consume(1, "food", activated=False)) for _ in range(4)]
    assert [r[0] for r in results] == [True, True, True, False]
    assert results[-1][1] == "quota"


def test_daily_quota_after_activation():
    # активированный: суточный лимит = 5
    results = [_run(limits.check_and_consume(2, "food", activated=True)) for _ in range(6)]
    assert [r[0] for r in results] == [True, True, True, True, True, False]
    assert results[-1][1] == "quota"


def test_fuse_hard_denies(monkeypatch):
    monkeypatch.setattr(limits.usage, "spent_today_usd", lambda: 12.0)  # выше hard-порога
    ok, reason = _run(limits.check_and_consume(3, "food", activated=True))
    assert not ok and reason == "fuse"


def test_redis_down_fail_open(monkeypatch):
    def boom():
        raise RuntimeError("redis down")
    monkeypatch.setattr(limits, "_client", boom)
    ok, reason = _run(limits.check_and_consume(4, "food", activated=True))
    assert ok and reason is None  # инфра-сбой не должен блокировать пользователя
