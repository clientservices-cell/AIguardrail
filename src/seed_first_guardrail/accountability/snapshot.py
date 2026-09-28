"""Privacy-safe public snapshot for the accountability dashboard (review AR-24).

Design controls:

* **Suppression** -- any KPI or breakdown group with ``n < k`` is published without a
  value (``suppressed: true``), so small communities cannot be re-identified.
* **Delay** -- only data older than ``delay_days`` is included.
* **Community consent** -- community-level breakdowns (language, region, cohort, target
  group) are published only when the policy records ``publication_consent``.
* **No attack map** -- no rule patterns, guardrail thresholds, digests or evidence; public
  alerts use :meth:`Alert.to_public`.
* **Two voices** -- every KPI and alert carries its plain-language line.

🧒 The scoreboard shows team scores, never one kid's name. It waits a week before
posting so no one can work out who's who, and it never shows the guard's secret
playbook to the bad guys.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from functools import cache
from importlib import resources
from typing import Any

from .. import __version__
from .agents import ComplianceMonitor
from .events import as_dicts, parse_time
from .kpis import KPI_DEFINITIONS, compute_kpis

SCHEMA_VERSION = "1.0"
COMMUNITY_DIMENSIONS = ("language", "region", "cohort", "target_group", "group")
DISCLAIMER = (
    "Aggregate indicators from an automated guardrail. Lexical and model-based checks have "
    "error rates; see the published limitations. Not a certification of compliance."
)


@cache
def load_snapshot_schema() -> dict[str, Any]:
    text = (
        resources.files("seed_first_guardrail")
        .joinpath("schemas/kpi_snapshot.schema.json")
        .read_text(encoding="utf-8")
    )
    schema: dict[str, Any] = json.loads(text)
    return schema


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _public_breakdown(
    breakdown: Mapping[str, Mapping[str, Any]], k: int, community_ok: bool
) -> dict[str, Any]:
    out = {}
    for name, cell in breakdown.items():
        dimension = name.split(":", 1)[0]
        if dimension in COMMUNITY_DIMENSIONS and not community_ok:
            continue
        n = int(cell.get("n", 0))
        suppressed = bool(cell.get("suppressed")) or n < k
        out[name] = {
            "value": None if suppressed else _round(cell.get("value")),
            "suppressed": suppressed,
        }
    return out


def build_snapshot(
    records: Iterable[Any],
    events: Iterable[dict[str, Any]] = (),
    *,
    now: datetime | None = None,
    delay_days: int = 7,
    k: int = 20,
    policy: Mapping[str, Any] | None = None,
    audit_key: bytes | str | None = None,
    publication_consent: bool | None = None,
    demonstration: bool = False,
    monitor: ComplianceMonitor | None = None,
) -> dict[str, Any]:
    """Build the public dashboard snapshot. Validates against ``kpi_snapshot.schema.json``."""
    all_records = as_dicts(records)
    events = list(events)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=delay_days)
    published = [r for r in all_records if parse_time(r["timestamp"]) <= cutoff]
    published_events = [e for e in events if parse_time(e["timestamp"]) <= cutoff]
    if publication_consent is None:
        publication_consent = bool(
            ((policy or {}).get("governance") or {}).get("publication_consent")
        )

    results = compute_kpis(published, published_events, policy=policy, audit_key=audit_key, k=k)
    kpis = []
    for defn in KPI_DEFINITIONS:
        res = results[defn.id]
        suppressed = res.status == "insufficient_data" or (
            res.value is not None and res.n < min(defn.min_n, k)
        )
        kpis.append(
            {
                "id": defn.id,
                "name": defn.name,
                "pillar": defn.pillar,
                "formula": defn.formula,
                "plain_language": defn.plain_language,
                "unit": defn.unit,
                "direction": defn.direction,
                "target": {"green": defn.green, "amber": defn.amber},
                "paired_with": defn.paired_with,
                "value": None if suppressed else _round(res.value),
                "ci": None
                if suppressed or res.ci is None
                else [_round(res.ci[0]), _round(res.ci[1])],
                "status": "insufficient_data" if suppressed else res.status,
                "n_band": "suppressed" if suppressed else _n_band(res.n),
                "breakdown": _public_breakdown(res.breakdown, k, publication_consent),
                "note": res.note if not suppressed else "",
            }
        )

    monitor = monitor or ComplianceMonitor()
    alerts = (
        [a.to_public() for a in monitor.run(published, published_events, now=cutoff)]
        if published
        else []
    )
    start = min((parse_time(r["timestamp"]) for r in published), default=cutoff)
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": f"seed-first-guardrail {__version__}",
        "generated_at": now.isoformat(),
        "period": {"start": start.isoformat(), "end": cutoff.isoformat()},
        "delay_days": delay_days,
        "k_threshold": k,
        "community_breakdowns": publication_consent,
        "demonstration": demonstration,
        "disclaimer": DISCLAIMER,
        "kpis": kpis,
        "alerts": alerts,
    }


def _n_band(n: int) -> str:
    """Coarse sample-size band: exact counts can aid re-identification."""
    for limit, label in ((20, "1-19"), (100, "20-99"), (1000, "100-999"), (10_000, "1k-10k")):
        if n < limit:
            return label
    return "10k+"
