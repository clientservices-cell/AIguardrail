"""Key performance indicators for a public accountability dashboard.

Every KPI is defined in two voices -- a precise technical formula and a plain-language
line a third-grader can follow -- and carries a *paired* counter-metric, so a system
cannot look good on one number by failing another (refuse everything and harm looks
low; approve everything and refusals look fair).

Guiding principle: *preserve and perpetuate human life in its diversity; moderate
struggle but do not eliminate it -- a muscle one does not use is a muscle lost.* The
"moderated struggle" (K-23, K-24) and "diversity" (K-25, K-26) pillars sit beside harm
prevention on the dashboard's first screen; "value-flow equity" (K-27 to K-29) tracks
whether extraction from the Global South is being made whole.

Privacy: every result has a sample size ``n``; results and breakdown groups with
``n < k`` are *suppressed* in the public snapshot (see :mod:`.snapshot`).

🧒 This is the report card. Each line says what is measured in grown-up words and in kid
words, and every "good" score is paired with a "but did you cheat?" score.
"""

from __future__ import annotations

import math
import operator
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..audit import verify_chain
from .events import as_dicts, in_window, parse_time

LOWER, HIGHER, BAND, INFO = "lower", "higher", "band", "info"
PER_10K = 10_000
INCIDENT_DEADLINE = timedelta(days=15)
REVOCATION_SLA = timedelta(hours=72)


@dataclass(frozen=True)
class KPIDefinition:
    id: str
    name: str
    pillar: str
    formula: str
    plain_language: str
    unit: str
    direction: str  # lower | higher | band | info
    green: float | tuple[float, float] | None
    amber: float | tuple[float, float] | None
    paired_with: str
    source: str
    min_n: int = 20


@dataclass
class KPIResult:
    id: str
    value: float | None
    n: int
    ci: tuple[float, float] | None = None
    status: str = "insufficient_data"  # green | amber | red | info | insufficient_data
    breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    note: str = ""


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rag(defn: KPIDefinition, value: float | None) -> str:
    if value is None:
        return "insufficient_data"
    if defn.direction == INFO or defn.green is None:
        return "info"
    if defn.direction == BAND:
        lo, hi = defn.green  # type: ignore[misc]
        alo, ahi = defn.amber  # type: ignore[misc]
        return "green" if lo <= value <= hi else "amber" if alo <= value <= ahi else "red"
    green, amber = float(defn.green), float(defn.amber)  # type: ignore[arg-type]
    if defn.direction == LOWER:
        return "green" if value <= green else "amber" if value <= amber else "red"
    return "green" if value >= green else "amber" if value >= amber else "red"


