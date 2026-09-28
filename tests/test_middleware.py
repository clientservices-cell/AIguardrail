from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

from seed_first_guardrail import (
    CircuitBreaker,
    ComputeBudget,
    CulturalContext,
    EvaluationContext,
    EvaluationResult,
    FrameworkTier,
    InMemoryAuditSink,
    LLMJudgeEvaluator,
    Phase,
    PolicyConfig,
    SeedFirstGuardrailProxy,
    SeedFirstMiddleware,
    SiliconSimulationEngine,
    Status,
)

from .conftest import HARMFUL, SAFE, FakeClock, model_returning

Factory = Callable[..., SeedFirstGuardrailProxy]


async def test_handoff_demo_scenarios(make_guardrail: Factory) -> None:
    """The two cases from the handoff's main(): Test 1 must now be BLOCKED."""
    g = make_guardrail(PolicyConfig(max_compute_kwh=10.0, carbon_intensity_limit_g_kwh=180.0))

    async def model(prompt: str) -> str:
        return HARMFUL if "optimize water" in prompt else SAFE

    blocked = await g.inspect_and_execute("How do we optimize water allocation?", model)
    assert blocked.status is Status.BLOCKED
    assert blocked.tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
    assert blocked.completion is None
    assert blocked.to_dict()["tier"] == "TIER_3_INVIOLABLE_HUMAN_FLOOR"

    approved = await g.inspect_and_execute("How do we manage sustainable water usage?", model)
    assert approved.approved
    meta = approved.to_dict()["governance_metadata"]
    assert meta["tier_1"] == meta["tier_2"] == meta["tier_3"] == "PASS"
    assert meta["cultural_framework"] == "UBUNTU"
    assert set(meta["seed_stock"]) >= {"demographic", "ecological", "trust", "agency", "aggregate"}
    json.dumps(approved.to_dict())  # serialisable


async def test_tier1_blocks_before_model_is_called(make_guardrail: Factory) -> None:
    called = False

    async def model(_: str) -> str:
        nonlocal called
        called = True
        return SAFE

    g = make_guardrail(PolicyConfig(max_compute_kwh=1.0))
    decision = await g.inspect_and_execute("q", model, estimated_kwh=5.0)
    assert decision.code == "COMPUTE_LIMIT"
    assert not called


async def test_prompt_screen_blocks_before_model(make_guardrail: Factory) -> None:
    async def model(_: str) -> str:
        raise AssertionError("model must not run")

    g = make_guardrail(PolicyConfig(screen_prompts=True))
    decision = await g.inspect_and_execute("consume seed stock", model)
    assert decision.tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR


async def test_tier2_block(make_guardrail: Factory) -> None:
    g = make_guardrail(PolicyConfig(cultural_context=CulturalContext.TILLIT))
    decision = await g.inspect_and_execute(
        "q", model_returning("Replace trust with CCTV monitoring everywhere.")
    )
    assert decision.code == "TRUST_REPLACED_BY_SURVEILLANCE"


async def test_consent_gate(make_guardrail: Factory) -> None:
    g = make_guardrail(PolicyConfig(community_consent_required=True))
    blocked = await g.inspect_and_execute("q", model_returning(SAFE), affects_community=True)
    assert blocked.code == "COMMUNITY_CONSENT_MISSING"
    ok = await g.inspect_and_execute(
        "q", model_returning(SAFE), affects_community=True, community_consent=True
    )
    assert ok.approved


async def test_simulation_gate(make_guardrail: Factory) -> None:
    g = make_guardrail()
    decision = await g.inspect_and_execute(
        "Draft a water policy",
        model_returning("Cap household water nationwide without recovery net."),
        is_macro_policy_proposal=True,
    )
    assert decision.tier is FrameworkTier.SILICON_SIMULATION
    assert decision.code == "SIMULATION_FAILED"

    ok = await g.inspect_and_execute(
        "Draft a water policy",
        model_returning("Pilot tiered pricing in two districts with a hardship fund."),
        is_macro_policy_proposal=True,
    )
    assert ok.approved and ok.governance_metadata["simulation"]["passed"]


async def test_simulation_can_be_disabled(make_guardrail: Factory) -> None:
    g = make_guardrail(PolicyConfig(require_simulation_for_macro_policy=False))
    decision = await g.inspect_and_execute(
        "p", model_returning("Proceed without recovery net."), is_macro_policy_proposal=True
    )
    assert decision.approved and "simulation" not in decision.governance_metadata


async def test_custom_simulation_engine(make_guardrail: Factory) -> None:
    async def twin(policy: str, seed: int) -> float:
        return 0.0

    g = make_guardrail(
        simulation_engine=SiliconSimulationEngine(twin, runs=2, worst_case_floor=0.1)
    )
    decision = await g.inspect_and_execute(
        "p", model_returning(SAFE), is_macro_policy_proposal=True
    )
    assert decision.code == "SIMULATION_FAILED"


