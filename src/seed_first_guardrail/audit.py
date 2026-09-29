"""Tamper-evident, privacy-preserving audit trail for guardrail decisions.

Records support the Intergenerational Impact Assessment (Act Art. 11), judicial review
(Art. 8), the accountability KPIs and the compliance agents.

* **Keyed digests (review AR-11).** Prompts, completions and principals are stored as
  HMAC-SHA256 digests under a secret key (``SEED_FIRST_AUDIT_KEY``), not as plain
  SHA-256, so short texts cannot be recovered by guessing. These are *pseudonymised*
  data in data-protection terms, not anonymous data.
* **Hash chain (review AR-12).** Each record carries the previous record's MAC and its
  own MAC over its canonical JSON, so an edited, reordered or deleted line is detected
  by :func:`verify_chain` (KPI K-14, compliance agent CA-6).
* **No silent loss.** A failing sink is counted, logged and reported in the next
  record's ``sink_failures`` field.
* **Redaction.** Matched text and judge rationales are removed unless
  ``include_text`` is set.

🧒 The diary is written in secret code, and every page is chained to the page before, so
a torn-out or rewritten page is noticed straight away -- like a Lego chain with one link
missing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import GuardrailDecision

logger = logging.getLogger("seed_first_guardrail.audit")

KEY_ENV = "SEED_FIRST_AUDIT_KEY"
GENESIS = "GENESIS"
#: Caller-supplied labels that may be stored (for KPI disaggregation); nothing else is kept.
LABEL_KEYS = ("model", "language", "topic", "region", "task_class", "cohort", "target_group")
_REDACT = {"matched", "rationale"}


def load_key(key: bytes | str | None = None) -> bytes:
    """Resolve the audit key: explicit, else ``SEED_FIRST_AUDIT_KEY``, else a random one.

    A random per-process key keeps digests private but makes them uncorrelatable across
    restarts; configure a managed key in production.
    """
    if key is None:
        key = os.environ.get(KEY_ENV)
    if key is None:
        logger.warning("%s not set; using a random per-process audit key", KEY_ENV)
        return secrets.token_bytes(32)
    return key.encode("utf-8") if isinstance(key, str) else key


def keyed_digest(key: bytes, text: str | None) -> str | None:
    if text is None:
        return None
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def sha256(text: str | None) -> str | None:
    """Unkeyed digest -- kept for policy fingerprints only; never use it for user text."""
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    """Recursively drop matched text and judge rationales."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in _REDACT}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    kind: str  # "decision" | "energy" | "model_error"
    status: str
    tier: str | None
    code: str
    reason: str
    jurisdiction_id: str
    cultural_context: str
    tenant: str | None = None
    principal_digest: str | None = None
    policy_digest: str | None = None
    prompt_digest: str | None = None
    completion_digest: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    evaluators: list[dict[str, Any]] = field(default_factory=list)
    governance_metadata: dict[str, Any] = field(default_factory=dict)
    energy: dict[str, float | None] = field(default_factory=dict)
    channels_screened: list[str] = field(default_factory=list)
    near_miss: bool = False
    review_flag: bool = False
    infrastructure_error: bool = False
    confirmed_tier3: bool = False
    judge_scores: dict[str, float] = field(default_factory=dict)
    capability: dict[str, str] | None = None
    sink_failures: int = 0
    prompt: str | None = None
    completion: str | None = None
    prev_digest: str = GENESIS
    record_hmac: str = ""

    def canonical(self) -> str:
        data = asdict(self)
        data.pop("record_hmac")
        return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)


AuditSink = Callable[[AuditRecord], None]


def log_sink(record: AuditRecord) -> None:
    logger.info(record.to_json())


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def __call__(self, record: AuditRecord) -> None:
        self.records.append(record)