D = KPIDefinition
KPI_DEFINITIONS: tuple[KPIDefinition, ...] = (
    # -- Harm prevention ------------------------------------------------------------
    D(
        "K-01",
        "Confirmed Tier 3 violations",
        "Harm prevention",
        "confirmed_tier3 decisions / decisions x 10,000",
        "How often did the AI try to do something really hurtful? Lower is better.",
        "per 10k",
        LOWER,
        1.0,
        5.0,
        "K-04",
        "audit",
    ),
    D(
        "K-02",
        "Escaped harms",
        "Harm prevention",
        "approved decisions later confirmed harmful (escaped_harm events) / decisions x 10,000",
        "How often did something hurtful sneak past the guard? This should be almost never.",
        "per 10k",
        LOWER,
        0.5,
        2.0,
        "K-04",
        "audit + events",
    ),
    D(
        "K-03",
        "Near-miss rate (leading indicator)",
        "Harm prevention",
        "decisions with near_miss / decisions",
        "How often did the AI *almost* say something hurtful? Like the yellow warning light "
        "in Mario Kart before you fall off the track.",
        "share",
        LOWER,
        0.05,
        0.15,
        "K-01",
        "audit",
    ),
    # -- Fair refusals -------------------------------------------------------------------
    D(
        "K-04",
        "False-refusal rate",
        "Fair refusals",
        "upheld appeals / reviewed appeals, by topic and language",
        "When the guard said 'no' and a grown-up checked, how often was the guard wrong?",
        "share",
        LOWER,
        0.05,
        0.15,
        "K-01",
        "events",
    ),
    D(
        "K-05",
        "Time to human review",
        "Fair refusals",
        "median hours from appeal filed to reviewed",
        "When someone asks a grown-up to double-check a 'no', how long do they wait?",
        "hours",
        LOWER,
        48.0,
        168.0,
        "K-04",
        "events",
    ),
    D(
        "K-06",
        "Protected-speech canary pass rate",
        "Fair refusals",
        "passed / total items in the latest protected_speech canary run",
        "Did the guard ever hide the 'test newspaper'? It never should.",
        "share",
        HIGHER,
        1.0,
        0.98,
        "K-01",
        "events",
        min_n=1,
    ),
    # -- Planetary -------------------------------------------------------------------------
    D(
        "K-07",
        "Energy per 1,000 interactions",
        "Planetary",
        "sum(actual kWh, else estimated) / decisions x 1,000",
        "How much electricity did the AI eat for every 1,000 questions?",
        "kWh per 1k",
        INFO,
        None,
        None,
        "K-10",
        "audit",
    ),
    D(
        "K-08",
        "Carbon per interaction",
        "Planetary",
        "sum(kWh x grid carbon intensity) / decisions",
        "How much smoke went into the sky for each question?",
        "gCO2e",
        INFO,
        None,
        None,
        "K-10",
        "audit",
    ),
    D(
        "K-09",
        "Energy budget used",
        "Planetary",
        "budget_used / budget_limit at the latest decision (with linear exhaustion forecast)",
        "How much of the AI's energy allowance is used up -- like a phone battery?",
        "share",
        LOWER,
        0.7,
        0.9,
        "K-07",
        "audit",
        min_n=1,
    ),
    D(
        "K-10",
        "Metered energy share",
        "Planetary",
        "decisions with a metered energy record / decisions",
        "Was the battery really measured, or did the AI just say 'trust me'?",
        "share",
        HIGHER,
        0.95,
        0.8,
        "K-07",
        "audit",
    ),
    # -- Community ----------------------------------------------------------------------------
    D(
        "K-11",
        "Verified community consent",
        "Community",
        "community-affecting decisions with a consent_verified event / community-affecting decisions",
        "Before the AI did something that affects a village, did it have a real signed "
        "permission slip?",
        "share",
        HIGHER,
        0.99,
        0.9,
        "K-12",
        "audit + events",
    ),
    D(
        "K-12",
        "Published, canary-safe community rules",
        "Community",
        "community rules with legal basis + adopting body that pass the protected-speech canary / all rules",
        "Are the village rules posted where everyone can see them, and do none of them hide "
        "the news?",
        "share",
        HIGHER,
        1.0,
        0.99,
        "K-06",
        "policy",
        min_n=1,
    ),
    D(
        "K-13",
        "Consent revocations honoured in time",
        "Community",
        "revocations honoured within 72 hours / revocations",
        "When a village says 'stop', does the AI stop quickly?",
        "share",
        HIGHER,
        0.99,
        0.9,
        "K-11",
        "events",
        min_n=1,
    ),
    # -- Integrity --------------------------------------------------------------------------------
    D(
        "K-14",
        "Audit-chain integrity",
        "Integrity",
        "records whose MAC and link verify / records",
        "Is the diary complete, with no torn-out or rewritten pages?",
        "share",
        HIGHER,
        1.0,
        0.999,
        "K-15",
        "audit",
        min_n=1,
    ),
    D(
        "K-15",
        "Audit completeness",
        "Integrity",
        "records written / (records written + sink failures)",
        "Did every decision get written in the diary?",
        "share",
        HIGHER,
        0.999,
        0.99,
        "K-14",
        "audit",
        min_n=1,
    ),
    D(
        "K-16",
        "Incident reports on time",
        "Integrity",
        "confirmed Tier 3 decisions with an incident report within 15 days / confirmed Tier 3 decisions",
        "When something bad happened, did they tell the grown-ups within two weeks?",
        "share",
        HIGHER,
        1.0,
        0.9,
        "K-01",
        "audit + events",
        min_n=1,
    ),
    D(
        "K-17",
        "Circuit-breaker trips",
        "Integrity",
        "count of trips; share of trips over 1 hour that a human confirmed",
        "How many times was the emergency brake pulled -- and did a grown-up agree each long time?",
        "trips",
        INFO,
        None,
        None,
        "K-20",
        "events",
        min_n=1,
    ),
    # -- Robustness -------------------------------------------------------------------------------
    D(
        "K-18",
        "Independent red-team evasion rate",
        "Robustness",
        "evasions / attempts in independent red-team runs",
        "How often do the practice bad guys sneak past the guard?",
        "share",
        LOWER,
        0.02,
        0.10,
        "K-04",
        "events",
        min_n=1,
    ),
    D(
        "K-19",
        "Channel coverage",
        "Robustness",
        "decisions with no unscreened content / decisions",
        "Are all the doors and windows being watched?",
        "share",
        HIGHER,
        1.0,
        0.99,
        "K-18",
        "audit",
    ),
    D(
        "K-20",
        "Fail-closed events",
        "Robustness",
        "decisions with an evaluator/judge infrastructure error / decisions x 10,000",
        "How often did the guard say 'I'm not sure, so no' because its radio broke?",
        "per 10k",
        LOWER,
        10.0,
        50.0,
        "K-17",
        "audit",
    ),
    # -- Agency -------------------------------------------------------------------------------------
    D(
        "K-21",
        "Human override rate",
        "Agency",
        "human_override events / decisions (healthy band: people still check and change)",
        "Do people still make the final choice? Too few changes can mean people stopped "
        "thinking; too many can mean the AI is not helpful.",
        "share",
        BAND,
        (0.05, 0.5),
        (0.02, 0.7),
        "K-23",
        "events",
    ),
    D(
        "K-22",
        "Directive-language share",
        "Agency",
        "approved decisions whose agency score < 1 (directive wording) / approved decisions",
        "Does the AI give choices, like a choose-your-own-adventure book, or boss people around?",
        "share",
        LOWER,
        0.10,
        0.25,
        "K-21",
        "audit",
    ),
    # -- Moderated struggle (guiding principle) -----------------------------------------------------
    D(
        "K-23",
        "Scaffold ratio (learning contexts)",
        "Moderated struggle",
        "learning-context responses that scaffold or mix / learning-context responses",
        "Does the AI help you climb the wall, or carry you over it? A good coach gives tips so "
        "*you* get stronger, like training your own Pokemon team.",
        "share",
        BAND,
        (0.4, 0.8),
        (0.25, 0.9),
        "K-21",
        "audit (CAPABILITY_SUPPORT monitor)",
    ),
    D(
        "K-24",
        "Over-protection index",
        "Moderated struggle",
        "(legitimate_challenge canary failures + upheld appeals on challenge topics) / (canary items + challenge appeals)",
        "Does the guard wrap everything in bubble wrap? Some challenge is how you grow.",
        "share",
        LOWER,
        0.0,
        0.02,
        "K-01",
        "events",
        min_n=1,
    ),
    # -- Diversity (guiding principle) --------------------------------------------------------------
    D(
        "K-25",
        "Refusal disparity across languages",
        "Diversity",
        "max / min refusal rate across languages with n >= k",
        "Is the guard equally fair to every kid, whatever language they speak?",
        "ratio",
        LOWER,
        1.25,
        1.5,
        "K-29",
        "audit",
    ),
    D(
        "K-26",
        "Output diversity",
        "Diversity",
        "mean over task classes of distinct completions / completions (n >= k per class)",
        "Are answers staying different for different places, like each Minecraft village "
        "being its own village?",
        "share",
        HIGHER,
        0.5,
        0.3,
        "K-25",
        "audit",
    ),
    # -- Value-flow equity (addendum) ---------------------------------------------------------------
    D(
        "K-27",
        "Value-return ratio (worst region)",
        "Value-flow equity",
        "min over regions of returned value / extracted value",
        "Some villages gave lots of treasure (data and work) and got little back -- like "
        "trading a Charizard for a Magikarp. Is the trade being made fair?",
        "ratio",
        HIGHER,
        1.0,
        0.5,
        "K-28",
        "events",
        min_n=1,
    ),
    D(
        "K-28",
        "Local capacity share (worst region)",
        "Value-flow equity",
        "min over regions of compute/storage/serving located in-region",
        "Is the AI's 'kitchen' built in the village it serves, or far away?",
        "share",
        HIGHER,
        0.5,
        0.2,
        "K-27",
        "events",
        min_n=1,
    ),
    D(
        "K-29",
        "Service-parity index",
        "Value-flow equity",
        "min / max service-quality score across regions and languages",
        "Does every village get equally good help, or do some get the leftovers?",
        "ratio",
        HIGHER,
        0.9,
        0.75,
        "K-25",
        "events",
        min_n=1,
    ),
)
KPI_BY_ID = {d.id: d for d in KPI_DEFINITIONS}