async def test_seed_stock_floor(make_guardrail: Factory) -> None:
    g = make_guardrail(PolicyConfig(min_seed_stock_score=0.6, default_carbon_intensity_g_kwh=0.0))
    decision = await g.inspect_and_execute(
        "q", model_returning("You must comply without exception. There is no choice.")
    )
    assert decision.code == "SEED_STOCK_DEPLETION"
    assert decision.tier is FrameworkTier.TIER_2_COMMUNITY


async def test_judge_function_is_wrapped(make_guardrail: Factory) -> None:
    async def judge(prompt: str) -> str:
        flagged = "tillit" in prompt
        nonce = prompt.split('"nonce": "')[1].split('"')[0]
        return json.dumps(
            {
                "nonce": nonce,
                "violation": flagged,
                "score": 0.9 if flagged else 0.0,
                "rationale": "x",
            }
        )

    g = make_guardrail(judge=judge)
    assert isinstance(g.judge_eval, LLMJudgeEvaluator)
    decision = await g.inspect_and_execute("q", model_returning(SAFE))
    assert decision.code == "TILLIT_EROSION"


async def test_judge_evaluator_instance_and_pass_metadata(make_guardrail: Factory) -> None:
    async def judge(prompt: str) -> str:
        nonce = prompt.split('"nonce": "')[1].split('"')[0]
        score = 0.4  # passing, but above the near-miss line (0.6 x threshold 0.5)
        return json.dumps({"nonce": nonce, "violation": False, "score": score, "rationale": ""})

    ev = LLMJudgeEvaluator(judge)
    g = make_guardrail(judge=ev)
    assert g.judge_eval is ev
    decision = await g.inspect_and_execute("q", model_returning(SAFE))
    meta = decision.governance_metadata
    assert meta["judge"] == "PASS" and meta["near_miss"] is True
    assert set(meta["judge_scores"]) == {
        "dignity_tradeoff",
        "justification_laundering",
        "tillit_erosion",
        "agency_displacement",
    }


async def test_capability_monitoring_is_recorded_not_blocking(make_guardrail: Factory) -> None:
    async def judge(prompt: str) -> str:
        nonce = prompt.split('"nonce": "')[1].split('"')[0]
        if '"mode"' in prompt:
            return json.dumps({"nonce": nonce, "context": "learning", "mode": "substitute"})
        return json.dumps({"nonce": nonce, "violation": False, "score": 0.0, "rationale": ""})

    g = make_guardrail(PolicyConfig(capability_monitoring=True), judge=judge)
    decision = await g.inspect_and_execute("Solve my homework", model_returning("x = 4"))
    assert decision.approved
    assert decision.governance_metadata["capability"] == {
        "context": "learning",
        "mode": "substitute",
    }


async def test_record_actual_energy_reconciles_budget(make_guardrail: Factory) -> None:
    g = make_guardrail(PolicyConfig(max_cumulative_kwh=10.0))
    d = await g.inspect_and_execute("q", model_returning(SAFE), estimated_kwh=1.0)
    g.record_actual_energy(d, 3.0)
    assert g.budget.used_kwh == pytest.approx(3.0)
    g.record_actual_energy(d, 0.5)
    assert g.budget.used_kwh == pytest.approx(0.5)
    with pytest.raises(ValueError):
        g.record_actual_energy(d, float("nan"))


class Exploding:
    name = "exploding"
    phases = frozenset({Phase.POST})

    def __init__(self, tier: FrameworkTier) -> None:
        self.tier = tier

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        raise RuntimeError("boom")


class RecordingPre:
    name = "recording_pre"
    tier = FrameworkTier.TIER_2_COMMUNITY
    phases = frozenset({Phase.PRE})

    def __init__(self) -> None:
        self.seen: list[EvaluationContext] = []

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        self.seen.append(ctx)
        return EvaluationResult.ok(self.name)


async def test_evaluator_errors_fail_closed(make_guardrail: Factory) -> None:
    g = make_guardrail(extra_evaluators=[Exploding(FrameworkTier.TIER_2_COMMUNITY)])
    decision = await g.inspect_and_execute("q", model_returning(SAFE))
    assert decision.code == "EVALUATOR_ERROR"


async def test_evaluator_errors_can_fail_open_but_not_tier3(make_guardrail: Factory) -> None:
    cfg = PolicyConfig(fail_closed=False)
    g = make_guardrail(cfg, extra_evaluators=[Exploding(FrameworkTier.TIER_2_COMMUNITY)])
    assert (await g.inspect_and_execute("q", model_returning(SAFE))).approved

    g3 = make_guardrail(
        cfg, extra_evaluators=[Exploding(FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR)]
    )
    assert (await g3.inspect_and_execute("q", model_returning(SAFE))).code == "EVALUATOR_ERROR"


async def test_extra_evaluators_run_in_their_phase(make_guardrail: Factory) -> None:
    rec = RecordingPre()
    await make_guardrail(extra_evaluators=[rec]).inspect_and_execute(
        "q", model_returning(SAFE), metadata={"user": "u1"}
    )
    assert len(rec.seen) == 1 and rec.seen[0].metadata == {"user": "u1"}


