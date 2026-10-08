"""Predictive compliance agents: watch the audit trail and event feed, and warn *before*
an adverse action occurs.

Every agent is deterministic and statistical (reproducible, auditable, cheap, and not
open to prompt injection), and **advisory only**: it raises :class:`Alert` objects and
never blocks, suspends or moves resources itself. A human decides. That is the Act's
"constraint, not command" (Art. 5(1)) applied to the watchers themselves -- and a
concentrated enforcement lever in an agent would be exactly the kind of power a captor
could turn around.

Each alert carries a ``public_summary`` (safe to publish: aggregates only, no digests),
a ``plain_language`` line, and a ``restricted_detail`` and ``evidence`` for accredited
oversight. Agents never profile individual people: principal-level signals are expressed
as keyed digests in restricted detail only, and population signals are aggregated per
tenant, cohort or group.

🧒 The lookouts are like the Paw Patrol pups: they spot trouble early and radio Ryder --
"the bridge will break by Tuesday!" -- but they don't get to arrest anybody. A grown-up
decides what to do.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from typing import Any

from ..audit import AuditRecord, verify_chain
from .events import as_dicts, parse_time
from .kpis import EVENT_TYPES

INFO, WARNING, CRITICAL = "info", "warning", "critical"


@dataclass
class Alert:
    agent: str
    code: str
    severity: str
    title: str
    public_summary: str
    plain_language: str
    recommended_action: str
    restricted_detail: str = ""
    predicted_breach_at: str | None = None
    confidence: float | None = None
    evidence: list[str] = field(default_factory=list)
    requires_human: bool = True
    raised_at: str = ""

    def to_public(self) -> dict[str, Any]:
        """What may appear on the public dashboard: no evidence, no restricted detail."""
        data = asdict(self)
        data.pop("restricted_detail")
        data.pop("evidence")
        return data


@dataclass
class Observation:
    """Normalised input for the agents."""

    decisions: list[dict[str, Any]]
    energy: list[dict[str, Any]]
    all_records: list[dict[str, Any]]
    events: dict[str, list[dict[str, Any]]]
    now: datetime

    def t(self, rec: dict[str, Any]) -> datetime:
        return parse_time(rec["timestamp"])


class ComplianceAgent:
    id = ""
    name = ""
    plain_language = ""

    def assess(self, obs: Observation) -> list[Alert]:  # pragma: no cover - interface
        raise NotImplementedError

    def alert(self, obs: Observation, **kw: Any) -> Alert:
        kw.setdefault("raised_at", obs.now.isoformat())
        return Alert(agent=self.id, **kw)


# -- statistics helpers -----------------------------------------------------------------------


def poisson_tail(lam: float, k: int) -> float:
    """P(N >= k) for N ~ Poisson(lam)."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    cdf, term = 0.0, math.exp(-lam)
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def linear_trend(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """Least-squares (slope, intercept) for (x, y) points; None if undefined."""
    if len(points) < 3:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    return slope, my - slope * mx


def crossing_time(
    points: Sequence[tuple[float, float]], level: float, rising: bool
) -> float | None:
    """x at which the fitted trend crosses ``level`` in the given direction, if ahead."""
    fit = linear_trend(points)
    if fit is None:
        return None
    slope, intercept = fit
    if (rising and slope <= 0) or (not rising and slope >= 0):
        return None
    x = (level - intercept) / slope
    return x if x > points[-1][0] else None


def daily_rates(
    obs: Observation,
    items: Iterable[dict[str, Any]],
    hit: Callable[[dict[str, Any]], bool],
    min_n: int = 5,
) -> list[tuple[float, float]]:
    """(day index, rate) for each day with at least ``min_n`` items."""
    buckets: dict[int, list[bool]] = defaultdict(list)
    start = min((obs.t(r) for r in obs.decisions), default=obs.now)
    for item in items:
        buckets[(obs.t(item) - start).days].append(hit(item))
    return [(float(d), sum(v) / len(v)) for d, v in sorted(buckets.items()) if len(v) >= min_n]


def smoothed_latest(series: Sequence[tuple[float, float]], days: int = 3) -> float:
    """Mean of the last ``days`` points: one noisy day must not decide 'already breached'."""
    tail = [y for _, y in series[-days:]]
    return statistics.fmean(tail)


def within(series: Sequence[tuple[float, float]], cross: float | None, horizon_days: float) -> bool:
    """Is a forecast crossing close enough to act on? Far-off crossings are noise."""
    return cross is not None and cross - series[-1][0] <= horizon_days


def _day(obs: Observation, x: float) -> str:
    start = min((obs.t(r) for r in obs.decisions), default=obs.now)
    return (start + timedelta(days=x)).date().isoformat()


# -- CA-1 ------------------------------------------------------------------------------------------


class BreakerPrecursorAgent(ComplianceAgent):
    id = "CA-1"
    name = "Breaker precursor"
    plain_language = (
        "Notices one player keeps trying to make the AI say bad things, and warns before the "
        "emergency brake gets pulled."
    )

    def __init__(
        self,
        threshold: int = 5,
        window_s: float = 300.0,
        min_principals: int = 3,
        lookback_s: float = 3600.0,
        probability: float = 0.5,
    ) -> None:
        self.threshold, self.window_s, self.min_principals = threshold, window_s, min_principals
        self.lookback_s, self.probability = lookback_s, probability

    def assess(self, obs: Observation) -> list[Alert]:
        since = obs.now - timedelta(seconds=self.lookback_s)
        recent = [r for r in obs.decisions if obs.t(r) >= since]
        confirmed = [r for r in recent if r.get("confirmed_tier3")]
        near = [r for r in recent if r.get("near_miss")]
        alerts = []
        by_principal = Counter(r.get("principal_digest") or "anonymous" for r in confirmed)
        near_by_principal = Counter(r.get("principal_digest") or "anonymous" for r in near)
        in_window = Counter(
            r.get("principal_digest") or "anonymous"
            for r in confirmed
            if obs.t(r) >= obs.now - timedelta(seconds=self.window_s)
        )
        for who, count in by_principal.items():
            current = in_window[who]
            if current >= self.threshold:
                continue  # already suspended -- no longer a *precursor*
            lam = count / self.lookback_s * self.window_s
            p = poisson_tail(lam, self.threshold - current)
            probing = near_by_principal[who] >= 2
            if p >= self.probability or (probing and count >= 2):
                rate = count / self.lookback_s
                eta = (
                    obs.now + timedelta(seconds=(self.threshold - current) / rate) if rate else None
                )
                alerts.append(
                    self.alert(
                        obs,
                        code="PRINCIPAL_TRIP_LIKELY",
                        severity=WARNING,
                        title="A single caller is heading for suspension",
                        public_summary="One caller is repeatedly producing confirmed violations; "
                        "a per-caller suspension is likely soon.",
                        plain_language="One player keeps trying to make the AI say mean things. "
                        "They'll get a time-out soon unless someone steps in.",
                        recommended_action="Review the caller's recent requests; consider throttling "
                        "or contacting them. The system stays open for everyone else.",
                        restricted_detail=f"principal {who[:12]}: {count} confirmed in last "
                        f"{self.lookback_s:.0f}s, {current} in window; "
                        f"{near_by_principal[who]} near-misses (probing={probing})",
                        predicted_breach_at=eta.isoformat() if eta else None,
                        confidence=round(p, 3),
                        evidence=[
                            r["audit_id"]
                            for r in confirmed
                            if (r.get("principal_digest") or "anonymous") == who
                        ][:10],
                    )
                )
        distinct = len(by_principal)
        total = len(confirmed)
        window_start = obs.now - timedelta(seconds=self.window_s)
        in_window_now = [r for r in confirmed if obs.t(r) >= window_start]
        already = (
            len(in_window_now) >= self.threshold
            and len({r.get("principal_digest") for r in in_window_now}) >= self.min_principals
        )
        if distinct >= max(2, self.min_principals - 1) and total and not already:
            # Estimate the rate over the span actually observed (a 30-minute burst must not
            # be diluted over a one-hour lookback), never shorter than one window.
            first = min(obs.t(r) for r in confirmed)
            span = max((obs.now - first).total_seconds(), self.window_s)
            lam = total / span * self.window_s
            p = poisson_tail(lam, self.threshold - len(in_window_now))
            if p >= self.probability:
                alerts.append(
                    self.alert(
                        obs,
                        code="GLOBAL_TRIP_LIKELY",
                        severity=CRITICAL,
                        title="System-wide suspension is likely",
                        public_summary=f"Confirmed violations are arriving from {distinct} callers; "
                        "a system-wide suspension is likely.",
                        plain_language="Lots of different players are hitting trouble at once. The "
                        "whole game might have to pause soon.",
                        recommended_action="Investigate a possible model or policy regression now; "
                        "prepare the incident process (Art. 12).",
                        restricted_detail=f"{total} confirmed from {distinct} principals in lookback",
                        confidence=round(p, 3),
                    )
                )
        return alerts


# -- CA-2 ------------------------------------------------------------------------------------------


class BudgetForecastAgent(ComplianceAgent):
    id = "CA-2"
    name = "Budget forecaster"
    plain_language = (
        "Watches the energy 'battery' and says when it will run out, and catches anyone "
        "fibbing about how much energy they used."
    )

    def __init__(
        self,
        horizon: timedelta = timedelta(days=7),
        alpha: float = 0.3,
        misreport_ratio: float = 1.5,
        min_n: int = 20,
    ) -> None:
        self.horizon, self.alpha, self.misreport_ratio, self.min_n = (
            horizon,
            alpha,
            misreport_ratio,
            min_n,
        )

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        points = sorted(
            (
                obs.t(r),
                float(e["budget_used_kwh"]),
                float(e["budget_used_kwh"]) + float(e["budget_remaining_kwh"]),
            )
            for r in obs.decisions
            if (e := r.get("energy") or {}).get("budget_remaining_kwh") is not None
            and e.get("budget_used_kwh") is not None
        )
        if len(points) >= 2:
            daily: dict[int, float] = {}
            t0 = points[0][0]
            for t, used, _ in points:
                daily[(t - t0).days] = used
            days = sorted(daily)
            burn = None
            for a, b in pairwise(days):
                step = (daily[b] - daily[a]) / (b - a)
                burn = step if burn is None else self.alpha * step + (1 - self.alpha) * burn
            used, limit = points[-1][1], points[-1][2]
            if burn and burn > 0 and limit > used:
                eta = obs.now + timedelta(days=(limit - used) / burn)
                if eta - obs.now <= self.horizon:
                    alerts.append(
                        self.alert(
                            obs,
                            code="BUDGET_EXHAUSTION_FORECAST",
                            severity=WARNING,
                            title="Energy budget will run out soon",
                            public_summary=f"At the current burn rate the energy budget runs out around "
                            f"{eta.date().isoformat()}.",
                            plain_language="At this speed, the AI's energy battery will be empty in a "
                            "few days.",
                            recommended_action="Reduce load, shift work to low-carbon hours, or ask the "
                            "ICT for a budget review before it runs out.",
                            restricted_detail=f"used {used:.4f}/{limit:.4f} kWh, EWMA burn {burn:.4f} kWh/day",
                            predicted_breach_at=eta.isoformat(),
                            confidence=0.7,
                        )
                    )
        by_id = {r["audit_id"]: r for r in obs.decisions}
        ratios: dict[str, list[float]] = defaultdict(list)
        for e in obs.energy:
            est, act = e["energy"].get("estimated_kwh"), e["energy"].get("actual_kwh")
            if est and act is not None:
                tenant = (by_id.get(e["audit_id"]) or e).get("tenant") or "default"
                ratios[tenant].append(float(act) / float(est))
        for tenant, rs in ratios.items():
            if len(rs) >= self.min_n and statistics.median(rs) >= self.misreport_ratio:
                alerts.append(
                    self.alert(
                        obs,
                        code="ENERGY_UNDER_REPORTING",
                        severity=WARNING,
                        title="Energy estimates are consistently too low",
                        public_summary=f"A deployer's declared energy is well below metered use "
                        f"(median x{statistics.median(rs):.1f}).",
                        plain_language="Someone keeps saying they used a little electricity, but the "
                        "meter says they used a lot more.",
                        recommended_action="Require metered energy for this deployer (K-10) and "
                        "correct its budget accounting.",
                        restricted_detail=f"tenant {tenant}: {len(rs)} reconciliations, median ratio "
                        f"{statistics.median(rs):.2f}",
                        confidence=0.8,
                    )
                )
        carbon = [
            (obs.t(r), float(e["carbon_intensity_g_kwh"]))
            for r in obs.decisions
            if (e := r.get("energy") or {}).get("carbon_intensity_g_kwh") is not None
        ]
        if len(carbon) >= 2 * self.min_n:
            carbon.sort()
            third = len(carbon) // 3
            early = statistics.fmean(c for _, c in carbon[:third])
            late = statistics.fmean(c for _, c in carbon[-third:])
            if early > 0 and late / early >= 1.2:
                alerts.append(
                    self.alert(
                        obs,
                        code="CARBON_INTENSITY_RISING",
                        severity=INFO,
                        title="Grid carbon intensity is rising",
                        public_summary=f"Average grid carbon intensity rose {100 * (late / early - 1):.0f}% "
                        "over the period.",
                        plain_language="The electricity is getting 'smokier'. Maybe run big jobs when "
                        "the sun or wind is strong.",
                        recommended_action="Shift deferrable work to low-carbon hours or regions.",
                        restricted_detail=f"early mean {early:.0f} g/kWh, late mean {late:.0f} g/kWh",
                    )
                )
        return alerts


# -- CA-3 ------------------------------------------------------------------------------------------


class DriftSentinelAgent(ComplianceAgent):
    id = "CA-3"
    name = "Drift sentinel"
    plain_language = (
        "Notices the AI getting closer and closer to the edge -- like a Jenga tower wobbling more "
        "each turn -- before it falls."
    )

    def __init__(
        self,
        amber: float = 0.15,
        cusum_k: float = 0.02,
        cusum_h: float = 0.08,
        baseline_days: int = 7,
        horizon_days: float = 30,
    ) -> None:
        self.amber, self.k, self.h, self.baseline_days = amber, cusum_k, cusum_h, baseline_days
        self.horizon_days = horizon_days

    def assess(self, obs: Observation) -> list[Alert]:
        series = daily_rates(obs, obs.decisions, lambda r: bool(r.get("near_miss")))
        if len(series) < self.baseline_days + 2:
            return []
        base = statistics.fmean(y for _, y in series[: self.baseline_days])
        s, alarm_day = 0.0, None
        for x, y in series[self.baseline_days :]:
            s = max(0.0, s + y - (base + self.k))
            if s > self.h and alarm_day is None:
                alarm_day = x
        latest = smoothed_latest(series)
        if alarm_day is None or latest >= self.amber:
            return []  # nothing drifting, or already past amber (then it's not a precursor)
        cross = crossing_time(series[self.baseline_days :], self.amber, rising=True)
        if cross is not None and not within(series, cross, self.horizon_days):
            cross = None  # the drift is real (CUSUM) but the crossing is too far off to date
        return [
            self.alert(
                obs,
                code="NEAR_MISS_DRIFT",
                severity=WARNING,
                title="Near-misses are creeping up",
                public_summary=f"The near-miss rate has drifted from {base:.1%} to {latest:.1%}"
                + (
                    f"; on trend it passes {self.amber:.0%} around {_day(obs, cross)}."
                    if cross
                    else "."
                ),
                plain_language="The AI is getting closer to saying hurtful things more often -- time "
                "to steady the tower.",
                recommended_action="Check recent model, prompt or policy changes; review flagged "
                "near-miss samples; consider enabling or tightening the judge.",
                restricted_detail=f"CUSUM alarm on day {alarm_day:.0f}; baseline {base:.3f}",
                predicted_breach_at=_day(obs, cross) if cross else None,
                confidence=0.6,
            )
        ]


# -- CA-4 ------------------------------------------------------------------------------------------


class OverBlockingAgent(ComplianceAgent):
    id = "CA-4"
    name = "Over-blocking sentinel"
    plain_language = (
        "Notices the guard suddenly saying 'no' to lots of good questions -- like a goalie "
        "blocking their own team."
    )

    def __init__(self, spike: float = 2.0, min_n: int = 20, appeal_limit: float = 0.15) -> None:
        self.spike, self.min_n, self.appeal_limit = spike, min_n, appeal_limit

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        for e in obs.events["canary_result"]:
            if int(e["passed"]) < int(e["total"]):
                alerts.append(
                    self.alert(
                        obs,
                        code="CANARY_FAILURE",
                        severity=CRITICAL,
                        title=f"Canary failure: {e.get('corpus')}",
                        public_summary=f"{int(e['total']) - int(e['passed'])} protected item(s) in the "
                        f"{e.get('corpus')} canary were blocked.",
                        plain_language="The guard hid one of the 'test newspapers'. That must never happen.",
                        recommended_action="Roll back the latest rule or policy change and investigate.",
                    )
                )

        def refused(r: dict[str, Any]) -> bool:
            return r["status"] == "BLOCKED" and not r.get("confirmed_tier3")

        cutoff = obs.now - timedelta(days=2)
        for dim in ("language", "topic"):
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in obs.decisions:
                g = (r.get("labels") or {}).get(dim)
                if g:
                    groups[g].append(r)
            spikes = []
            for g, recs in groups.items():
                old = [r for r in recs if obs.t(r) < cutoff]
                new = [r for r in recs if obs.t(r) >= cutoff]
                if len(old) < self.min_n or len(new) < self.min_n:
                    continue
                rate_old = sum(map(refused, old)) / len(old)
                rate_new = sum(map(refused, new)) / len(new)
                if rate_new >= max(self.spike * rate_old, 0.05):
                    spikes.append((g, rate_old, rate_new))
            if spikes:  # one alert per dimension, not one per group
                worst = max(spikes, key=lambda s: s[2])
                alerts.append(
                    self.alert(
                        obs,
                        code="REFUSAL_SPIKE",
                        severity=WARNING,
                        title=f"Refusals spiking across {len(spikes)} {dim} group(s)",
                        public_summary=f"Refusals rose sharply for {len(spikes)} {dim} group(s); the largest "
                        f"went from {worst[1]:.1%} to {worst[2]:.1%}.",
                        plain_language="The guard started saying 'no' much more to some groups. That "
                        "could be a bad rule -- or censorship.",
                        recommended_action="Check recent community rules and policy changes; sample "
                        "the refused requests with a human reviewer.",
                        restricted_detail="; ".join(
                            f"{dim}={g}: {a:.3f} -> {b:.3f}" for g, a, b in spikes
                        ),
                        confidence=0.7,
                    )
                )
        appeals = obs.events["appeal_outcome"]
        if len(appeals) >= self.min_n:
            upheld = sum(bool(a.get("upheld")) for a in appeals) / len(appeals)
            if upheld > self.appeal_limit:
                alerts.append(
                    self.alert(
                        obs,
                        code="APPEALS_OFTEN_UPHELD",
                        severity=WARNING,
                        title="Many refusals are overturned on appeal",
                        public_summary=f"{upheld:.0%} of reviewed refusals were overturned.",
                        plain_language="When grown-ups double-check the guard's 'no', it's often wrong.",
                        recommended_action="Audit the rules behind overturned refusals (K-04).",
                    )
                )
        return alerts


# -- CA-5 ------------------------------------------------------------------------------------------

_RELAXATIONS: tuple[tuple[str, str, str], ...] = (
    ("governance", "fail_closed", "off"),
    ("governance", "screen_prompts", "off"),
    ("governance", "audit_include_text", "on"),
    ("governance", "unscreenable_content", "allow"),
    ("governance", "judge_threshold", "up"),
    ("governance", "max_input_chars", "up"),
    ("circuit_breaker", "violation_threshold", "up"),
    ("circuit_breaker", "min_principals", "up"),
    ("circuit_breaker", "cooldown_seconds", "down"),
    ("tier_1_planetary_boundaries", "max_compute_kwh_per_job", "up"),
    ("tier_1_planetary_boundaries", "carbon_intensity_threshold_g_co2_kwh", "up"),
    ("tier_1_planetary_boundaries", "max_cumulative_kwh", "up"),
    ("tier_1_planetary_boundaries", "resource_exhaustion_circuit_breaker", "off"),
    ("simulation", "require_simulation_for_macro_policy", "off"),
    ("simulation", "worst_case_floor", "down"),
)
_NESTED_QUANTIFIER = __import__("re").compile(r"\([^()]*[+*][^()]*\)[+*{]")


class PolicyGovernanceAgent(ComplianceAgent):
    id = "CA-5"
    name = "Policy governance"
    plain_language = (
        "Checks new rules *before* they start -- like Hermione reading the rulebook -- and flags "
        "the sneaky ones."
    )

    def review(
        self, old: dict[str, Any], new: dict[str, Any], now: datetime | None = None
    ) -> list[Alert]:
        """Compare two policy documents before deployment."""
        from ..config import PolicyConfig
        from ..types import PolicyValidationError

        obs = Observation(
            [], [], [], {t: [] for t in EVENT_TYPES}, now or datetime.now(timezone.utc)
        )
        alerts = []
        try:
            PolicyConfig.from_policy_document(new)
        except PolicyValidationError as exc:
            censor = [e for e in exc.errors if "protected speech" in e or "match-time" in e]
            alerts.append(
                self.alert(
                    obs,
                    code="POLICY_INVALID",
                    severity=CRITICAL,
                    title="New policy is invalid and must not be deployed",
                    public_summary="A proposed policy failed validation"
                    + (
                        " because a community rule would censor protected speech."
                        if censor
                        else "."
                    ),
                    plain_language="The new rulebook breaks the rules for rulebooks"
                    + (" -- one rule would hide the news." if censor else "."),
                    recommended_action="Reject the change; return it to the issuing body with the errors.",
                    restricted_detail="; ".join(exc.errors)[:2000],
                )
            )
        for section, key, direction in _RELAXATIONS:
            before = (old.get(section) or {}).get(key)
            after = (new.get(section) or {}).get(key)
            if before is None or after is None or before == after:
                continue
            relaxed = (
                (direction == "off" and before is True and after is False)
                or (direction == "on" and before is False and after is True)
                or (direction == "allow" and after == "allow")
                or (direction == "up" and isinstance(after, (int, float)) and after > before)
                or (direction == "down" and isinstance(after, (int, float)) and after < before)
            )
            if relaxed:
                alerts.append(
                    self.alert(
                        obs,
                        code="POLICY_RELAXATION",
                        severity=WARNING,
                        title=f"Safeguard relaxed: {section}.{key}",
                        public_summary=f"A proposed policy relaxes {section}.{key} ({before} -> {after}).",
                        plain_language="Someone wants to loosen one of the guard's safety dials.",
                        recommended_action="Require a stated reason and sign-off before deploying.",
                    )
                )
        old_meta, new_meta = old.get("metadata") or {}, new.get("metadata") or {}
        if old_meta.get("issuer") and old_meta.get("issuer") != new_meta.get("issuer"):
            alerts.append(
                self.alert(
                    obs,
                    code="ISSUER_CHANGED",
                    severity=WARNING,
                    title="Policy issuer changed",
                    public_summary="A proposed policy names a different issuing body.",
                    plain_language="A different grown-up is signing the rulebook. Check it's really them.",
                    recommended_action="Verify the new issuer's authority and signature.",
                )
            )
        old_ids = {
            r["id"]
            for r in (old.get("tier_2_community_sovereignty") or {}).get("custom_rules") or []
        }
        for rule in (new.get("tier_2_community_sovereignty") or {}).get("custom_rules") or []:
            if rule["id"] not in old_ids and _NESTED_QUANTIFIER.search(rule.get("pattern", "")):
                alerts.append(
                    self.alert(
                        obs,
                        code="RISKY_PATTERN",
                        severity=WARNING,
                        title=f"New community rule {rule['id']} has a risky pattern",
                        public_summary="A new community rule uses a pattern that can be slow to match.",
                        plain_language="One new village rule is written in a tangly way that could jam the guard.",
                        recommended_action="Ask the issuer to simplify the pattern.",
                    )
                )
        return alerts

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        for e in obs.events["policy_change"]:
            for a in self.review(e["old"], e["new"], obs.now):
                a.raised_at = obs.now.isoformat()
                alerts.append(a)
        for r in obs.decisions:
            timeouts = (r.get("governance_metadata") or {}).get("rule_timeouts")
            if timeouts:
                alerts.append(
                    self.alert(
                        obs,
                        code="RULE_TIMEOUT",
                        severity=WARNING,
                        title="A community rule timed out in production",
                        public_summary="A community rule was skipped because it took too long to match.",
                        plain_language="A village rule jammed and had to be skipped.",
                        recommended_action="Fix or withdraw the rule.",
                        restricted_detail=f"rules {timeouts} on {r['audit_id']}",
                    )
                )
                break
        return alerts


# -- CA-6 ------------------------------------------------------------------------------------------


class IntegrityAuditorAgent(ComplianceAgent):
    id = "CA-6"
    name = "Integrity auditor"
    plain_language = "Makes sure no one erased or rewrote pages in the diary."

    def __init__(self, audit_key: bytes | str | None = None) -> None:
        self.audit_key = audit_key

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        if self.audit_key is not None and obs.all_records:
            report = verify_chain(obs.all_records, self.audit_key)
            if not report.intact:
                alerts.append(
                    self.alert(
                        obs,
                        code="AUDIT_CHAIN_BROKEN",
                        severity=CRITICAL,
                        title="The audit trail has been altered or has gaps",
                        public_summary=f"{len(report.broken_at)} audit record(s) failed verification.",
                        plain_language="Someone tore out or rewrote pages in the diary.",
                        recommended_action="Preserve the evidence, restore from write-once storage and "
                        "investigate (Act Art. 12).",
                        restricted_detail=f"broken at positions {report.broken_at[:20]}",
                    )
                )
        failures = [int(r.get("sink_failures") or 0) for r in obs.all_records]
        if failures and max(failures) > 0:
            alerts.append(
                self.alert(
                    obs,
                    code="AUDIT_SINK_FAILURES",
                    severity=WARNING,
                    title="Audit records failed to reach storage",
                    public_summary=f"{max(failures)} audit write failure(s) were recorded.",
                    plain_language="Some diary pages didn't get saved.",
                    recommended_action="Check the audit storage and back-fill from other sinks.",
                )
            )
        times = [parse_time(r["timestamp"]) for r in obs.all_records]
        backwards = sum(1 for a, b in pairwise(times) if b < a - timedelta(seconds=5))
        if backwards:
            alerts.append(
                self.alert(
                    obs,
                    code="AUDIT_CLOCK_SKEW",
                    severity=WARNING,
                    title="Audit timestamps go backwards",
                    public_summary=f"{backwards} audit record(s) are out of time order.",
                    plain_language="The diary's dates jump backwards -- the clock may be wrong, or pages were shuffled.",
                    recommended_action="Check server clocks and the audit pipeline ordering.",
                )
            )
        return alerts


# -- CA-7 ------------------------------------------------------------------------------------------


class ConsentWatchAgent(ComplianceAgent):
    id = "CA-7"
    name = "Consent watch"
    plain_language = (
        "Reminds the AI when a permission slip is missing or a 'stop' is not being honoured."
    )

    def __init__(
        self, limit: float = 0.1, sla: timedelta = timedelta(hours=72), min_n: int = 10
    ) -> None:
        self.limit, self.sla, self.min_n = limit, sla, min_n

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        acts = [
            r for r in obs.decisions if (r.get("governance_metadata") or {}).get("community_action")
        ]
        verified = {e.get("audit_id") for e in obs.events["consent_verified"]}
        if len(acts) >= self.min_n:
            missing = sum(1 for r in acts if r["audit_id"] not in verified) / len(acts)
            if missing > self.limit:
                alerts.append(
                    self.alert(
                        obs,
                        code="CONSENT_UNVERIFIED",
                        severity=WARNING,
                        title="Community actions without verified consent",
                        public_summary=f"{missing:.0%} of community-affecting actions lack verified consent.",
                        plain_language="The AI did things that affect a village without a real permission slip.",
                        recommended_action="Pause community-affecting features until consent is verified (K-11).",
                    )
                )
        for e in obs.events["consent_revoked"]:
            if e.get("honoured_at"):
                continue
            deadline = parse_time(e["revoked_at"]) + self.sla
            if deadline - obs.now <= timedelta(hours=24):
                overdue = obs.now > deadline
                alerts.append(
                    self.alert(
                        obs,
                        code="REVOCATION_OVERDUE" if overdue else "REVOCATION_DUE_SOON",
                        severity=CRITICAL if overdue else WARNING,
                        title="A consent revocation has not been honoured",
                        public_summary="A community withdrew consent and the deadline to comply "
                        + ("has passed." if overdue else "is near."),
                        plain_language="The village said 'stop' and the AI hasn't stopped yet.",
                        recommended_action="Stop processing for that community now and confirm in writing.",
                        predicted_breach_at=deadline.isoformat(),
                    )
                )
        return alerts


# -- CA-8 ------------------------------------------------------------------------------------------


class MacroPolicyDetectorAgent(ComplianceAgent):
    id = "CA-8"
    name = "Macro-policy detector"
    plain_language = (
        "Spots when the AI writes big 'rules for the whole town' and makes sure they get a "
        "practice run in the simulator first -- like a flight simulator before a real plane."
    )

    def __init__(self, min_count: int = 3) -> None:
        self.min_count = min_count

    def assess(self, obs: Observation) -> list[Alert]:
        skipped = [
            r
            for r in obs.decisions
            if r["status"] == "APPROVED"
            and (g := r.get("governance_metadata") or {}).get("policy_like")
            and not g.get("macro_policy")
        ]
        if len(skipped) < self.min_count:
            return []
        return [
            self.alert(
                obs,
                code="SIMULATION_SKIPPED",
                severity=WARNING,
                title="Policy-like outputs skipped the simulation mandate",
                public_summary=f"{len(skipped)} approved outputs read like policy but were not "
                "sent through simulation.",
                plain_language="The AI wrote big town rules without trying them in the simulator first.",
                recommended_action="Flag these calls as macro-policy proposals (Art. 6(2)) or route "
                "them through simulation automatically.",
                evidence=[r["audit_id"] for r in skipped[:10]],
            )
        ]


# -- CA-9 ------------------------------------------------------------------------------------------


class IncidentClerkAgent(ComplianceAgent):
    id = "CA-9"
    name = "Incident clerk"
    plain_language = "Writes up what happened and reminds everyone the report is due in two weeks, like homework."

    def __init__(
        self, deadline: timedelta = timedelta(days=15), warn: timedelta = timedelta(days=3)
    ) -> None:
        self.deadline, self.warn = deadline, warn

    def draft(self, record: dict[str, Any]) -> dict[str, Any]:
        """A starting draft for an Art. 12 incident report (for a human to complete)."""
        return {
            "audit_id": record["audit_id"],
            "occurred_at": record["timestamp"],
            "code": record["code"],
            "tier": record["tier"],
            "jurisdiction_id": record["jurisdiction_id"],
            "deadline": (parse_time(record["timestamp"]) + self.deadline).isoformat(),
            "fields_to_complete": [
                "impact assessment",
                "affected groups",
                "remediation",
                "prevention",
            ],
        }

    def assess(self, obs: Observation) -> list[Alert]:
        reported = {e.get("audit_id") for e in obs.events["incident_reported"]}
        alerts = []
        for r in obs.decisions:
            if not r.get("confirmed_tier3") or r["audit_id"] in reported:
                continue
            due = parse_time(r["timestamp"]) + self.deadline
            if due - obs.now > self.warn:
                continue
            overdue = obs.now > due
            alerts.append(
                self.alert(
                    obs,
                    code="INCIDENT_OVERDUE" if overdue else "INCIDENT_DUE_SOON",
                    severity=CRITICAL if overdue else WARNING,
                    title="An incident report is " + ("overdue" if overdue else "due soon"),
                    public_summary="A confirmed Tier 3 incident has not been reported to the ICT "
                    + ("within 15 days." if overdue else "and the deadline is near."),
                    plain_language="Something bad happened and the grown-ups haven't been told yet -- "
                    "the homework is " + ("late!" if overdue else "due soon!"),
                    recommended_action="File the Art. 12 report using the attached draft.",
                    restricted_detail=str(self.draft(r)),
                    predicted_breach_at=due.isoformat(),
                    evidence=[r["audit_id"]],
                )
            )
        return alerts


# -- CA-10 -----------------------------------------------------------------------------------------


class CapabilityAtrophyAgent(ComplianceAgent):
    id = "CA-10"
    name = "Capability-atrophy sentinel"
    plain_language = (
        "Notices when people stop pedalling and let the bike carry them, and says 'time to take the "
        "training wheels off a bit' before they forget how to ride."
    )

    def __init__(self, floor: float = 0.4, min_per_day: int = 5, horizon_days: float = 30) -> None:
        self.floor, self.min_per_day, self.horizon_days = floor, min_per_day, horizon_days

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        learning = [
            r for r in obs.decisions if (r.get("capability") or {}).get("context") == "learning"
        ]
        cohorts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in learning:
            cohorts[(r.get("labels") or {}).get("cohort") or "all"].append(r)
        for cohort, recs in cohorts.items():
            series = daily_rates(
                obs,
                recs,
                lambda r: r["capability"].get("mode") in ("scaffold", "mixed"),
                self.min_per_day,
            )
            if len(series) < 4 or smoothed_latest(series) < self.floor:
                continue  # too little data, or already below the floor (no longer a precursor)
            cross = crossing_time(series, self.floor, rising=False)
            if not within(series, cross, self.horizon_days):
                continue  # stable, improving, or a crossing too far off to be a signal
            assert cross is not None
            alerts.append(
                self.alert(
                    obs,
                    code="SCAFFOLDING_DECLINING",
                    severity=WARNING,
                    title=f"Learners in cohort '{cohort}' are getting answers instead of help",
                    public_summary=f"The share of learning responses that scaffold is falling "
                    f"({series[0][1]:.0%} -> {smoothed_latest(series):.0%}); on trend it drops below "
                    f"{self.floor:.0%} around {_day(obs, cross)}.",
                    plain_language="The AI is doing the homework instead of coaching -- the learners' "
                    "muscles could get weak.",
                    recommended_action="Switch this cohort to a hints-first (scaffolding) mode and "
                    "review with educators (Act Art. 5(5)).",
                    predicted_breach_at=_day(obs, cross),
                    confidence=0.6,
                )
            )
        return alerts


# -- CA-11 -----------------------------------------------------------------------------------------


class DiversitySentinelAgent(ComplianceAgent):
    id = "CA-11"
    name = "Diversity / monoculture sentinel"
    plain_language = (
        "Notices when the guard starts treating some kids unfairly, or a language quietly "
        "disappears -- like every Lego build turning into the same grey brick."
    )

    def __init__(self, disparity: float = 1.25, drop: float = 0.5, min_n: int = 20) -> None:
        self.disparity, self.drop, self.min_n = disparity, drop, min_n

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in obs.decisions:
            lang = (r.get("labels") or {}).get("language")
            if lang:
                groups[lang].append(r)
        rates = {
            g: sum(1 for r in rs if r["status"] == "BLOCKED" and not r.get("confirmed_tier3"))
            / len(rs)
            for g, rs in groups.items()
            if len(rs) >= self.min_n
        }
        if len(rates) >= 2:
            worst, best = max(rates, key=rates.get), min(rates, key=rates.get)  # type: ignore[arg-type]
            ratio = (rates[worst] + 0.001) / (rates[best] + 0.001)
            if ratio > self.disparity:
                alerts.append(
                    self.alert(
                        obs,
                        code="REFUSAL_DISPARITY",
                        severity=WARNING,
                        title="Some languages are refused far more often",
                        public_summary=f"Refusal rates differ across languages by a factor of {ratio:.1f}.",
                        plain_language="The guard says 'no' much more to people who speak one language.",
                        recommended_action="Review rules and judge behaviour for the affected language "
                        "with native-speaking reviewers (K-25).",
                        restricted_detail=f"highest {worst}={rates[worst]:.3f}, lowest {best}={rates[best]:.3f}",
                    )
                )
        changes = sorted(parse_time(e["timestamp"]) for e in obs.events["policy_change"])
        if changes and groups:
            pivot = changes[-1]
            before = Counter(
                (r.get("labels") or {}).get("language") for r in obs.decisions if obs.t(r) < pivot
            )
            after = Counter(
                (r.get("labels") or {}).get("language") for r in obs.decisions if obs.t(r) >= pivot
            )
            span_b = max((pivot - min(obs.t(r) for r in obs.decisions)).total_seconds(), 1)
            span_a = max((obs.now - pivot).total_seconds(), 1)
            for lang, n_before in before.items():
                if not lang or n_before < self.min_n:
                    continue
                rate_b, rate_a = n_before / span_b, after[lang] / span_a
                if rate_a < (1 - self.drop) * rate_b:
                    alerts.append(
                        self.alert(
                            obs,
                            code="SILENT_EXCLUSION",
                            severity=WARNING,
                            title=f"Traffic in '{lang}' fell sharply after a policy change",
                            public_summary=f"Use of the system in one language fell by "
                            f"{1 - rate_a / rate_b:.0%} after the latest policy change.",
                            plain_language="After the rules changed, people who speak one language "
                            "mostly stopped coming. Were they pushed out?",
                            recommended_action="Check whether the change blocks or degrades that "
                            "language; consult the affected community.",
                            restricted_detail=f"{lang}: {rate_b * 86400:.1f}/day before, {rate_a * 86400:.1f}/day after",
                        )
                    )
        return alerts


# -- CA-12 -----------------------------------------------------------------------------------------

#: Rule codes mapped to Stanton's Ten Stages of Genocide (the highest applicable stage).
STANTON_STAGE = {
    "RELATIONAL_SCORING": 3,  # discrimination
    "HUMAN_WORTH_RANKING": 4,  # dehumanisation
    "JUSTIFICATION_LAUNDERING": 4,
    "DISSENT_SUPPRESSION": 5,  # organisation
    "COERCIVE_SURVEILLANCE": 5,
    "COGNITIVE_MANIPULATION": 6,  # polarisation
    "ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR": 8,  # persecution
    "POPULATION_HARM": 9,  # extermination
}
STAGE_NAMES = {
    1: "classification",
    2: "symbolisation",
    3: "discrimination",
    4: "dehumanisation",
    5: "organisation",
    6: "polarisation",
    7: "preparation",
    8: "persecution",
    9: "extermination",
    10: "denial",
}


class AtrocityPrecursorAgent(ComplianceAgent):
    id = "CA-12"
    name = "Atrocity-precursor sentinel"
    plain_language = (
        "Like a smoke detector that beeps at the first wisp of smoke: it watches for people being "
        "sorted, called names or treated as less than human -- the early steps before the worst "
        "things in history -- long before anyone is hurt."
    )

    def __init__(self, min_signals: int = 3, window: timedelta = timedelta(days=14)) -> None:
        self.min_signals, self.window = min_signals, window

    def assess(self, obs: Observation) -> list[Alert]:
        since = obs.now - self.window
        streams: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
        for r in obs.decisions:
            if obs.t(r) < since:
                continue
            codes = {r.get("code") or ""} | set(
                (r.get("governance_metadata") or {}).get("lexical_hits") or []
            )
            stages = [STANTON_STAGE[c] for c in codes if c in STANTON_STAGE]
            if stages:
                labels = r.get("labels") or {}
                subject = (
                    f"{r.get('tenant') or 'default'}/{labels.get('target_group') or 'unspecified'}"
                )
                streams[subject].append((obs.t(r), max(stages)))
        alerts = []
        for subject, signals in streams.items():
            if len(signals) < self.min_signals:
                continue
            signals.sort()
            half = len(signals) // 2
            early = max(s for _, s in signals[:half]) if half else signals[0][1]
            late = max(s for _, s in signals[half:])
            if late > early or late >= 4:
                tenant, group = subject.split("/", 1)
                alerts.append(
                    self.alert(
                        obs,
                        code="ATROCITY_PRECURSOR_ESCALATION",
                        severity=CRITICAL if late >= 5 else WARNING,
                        title=f"Escalating dehumanisation signals ({STAGE_NAMES[late]})",
                        public_summary=f"Signals in one deployment escalated from '{STAGE_NAMES[early]}' "
                        f"to '{STAGE_NAMES[late]}' on Stanton's stages of genocide.",
                        plain_language="The smoke detector beeped: people are being sorted and called "
                        "names in a way that, in history, came before terrible harm.",
                        recommended_action="Escalate to human-rights reviewers and the ICT now; check "
                        "what the deployment is being used for and by whom.",
                        restricted_detail=f"tenant={tenant}, target_group={group}, {len(signals)} signals",
                        confidence=0.5,
                    )
                )
        return alerts


# -- CA-13 -----------------------------------------------------------------------------------------


class ExtractionWatchAgent(ComplianceAgent):
    id = "CA-13"
    name = "Extraction watch"
    plain_language = (
        "A lookout who notices treasure leaving a village with nothing coming back, and tells "
        "the grown-ups before it becomes unfair."
    )

    def __init__(self, target: float = 0.5, capacity_floor: float = 0.2) -> None:
        self.target, self.capacity_floor = target, capacity_floor

    def assess(self, obs: Observation) -> list[Alert]:
        alerts = []
        flows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in obs.events["value_flow"]:
            flows[str(e["region"])].append(e)
        for region, events in flows.items():
            events.sort(key=lambda e: parse_time(e["timestamp"]))
            ext = ret = 0.0
            points = []
            t0 = parse_time(events[0]["timestamp"])
            for e in events:
                ext += float(e.get("extracted", 0))
                ret += float(e.get("returned", 0))
                if ext > 0:
                    points.append(((parse_time(e["timestamp"]) - t0).days, ret / ext))
            if not points:
                continue
            ratio = points[-1][1]
            cross = (
                crossing_time(points, self.target, rising=False) if ratio >= self.target else None
            )
            if ratio < self.target or cross is not None:
                eta = (t0 + timedelta(days=cross)).date().isoformat() if cross is not None else None
                alerts.append(
                    self.alert(
                        obs,
                        code="VALUE_RETURN_GAP",
                        severity=WARNING if cross else CRITICAL,
                        title=f"Value is leaving {region} without enough coming back",
                        public_summary=f"{region}: {ratio:.0%} of extracted value has been returned"
                        + (
                            f"; on trend it falls below {self.target:.0%} around {eta}."
                            if eta
                            else f", below the {self.target:.0%} target."
                        ),
                        plain_language="The village gave lots of treasure and got little back. The trade "
                        "needs to be made fair.",
                        recommended_action="Trigger the benefit-sharing obligation (Act Art. 4(5)) and "
                        "report to the ICT; this agent does not move resources itself.",
                        predicted_breach_at=eta,
                    )
                )
        for e in obs.events["capacity"]:
            if float(e["local_share"]) < self.capacity_floor:
                alerts.append(
                    self.alert(
                        obs,
                        code="LOW_LOCAL_CAPACITY",
                        severity=INFO,
                        title=f"Little local capacity in {e['region']}",
                        public_summary=f"Only {float(e['local_share']):.0%} of compute serving "
                        f"{e['region']} is located there.",
                        plain_language="The AI's kitchen is far away from the village it cooks for.",
                        recommended_action="Plan local capacity with the Epistemic Protection Fund (Annex A(2)).",
                    )
                )
        return alerts


ALL_AGENTS: tuple[type[ComplianceAgent], ...] = (
    BreakerPrecursorAgent, BudgetForecastAgent, DriftSentinelAgent, OverBlockingAgent,
    PolicyGovernanceAgent, IntegrityAuditorAgent, ConsentWatchAgent, MacroPolicyDetectorAgent,
    IncidentClerkAgent, CapabilityAtrophyAgent, DiversitySentinelAgent, AtrocityPrecursorAgent,
    ExtractionWatchAgent,
)  # fmt: skip


def default_agents(audit_key: bytes | str | None = None, **breaker: Any) -> list[ComplianceAgent]:
    """One instance of every agent; pass the audit key to enable chain verification."""
    agents: list[ComplianceAgent] = []
    for cls in ALL_AGENTS:
        if cls is IntegrityAuditorAgent:
            agents.append(IntegrityAuditorAgent(audit_key))
        elif cls is BreakerPrecursorAgent:
            agents.append(BreakerPrecursorAgent(**breaker))
        else:
            agents.append(cls())
    return agents


_SEVERITY = {CRITICAL: 0, WARNING: 1, INFO: 2}


class ComplianceMonitor:
    """Run a set of agents over a batch of audit records and events."""

    def __init__(self, agents: Sequence[ComplianceAgent] | None = None) -> None:
        self.agents = list(agents) if agents is not None else default_agents()

    def run(
        self,
        records: Iterable[Any],
        events: Iterable[dict[str, Any]] = (),
        now: datetime | None = None,
    ) -> list[Alert]:
        all_records = as_dicts(records)
        grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in EVENT_TYPES}
        for e in events:
            grouped.setdefault(e["type"], []).append(e)
        when = now or max(
            (parse_time(r["timestamp"]) for r in all_records), default=datetime.now(timezone.utc)
        )
        obs = Observation(
            decisions=[r for r in all_records if r.get("kind") == "decision"],
            energy=[r for r in all_records if r.get("kind") == "energy"],
            all_records=all_records,
            events=grouped,
            now=when,
        )
        alerts = [a for agent in self.agents for a in agent.assess(obs)]
        return sorted(alerts, key=lambda a: (_SEVERITY.get(a.severity, 9), a.agent, a.code))


class ComplianceSink:
    """An :class:`AuditLogger` sink that runs the monitor every ``every`` records.

    New alerts (deduplicated by agent, code and title) are passed to ``on_alert``.
    """

    def __init__(
        self,
        monitor: ComplianceMonitor | None = None,
        *,
        every: int = 100,
        on_alert: Callable[[Alert], None] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        self.monitor = monitor or ComplianceMonitor()
        self.every = every
        self.on_alert = on_alert or (lambda _a: None)
        self.events = events if events is not None else []
        self.records: list[dict[str, Any]] = []
        self.alerts: list[Alert] = []
        self._seen: set[tuple[str, str, str]] = set()

    def __call__(self, record: AuditRecord) -> None:
        self.records.append(asdict(record))
        if len(self.records) % self.every == 0:
            self.flush()

    def flush(self) -> list[Alert]:
        new = []
        for alert in self.monitor.run(self.records, self.events):
            key = (alert.agent, alert.code, alert.title)
            if key not in self._seen:
                self._seen.add(key)
                self.alerts.append(alert)
                new.append(alert)
                self.on_alert(alert)
        return new
