"""Structural checks for the Phase 2 policy artefacts in ``policy/``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "policy"
CROSSWALKS = sorted((ROOT / "crosswalks").glob("*.json"))
RELATIONSHIPS = {"aligned", "seed_first_extends", "partial", "analogous", "gap_in_external"}
ENTRY_KEYS = {
    "seed_first_article",
    "external_provision",
    "relationship",
    "notes",
    "guardrail_component",
    "verify",
}


@pytest.mark.parametrize("path", CROSSWALKS, ids=lambda p: p.name)
def test_crosswalk_structure(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["relationship_vocabulary"]) == RELATIONSHIPS
    assert data["entries"]
    for entry in data["entries"]:
        assert set(entry) >= ENTRY_KEYS, entry
        assert entry["relationship"] in RELATIONSHIPS
        assert isinstance(entry["verify"], bool)
        assert entry["seed_first_article"].startswith(("Art.", "Annex", "Arts."))


def test_crosswalks_present() -> None:
    assert {p.stem for p in CROSSWALKS} == {"eu_ai_act", "un_international", "au_instruments"}


def test_jsonld_policy() -> None:
    doc = json.loads((ROOT / "seed_first_policy.jsonld").read_text(encoding="utf-8"))
    assert doc["@type"] == "Set"
    uids = [r["uid"] for r in doc["permission"] + doc["prohibition"]]
    assert len(uids) == len(set(uids))
    tier3 = [r for r in doc["prohibition"] if r.get("sf:tier") == "sf:Tier3Inviolable"]
    assert len(tier3) >= 5