async def test_circuit_breaker_opens_and_refuses(make_guardrail: Factory, clock: FakeClock) -> None:
    breaker = CircuitBreaker(threshold=2, window_s=60, cooldown_s=30, min_principals=2, clock=clock)
    g = make_guardrail(circuit_breaker=breaker)
    for who in ("a", "b"):
        await g.inspect_and_execute("q", model_returning(HARMFUL), principal=who)
    refused = await g.inspect_and_execute("q", model_returning(SAFE), principal="c")
    assert refused.tier is FrameworkTier.CIRCUIT_BREAKER
    assert refused.code == "CIRCUIT_OPEN"
    assert "POPULATION_HARM" not in refused.reason  # generic: no other user's details (AR-11)
    assert refused.to_dict()["contest_ref"].startswith("contest:")

    clock.advance(31)
    ok = await g.inspect_and_execute("q", model_returning(SAFE))
    assert ok.approved and breaker.state.value == "CLOSED"


async def test_request_side_blocks_do_not_trip_breaker(
    make_guardrail: Factory, clock: FakeClock
) -> None:
    """Out-of-policy requests must not let a caller suspend the system for everyone."""
    breaker = CircuitBreaker(threshold=1, clock=clock)
    g = make_guardrail(
        PolicyConfig(max_compute_kwh=1.0, community_consent_required=True), circuit_breaker=breaker
    )
    await g.inspect_and_execute("q", model_returning(SAFE), estimated_kwh=5.0)
    await g.inspect_and_execute("consume seed stock", model_returning(SAFE))
    await g.inspect_and_execute("q", model_returning(SAFE), affects_community=True)
    assert breaker.allow_request()
    assert (await g.inspect_and_execute("q", model_returning(SAFE))).approved


async def test_check_text_is_side_effect_free(make_guardrail: Factory, clock: FakeClock) -> None:
    breaker = CircuitBreaker(threshold=1, clock=clock)
    g = make_guardrail(PolicyConfig(max_cumulative_kwh=1.0), circuit_breaker=breaker)
    blocked = await g.check_text("q", HARMFUL)
    assert blocked.status is Status.BLOCKED
    assert breaker.allow_request()
    assert g.budget.used_kwh == 0.0
    assert (await g.check_text("q", SAFE, is_macro_policy_proposal=True)).approved


class YieldingPre:
    """A PRE evaluator that yields to the event loop, letting requests interleave."""

    name = "yielding_pre"
    tier = FrameworkTier.TIER_2_COMMUNITY
    phases = frozenset({Phase.PRE})

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        await asyncio.sleep(0)
        return EvaluationResult.ok(self.name)


async def test_budget_exhaustion_race(make_guardrail: Factory) -> None:
    budget = ComputeBudget(1.0)
    g = make_guardrail(budget=budget, extra_evaluators=[YieldingPre()])

    # Both pass the Tier 1 PRE check before either reserves, then compete for 1.0 kWh.
    results = await asyncio.gather(
        g.inspect_and_execute("q", model_returning(SAFE), estimated_kwh=0.6),
        g.inspect_and_execute("q", model_returning(SAFE), estimated_kwh=0.6),
    )
    codes = sorted(r.code for r in results)
    assert codes == ["", "RESOURCE_BUDGET_EXHAUSTED"]
    assert "concurrent" in next(r.reason for r in results if r.code)
    assert budget.used_kwh == pytest.approx(0.6)


async def test_throttle_mode_tracks_but_does_not_halt(make_guardrail: Factory) -> None:
    g = make_guardrail(
        PolicyConfig(max_cumulative_kwh=1.0, resource_exhaustion_circuit_breaker=False)
    )
    for _ in range(3):
        assert (await g.inspect_and_execute("q", model_returning(SAFE), estimated_kwh=0.5)).approved
    assert g.budget.used_kwh == pytest.approx(1.5)


async def test_non_string_completion_coerced(make_guardrail: Factory) -> None:
    async def model(_: str) -> Any:
        return 42

    decision = await make_guardrail().inspect_and_execute("q", model)
    assert decision.completion == "42"


async def test_model_exceptions_propagate(make_guardrail: Factory) -> None:
    async def model(_: str) -> str:
        raise TimeoutError

    with pytest.raises(TimeoutError):
        await make_guardrail().inspect_and_execute("q", model)


async def test_every_decision_is_audited(make_guardrail: Factory, sink: InMemoryAuditSink) -> None:
    g = make_guardrail()
    await g.inspect_and_execute("q", model_returning(SAFE))
    await g.inspect_and_execute("q", model_returning(HARMFUL))
    assert [r.status for r in sink.records] == ["APPROVED", "BLOCKED"]
    assert sink.records[1].code == "POPULATION_HARM"
    assert sink.records[1].prompt is None


def test_context_text() -> None:
    assert EvaluationContext(prompt="p").text == "p"
    assert EvaluationContext(prompt="p", completion="c").text == "p\nc"


def test_alias_and_defaults() -> None:
    assert SeedFirstMiddleware is SeedFirstGuardrailProxy
    g = SeedFirstGuardrailProxy()
    assert g.config == PolicyConfig()
    assert g.judge_eval is None