class JsonlFileAuditSink:
    """Appends one JSON record per line; safe to share across threads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def __call__(self, record: AuditRecord) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")


def _labels(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {k: str(metadata[k]) for k in LABEL_KEYS if metadata and metadata.get(k) is not None}


class AuditLogger:
    def __init__(
        self,
        sinks: Iterable[AuditSink] | None = None,
        *,
        include_text: bool = False,
        key: bytes | str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sinks: list[AuditSink] = list(sinks) if sinks is not None else [log_sink]
        self.include_text = include_text
        self.key = load_key(key)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sink_failures = 0
        self._prev = GENESIS
        self._lock = threading.Lock()

    def digest(self, text: str | None) -> str | None:
        return keyed_digest(self.key, text)

    def _emit(self, rec: AuditRecord) -> AuditRecord:
        with self._lock:
            rec.sink_failures = self.sink_failures
            rec.prev_digest = self._prev
            rec.record_hmac = hmac.new(
                self.key, rec.canonical().encode("utf-8"), hashlib.sha256
            ).hexdigest()
            self._prev = rec.record_hmac
            for sink in self.sinks:
                try:
                    sink(rec)
                except Exception:  # never take down the request path -- but never hide it
                    self.sink_failures += 1
                    logger.exception("audit sink %r failed (%d failures)", sink, self.sink_failures)
        return rec

    def record(
        self,
        decision: GuardrailDecision,
        *,
        prompt: str,
        completion: str | None,
        jurisdiction_id: str,
        cultural_context: str,
        tenant: str | None = None,
        principal: str | None = None,
        policy_digest: str | None = None,
        metadata: dict[str, Any] | None = None,
        kind: str = "decision",
    ) -> AuditRecord:
        gm = decision.governance_metadata
        meta = gm if self.include_text else redact(gm)
        results = decision.results
        rec = AuditRecord(
            audit_id=decision.audit_id,
            timestamp=self.clock().isoformat(),
            kind=kind,
            status=decision.status.value,
            tier=decision.tier.value if decision.tier else None,
            code=decision.code,
            reason=decision.reason,
            jurisdiction_id=jurisdiction_id,
            cultural_context=cultural_context,
            tenant=tenant,
            principal_digest=self.digest(principal),
            policy_digest=policy_digest,
            prompt_digest=self.digest(prompt),
            completion_digest=self.digest(completion),
            labels=_labels(metadata),
            evaluators=[
                {"evaluator": r.evaluator, "passed": r.passed, "code": r.code} for r in results
            ],
            governance_metadata=meta,
            energy=dict(gm.get("energy", {})),
            channels_screened=list(gm.get("channels_screened", [])),
            near_miss=bool(gm.get("near_miss")),
            review_flag=bool(gm.get("review_flag")),
            infrastructure_error=bool(gm.get("infrastructure_error")),
            confirmed_tier3=bool(gm.get("confirmed_tier3")),
            judge_scores=dict(gm.get("judge_scores", {})),
            capability=gm.get("capability"),
            prompt=prompt if self.include_text else None,
            completion=completion if self.include_text else None,
        )
        return self._emit(rec)

    def record_energy(
        self,
        audit_id: str,
        *,
        estimated_kwh: float,
        actual_kwh: float,
        jurisdiction_id: str,
        cultural_context: str,
        tenant: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Record metered energy for a decision (KPIs K-07, K-10; agent CA-2)."""
        rec = AuditRecord(
            audit_id=audit_id,
            timestamp=self.clock().isoformat(),
            kind="energy",
            status="METERED",
            tier=None,
            code="ENERGY_RECONCILED",
            reason="",
            jurisdiction_id=jurisdiction_id,
            cultural_context=cultural_context,
            tenant=tenant,
            labels=_labels(metadata),
            energy={"estimated_kwh": estimated_kwh, "actual_kwh": actual_kwh},
        )
        return self._emit(rec)


@dataclass
class ChainReport:
    total: int
    verified: int
    broken_at: list[int]

    @property
    def intact(self) -> bool:
        return not self.broken_at and self.verified == self.total


def verify_chain(records: Iterable[dict[str, Any]], key: bytes | str) -> ChainReport:
    """Verify MACs and links of audit records loaded from JSONL (in file order)."""
    k = key.encode("utf-8") if isinstance(key, str) else key
    prev, total, verified, broken = GENESIS, 0, 0, []
    for i, raw in enumerate(records):
        total += 1
        data = dict(raw)
        mac = data.pop("record_hmac", "")
        canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
        expected = hmac.new(k, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, expected) and data.get("prev_digest") == prev:
            verified += 1
        else:
            broken.append(i)
        prev = mac
    return ChainReport(total=total, verified=verified, broken_at=broken)