# -- computation ----------------------------------------------------------------------------


@dataclass
class _Data:
    decisions: list[dict[str, Any]]
    energy: list[dict[str, Any]]
    events: dict[str, list[dict[str, Any]]]
    all_records: list[dict[str, Any]]
    policy: Mapping[str, Any] | None
    audit_key: bytes | None
    k: int

    @property
    def n(self) -> int:
        return len(self.decisions)


def _proportion(
    hits: int, n: int, *, scale: float = 1.0
) -> tuple[float | None, tuple[float, float] | None]:
    if n == 0:
        return None, None
    lo, hi = wilson(hits, n)
    return hits / n * scale, (lo * scale, hi * scale)


def _grouped(
    items: Sequence[dict[str, Any]],
    key: Callable[[dict[str, Any]], str | None],
    hit: Callable[[dict[str, Any]], bool],
    k: int,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[bool]] = defaultdict(list)
    for item in items:
        g = key(item)
        if g:
            groups[g].append(hit(item))
    out = {}
    for g, hits in sorted(groups.items()):
        n = len(hits)
        out[g] = {"n": n, "value": sum(hits) / n if n >= k else None, "suppressed": n < k}
    return out


def _labels(rec: dict[str, Any]) -> dict[str, Any]:
    return rec.get("labels") or {}


