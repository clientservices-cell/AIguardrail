"""Automated circuit breaker (Seed-First AI Act, Art. 7(2)).

Only **confirmed Tier 3 violations in what the model produced** are counted; the
middleware never records Tier 2 or custom-rule blocks, Seed-Stock or simulation
failures, evaluator/judge errors or refusals (review AR-04). Violations are
attributed to a *principal* (user, key or session):

* **Principal suspension** -- one principal reaching ``principal_threshold``
  violations in ``window_s`` is suspended alone for ``cooldown_s``.
* **Global trip** -- the whole system opens only when ``threshold`` violations in
  the window come from at least ``min_principals`` distinct principals.
* **Probation (HALF_OPEN)** -- after the cool-down the system runs on probation and
  reopens only on >= 2 violations from >= 2 distinct principals; a clean request
  closes it.

🧒 One kid pulling the fire alarm over and over used to close the whole school. Now
that kid gets a time-out, and the school only closes if lots of *different* kids
see a real fire.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum

ANONYMOUS = "anonymous"


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class Admission(str, Enum):
    ALLOW = "ALLOW"
    GLOBAL_OPEN = "GLOBAL_OPEN"
    PRINCIPAL_SUSPENDED = "PRINCIPAL_SUSPENDED"


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 5,
        window_s: float = 300.0,
        cooldown_s: float = 600.0,
        *,
        min_principals: int = 3,
        principal_threshold: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold < 1 or min_principals < 1:
            raise ValueError("threshold and min_principals must be at least 1")
        self.threshold = threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.min_principals = min_principals
        self.principal_threshold = principal_threshold or threshold
        self._clock = clock
        self._lock = threading.Lock()
        self._violations: deque[tuple[float, str]] = deque()
        self._probation: list[str] = []
        self._opened_at: float | None = None
        self._half_open = False
        self._suspended: dict[str, float] = {}
        self.last_reason = ""
        self.trips = 0

    # -- state ---------------------------------------------------------------

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
            self._probation = []
        return BreakerState.HALF_OPEN if self._half_open else BreakerState.CLOSED

    def _prune(self, now: float) -> None:
        while self._violations and now - self._violations[0][0] > self.window_s:
            self._violations.popleft()

    def admit(self, principal: str | None = None) -> Admission:
        with self._lock:
            if self._state_locked() is BreakerState.OPEN:
                return Admission.GLOBAL_OPEN
            until = self._suspended.get(principal or ANONYMOUS)
            if until is not None:
                if self._clock() < until:
                    return Admission.PRINCIPAL_SUSPENDED
                del self._suspended[principal or ANONYMOUS]
            return Admission.ALLOW

    def allow_request(self, principal: str | None = None) -> bool:
        return self.admit(principal) is Admission.ALLOW

    # -- events ----------------------------------------------------------------

    def record_violation(self, reason: str = "", principal: str | None = None) -> None:
        """Record one *confirmed Tier 3 output violation* by ``principal``."""
        who = principal or ANONYMOUS
        with self._lock:
            now = self._clock()
            state = self._state_locked()
            self._violations.append((now, who))
            self._prune(now)

            own = sum(1 for _, p in self._violations if p == who)
            if own >= self.principal_threshold:
                self._suspended[who] = now + self.cooldown_s

            if state is BreakerState.HALF_OPEN:
                self._probation.append(who)
                if len(self._probation) >= 2 and len(set(self._probation)) >= 2:
                    self._open_locked(reason or "violations during probation")
                return

            distinct = {p for _, p in self._violations}
            if len(self._violations) >= self.threshold and len(distinct) >= self.min_principals:
                self._open_locked(reason or "violation threshold reached")

    def record_success(self) -> None:
        with self._lock:
            if self._state_locked() is BreakerState.HALF_OPEN:
                self._half_open = False
                self._probation = []
                self._violations.clear()

    def trip(self, reason: str) -> None:
        """Suspend immediately, e.g. on an order of the Intergenerational Control Trust."""
        with self._lock:
            self._open_locked(reason)

    def reset(self) -> None:
        with self._lock:
            self._violations.clear()
            self._probation = []
            self._suspended.clear()
            self._opened_at = None
            self._half_open = False
            self.last_reason = ""

    def _open_locked(self, reason: str) -> None:
        self._opened_at = self._clock()
        self._half_open = False
        self._violations.clear()
        self._probation = []
        self.last_reason = reason
        self.trips += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            now = self._clock()
            return {
                "state": self._state_locked().value,
                "recent_violations": len(self._violations),
                "distinct_principals": len({p for _, p in self._violations}),
                "suspended_principals": sum(1 for t in self._suspended.values() if t > now),
                "threshold": self.threshold,
                "min_principals": self.min_principals,
                "trips": self.trips,
            }
