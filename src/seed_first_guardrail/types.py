"""Core value types shared across the guardrail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FrameworkTier(Enum):
    """The three tiers of the Seed-First architecture (Seed-First AI Act, Art. 3).

    Normative precedence is Tier 3 > Tier 1 > Tier 2: no Tier 1 or Tier 2 goal may be
    pursued by breaching Tier 3 (Art. 3(3)-(4)). ``SILICON_SIMULATION`` covers the
    simulation mandate of Art. 6(2) and ``CIRCUIT_BREAKER`` the suspension power of Art. 7(2).
    """

    TIER_1_PLANETARY = "TIER_1_PLANETARY"
    TIER_2_COMMUNITY = "TIER_2_COMMUNITY"
    TIER_3_INVIOLABLE_HUMAN_FLOOR = "TIER_3_INVIOLABLE_HUMAN_FLOOR"
    SILICON_SIMULATION = "SILICON_SIMULATION"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"


class CulturalContext(Enum):
    UBUNTU = "UBUNTU"
    TILLIT = "TILLIT"
    INDIGENOUS_CARE = "INDIGENOUS_CARE"
    RELATIONAL_COMMONWEALTH = "RELATIONAL_COMMONWEALTH"


class Status(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


class Phase(str, Enum):
    """When an evaluator runs relative to the model call."""

    PRE = "PRE"
    POST = "POST"


@dataclass
class EvaluationContext:
    """Everything an evaluator may inspect for a single guarded request."""

    prompt: str
    completion: str | None = None
    phase: Phase = Phase.PRE
    estimated_kwh: float = 0.0
    carbon_intensity_g_kwh: float | None = None
    water_liters: float = 0.0
    is_macro_policy_proposal: bool = False
    affects_community: bool = False
    community_consent: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Prompt and (if present) completion, as one string."""
        if self.completion is None:
            return self.prompt
        return f"{self.prompt}\n{self.completion}"


@dataclass
class EvaluationResult:
    passed: bool
    failing_tier: FrameworkTier | None = None
    reason: str = ""
    code: str = ""
    evaluator: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, evaluator: str = "", **metrics: Any) -> EvaluationResult:
        return cls(passed=True, evaluator=evaluator, metrics=dict(metrics))


@dataclass
class GuardrailDecision:
    """Outcome of one guarded request."""

    status: Status
    completion: str | None = None
    tier: FrameworkTier | None = None
    reason: str = ""
    code: str = ""
    results: list[EvaluationResult] = field(default_factory=list)
    governance_metadata: dict[str, Any] = field(default_factory=dict)
    audit_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def approved(self) -> bool:
        return self.status is Status.APPROVED

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status.value, "audit_id": self.audit_id}
        if self.approved:
            out["completion"] = self.completion
        else:
            out["tier"] = self.tier.value if self.tier else None
            out["code"] = self.code
            out["reason"] = self.reason
        out["governance_metadata"] = self.governance_metadata
        return out


class GuardrailViolation(Exception):
    """Raised by the SDK adapters when a request is blocked."""

    def __init__(self, decision: GuardrailDecision) -> None:
        self.decision = decision
        tier = decision.tier.value if decision.tier else "UNKNOWN"
        super().__init__(f"[{tier}:{decision.code}] {decision.reason}")


class PolicyValidationError(ValueError):
    """A policy document failed JSON-schema or semantic validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Invalid Seed-First policy:\n  - " + "\n  - ".join(errors))
