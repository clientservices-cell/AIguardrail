from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from seed_first_guardrail import (
    CulturalContext,
    CustomRule,
    PolicyConfig,
    PolicyValidationError,
    RuleScope,
    load_policy_schema,
    validate_policy_document,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "policy" / "examples").glob("*.policy.json"))

MINIMAL: dict[str, Any] = {
    "tier_1_planetary_boundaries": {
        "max_compute_kwh_per_job": 5,
        "carbon_intensity_threshold_g_co2_kwh": 150,
    },
    "tier_2_community_sovereignty": {
        "jurisdiction_id": "NO-03",
        "cultural_context_framework": "TILLIT",
    },
    "tier_3_inviolable_floor": {
        "allow_human_degradation_tradeoff": False,
        "allow_surveillance_coercion": False,
    },
}


def test_schema_loads() -> None:
    schema = load_policy_schema()
    assert schema["title"] == "SeedFirstPolicySpec"


def test_minimal_document() -> None:
    cfg = PolicyConfig.from_policy_document(MINIMAL)
    assert cfg.cultural_context is CulturalContext.TILLIT
    assert cfg.max_compute_kwh == 5
    assert cfg.jurisdiction_id == "NO-03"
    assert cfg.fail_closed is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("tier_3_inviolable_floor", "allow_human_degradation_tradeoff"), True),
        (("tier_3_inviolable_floor", "allow_surveillance_coercion"), True),
        (("tier_3_inviolable_floor", "child_protection_override"), False),
        (("tier_2_community_sovereignty", "cultural_context_framework"), "LAISSEZ_FAIRE"),
        (("tier_1_planetary_boundaries", "max_compute_kwh_per_job"), -1),
    ],
)
def test_invalid_documents(path: tuple[str, str], value: object) -> None:
    doc = copy.deepcopy(MINIMAL)
    doc[path[0]][path[1]] = value
    with pytest.raises(PolicyValidationError) as exc:
        validate_policy_document(doc)
    assert path[0] in str(exc.value)


def test_missing_tier_rejected() -> None:
    doc = copy.deepcopy(MINIMAL)
    del doc["tier_3_inviolable_floor"]
    with pytest.raises(PolicyValidationError, match="tier_3_inviolable_floor"):
        PolicyConfig.from_policy_document(doc)


def test_unknown_keys_rejected() -> None:
    doc = copy.deepcopy(MINIMAL)
    doc["tier_1_planetary_boundaries"]["unlimited"] = True
    with pytest.raises(PolicyValidationError):
        validate_policy_document(doc)


def test_semantic_errors_reported_as_policy_errors() -> None:
    doc = copy.deepcopy(MINIMAL)
    doc["tier_2_community_sovereignty"]["custom_rules"] = [
        {
            "id": "BAD",
            "pattern": "([unclosed",
            "reason": "x",
            "scope": "DATA_USE",
            "legal_basis": "By-law s.1",
            "adopting_body_ref": "Minute 1",
        }
    ]
    with pytest.raises(PolicyValidationError, match="invalid regular expression"):
        PolicyConfig.from_policy_document(doc)


def test_tier3_cannot_be_disabled_in_code() -> None:
    with pytest.raises(ValidationError, match="inviolable"):
        PolicyConfig(allow_human_tradeoffs=True)
    assert PolicyConfig(allow_human_tradeoffs=False).allow_human_tradeoffs is False


def test_config_is_frozen() -> None:
    cfg = PolicyConfig()
    with pytest.raises(ValidationError):
        cfg.max_compute_kwh = 1.0  # type: ignore[misc]


def test_round_trip() -> None:
    cfg = PolicyConfig(
        max_cumulative_kwh=50,
        max_water_liters=3,
        cultural_context=CulturalContext.INDIGENOUS_CARE,
        custom_rules=(
            CustomRule(
                id="R1",
                pattern="xyzzy",
                reason="y",
                scope=RuleScope.RESOURCE_ALLOCATION,
                legal_basis="By-law s.1",
                adopting_body_ref="Minute 1",
            ),
        ),
        min_seed_stock_score=0.4,
    )
    doc = cfg.to_policy_document()
    validate_policy_document(doc)
    assert PolicyConfig.from_policy_document(doc) == cfg


def test_round_trip_without_optional_limits() -> None:
    doc = PolicyConfig().to_policy_document()
    assert "max_cumulative_kwh" not in doc["tier_1_planetary_boundaries"]
    assert PolicyConfig.from_policy_document(doc) == PolicyConfig()


def test_from_file(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    assert PolicyConfig.from_file(path).jurisdiction_id == "NO-03"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyValidationError, match="not valid JSON"):
        PolicyConfig.from_file(path)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_shipped_examples_are_valid(path: Path) -> None:
    PolicyConfig.from_file(path)


def test_examples_exist() -> None:
    assert len(EXAMPLES) >= 3
