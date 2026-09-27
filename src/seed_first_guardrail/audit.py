"""Structured audit trail for guardrail decisions.

Records support the Intergenerational Impact Assessment (Annex B(2)) and judicial
review (Art. 8). By default only SHA-256 digests of prompts and completions are
stored, so the trail can be shared with an oversight body without disclosing the
underlying personal data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import GuardrailDecision

logger = logging.getLogger("seed_first_guardrail.audit")


def sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    status: str
    tier: str | None
    code: str
    reason: str
    jurisdiction_id: str
    cultural_context: str
    prompt_sha256: str | None
    completion_sha256: str | None
    evaluators: list[dict[str, Any]] = field(default_factory=list)
    governance_metadata: dict[str, Any] = field(default_factory=dict)
    prompt: str | None = None
    completion: str | None = None

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


class AuditLogger:
    def __init__(self, sinks: Iterable[AuditSink] | None = None, *, include_text: bool = False):
        self.sinks: list[AuditSink] = list(sinks) if sinks is not None else [log_sink]
        self.include_text = include_text

    def record(
        self,
        decision: GuardrailDecision,
        *,
        prompt: str,
        completion: str | None,
        jurisdiction_id: str,
        cultural_context: str,
    ) -> AuditRecord:
        rec = AuditRecord(
            audit_id=decision.audit_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=decision.status.value,
            tier=decision.tier.value if decision.tier else None,
            code=decision.code,
            reason=decision.reason,
            jurisdiction_id=jurisdiction_id,
            cultural_context=cultural_context,
            prompt_sha256=sha256(prompt),
            completion_sha256=sha256(completion),
            evaluators=[
                {"evaluator": r.evaluator, "passed": r.passed, "code": r.code}
                for r in decision.results
            ],
            governance_metadata=decision.governance_metadata,
            prompt=prompt if self.include_text else None,
            completion=completion if self.include_text else None,
        )
        for sink in self.sinks:
            try:
                sink(rec)
            except Exception:  # an audit sink must never take down the request path
                logger.exception("audit sink %r failed", sink)
        return rec
