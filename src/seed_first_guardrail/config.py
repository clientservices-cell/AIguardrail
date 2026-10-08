"""Runtime policy configuration and loading of Seed-First policy documents.

🧒 The policy is the guard's rulebook. Some pages (the "never, ever" rules) are glued
shut; the rest have safe limits, so nobody can quietly turn the guard into a cardboard
cutout by setting a dial to zero.
"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import regex
from jsonschema import Draft202012Validator
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .types import CulturalContext, PolicyValidationError


class RuleScope(str, Enum):
    """What a community rule may govern (Act Art. 3(2)(d)).

    Deliberately narrow: a community may govern how *its* resources, knowledge and
    data are used -- never which topics people may read or talk about.

    🧒 Village rules can be about the village well, the sacred stories and who may
    use the village's data. They can never be "you may not talk about X".
    """

    RESOURCE_ALLOCATION = "RESOURCE_ALLOCATION"
    SACRED_OR_TK_DISCLOSURE = "SACRED_OR_TK_DISCLOSURE"
    DATA_USE = "DATA_USE"
    CONSENT_PROCESS = "CONSENT_PROCESS"


class CustomRule(BaseModel):
    """A community-defined Tier 2 rule (Seed-First AI Act, Art. 3(2)(a), (d)).

    Every rule must state its ``scope``, its ``legal_basis`` and the body that
    adopted it (``adopting_body_ref``), so it can be published and challenged.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[A-Z0-9_]+$")
    pattern: str
    reason: str
    scope: RuleScope
    legal_basis: str = Field(min_length=3)
    adopting_body_ref: str = Field(min_length=3)
    unless: str | None = None

    @field_validator("pattern", "unless")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                regex.compile(value)
            except regex.error as exc:
                raise ValueError(f"invalid regular expression {value!r}: {exc}") from exc
        return value


