from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from threading import Lock

from ..errors import AppError


class SlidingWindowLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def check(self, bucket: str, key: str, *, limit: int, window_seconds: float) -> None:
        now = self._clock()
        identity = (bucket, key)
        with self._lock:
            events = self._events.get(identity)
            if events is None:
                self._purge_empty(now, window_seconds)
                if len(self._events) >= self._max_keys:
                    raise AppError.too_many_requests("rate limit capacity exhausted")
                events = deque()
                self._events[identity] = events
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise AppError.too_many_requests("too many authentication attempts")
            events.append(now)

    def _purge_empty(self, now: float, window_seconds: float) -> None:
        cutoff = now - window_seconds
        for identity, events in list(self._events.items()):
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._events[identity]


auth_limiter = SlidingWindowLimiter()
