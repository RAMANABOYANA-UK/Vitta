"""In-process sliding-window rate limiter (standard library only).

Single-process only: the counters live in *this* worker's memory. A multi-worker
(uvicorn --workers N) or multi-instance deployment must move this to a shared
store such as Redis, otherwise each worker enforces the limit independently and
the effective ceiling is N x the configured value.

Kept dependency-free (no app config, no third-party packages) so it can be unit
tested in isolation. The clock is injectable for deterministic tests.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict


class InMemoryRateLimiter:
    """Sliding-window log limiter: at most ``max_events`` events per ``key``
    within any ``window_seconds`` interval.

    A sliding window (rather than a fixed calendar window) avoids the burst at
    window boundaries where a fixed window would briefly allow ``2 * max_events``.
    """

    def __init__(
        self,
        max_events: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record and permit an event for ``key``, or return False if it would
        exceed the limit. Thread-safe."""
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            # Drop timestamps that have aged out of the window.
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        """Clear state for one key, or all keys when ``key`` is None. Mainly for
        tests and administrative use."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
