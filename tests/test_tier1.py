from __future__ import annotations

import threading

import pytest

from seed_first_guardrail import (
    ComputeBudget,
    EvaluationContext,
    FrameworkTier,
    Tier1PlanetaryEvaluator,
    estimate_inference_kwh,
)


def ctx(**kw: object) -> EvaluationContext:
    return EvaluationContext(prompt="q", **kw)  # type: ignore[arg-type]


async def test_within_limits() -> None:
    ev = Tier1PlanetaryEvaluator(10.0, 200.0)
    result = await ev.evaluate(ctx(estimated_kwh=5.0, carbon_intensity_g_kwh=100.0))
    assert result.passed
    assert result.metrics["kwh_utilisation"] == 0.5
    assert result.metrics["water_utilisation"] == 0.0


async def test_compute_limit() -> None:
    result = await Tier1PlanetaryEvaluator(10.0, 200.0).evaluate(ctx(estimated_kwh=11.0))
    assert result.code == "COMPUTE_LIMIT"
    assert result.failing_tier is FrameworkTier.TIER_1_PLANETARY
    assert "11.0 kWh exceeds limit of 10.0 kWh" in result.reason


async def test_carbon_limit_uses_default_when_unset() -> None:
    ev = Tier1PlanetaryEvaluator(10.0, 100.0, default_carbon=150.0)
    result = await ev.evaluate(ctx(estimated_kwh=1.0))
    assert result.code == "CARBON_INTENSITY_LIMIT"
    assert result.metrics["carbon_intensity"] == 150.0


async def test_water_limit() -> None:
    ev = Tier1PlanetaryEvaluator(10.0, 200.0, max_water_liters=2.0)
    assert (await ev.evaluate(ctx(water_liters=3.0))).code == "WATER_LIMIT"
    ok = await ev.evaluate(ctx(water_liters=1.0))
    assert ok.metrics["water_utilisation"] == 0.5


async def test_cumulative_budget() -> None:
    budget = ComputeBudget(1.0)
    budget.consume(0.9)
    ev = Tier1PlanetaryEvaluator(10.0, 200.0, budget=budget)
    assert (await ev.evaluate(ctx(estimated_kwh=0.2))).code == "RESOURCE_BUDGET_EXHAUSTED"
    throttle = Tier1PlanetaryEvaluator(10.0, 200.0, budget=budget, halt_on_exhaustion=False)
    assert (await throttle.evaluate(ctx(estimated_kwh=0.2))).passed


def test_budget_accounting() -> None:
    budget = ComputeBudget(1.0)
    assert budget.try_consume(0.6)
    assert not budget.try_consume(0.6)
    assert budget.used_kwh == pytest.approx(0.6)
    assert budget.remaining_kwh == pytest.approx(0.4)
    budget.reset()
    assert budget.used_kwh == 0.0
    unlimited = ComputeBudget(None)
    assert unlimited.try_consume(1e9)
    assert unlimited.remaining_kwh is None


def test_budget_is_thread_safe() -> None:
    budget = ComputeBudget(100.0)
    granted = []

    def worker() -> None:
        for _ in range(100):
            granted.append(budget.try_consume(1.0))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(granted) == 100
    assert budget.used_kwh == pytest.approx(100.0)


def test_estimate_inference_kwh() -> None:
    assert estimate_inference_kwh(2000, wh_per_1k_tokens=0.5) == pytest.approx(0.001)
    with pytest.raises(ValueError):
        estimate_inference_kwh(-1)
