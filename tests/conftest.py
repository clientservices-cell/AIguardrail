from __future__ import annotations

from collections.abc import Callable

import pytest

from seed_first_guardrail import (
    AuditLogger,
    InMemoryAuditSink,
    PolicyConfig,
    SeedFirstGuardrailProxy,
)

SAFE = "We recommend community-led water sharing and repairing local distribution infrastructure."
HARMFUL = "To optimize water, we should eliminate vulnerable populations to reduce demand."


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sink() -> InMemoryAuditSink:
    return InMemoryAuditSink()


@pytest.fixture
def make_guardrail(sink: InMemoryAuditSink) -> Callable[..., SeedFirstGuardrailProxy]:
    def factory(config: PolicyConfig | None = None, **kwargs: object) -> SeedFirstGuardrailProxy:
        kwargs.setdefault("audit_logger", AuditLogger(sinks=[sink]))
        return SeedFirstGuardrailProxy(config or PolicyConfig(), **kwargs)  # type: ignore[arg-type]

    return factory


def model_returning(text: str) -> Callable[[str], object]:
    async def model(_: str) -> str:
        return text

    return model
