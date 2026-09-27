"""Evaluator protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..types import EvaluationContext, EvaluationResult, FrameworkTier, Phase


@runtime_checkable
class Evaluator(Protocol):
    """Anything with a ``name``, a ``tier``, the ``phases`` it runs in and an async ``evaluate``."""

    name: str
    tier: FrameworkTier
    phases: frozenset[Phase]

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult: ...
