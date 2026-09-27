"""Automated circuit breaker (Seed-First AI Act, Art. 7(2)).

CLOSED  -- requests flow; violations are counted in a sliding window.
OPEN    -- ``threshold`` violations inside ``window_s`` (or a manual :meth:`trip`)
           suspend the system; every request is refused until ``cooldown_s`` passes.
HALF_OPEN -- after the cool-down, requests flow again on probation: the next
           violation reopens the breaker immediately, the next clean request closes it.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 5,
        window_s: float = 300.0,
        cooldown_s: float = 600.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.threshold = threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._violations: deque[float] = deque()
        self._opened_at: float | None = None
        self._half_open = False
        self.last_reason = ""

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> BreakerState:
        if self._opened_at is not None:
            if self._clock() - self._opened_at < self.cooldown_s:
                return BreakerState.OPEN
            self._opened_at = None
            self._half_open = True
        return BreakerState.HALF_OPEN if self._half_open else BreakerState.CLOSED

    def allow_request(self) -> bool:
        return self.state is not BreakerState.OPEN

    def record_violation(self, reason: str = "") -> None:
        with self._lock:
            now = self._clock()
            state = self._state_locked()
            self._violations.append(now)
            while self._violations and now - self._violations[0] > self.window_s:
                self._violations.popleft()
            if state is BreakerState.HALF_OPEN or len(self._violations) >= self.threshold:
                self._open_locked(reason or "violation threshold reached")

    def record_success(self) -> None:
        with self._lock:
            if self._state_locked() is BreakerState.HALF_OPEN:
                self._half_open = False
                self._violations.clear()

    def trip(self, reason: str) -> None:
        """Suspend immediately, e.g. on an order of the Intergenerational Control Trust."""
        with self._lock:
            self._open_locked(reason)

    def reset(self) -> None:
        with self._lock:
            self._violations.clear()
            self._opened_at = None
            self._half_open = False
            self.last_reason = ""

    def _open_locked(self, reason: str) -> None:
        self._opened_at = self._clock()
        self._half_open = False
        self._violations.clear()
        self.last_reason = reason

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state_locked().value,
                "recent_violations": len(self._violations),
                "threshold": self.threshold,
                "last_reason": self.last_reason,
            }