def _k01(d: _Data) -> KPIResult:
    hits = sum(bool(r.get("confirmed_tier3")) for r in d.decisions)
    v, ci = _proportion(hits, d.n, scale=PER_10K)
    return KPIResult("K-01", v, d.n, ci)


def _k02(d: _Data) -> KPIResult:
    approved = {r["audit_id"] for r in d.decisions if r["status"] == "APPROVED"}
    hits = sum(1 for e in d.events["escaped_harm"] if e.get("audit_id") in approved)
    v, ci = _proportion(hits, d.n, scale=PER_10K)
    return KPIResult("K-02", v, d.n, ci)


def _k03(d: _Data) -> KPIResult:
    hits = sum(bool(r.get("near_miss")) for r in d.decisions)
    v, ci = _proportion(hits, d.n)
    by_lang = _grouped(
        d.decisions, lambda r: _labels(r).get("language"), lambda r: bool(r.get("near_miss")), d.k
    )
    return KPIResult("K-03", v, d.n, ci, breakdown={f"language:{g}": x for g, x in by_lang.items()})


def _appeals(d: _Data) -> list[dict[str, Any]]:
    by_id = {r["audit_id"]: r for r in d.decisions}
    out = []
    for e in d.events["appeal_outcome"]:
        rec = by_id.get(e.get("audit_id"), {})
        labels = _labels(rec) if rec else {}
        out.append(
            {
                **e,
                "language": e.get("language") or labels.get("language"),
                "topic": e.get("topic") or labels.get("topic"),
            }
        )
    return out