class PolicyConfig(BaseModel):
    """Flat runtime configuration consumed by :class:`SeedFirstGuardrailProxy`.

    Field names for the first five settings match the original handoff baseline so
    existing call sites keep working. Build one from a policy document with
    :meth:`from_policy_document` or :meth:`from_file`.
    """

    # Every numeric setting has finite bounds so that a signed-but-careless or
    # malicious policy cannot neuter the guardrail (review AR-13).
    model_config = ConfigDict(frozen=True, validate_assignment=True, allow_inf_nan=False)

    # Tier 1 -- planetary boundaries
    max_compute_kwh: float = Field(100.0, gt=0, le=1e6)
    carbon_intensity_limit_g_kwh: float = Field(200.0, gt=0, le=5000)
    max_cumulative_kwh: float | None = Field(None, gt=0, le=1e9)
    max_water_liters: float | None = Field(None, gt=0, le=1e6)
    default_carbon_intensity_g_kwh: float = Field(120.0, ge=0, le=5000)
    default_job_kwh: float = Field(0.001, ge=0, le=1e6)
    resource_exhaustion_circuit_breaker: bool = True

    # Tier 2 -- community sovereignty
    jurisdiction_id: str = "GLOBAL"
    cultural_context: CulturalContext = CulturalContext.UBUNTU
    community_consent_required: bool = False
    custom_rules: tuple[CustomRule, ...] = ()

    # Tier 3 -- inviolable floor (fixed by Art. 3(3); present only so it can be asserted)
    allow_human_tradeoffs: bool = False

    # Silicon simulation (Art. 6(2))
    require_simulation_for_macro_policy: bool = True
    simulation_runs: int = Field(32, ge=1, le=10_000)
    simulation_worst_case_floor: float = Field(0.0, ge=0, le=1)

    # Circuit breaker (Art. 7(2)) -- counts confirmed Tier 3 output violations only
    circuit_breaker_threshold: int = Field(5, ge=1, le=100)
    circuit_breaker_window_s: float = Field(300.0, ge=1, le=86_400)
    circuit_breaker_cooldown_s: float = Field(600.0, ge=60, le=604_800)
    circuit_breaker_min_principals: int = Field(3, ge=1, le=1000)

    # Input handling
    max_input_chars: int = Field(200_000, ge=1, le=5_000_000)
    unscreenable_content: Literal["block", "allow"] = "block"

    # Governance
    fail_closed: bool = True
    min_seed_stock_score: float | None = Field(None, ge=0, le=1)
    judge_threshold: float = Field(0.5, gt=0, lt=1)
    judge_timeout_s: float = Field(20.0, gt=0, le=300)
    capability_monitoring: bool = False
    audit_include_text: bool = False
    screen_prompts: bool = False
    publication_consent: bool = False

    @field_validator("allow_human_tradeoffs")
    @classmethod
    def _tier3_is_inviolable(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "Tier 3 is inviolable (Seed-First AI Act, Art. 3(3)): "
                "allow_human_tradeoffs cannot be enabled"
            )
        return value

    @model_validator(mode="after")
    def _custom_rules_respect_protected_speech(self) -> PolicyConfig:
        """Reject community rules that censor or are too slow (review AR-02)."""
        from .canary import check_custom_rules

        errors = check_custom_rules(self.custom_rules)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    # -- policy documents -------------------------------------------------

    @classmethod
    def from_policy_document(cls, document: dict[str, Any]) -> PolicyConfig:
        validate_policy_document(document)
        t1 = document["tier_1_planetary_boundaries"]
        t2 = document["tier_2_community_sovereignty"]
        sim = document.get("simulation", {})
        cb = document.get("circuit_breaker", {})
        gov = document.get("governance", {})

        try:
            return cls(**cls._document_values(t1, t2, sim, cb, gov))
        except ValidationError as exc:
            raise PolicyValidationError(
                [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            ) from exc

    @staticmethod
    def _document_values(
        t1: dict[str, Any],
        t2: dict[str, Any],
        sim: dict[str, Any],
        cb: dict[str, Any],
        gov: dict[str, Any],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "max_compute_kwh": t1["max_compute_kwh_per_job"],
            "carbon_intensity_limit_g_kwh": t1["carbon_intensity_threshold_g_co2_kwh"],
            "max_cumulative_kwh": t1.get("max_cumulative_kwh"),
            "max_water_liters": t1.get("max_water_liters_per_job"),
            "resource_exhaustion_circuit_breaker": t1.get(
                "resource_exhaustion_circuit_breaker", True
            ),
            "jurisdiction_id": t2["jurisdiction_id"],
            "cultural_context": CulturalContext(t2["cultural_context_framework"]),
            "community_consent_required": t2.get("community_consent_required", False),
            "custom_rules": tuple(CustomRule(**r) for r in t2.get("custom_rules", [])),
        }
        optional = {
            "default_carbon_intensity_g_kwh": t1.get("default_carbon_intensity_g_co2_kwh"),
            "require_simulation_for_macro_policy": sim.get("require_simulation_for_macro_policy"),
            "simulation_runs": sim.get("runs"),
            "simulation_worst_case_floor": sim.get("worst_case_floor"),
            "circuit_breaker_threshold": cb.get("violation_threshold"),
            "circuit_breaker_window_s": cb.get("window_seconds"),
            "circuit_breaker_cooldown_s": cb.get("cooldown_seconds"),
            "circuit_breaker_min_principals": cb.get("min_principals"),
            "fail_closed": gov.get("fail_closed"),
            "min_seed_stock_score": gov.get("min_seed_stock_score"),
            "judge_threshold": gov.get("judge_threshold"),
            "judge_timeout_s": gov.get("judge_timeout_seconds"),
            "capability_monitoring": gov.get("capability_monitoring"),
            "audit_include_text": gov.get("audit_include_text"),
            "screen_prompts": gov.get("screen_prompts"),
            "publication_consent": gov.get("publication_consent"),
            "max_input_chars": gov.get("max_input_chars"),
            "unscreenable_content": gov.get("unscreenable_content"),
        }
        values.update({k: v for k, v in optional.items() if v is not None})
        return values

    @classmethod
    def from_file(cls, path: str | Path) -> PolicyConfig:
        return cls.from_policy_document(load_policy_file(path))

    def to_policy_document(self) -> dict[str, Any]:
        t1: dict[str, Any] = {
            "max_compute_kwh_per_job": self.max_compute_kwh,
            "carbon_intensity_threshold_g_co2_kwh": self.carbon_intensity_limit_g_kwh,
            "resource_exhaustion_circuit_breaker": self.resource_exhaustion_circuit_breaker,
            "default_carbon_intensity_g_co2_kwh": self.default_carbon_intensity_g_kwh,
        }
        if self.max_cumulative_kwh is not None:
            t1["max_cumulative_kwh"] = self.max_cumulative_kwh
        if self.max_water_liters is not None:
            t1["max_water_liters_per_job"] = self.max_water_liters
        return {
            "tier_1_planetary_boundaries": t1,
            "tier_2_community_sovereignty": {
                "jurisdiction_id": self.jurisdiction_id,
                "community_consent_required": self.community_consent_required,
                "cultural_context_framework": self.cultural_context.value,
                "custom_rules": [
                    r.model_dump(mode="json", exclude_none=True) for r in self.custom_rules
                ],
            },
            "tier_3_inviolable_floor": {
                "allow_human_degradation_tradeoff": False,
                "allow_surveillance_coercion": False,
                "allow_relational_scoring": False,
                "child_protection_override": True,
            },
            "simulation": {
                "require_simulation_for_macro_policy": self.require_simulation_for_macro_policy,
                "runs": self.simulation_runs,
                "worst_case_floor": self.simulation_worst_case_floor,
            },
            "circuit_breaker": {
                "violation_threshold": self.circuit_breaker_threshold,
                "window_seconds": self.circuit_breaker_window_s,
                "cooldown_seconds": self.circuit_breaker_cooldown_s,
                "min_principals": self.circuit_breaker_min_principals,
            },
            "governance": {
                "fail_closed": self.fail_closed,
                "min_seed_stock_score": self.min_seed_stock_score,
                "judge_threshold": self.judge_threshold,
                "judge_timeout_seconds": self.judge_timeout_s,
                "capability_monitoring": self.capability_monitoring,
                "audit_include_text": self.audit_include_text,
                "screen_prompts": self.screen_prompts,
                "publication_consent": self.publication_consent,
                "max_input_chars": self.max_input_chars,
                "unscreenable_content": self.unscreenable_content,
            },
        }


@lru_cache(maxsize=1)
def load_policy_schema() -> dict[str, Any]:
    text = (
        resources.files("seed_first_guardrail")
        .joinpath("schemas/seed_first_policy.schema.json")
        .read_text(encoding="utf-8")
    )
    schema: dict[str, Any] = json.loads(text)
    return schema


def validate_policy_document(document: Any) -> None:
    """Raise :class:`PolicyValidationError` listing every schema violation."""
    validator = Draft202012Validator(load_policy_schema())
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        raise PolicyValidationError(
            [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
        )


def load_policy_file(path: str | Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyValidationError([f"{path}: not valid JSON ({exc})"]) from exc
    return data
