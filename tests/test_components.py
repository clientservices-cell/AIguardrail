"""Metrics, simulation, circuit breaker, audit and pattern-engine tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from seed_first_guardrail import (
    AuditLogger,
    BreakerState,
    CircuitBreaker,
    GuardrailDecision,
    InMemoryAuditSink,
    JsonlFileAuditSink,
    SiliconSimulationEngine,
    Status,
    compute_seed_stock,
)
from seed_first_guardrail._patterns import PatternRule, first_match, normalize
from seed_first_guardrail.audit import sha256
from seed_first_guardrail.metrics import (
    agency_score,
    demographic_score,
    ecological_score,
    signal_score,
    trust_score,
)

from .conftest import FakeClock

# -- patterns ------------------------------------------------------------------


def test_normalize() -> None:
    assert normalize("ｆｕｌｌ​width \n\t text­") == "fullwidth text"


def test_pattern_rule_unless() -> None:
    rule = PatternRule(code="X", pattern="alpha", reason="r", unless="beta")
    assert rule.search("alpha") is not None
    assert rule.search("alpha beta") is None
    assert first_match([rule], "gamma") is None


# -- metrics -------------------------------------------------------------------


def test_signal_score() -> None:
    assert signal_score(0, 0) == 1.0
    assert signal_score(0, 1) == 0.5
    assert signal_score(3, 1) == 0.8
    with pytest.raises(ValueError):
        signal_score(-1, 0)


def test_text_metrics() -> None:
    assert demographic_score("Cut services for elderly residents.") < 1.0
    assert demographic_score("Protect maternal health and child development.") == 1.0
    assert trust_score("Encourage people to report on your neighbours.") < 1.0
    assert agency_score("You must comply. There is no choice.") < 0.5
    assert agency_score("Here are three options; the choice is yours.") == 1.0


def test_ecological_score() -> None:
    assert ecological_score() == 1.0
    assert ecological_score(0.25, 0.5) == 0.5
    assert ecological_score(2.0) == 0.0


def test_seed_stock_report() -> None:
    report = compute_seed_stock("You must comply.", 0.1)
    assert report.aggregate == report.agency
    assert report.weakest[0] == "agency"
    assert report.as_dict()["aggregate"] == report.aggregate
    assert 0 < report.weighted({"agency": 1, "ecological": 1}) < 1
    with pytest.raises(ValueError):
        report.weighted({"agency": 0})


# -- simulation ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy", "finding"),
    [
        ("Proceed without recovery net.", "UNBUFFERED_RISK"),
        ("Accept unbuffered risk in the delta.", "UNBUFFERED_RISK"),
        ("This change is irreversible.", "IRREVERSIBLE_WITHOUT_MITIGATION"),
        ("Eliminate all food aid subsidies next month.", "SAFETY_NET_REMOVAL"),
        ("Roll this out nationwide on Monday.", "POPULATION_SCALE_WITHOUT_PILOT"),
    ],
)
async def test_structural_review_blocks(policy: str, finding: str) -> None:
    report = await SiliconSimulationEngine().simulate(policy)
    assert not report.passed
    assert report.findings[0].startswith(finding)
    assert report.message.startswith("Simulation Failed")


@pytest.mark.parametrize(
    "policy",
    [
        "Phase out fuel subsidies gradually with transitional support for low-income households.",
        "Pilot the scheme in two districts, then roll out nationwide after review.",
    ],
)
async def test_mitigations_pass(policy: str) -> None:
    passed, message = await SiliconSimulationEngine().run_policy_simulation(policy)
    assert passed, message


async def test_twin_maximin() -> None:
    async def twin(policy: str, seed: int) -> float:
        return 0.1 if seed == 3 else 0.9

    failing = await SiliconSimulationEngine(twin, runs=8, worst_case_floor=0.5).simulate("plan")
    assert not failing.passed
    assert failing.worst_case == pytest.approx(0.1)
    assert failing.mean == pytest.approx((0.9 * 7 + 0.1) / 8)

    passing = await SiliconSimulationEngine(twin, runs=3, worst_case_floor=0.5).simulate("plan")
    assert passing.passed and passing.runs == 3
    assert passing.as_dict()["worst_case"] == pytest.approx(0.9)


async def test_twin_outputs_are_clipped() -> None:
    async def twin(policy: str, seed: int) -> float:
        return 5.0

    report = await SiliconSimulationEngine(twin, runs=2, worst_case_floor=0.9).simulate("plan")
    assert report.worst_case == 1.0


def test_simulation_requires_runs() -> None:
    with pytest.raises(ValueError):
        SiliconSimulationEngine(runs=0)


# -- circuit breaker -----------------------------------------------------------


def test_breaker_lifecycle(clock: FakeClock) -> None:
    cb = CircuitBreaker(threshold=2, window_s=10, cooldown_s=60, clock=clock)
    assert cb.state is BreakerState.CLOSED
    cb.record_violation("a")
    clock.advance(20)  # first violation ages out of the window
    cb.record_violation("b")
    assert cb.state is BreakerState.CLOSED
    cb.record_violation("c")
    assert cb.state is BreakerState.OPEN and not cb.allow_request()
    assert cb.last_reason == "c"
    clock.advance(61)
    assert cb.state is BreakerState.HALF_OPEN and cb.allow_request()
    cb.record_violation("d")  # probation violation reopens at once
    assert cb.state is BreakerState.OPEN
    clock.advance(61)
    cb.record_success()
    assert cb.state is BreakerState.CLOSED
    cb.record_success()  # no-op when closed
    assert cb.snapshot()["state"] == "CLOSED"


def test_breaker_manual_trip_and_reset(clock: FakeClock) -> None:
    cb = CircuitBreaker(clock=clock)
    cb.trip("ICT suspension order")
    assert cb.state is BreakerState.OPEN
    assert cb.snapshot()["last_reason"] == "ICT suspension order"
    cb.reset()
    assert cb.state is BreakerState.CLOSED and cb.last_reason == ""


def test_breaker_validation() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker(threshold=0)


# -- audit -----------------------------------------------------------------------


def _decision() -> GuardrailDecision:
    return GuardrailDecision(status=Status.APPROVED, completion="ok")


def test_audit_hashes_by_default() -> None:
    sink = InMemoryAuditSink()
    rec = AuditLogger([sink]).record(
        _decision(), prompt="secret", completion="ok", jurisdiction_id="J", cultural_context="C"
    )
    assert sink.records == [rec]
    assert rec.prompt is None and rec.prompt_sha256 == sha256("secret")
    assert sha256(None) is None
    assert json.loads(rec.to_json())["status"] == "APPROVED"


def test_audit_can_include_text_and_write_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger([JsonlFileAuditSink(path)], include_text=True)
    for _ in range(2):
        logger.record(
            _decision(), prompt="p", completion=None, jurisdiction_id="J", cultural_context="C"
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["prompt"] == "p"


def test_failing_sink_does_not_break_request(caplog: pytest.LogCaptureFixture) -> None:
    def broken(_: object) -> None:
        raise RuntimeError("disk full")

    good = InMemoryAuditSink()
    with caplog.at_level(logging.ERROR):
        AuditLogger([broken, good]).record(
            _decision(), prompt="p", completion="c", jurisdiction_id="J", cultural_context="C"
        )
    assert len(good.records) == 1
    assert "audit sink" in caplog.text


def test_default_sink_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="seed_first_guardrail.audit"):
        AuditLogger().record(
            _decision(), prompt="p", completion="c", jurisdiction_id="J", cultural_context="C"
        )
    assert '"status": "APPROVED"' in caplog.text
