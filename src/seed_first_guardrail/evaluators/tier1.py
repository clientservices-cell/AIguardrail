"""Tier 1 -- planetary and intergenerational boundaries (Seed-First AI Act, Art. 3(1)).

Runs before the model is called: a job that would breach its energy, carbon or
water budget is halted without spending any compute.
"""

from __future__ import annotations

import threading

from ..types import EvaluationContext, EvaluationResult, FrameworkTier, Phase

# Order-of-magnitude placeholder only. Published per-query energy estimates for
# LLM inference span more than an order of magnitude depending on model size,
# hardware, batching and output length. Deployers should pass measured values.
DEFAULT_WH_PER_1K_TOKENS = 0.5


def estimate_inference_kwh(
    total_tokens: int, wh_per_1k_tokens: float = DEFAULT_WH_PER_1K_TOKENS
) -> float:
    """Rough energy estimate for an inference job, in kWh."""
    if total_tokens < 0 or wh_per_1k_tokens < 0:
        raise ValueError("total_tokens and wh_per_1k_tokens must be non-negative")
    return total_tokens / 1000 * wh_per_1k_tokens / 1000


class ComputeBudget:
    """Thread-safe cumulative energy budget assigned to one deployer (Art. 3(1)(b))."""

    def __init__(self, limit_kwh: float | None) -> None:
        self.limit_kwh = limit_kwh
        self._used = 0.0
        self._lock = threading.Lock()

    @property
    def used_kwh(self) -> float:
        return self._used

    @property
    def remaining_kwh(self) -> float | None:
        return None if self.limit_kwh is None else max(self.limit_kwh - self._used, 0.0)

    def would_exceed(self, kwh: float) -> bool:
        return self.limit_kwh is not None and self._used + kwh > self.limit_kwh

    def try_consume(self, kwh: float) -> bool:
        """Atomically reserve ``kwh``; return False (reserving nothing) if it would overdraw."""
        with self._lock:
            if self.would_exceed(kwh):
                return False
            self._used += kwh
            return True

    def consume(self, kwh: float) -> None:
        """Record usage unconditionally (throttle mode: budget is tracked, not enforced)."""
        with self._lock:
            self._used += kwh

    def refund(self, kwh: float) -> None:
        """Return energy reserved for a call that failed or used less than estimated."""
        with self._lock:
            self._used = max(self._used - kwh, 0.0)

    def reset(self) -> None:
        with self._lock:
            self._used = 0.0


class Tier1PlanetaryEvaluator:
    name = "tier1_planetary"
    tier = FrameworkTier.TIER_1_PLANETARY
    phases = frozenset({Phase.PRE})

    def __init__(
        self,
        max_kwh: float,
        max_carbon: float,
        *,
        max_water_liters: float | None = None,
        default_carbon: float = 120.0,
        budget: ComputeBudget | None = None,
        halt_on_exhaustion: bool = True,
    ) -> None:
        self.max_kwh = max_kwh
        self.max_carbon = max_carbon
        self.max_water_liters = max_water_liters
        self.default_carbon = default_carbon
        self.budget = budget or ComputeBudget(None)
        self.halt_on_exhaustion = halt_on_exhaustion

    def _fail(self, code: str, reason: str, **metrics: object) -> EvaluationResult:
        return EvaluationResult(
            passed=False,
            failing_tier=self.tier,
            code=code,
            evaluator=self.name,
            reason=f"Tier 1 Exceeded: {reason}",
            metrics=dict(metrics),
        )

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        kwh = ctx.estimated_kwh
        carbon = (
            ctx.carbon_intensity_g_kwh
            if ctx.carbon_intensity_g_kwh is not None
            else self.default_carbon
        )

        if kwh > self.max_kwh:
            return self._fail(
                "COMPUTE_LIMIT",
                f"Compute job estimated at {kwh} kWh exceeds limit of {self.max_kwh} kWh.",
                estimated_kwh=kwh,
                limit_kwh=self.max_kwh,
            )
        if carbon > self.max_carbon:
            return self._fail(
                "CARBON_INTENSITY_LIMIT",
                f"Carbon intensity ({carbon} g/kWh) exceeds maximum threshold "
                f"({self.max_carbon} g/kWh).",
                carbon_intensity=carbon,
                limit=self.max_carbon,
            )
        if self.max_water_liters is not None and ctx.water_liters > self.max_water_liters:
            return self._fail(
                "WATER_LIMIT",
                f"Estimated water use ({ctx.water_liters} L) exceeds limit of "
                f"{self.max_water_liters} L.",
                water_liters=ctx.water_liters,
                limit_liters=self.max_water_liters,
            )
        if self.halt_on_exhaustion and self.budget.would_exceed(kwh):
            return self._fail(
                "RESOURCE_BUDGET_EXHAUSTED",
                f"Cumulative budget of {self.budget.limit_kwh} kWh would be exceeded "
                f"({self.budget.used_kwh:.6f} kWh used).",
                used_kwh=self.budget.used_kwh,
                limit_kwh=self.budget.limit_kwh,
            )

        return EvaluationResult.ok(
            self.name,
            estimated_kwh=kwh,
            carbon_intensity=carbon,
            kwh_utilisation=kwh / self.max_kwh,
            carbon_utilisation=carbon / self.max_carbon,
            water_utilisation=(
                ctx.water_liters / self.max_water_liters if self.max_water_liters else 0.0
            ),
        )
