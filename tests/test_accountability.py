"""KPI engine, public snapshot and predictive compliance agents.

🧒 Checks that the report card adds up, that the classroom poster never shows a kid's
name, and that every lookout shouts *before* the trouble -- and stays quiet when there
is none.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from seed_first_guardrail import (
    AuditLogger,
    InMemoryAuditSink,
    PolicyConfig,
    SeedFirstGuardrailProxy,
)
from seed_first_guardrail.accountability import (
    KPI_BY_ID,
    KPI_DEFINITIONS,
    ComplianceMonitor,
    ComplianceSink,
    build_snapshot,
    compute_kpis,
    default_agents,
    load_jsonl,
    load_snapshot_schema,
    wilson,
)
from seed_first_guardrail.accountability import agents as A
from seed_first_guardrail.accountability.kpis import rag
from seed_first_guardrail.cli import main as cli

from .conftest import HARMFUL, SAFE

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def rec(minutes: float = 0, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "audit_id": kw.pop("audit_id", f"id{minutes}-{len(kw)}-{id(kw)}"),
        "timestamp": (T0 + timedelta(minutes=minutes)).isoformat(),
        "kind": "decision",
        "status": "APPROVED",
        "tier": None,
        "code": "",
        "jurisdiction_id": "J",
        "tenant": "t",
        "principal_digest": "p",
        "labels": {},
        "governance_metadata": {},
        "energy": {},
        "capability": None,
        "confirmed_tier3": False,
        "near_miss": False,
        "sink_failures": 0,
        "infrastructure_error": False,
        "completion_digest": "c",
    }
    base.update(kw)
    return base


def ev(kind: str, minutes: float = 0, **kw: Any) -> dict[str, Any]:
    return {"type": kind, "timestamp": (T0 + timedelta(minutes=minutes)).isoformat(), **kw}


def run(
    agent: A.ComplianceAgent,
    records: list[dict[str, Any]],
    events: list[dict[str, Any]] = (),  # type: ignore[assignment]
    now_min: float | None = None,
) -> list[A.Alert]:
    now = T0 + timedelta(minutes=now_min) if now_min is not None else None
    return ComplianceMonitor([agent]).run(records, list(events), now=now)


# -- definitions -------------------------------------------------------------------------------------


def test_every_kpi_has_two_voices_and_a_pair() -> None:
    assert [d.id for d in KPI_DEFINITIONS] == [f"K-{i:02d}" for i in range(1, 30)]
    for d in KPI_DEFINITIONS:
        assert d.formula and len(d.plain_language) > 20
        assert d.paired_with in KPI_BY_ID and d.paired_with != d.id
    pillars = {d.pillar for d in KPI_DEFINITIONS}
    assert {"Moderated struggle", "Diversity", "Value-flow equity"} <= pillars


def test_every_agent_has_two_voices() -> None:
    for agent in default_agents():
        assert agent.id.startswith("CA-") and agent.name and len(agent.plain_language) > 20
    assert len(default_agents()) == 13


def test_wilson_and_rag() -> None:
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(5, 100)
    assert 0.02 < lo < 0.05 < hi < 0.12
    assert rag(KPI_BY_ID["K-01"], None) == "insufficient_data"
    assert rag(KPI_BY_ID["K-01"], 0.5) == "green"
    assert rag(KPI_BY_ID["K-01"], 3) == "amber"
    assert rag(KPI_BY_ID["K-01"], 9) == "red"
    assert rag(KPI_BY_ID["K-10"], 0.99) == "green" and rag(KPI_BY_ID["K-10"], 0.5) == "red"
    assert rag(KPI_BY_ID["K-23"], 0.6) == "green" and rag(KPI_BY_ID["K-23"], 0.3) == "amber"
    assert rag(KPI_BY_ID["K-23"], 0.1) == "red" and rag(KPI_BY_ID["K-07"], 5) == "info"


# -- KPI computation ------------------------------------------------------------------------------------


@pytest.fixture
def traffic() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    for i in range(60):
        lang = "en" if i % 2 else "sw"
        status = "BLOCKED" if i % 10 == 0 else "APPROVED"
        records.append(
            rec(
                i * 60,
                audit_id=f"a{i}",
                status=status,
                code="COMMUNITY_CONSENT_MISSING" if status == "BLOCKED" else "",
                confirmed_tier3=(i == 5),
                near_miss=(i % 7 == 0),
                completion_digest=f"d{i % 30}",
                labels={"language": lang, "topic": "water", "task_class": "advice", "cohort": "c1"},
                infrastructure_error=(i == 9),
                energy={
                    "estimated_kwh": 0.01,
                    "carbon_intensity_g_kwh": 100.0,
                    "budget_used_kwh": 0.01 * i,
                    "budget_remaining_kwh": 1 - 0.01 * i,
                },
                capability={"context": "learning", "mode": "scaffold" if i % 3 else "substitute"},
                governance_metadata={
                    "community_action": i % 4 == 0,
                    "seed_stock": {"agency": 1.0 if i % 5 else 0.5},
                    **({"unscreened": ["image"]} if i == 11 else {}),
                },
            )
        )
    records.append(
        rec(10, kind="energy", audit_id="a1", energy={"estimated_kwh": 0.01, "actual_kwh": 0.03})
    )
    events = [
        ev(
            "appeal_outcome",
            100,
            audit_id="a0",
            upheld=True,
            filed_at=T0.isoformat(),
            reviewed_at=(T0 + timedelta(hours=10)).isoformat(),
            topic="hard_history",
        ),
        ev(
            "appeal_outcome",
            200,
            audit_id="a10",
            upheld=False,
            filed_at=T0.isoformat(),
            reviewed_at=(T0 + timedelta(hours=30)).isoformat(),
        ),
        ev("escaped_harm", 300, audit_id="a3"),
        ev(
            "incident_reported",
            400,
            audit_id="a5",
            occurred_at=T0.isoformat(),
            reported_at=(T0 + timedelta(days=2)).isoformat(),
        ),
        ev("consent_verified", 10, audit_id="a4"),
        ev(
            "consent_revoked",
            20,
            revoked_at=T0.isoformat(),
            honoured_at=(T0 + timedelta(hours=5)).isoformat(),
        ),
        ev("redteam_result", 30, attempts=100, evasions=3),
        ev("canary_result", 40, corpus="protected_speech", passed=28, total=28),
        ev("canary_result", 41, corpus="legitimate_challenge", passed=15, total=16),
        ev("human_override", 50),
        ev("human_override", 51),
        ev(
            "breaker_trip",
            60,
            started_at=T0.isoformat(),
            ended_at=(T0 + timedelta(hours=2)).isoformat(),
            cause="confirmed_tier3",
            human_confirmed=False,
        ),
        ev("value_flow", 70, region="R1", extracted=100, returned=40),
        ev("value_flow", 71, region="R2", extracted=0, returned=5),
        ev("capacity", 80, region="R1", local_share=0.3),
        ev("service_quality", 90, group="en", score=0.9),
        ev("service_quality", 91, group="sw", score=0.6),
    ]
    return records, events


def test_compute_kpis_covers_every_indicator(traffic: Any) -> None:
    records, events = traffic
    policy = PolicyConfig().to_policy_document()
    res = compute_kpis(records, events, policy=policy, k=5)
    assert set(res) == set(KPI_BY_ID)
    assert res["K-01"].value == pytest.approx(1 / 60 * 10_000)
    assert res["K-03"].breakdown["language:sw"]["value"] is not None
    assert res["K-04"].value == 0.5 and res["K-04"].breakdown["topic:hard_history"]["n"] == 1
    assert res["K-05"].value == 20.0
    assert res["K-06"].value == 1.0 and res["K-06"].status == "green"
    assert res["K-07"].value == pytest.approx((0.03 + 59 * 0.01) / 60 * 1000)
    assert res["K-08"].value > 0 and "projected exhaustion" in res["K-09"].note
    assert res["K-10"].value == pytest.approx(1 / 60)
    assert res["K-11"].n == 15 and res["K-12"].note == "no community rules"
    assert res["K-13"].value == 1.0 and res["K-14"].note == "audit key not supplied"
    assert res["K-15"].value == 1.0 and res["K-16"].value == 1.0
    assert res["K-17"].value == 1 and "without human confirmation" in res["K-17"].note
    assert res["K-18"].value == 0.03 and res["K-19"].value == pytest.approx(59 / 60)
    assert res["K-20"].value == pytest.approx(1 / 60 * 10_000)
    assert res["K-21"].value == pytest.approx(2 / 60)
    assert res["K-22"].value is not None and res["K-23"].value == pytest.approx(40 / 60)
    assert res["K-24"].value == pytest.approx(2 / 17)
    assert res["K-25"].value is not None and res["K-26"].value == 0.5
    assert res["K-27"].value == 0.4 and res["K-28"].value == 0.3
    assert res["K-29"].value == pytest.approx(0.6 / 0.9)


def test_compute_kpis_empty_and_windowed(traffic: Any) -> None:
    empty = compute_kpis([], [])
    assert all(r.value is None or r.id in {"K-12", "K-17"} for r in empty.values())
    records, events = traffic
    windowed = compute_kpis(records, events, start=T0 + timedelta(hours=30), k=5)
    assert windowed["K-01"].n == 30


def test_k12_and_k14_with_policy_and_key() -> None:
    sink = InMemoryAuditSink()
    g = SeedFirstGuardrailProxy(audit_logger=AuditLogger(sinks=[sink], key=b"k"))
    import asyncio

    async def go() -> None:
        async def m(_: str) -> str:
            return SAFE

        for _ in range(3):
            await g.inspect_and_execute("q", m)

    asyncio.run(go())
    records = [json.loads(r.to_json()) for r in sink.records]
    assert compute_kpis(records, audit_key="k")["K-14"].value == 1.0
    records[1]["status"] = "BLOCKED"
    assert compute_kpis(records, audit_key=b"k")["K-14"].value == pytest.approx(2 / 3)
    doc = json.loads((ROOT / "policy/examples/ubuntu.policy.json").read_text(encoding="utf-8"))
    assert compute_kpis(records, policy=doc)["K-12"].value == 1.0
    doc["tier_2_community_sovereignty"]["custom_rules"][0]["pattern"] = r"\bprotest"
    assert compute_kpis(records, policy=doc)["K-12"].value == 0.0


# -- snapshot ---------------------------------------------------------------------------------------------


def test_snapshot_is_schema_valid_suppressed_delayed_and_private(traffic: Any) -> None:
    records, events = traffic
    now = T0 + timedelta(days=8)
    snap = build_snapshot(records, events, now=now, delay_days=7, k=20, demonstration=True)
    assert not list(Draft202012Validator(load_snapshot_schema()).iter_errors(snap))
    text = json.dumps(snap)
    assert "principal_digest" not in text and "completion_digest" not in text
    assert not snap["community_breakdowns"]
    assert all(not name.startswith("language:") for k in snap["kpis"] for name in k["breakdown"])
    k04 = next(k for k in snap["kpis"] if k["id"] == "K-04")
    assert k04["value"] is None and k04["n_band"] == "suppressed"  # 2 appeals < k
    assert all(a["requires_human"] for a in snap["alerts"])

    consented = build_snapshot(records, events, now=now, k=5, publication_consent=True)
    k03 = next(k for k in consented["kpis"] if k["id"] == "K-03")
    assert "language:sw" in k03["breakdown"]

    early = build_snapshot(records, events, now=T0 + timedelta(days=1), delay_days=7)
    assert all(k["value"] is None for k in early["kpis"] if k["id"] not in {"K-12", "K-17"})
    assert early["alerts"] == []


# -- agents: each must warn before the breach, and stay quiet on clean data ----------------------------


def test_ca1_breaker_precursor() -> None:
    probing = [rec(i * 5, principal_digest="m", near_miss=True) for i in range(3)]
    probing += [
        rec(20 + i * 5, principal_digest="m", confirmed_tier3=True, audit_id=f"v{i}")
        for i in range(2)
    ]
    alerts = run(A.BreakerPrecursorAgent(), probing, now_min=40)
    assert alerts[0].code == "PRINCIPAL_TRIP_LIKELY"
    assert alerts[0].predicted_breach_at > (T0 + timedelta(minutes=40)).isoformat()
    burst = [rec(i, principal_digest=f"p{i % 4}", confirmed_tier3=True) for i in range(30)]
    codes = {a.code for a in run(A.BreakerPrecursorAgent(), burst, now_min=31)}
    assert "GLOBAL_TRIP_LIKELY" in codes
    suspended = [rec(i, principal_digest="m", confirmed_tier3=True) for i in range(5)]
    assert run(A.BreakerPrecursorAgent(), suspended, now_min=5) == []
    assert run(A.BreakerPrecursorAgent(), [rec(0)], now_min=1) == []


def test_ca2_budget_forecast_and_under_reporting() -> None:
    recs = [
        rec(
            d * 1440,
            energy={
                "budget_used_kwh": d * 1.0,
                "budget_remaining_kwh": 10 - d * 1.0,
                "carbon_intensity_g_kwh": 100 + d * 10,
            },
        )
        for d in range(8)
    ]
    recs += [
        rec(8 * 1440 + i, audit_id=f"e{i}", tenant="heavy", energy={"carbon_intensity_g_kwh": 300})
        for i in range(40)
    ]
    recs += [
        rec(
            8 * 1440 + i,
            kind="energy",
            audit_id=f"e{i}",
            energy={"estimated_kwh": 1, "actual_kwh": 3},
        )
        for i in range(40)
    ]
    alerts = {a.code: a for a in run(A.BudgetForecastAgent(), recs)}
    assert alerts["BUDGET_EXHAUSTION_FORECAST"].predicted_breach_at > recs[-1]["timestamp"]
    assert "ENERGY_UNDER_REPORTING" in alerts and "CARBON_INTENSITY_RISING" in alerts
    assert run(A.BudgetForecastAgent(), [rec(0)]) == []


def near_miss_days(rate_for_day: Any, days: int = 20) -> list[dict[str, Any]]:
    """100 decisions a day; ``rate_for_day(d)`` percent of them are near-misses."""
    return [
        rec(d * 1440 + i, near_miss=i < rate_for_day(d)) for d in range(days) for i in range(100)
    ]


def test_ca3_drift_sentinel() -> None:
    drifting = near_miss_days(lambda d: 1 if d < 7 else 1 + 0.6 * (d - 7))  # 1% -> ~8.8%
    alerts = run(A.DriftSentinelAgent(), drifting)
    assert alerts and alerts[0].code == "NEAR_MISS_DRIFT"
    assert (
        alerts[0].predicted_breach_at
        and alerts[0].predicted_breach_at > drifting[-1]["timestamp"][:10]
    )
    assert run(A.DriftSentinelAgent(), near_miss_days(lambda d: 2)) == []  # flat: quiet
    past = near_miss_days(lambda d: 1 if d < 7 else 30)
    assert run(A.DriftSentinelAgent(), past) == []  # already past amber: not a precursor
    assert run(A.DriftSentinelAgent(), [rec(0)]) == []


def test_ca4_over_blocking() -> None:
    recs = [rec(i, labels={"language": "sw"}) for i in range(30)]
    recs += [
        rec(3 * 1440 + i, labels={"language": "sw"}, status="BLOCKED", code="X") for i in range(30)
    ]
    events = [ev("canary_result", 1, corpus="protected_speech", passed=27, total=28)]
    events += [
        ev("appeal_outcome", i, upheld=i < 10, filed_at=T0.isoformat(), reviewed_at=T0.isoformat())
        for i in range(20)
    ]
    codes = {a.code for a in run(A.OverBlockingAgent(), recs, events, now_min=3 * 1440 + 60)}
    assert codes == {"CANARY_FAILURE", "REFUSAL_SPIKE", "APPEALS_OFTEN_UPHELD"}


def test_ca5_policy_governance_review() -> None:
    old = json.loads((ROOT / "policy/examples/ubuntu.policy.json").read_text(encoding="utf-8"))
    new = json.loads(json.dumps(old))
    new["governance"]["fail_closed"] = False
    new["circuit_breaker"]["cooldown_seconds"] = 900
    new["metadata"]["issuer"] = "Someone else"
    new["tier_2_community_sovereignty"]["custom_rules"].append(
        {
            "id": "RISKY",
            "pattern": r"(a+)+b",
            "reason": "r",
            "scope": "DATA_USE",
            "legal_basis": "basis",
            "adopting_body_ref": "ref 1",
        }
    )
    codes = [a.code for a in A.PolicyGovernanceAgent().review(old, new)]
    assert "POLICY_RELAXATION" in codes and "ISSUER_CHANGED" in codes and "RISKY_PATTERN" in codes
    censor = json.loads(json.dumps(old))
    censor["tier_2_community_sovereignty"]["custom_rules"][0]["pattern"] = r"\bprotest"
    alerts = A.PolicyGovernanceAgent().review(old, censor)
    assert alerts[0].code == "POLICY_INVALID" and alerts[0].severity == "critical"
    assert "hide the news" in alerts[0].plain_language
    assert A.PolicyGovernanceAgent().review(old, old) == []
    timeouts = [rec(0, governance_metadata={"rule_timeouts": ["SLOW"]})]
    events = [ev("policy_change", 0, old=old, new=censor)]
    codes = {a.code for a in run(A.PolicyGovernanceAgent(), timeouts, events)}
    assert codes == {"POLICY_INVALID", "RULE_TIMEOUT"}


def test_ca6_integrity_auditor() -> None:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink], key=b"k")
    from seed_first_guardrail import GuardrailDecision, Status

    for _ in range(3):
        logger.record(
            GuardrailDecision(status=Status.APPROVED),
            prompt="p",
            completion="c",
            jurisdiction_id="J",
            cultural_context="C",
        )
    records = [json.loads(r.to_json()) for r in sink.records]
    assert run(A.IntegrityAuditorAgent(b"k"), records) == []
    records[0]["code"] = "TAMPERED"
    records[2]["sink_failures"] = 2
    records[2]["timestamp"] = "2020-01-01T00:00:00+00:00"
    codes = {a.code for a in run(A.IntegrityAuditorAgent(b"k"), records)}
    assert codes == {"AUDIT_CHAIN_BROKEN", "AUDIT_SINK_FAILURES", "AUDIT_CLOCK_SKEW"}


def test_ca7_consent_watch() -> None:
    acts = [
        rec(i, audit_id=f"c{i}", governance_metadata={"community_action": True}) for i in range(20)
    ]
    events = [ev("consent_verified", i, audit_id=f"c{i}") for i in range(10)]
    events += [ev("consent_revoked", 0, revoked_at=T0.isoformat())]
    alerts = run(A.ConsentWatchAgent(), acts, events, now_min=60 * 60)
    assert {a.code for a in alerts} == {"CONSENT_UNVERIFIED", "REVOCATION_DUE_SOON"}
    overdue = run(A.ConsentWatchAgent(), acts[:1], events[-1:], now_min=60 * 80)
    assert overdue[0].code == "REVOCATION_OVERDUE" and overdue[0].severity == "critical"


def test_ca8_macro_policy_detector() -> None:
    skipped = [
        rec(i, governance_metadata={"policy_like": True, "macro_policy": False}) for i in range(3)
    ]
    assert run(A.MacroPolicyDetectorAgent(), skipped)[0].code == "SIMULATION_SKIPPED"
    assert run(A.MacroPolicyDetectorAgent(), skipped[:2]) == []


def test_ca9_incident_clerk() -> None:
    v = rec(
        0,
        audit_id="v1",
        confirmed_tier3=True,
        status="BLOCKED",
        code="POPULATION_HARM",
        tier="TIER_3_INVIOLABLE_HUMAN_FLOOR",
    )
    assert run(A.IncidentClerkAgent(), [v], now_min=60) == []
    due = run(A.IncidentClerkAgent(), [v], now_min=13 * 1440)
    assert due[0].code == "INCIDENT_DUE_SOON" and "fields_to_complete" in due[0].restricted_detail
    assert run(A.IncidentClerkAgent(), [v], now_min=16 * 1440)[0].code == "INCIDENT_OVERDUE"
    reported = [ev("incident_reported", 10, audit_id="v1")]
    assert run(A.IncidentClerkAgent(), [v], reported, now_min=16 * 1440) == []


def test_ca10_capability_atrophy() -> None:
    def cap(d: int, i: int) -> dict[str, Any]:
        mode = "scaffold" if i < 90 - 3 * d else "substitute"
        return {"capability": {"context": "learning", "mode": mode}, "labels": {"cohort": "A"}}

    declining = [rec(d * 1440 + i, **cap(d, i)) for d in range(12) for i in range(100)]
    alert = run(A.CapabilityAtrophyAgent(), declining)[0]
    assert (
        alert.code == "SCAFFOLDING_DECLINING"
        and alert.predicted_breach_at > declining[-1]["timestamp"][:10]
    )
    stable = [
        rec(
            d * 1440 + i,
            capability={"context": "learning", "mode": "scaffold" if i < 70 else "substitute"},
        )
        for d in range(12)
        for i in range(100)
    ]
    assert run(A.CapabilityAtrophyAgent(), stable) == []


def test_ca11_diversity_sentinel() -> None:
    recs = [rec(i, labels={"language": "en"}) for i in range(40)]
    recs += [
        rec(i, labels={"language": "sw"}, status="BLOCKED", code="X" if i < 20 else "")
        for i in range(40)
    ]
    recs += [rec(2000 + i, labels={"language": "en"}) for i in range(40)]
    events = [ev("policy_change", 1500, old={}, new={})]
    codes = {a.code for a in run(A.DiversitySentinelAgent(), recs, events, now_min=2100)}
    assert codes == {"REFUSAL_DISPARITY", "SILENT_EXCLUSION"}


def test_ca12_atrocity_precursor() -> None:
    labels = {"target_group": "migrants"}
    early = [
        rec(i, code="", labels=labels, governance_metadata={"lexical_hits": ["RELATIONAL_SCORING"]})
        for i in range(3)
    ]
    late = [
        rec(100 + i, status="BLOCKED", code="HUMAN_WORTH_RANKING", labels=labels) for i in range(3)
    ]
    alert = run(A.AtrocityPrecursorAgent(), early + late)[0]
    assert alert.code == "ATROCITY_PRECURSOR_ESCALATION" and "dehumanisation" in alert.title
    assert "migrants" not in alert.public_summary  # group only in restricted detail
    assert run(A.AtrocityPrecursorAgent(), early) == []  # stage 3, not escalating


def test_ca13_extraction_watch() -> None:
    events = [
        ev("value_flow", d * 1440, region="R", extracted=100, returned=90 - 10 * d)
        for d in range(5)
    ]
    events += [ev("value_flow", 0, region="Q", extracted=100, returned=10)]
    events += [ev("capacity", 0, region="Q", local_share=0.05)]
    alerts = {(a.code, a.severity) for a in run(A.ExtractionWatchAgent(), [rec(0)], events)}
    assert ("VALUE_RETURN_GAP", "warning") in alerts and ("VALUE_RETURN_GAP", "critical") in alerts
    assert ("LOW_LOCAL_CAPACITY", "info") in alerts


def test_alert_public_view_hides_evidence() -> None:
    alert = A.Alert(
        agent="CA-1",
        code="X",
        severity="info",
        title="t",
        public_summary="s",
        plain_language="plain words here",
        recommended_action="a",
        restricted_detail="secret",
        evidence=["id"],
    )
    public = alert.to_public()
    assert "restricted_detail" not in public and "evidence" not in public


def test_statistics_helpers() -> None:
    assert A.poisson_tail(0, 1) == 0.0 and A.poisson_tail(3, 0) == 1.0
    assert A.poisson_tail(2, 3) == pytest.approx(
        1 - 5 * 2.718281828459045**-2
    )  # 1 - e^-2 (1 + 2 + 2)
    assert A.linear_trend([(0, 1), (1, 2)]) is None
    assert A.linear_trend([(1, 1), (1, 2), (1, 3)]) is None
    assert A.crossing_time([(0, 1), (1, 2), (2, 3)], 5, rising=False) is None


async def test_compliance_sink_live_and_deduplicated() -> None:
    seen: list[A.Alert] = []
    sink = ComplianceSink(
        ComplianceMonitor([A.IncidentClerkAgent(deadline=timedelta(0))]),
        every=2,
        on_alert=seen.append,
    )
    g = SeedFirstGuardrailProxy(PolicyConfig(), audit_logger=AuditLogger(sinks=[sink], key=b"k"))

    async def bad(_: str) -> str:
        return HARMFUL

    for _ in range(4):
        await g.inspect_and_execute("q", bad, principal="x")
    sink.flush()
    assert seen and len({(a.code, a.title) for a in seen}) == len(seen)


# -- CLI --------------------------------------------------------------------------------------------------


def test_cli_accountability_commands(
    tmp_path: Path, traffic: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    records, events = traffic
    audit, evs = tmp_path / "audit.jsonl", tmp_path / "events.jsonl"
    audit.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    evs.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    assert len(load_jsonl(audit)) == len(records)

    out = tmp_path / "snap.json"
    now = (T0 + timedelta(days=9)).isoformat()
    assert (
        cli(
            [
                "kpi-export",
                "--audit",
                str(audit),
                "--events",
                str(evs),
                "--out",
                str(out),
                "--now",
                now,
                "--k",
                "5",
                "--demonstration",
                "--policy",
                str(ROOT / "policy/examples/ubuntu.policy.json"),
            ]
        )
        == 0
    )
    assert json.loads(out.read_text(encoding="utf-8"))["demonstration"] is True
    assert cli(["kpi-export", "--audit", str(audit), "--now", now]) == 0
    assert '"schema_version"' in capsys.readouterr().out

    alerts = tmp_path / "alerts.jsonl"
    code = cli(
        ["monitor", "--audit", str(audit), "--events", str(evs), "--out", str(alerts), "--now", now]
    )
    assert code in (0, 2) and alerts.exists()

    ok = ROOT / "policy/examples/ubuntu.policy.json"
    assert cli(["policy-diff", str(ok), str(ok)]) == 0
    bad = tmp_path / "bad.json"
    doc = json.loads(ok.read_text(encoding="utf-8"))
    doc["tier_2_community_sovereignty"]["custom_rules"][0]["pattern"] = r"\bprotest"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert cli(["policy-diff", str(ok), str(bad)]) == 2


# -- end to end ---------------------------------------------------------------------------------------------


async def test_demo_every_planted_scenario_fires_before_breach(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "accountability_demo", ROOT / "examples/accountability_demo.py"
    )
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    result = await demo.run(tmp_path)
    fired = {(a.agent, a.code) for a in result["alerts"]}
    assert set(demo.EXPECTED.items()) <= fired
    end = demo.END.date().isoformat()
    for a in result["alerts"]:
        if a.predicted_breach_at and not a.code.endswith("OVERDUE"):
            assert a.predicted_breach_at[:10] >= end, a
    snap = result["snapshot"]
    assert snap["demonstration"] and not list(
        Draft202012Validator(load_snapshot_schema()).iter_errors(snap)
    )


def test_committed_dashboard_snapshot_is_valid() -> None:
    path = ROOT / "docs/dashboard/demo_snapshot.json"
    snap = json.loads(path.read_text(encoding="utf-8"))
    assert snap["demonstration"] is True
    assert not list(Draft202012Validator(load_snapshot_schema()).iter_errors(snap))


def test_dashboard_render_embeds_snapshot_safely(tmp_path: Path) -> None:
    from seed_first_guardrail.dashboard import render

    snap = json.loads((ROOT / "docs/dashboard/demo_snapshot.json").read_text(encoding="utf-8"))
    snap["disclaimer"] = "</script><script>alert(1)</script>"
    page = render(snap)
    assert page.lstrip().startswith("<meta")
    assert page.count("</script>") == 2  # only the page's own two script blocks
    assert "Kid view" in page and "Struggle kept" in page and "Harm stopped" in page
    start = page.index('id="snapshot">') + len('id="snapshot">')
    embedded = json.loads(page[start : page.index("</script>", start)])
    assert embedded["disclaimer"] == snap["disclaimer"]

    out = tmp_path / "index.html"
    assert (
        cli(
            [
                "dashboard",
                "--snapshot",
                str(ROOT / "docs/dashboard/demo_snapshot.json"),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert out.read_text(encoding="utf-8") == (ROOT / "docs/dashboard/index.html").read_text(
        encoding="utf-8"
    ), "docs/dashboard/index.html is stale: re-run the dashboard command"


def _decision(model: str, i: int, **kw: Any) -> dict[str, Any]:
    rec = {
        "kind": "decision",
        "audit_id": f"{model}-{i}",
        "timestamp": "2026-09-01T00:00:00+00:00",
        "status": "APPROVED",
        "labels": {"model": model, "language": "en"},
        "channels_screened": ["text"],
    }
    rec.update(kw)
    return rec


def test_model_scorecards_grade_caps_and_minimums() -> None:
    from seed_first_guardrail.accountability.scorecards import grade_for, model_scorecards

    assert [grade_for(s) for s in (0.95, 0.8, 0.65, 0.5, 0.1)] == list("ABCDF")
    records = [_decision("good-model", i) for i in range(200)]
    records += [_decision("harmful-model", i) for i in range(200)]
    for i in range(0, 200, 20):  # 100 per 10k confirmed violations -> red K-01
        records[200 + i].update(status="BLOCKED", confirmed_tier3=True)
    records += [_decision("tiny-model", i) for i in range(5)]
    events = [
        {
            "type": "redteam_result",
            "timestamp": "2026-09-02T00:00:00+00:00",
            "attempts": 100,
            "evasions": 1,
            "model": "good-model",
        },
    ]
    events += [  # people still review and change 10% of good-model's answers (K-21 band)
        {"type": "human_override", "timestamp": "2026-09-02T00:00:00+00:00",
         "audit_id": f"good-model-{i}"}
        for i in range(0, 200, 10)
    ]  # fmt: skip
    cards = {c["model"]: c for c in model_scorecards(records, events, k=20)}
    assert cards["good-model"]["kpis"]["K-21"]["status"] == "green"
    assert cards["harmful-model"]["kpis"]["K-21"]["status"] == "red"  # nobody ever overrides
    assert cards["good-model"]["grade"] in ("A", "B")
    assert cards["good-model"]["kpis"]["K-18"]["status"] == "green"  # model-tagged event
    assert cards["harmful-model"]["kpis"]["K-18"]["status"] == "insufficient_data"
    assert cards["harmful-model"]["grade"] >= "C"
    assert "confirmed serious harm" in cards["harmful-model"]["caps"]
    assert cards["tiny-model"]["grade"] is None and cards["tiny-model"]["score"] is None
    assert list(cards)[-1] == "tiny-model"  # unrated models sort last


def test_committed_snapshot_names_and_rates_models() -> None:
    snap = json.loads((ROOT / "docs/dashboard/demo_snapshot.json").read_text(encoding="utf-8"))
    names = [m["model"] for m in snap["models"]]
    assert names and all(n.startswith("demo-model-") for n in names)  # placeholders only
    assert [m["grade"] for m in snap["models"]] == sorted(m["grade"] for m in snap["models"])
    assert snap["rating_method"]["groups"]["harm"][0] == "K-01"