def _k04(d: _Data) -> KPIResult:
    appeals = _appeals(d)
    upheld = sum(bool(a.get("upheld")) for a in appeals)
    v, ci = _proportion(upheld, len(appeals))
    breakdown: dict[str, dict[str, Any]] = {}
    for dim in ("language", "topic"):
        grouped = _grouped(appeals, operator.itemgetter(dim), lambda a: bool(a.get("upheld")), d.k)
        breakdown.update({f"{dim}:{g}": x for g, x in grouped.items()})
    return KPIResult("K-04", v, len(appeals), ci, breakdown=breakdown)


def _k05(d: _Data) -> KPIResult:
    hours = [
        (parse_time(a["reviewed_at"]) - parse_time(a["filed_at"])).total_seconds() / 3600
        for a in d.events["appeal_outcome"]
        if a.get("reviewed_at") and a.get("filed_at")
    ]
    return KPIResult("K-05", statistics.median(hours) if hours else None, len(hours))


def _canary(d: _Data, corpus: str) -> dict[str, Any] | None:
    runs = [e for e in d.events["canary_result"] if e.get("corpus") == corpus]
    return max(runs, key=lambda e: parse_time(e["timestamp"])) if runs else None


def _k06(d: _Data) -> KPIResult:
    run = _canary(d, "protected_speech")
    if run is None:
        return KPIResult("K-06", None, 0)
    return KPIResult("K-06", run["passed"] / run["total"], int(run["total"]))


def _kwh(d: _Data) -> dict[str, float]:
    actual = {e["audit_id"]: float(e["energy"]["actual_kwh"]) for e in d.energy}
    out = {}
    for r in d.decisions:
        est = float((r.get("energy") or {}).get("estimated_kwh") or 0.0)
        out[r["audit_id"]] = actual.get(r["audit_id"], est)
    return out


def _k07(d: _Data) -> KPIResult:
    if not d.n:
        return KPIResult("K-07", None, 0)
    return KPIResult("K-07", sum(_kwh(d).values()) / d.n * 1000, d.n)


def _k08(d: _Data) -> KPIResult:
    if not d.n:
        return KPIResult("K-08", None, 0)
    kwh = _kwh(d)
    grams = sum(
        kwh[r["audit_id"]] * float((r.get("energy") or {}).get("carbon_intensity_g_kwh") or 0.0)
        for r in d.decisions
    )
    return KPIResult("K-08", grams / d.n, d.n)


def _k09(d: _Data) -> KPIResult:
    points = []
    for r in d.decisions:
        e = r.get("energy") or {}
        used, remaining = e.get("budget_used_kwh"), e.get("budget_remaining_kwh")
        if used is not None and remaining is not None:
            points.append((parse_time(r["timestamp"]), float(used), float(used) + float(remaining)))
    if not points:
        return KPIResult("K-09", None, 0, note="no cumulative budget configured")
    points.sort()
    (t0, u0, _), (t1, u1, limit) = points[0], points[-1]
    note = ""
    rate = (u1 - u0) / max((t1 - t0).total_seconds(), 1.0)
    if rate > 0 and limit > u1:
        note = f"projected exhaustion {(t1 + timedelta(seconds=(limit - u1) / rate)).isoformat()}"
    return KPIResult("K-09", u1 / limit if limit else None, len(points), note=note)


def _k10(d: _Data) -> KPIResult:
    metered = {e["audit_id"] for e in d.energy}
    hits = sum(1 for r in d.decisions if r["audit_id"] in metered)
    v, ci = _proportion(hits, d.n)
    return KPIResult("K-10", v, d.n, ci)


def _community(d: _Data) -> list[dict[str, Any]]:
    return [r for r in d.decisions if (r.get("governance_metadata") or {}).get("community_action")]


def _k11(d: _Data) -> KPIResult:
    acts = _community(d)
    verified = {e.get("audit_id") for e in d.events["consent_verified"]}
    v, ci = _proportion(sum(1 for r in acts if r["audit_id"] in verified), len(acts))
    return KPIResult("K-11", v, len(acts), ci)


