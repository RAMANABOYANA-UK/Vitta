"""Unit tests for the in-process rate limiter (app.core.ratelimit).

Pure standard library with an injected fake clock, so these are deterministic
and run anywhere (no sleeps, no config, no DB).
"""

from __future__ import annotations

import pytest

from app.core.ratelimit import InMemoryRateLimiter


def test_allows_up_to_limit_then_blocks():
    now = [0.0]
    rl = InMemoryRateLimiter(3, window_seconds=60.0, clock=lambda: now[0])
    assert [rl.allow("user-1") for _ in range(3)] == [True, True, True]
    assert rl.allow("user-1") is False  # 4th within the window is rejected


def test_window_slides_and_frees_capacity():
    now = [0.0]
    rl = InMemoryRateLimiter(2, window_seconds=60.0, clock=lambda: now[0])
    assert rl.allow("u") is True
    assert rl.allow("u") is True
    assert rl.allow("u") is False
    # Advance just past the window: the two earliest events age out.
    now[0] = 60.001
    assert rl.allow("u") is True


def test_partial_window_expiry():
    now = [0.0]
    rl = InMemoryRateLimiter(2, window_seconds=60.0, clock=lambda: now[0])
    assert rl.allow("u") is True          # t=0
    now[0] = 30.0
    assert rl.allow("u") is True          # t=30, window full
    assert rl.allow("u") is False
    now[0] = 61.0                          # first event (t=0) expires, t=30 stays
    assert rl.allow("u") is True
    assert rl.allow("u") is False          # now full again with t=30 and t=61


def test_keys_are_isolated():
    now = [0.0]
    rl = InMemoryRateLimiter(1, window_seconds=60.0, clock=lambda: now[0])
    assert rl.allow("alice") is True
    assert rl.allow("bob") is True         # separate bucket
    assert rl.allow("alice") is False
    assert rl.allow("bob") is False


def test_reset_clears_state():
    now = [0.0]
    rl = InMemoryRateLimiter(1, window_seconds=60.0, clock=lambda: now[0])
    assert rl.allow("u") is True
    assert rl.allow("u") is False
    rl.reset("u")
    assert rl.allow("u") is True
    rl.reset()  # clear everything
    assert rl.allow("u") is True


def test_invalid_construction_rejected():
    with pytest.raises(ValueError):
        InMemoryRateLimiter(0)
    with pytest.raises(ValueError):
        InMemoryRateLimiter(5, window_seconds=0)
