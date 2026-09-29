"""Doc lint: every review finding, KPI and agent is documented in both voices.

Each AR-, K- and CA- item has its own heading section containing technical text and a
🧒 plain-language line, and the documented IDs match the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from seed_first_guardrail.accountability import ALL_AGENTS, KPI_DEFINITIONS

DOCS = Path(__file__).resolve().parents[1] / "docs"
HEADING = re.compile(r"^(#{2,4})\s+(.*)$")


def sections(path: Path, pattern: str) -> dict[str, str]:
    """Map each ID found in a heading to the text of that heading's section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        ident = re.search(pattern, m.group(2))
        if not ident:
            continue
        level = len(m.group(1))
        body = []
        for nxt in lines[i + 1 :]:
            h = HEADING.match(nxt)
            if h and len(h.group(1)) <= level:
                break
            body.append(nxt)
        found[ident.group(0)] = "\n".join(body)
    return found


def expected_agent_ids() -> set[str]:
    return {cls.id for cls in ALL_AGENTS}


@pytest.mark.parametrize(
    ("doc", "pattern", "expected"),
    [
        ("adversarial_review.md", r"AR-\d{2}", {f"AR-{i:02d}" for i in range(1, 28)}),
        ("accountability_kpis.md", r"K-\d{2}", {d.id for d in KPI_DEFINITIONS}),
        ("compliance_agents.md", r"CA-\d{1,2}", None),
    ],
)
def test_every_item_has_both_voices(doc: str, pattern: str, expected: set[str] | None) -> None:
    found = sections(DOCS / doc, pattern)
    assert set(found) == (expected if expected is not None else expected_agent_ids())
    for ident, body in found.items():
        kid = [ln for ln in body.splitlines() if "🧒" in ln]
        technical = [ln for ln in body.splitlines() if ln.strip() and "🧒" not in ln]
        assert kid, f"{doc}: {ident} has no 🧒 plain-language line"
        assert technical, f"{doc}: {ident} has no technical text"


def test_scenario_doc_is_belief_neutral_and_covers_every_scenario() -> None:
    text = (DOCS / "scenario_gaming.md").read_text(encoding="utf-8")
    for sid in ("S-1", "S-2", "S-3", "S-4", "S-5", "S-6", "S-7"):
        assert f"### {sid} " in text
    assert "Belief neutrality" in text and "ICCPR Art. 18" in text
    assert text.count("🧒") >= 8


def test_act_has_the_new_provisions() -> None:
    act = (DOCS / "seed_first_ai_act.md").read_text(encoding="utf-8")
    for marker in (
        "**Moderated struggle.**",
        "**Restorative value flows.**",
        "**Public accountability dashboard and model scorecards.**",
        "**naming the model and its version**",
        "## Annex E",
        "## Change Log: v2 → v2.1",
    ):
        assert marker in act, marker
