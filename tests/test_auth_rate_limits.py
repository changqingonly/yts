from __future__ import annotations

import pytest
from yts_server.errors import AppError
from yts_server.security.rate_limits import SlidingWindowLimiter


def test_sliding_window_rejects_limit_and_recovers_after_window() -> None:
    now = [100.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0], max_keys=10)
    limiter.check("login", "ip", limit=2, window_seconds=60)
    limiter.check("login", "ip", limit=2, window_seconds=60)

    with pytest.raises(AppError) as raised:
        limiter.check("login", "ip", limit=2, window_seconds=60)

    assert raised.value.status_code == 429
    now[0] = 161.0
    limiter.check("login", "ip", limit=2, window_seconds=60)


def test_sliding_window_refuses_unbounded_key_growth() -> None:
    limiter = SlidingWindowLimiter(max_keys=1)
    limiter.check("login", "first", limit=2, window_seconds=60)

    with pytest.raises(AppError) as raised:
        limiter.check("login", "second", limit=2, window_seconds=60)
    assert raised.value.message == "rate limit capacity exhausted"


def test_password_key_capacity_rejects_before_rsa_generation(monkeypatch) -> None:
    from yts_server.security import password_keys

    generated = False

    def generate_private_key(**_kwargs):
        nonlocal generated
        generated = True

    monkeypatch.setattr(password_keys, "MAX_CACHED_KEYS", 0)
    monkeypatch.setattr(password_keys.rsa, "generate_private_key", generate_private_key)

    with pytest.raises(AppError) as raised:
        password_keys.issue_password_key()

    assert raised.value.status_code == 429
    assert generated is False