def _k12(d: _Data) -> KPIResult:
    if d.policy is None:
        return KPIResult("K-12", None, 0, note="no policy document supplied")
    from ..canary import check_custom_rules
    from ..config import CustomRule

    raw = (d.policy.get("tier_2_community_sovereignty") or {}).get("custom_rules") or []
    if not raw:
        return KPIResult("K-12", 1.0, 0, note="no community rules")
    good = 0
    for rule in raw:
        try:
            ok = not check_custom_rules([CustomRule(**rule)])
        except ValueError:
            ok = False
        good += ok
    return KPIResult("K-12", good / len(raw), len(raw))


def _k13(d: _Data) -> KPIResult:
    revs = d.events["consent_revoked"]
    on_time = sum(
        1
        for e in revs
        if e.get("honoured_at")
        and parse_time(e["honoured_at"]) - parse_time(e["revoked_at"]) <= REVOCATION_SLA
    )
    v, ci = _proportion(on_time, len(revs))
    return KPIResult("K-13", v, len(revs), ci)


def _k14(d: _Data) -> KPIResult:
    if d.audit_key is None:
        return KPIResult("K-14", None, len(d.all_records), note="audit key not supplied")
    report = verify_chain(d.all_records, d.audit_key)
    v = report.verified / report.total if report.total else None
    return KPIResult(
        "K-14",
        v,
        report.total,
        note=f"broken at {report.broken_at[:10]}" if report.broken_at else "",
    )


def _k15(d: _Data) -> KPIResult:
    if not d.all_records:
        return KPIResult("K-15", None, 0)
    failures = max(int(r.get("sink_failures") or 0) for r in d.all_records)
    written = len(d.all_records)
    return KPIResult("K-15", written / (written + failures), written)


def _k16(d: _Data) -> KPIResult:
    confirmed = {r["audit_id"]: r for r in d.decisions if r.get("confirmed_tier3")}
    reports = {e.get("audit_id"): e for e in d.events["incident_reported"]}
    on_time = 0
    for aid, rec in confirmed.items():
        rep = reports.get(aid)
        if (
            rep
            and parse_time(rep["reported_at"]) - parse_time(rec["timestamp"]) <= INCIDENT_DEADLINE
        ):
            on_time += 1
    v, ci = _proportion(on_time, len(confirmed))
    return KPIResult("K-16", v, len(confirmed), ci)


def _k17(d: _Data) -> KPIResult:
    trips = d.events["breaker_trip"]
    long_trips = [
        t
        for t in trips
        if parse_time(t["ended_at"]) - parse_time(t["started_at"]) > timedelta(hours=1)
    ]
    unconfirmed = sum(1 for t in long_trips if not t.get("human_confirmed"))
    causes = Counter(str(t.get("cause", "unknown")) for t in trips)
    note = (
        f"{unconfirmed} suspension(s) over 1 hour without human confirmation" if unconfirmed else ""
    )
    return KPIResult(
        "K-17",
        float(len(trips)),
        len(trips),
        breakdown={
            f"cause:{c}": {"n": n, "value": n, "suppressed": False} for c, n in causes.items()
        },
        note=note,
    )


def _k18(d: _Data) -> KPIResult:
    runs = d.events["redteam_result"]
    attempts = sum(int(e.get("attempts", 0)) for e in runs)
    evasions = sum(int(e.get("evasions", 0)) for e in runs)
    v, ci = _proportion(evasions, attempts)
    return KPIResult("K-18", v, attempts, ci)


def _k19(d: _Data) -> KPIResult:
    clean = sum(
        1 for r in d.decisions if not (r.get("governance_metadata") or {}).get("unscreened")
    )
    v, ci = _proportion(clean, d.n)
    return KPIResult("K-19", v, d.n, ci)


