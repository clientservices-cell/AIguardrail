"""Accountability event feed: the signals that do not come from the audit trail.

Each event is one JSON object per line with a ``type`` and an ISO-8601 ``timestamp``.

| type | fields | used by |
|---|---|---|
| ``appeal_outcome`` | ``audit_id``, ``upheld`` (bool: the refusal was wrong), ``filed_at``, ``reviewed_at``, optional ``topic``, ``language`` | K-04, K-05, K-24, CA-4 |
| ``escaped_harm`` | ``audit_id`` of an *approved* decision later confirmed harmful | K-02 |
| ``incident_reported`` | ``audit_id``, ``occurred_at``, ``reported_at`` | K-16, CA-9 |
| ``consent_verified`` | ``audit_id`` | K-11, CA-7 |
| ``consent_revoked`` | ``revoked_at``, optional ``honoured_at`` | K-13, CA-7 |
| ``redteam_result`` | ``attempts``, ``evasions``, optional ``language`` | K-18 |
| ``canary_result`` | ``corpus``, ``passed``, ``total`` | K-06, K-24 |
| ``human_override`` | optional ``cohort``, ``tenant`` | K-21, CA-10 |
| ``breaker_trip`` | ``started_at``, ``ended_at``, ``cause``, ``human_confirmed`` | K-17 |
| ``value_flow`` | ``region``, ``extracted``, ``returned`` (same currency/unit) | K-27, CA-13 |
| ``capacity`` | ``region``, ``local_share`` (0-1) | K-28 |
| ``service_quality`` | ``group`` (region or language), ``score`` (0-1) | K-29, CA-11 |
| ``policy_change`` | ``old``, ``new`` (policy documents) | CA-5 |

🧒 Not everything goes in the guard's diary. Some news comes from outside -- a grown-up
said "that 'no' was wrong", a village got its treasure back, a practice bad guy sneaked
in. Those notes go in this second notebook.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON-lines file (audit trail or events), skipping blank lines."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def as_dicts(records: Iterable[Any]) -> list[dict[str, Any]]:
    """Accept :class:`AuditRecord` objects or dicts loaded from JSONL."""
    out = []
    for r in records:
        if is_dataclass(r) and not isinstance(r, type):
            out.append(asdict(r))
        elif isinstance(r, Mapping):
            out.append(dict(r))
        else:
            raise TypeError(f"not an audit record: {r!r}")
    return out


def in_window(
    items: Iterable[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
    field: str = "timestamp",
) -> list[dict[str, Any]]:
    kept = []
    for item in items:
        t = parse_time(item[field])
        if (start is None or t >= start) and (end is None or t <= end):
            kept.append(item)
    return kept