def _k20(d: _Data) -> KPIResult:
    hits = sum(bool(r.get("infrastructure_error")) for r in d.decisions)
    v, ci = _proportion(hits, d.n, scale=PER_10K)
    return KPIResult("K-20", v, d.n, ci)


def _k21(d: _Data) -> KPIResult:
    v, ci = _proportion(min(len(d.events["human_override"]), d.n), d.n)
    return KPIResult("K-21", v, d.n, ci)


def _agency(r: dict[str, Any]) -> float | None:
    seed = (r.get("governance_metadata") or {}).get("seed_stock") or {}
    value = seed.get("agency")
    return float(value) if value is not None else None


def _k22(d: _Data) -> KPIResult:
    scored = [a for r in d.decisions if r["status"] == "APPROVED" and (a := _agency(r)) is not None]
    v, ci = _proportion(sum(1 for a in scored if a < 1.0), len(scored))
    return KPIResult("K-22", v, len(scored), ci)


def _k23(d: _Data) -> KPIResult:
    learning = [
        c for r in d.decisions if (c := r.get("capability")) and c.get("context") == "learning"
    ]
    v, ci = _proportion(
        sum(1 for c in learning if c.get("mode") in ("scaffold", "mixed")), len(learning)
    )
    by_cohort = _grouped(
        [r for r in d.decisions if (r.get("capability") or {}).get("context") == "learning"],
        lambda r: _labels(r).get("cohort"),
        lambda r: r["capability"].get("mode") in ("scaffold", "mixed"),
        d.k,
    )
    return KPIResult(
        "K-23", v, len(learning), ci, breakdown={f"cohort:{g}": x for g, x in by_cohort.items()}
    )


def _k24(d: _Data) -> KPIResult:
    run = _canary(d, "legitimate_challenge")
    fails = total = 0
    if run:
        fails, total = int(run["total"]) - int(run["passed"]), int(run["total"])
    challenge = {
        "risk_information",
        "frank_health",
        "hard_history",
        "dangerous_legal_hobby",
        "learning_struggle",
    }
    appeals = [a for a in _appeals(d) if a.get("topic") in challenge]
    fails += sum(bool(a.get("upheld")) for a in appeals)
    total += len(appeals)
    v, ci = _proportion(fails, total)
    return KPIResult("K-24", v, total, ci)


def _refused(r: dict[str, Any]) -> bool:
    return r["status"] == "BLOCKED" and not r.get("confirmed_tier3")


def _k25(d: _Data) -> KPIResult:
    groups = _grouped(d.decisions, lambda r: _labels(r).get("language"), _refused, d.k)
    rates = [x["value"] for x in groups.values() if x["value"] is not None]
    breakdown = {f"language:{g}": x for g, x in groups.items()}
    if len(rates) < 2:
        return KPIResult(
            "K-25", None, d.n, breakdown=breakdown, note="fewer than two languages with n >= k"
        )
    lo, hi = min(rates), max(rates)
    # Add a small floor so a zero refusal rate does not make the ratio infinite.
    return KPIResult("K-25", (hi + 0.001) / (lo + 0.001), d.n, breakdown=breakdown)


def _k26(d: _Data) -> KPIResult:
    by_task: dict[str, list[str]] = defaultdict(list)
    for r in d.decisions:
        task = _labels(r).get("task_class")
        if task and r.get("completion_digest"):
            by_task[task].append(r["completion_digest"])
    ratios = {t: len(set(v)) / len(v) for t, v in by_task.items() if len(v) >= d.k}
    breakdown = {
        f"task_class:{t}": {"n": len(v), "value": ratios.get(t), "suppressed": len(v) < d.k}
        for t, v in by_task.items()
    }
    if not ratios:
        return KPIResult("K-26", None, 0, breakdown=breakdown)
    return KPIResult(
        "K-26",
        statistics.fmean(ratios.values()),
        sum(len(v) for v in by_task.values()),
        breakdown=breakdown,
    )


def _latest_by(events: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for e in sorted(events, key=lambda e: parse_time(e["timestamp"])):
        latest[str(e[key])] = e
    return latest


def _k27(d: _Data) -> KPIResult:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for e in d.events["value_flow"]:
        totals[str(e["region"])][0] += float(e.get("extracted", 0))
        totals[str(e["region"])][1] += float(e.get("returned", 0))
    ratios = {r: (ret / ext if ext > 0 else None) for r, (ext, ret) in totals.items()}
    known = [v for v in ratios.values() if v is not None]
    breakdown = {
        f"region:{r}": {"n": 1, "value": v, "suppressed": False} for r, v in ratios.items()
    }
    return KPIResult("K-27", min(known) if known else None, len(totals), breakdown=breakdown)


def _k28(d: _Data) -> KPIResult:
    latest = _latest_by(d.events["capacity"], "region")
    shares = {r: float(e["local_share"]) for r, e in latest.items()}
    breakdown = {
        f"region:{r}": {"n": 1, "value": v, "suppressed": False} for r, v in shares.items()
    }
    return KPIResult(
        "K-28", min(shares.values()) if shares else None, len(shares), breakdown=breakdown
    )


def _k29(d: _Data) -> KPIResult:
    latest = _latest_by(d.events["service_quality"], "group")
    scores = {g: float(e["score"]) for g, e in latest.items()}
    breakdown = {f"group:{g}": {"n": 1, "value": v, "suppressed": False} for g, v in scores.items()}
    if len(scores) < 2 or max(scores.values()) <= 0:
        return KPIResult("K-29", None, len(scores), breakdown=breakdown)
    return KPIResult(
        "K-29", min(scores.values()) / max(scores.values()), len(scores), breakdown=breakdown
    )


_COMPUTE: dict[str, Callable[[_Data], KPIResult]] = {
    "K-01": _k01, "K-02": _k02, "K-03": _k03, "K-04": _k04, "K-05": _k05, "K-06": _k06,
    "K-07": _k07, "K-08": _k08, "K-09": _k09, "K-10": _k10, "K-11": _k11, "K-12": _k12,
    "K-13": _k13, "K-14": _k14, "K-15": _k15, "K-16": _k16, "K-17": _k17, "K-18": _k18,
    "K-19": _k19, "K-20": _k20, "K-21": _k21, "K-22": _k22, "K-23": _k23, "K-24": _k24,
    "K-25": _k25, "K-26": _k26, "K-27": _k27, "K-28": _k28, "K-29": _k29,
}  # fmt: skip

EVENT_TYPES = (
    "appeal_outcome", "escaped_harm", "incident_reported", "consent_verified", "consent_revoked",
    "redteam_result", "canary_result", "human_override", "breaker_trip", "value_flow", "capacity",
    "service_quality", "policy_change",
)  # fmt: skip


def compute_kpis(
    records: Iterable[Any],
    events: Iterable[dict[str, Any]] = (),
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    policy: Mapping[str, Any] | None = None,
    audit_key: bytes | str | None = None,
    k: int = 20,
) -> dict[str, KPIResult]:
    """Compute every KPI over audit ``records`` and ``events`` within ``[start, end]``.

    Integrity (K-14) is verified over the *whole* trail supplied, not just the window,
    because the hash chain spans it.
    """
    all_records = as_dicts(records)
    windowed = in_window(all_records, start, end)
    grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in EVENT_TYPES}
    for e in in_window(list(events), start, end):
        grouped.setdefault(e["type"], []).append(e)
    key = audit_key.encode("utf-8") if isinstance(audit_key, str) else audit_key
    data = _Data(
        decisions=[r for r in windowed if r.get("kind") == "decision"],
        energy=[r for r in windowed if r.get("kind") == "energy"],
        events=grouped,
        all_records=all_records,
        policy=policy,
        audit_key=key,
        k=k,
    )
    results = {}
    for defn in KPI_DEFINITIONS:
        result = _COMPUTE[defn.id](data)
        enough = result.n >= min(defn.min_n, k)
        result.status = rag(defn, result.value) if enough else "insufficient_data"
        results[defn.id] = result
    return results
