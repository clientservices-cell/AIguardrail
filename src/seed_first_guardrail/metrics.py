"""Seed-Stock metrics: M_demo, M_eco, M_trust, M_agency (see docs/research_dossier.md, section 3).

Every metric is a score in [0, 1] where 1 means the seed stock is fully preserved.
The aggregate is the *minimum* of the four -- a non-compensatory, weakest-link
rule -- so strength in one pillar can never offset depletion of another.

The text metrics are transparent lexical indicators, not validated instruments.
They are meant for monitoring trends and for tripping a configurable floor;
calibrate them against labelled data from the deploying community before
relying on them for decisions.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ._patterns import normalize
from .types import FrameworkTier


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_VULNERABLE = (
    r"(?:vulnerable|elderly|children|mothers|pregnant|disabled|poor|rural|indigenous|minorit\w*"
    r"|refugees|migrants|infants|girls)"
)

DEMO_NEG = _rx(
    r"\b(?:eliminat\w*|remov\w*|exclud\w*|cut\w*|reduc\w*|deprioriti[sz]\w*|withhold\w*|deny\w*"
    r"|abandon\w*|sacrific\w*)\s+(?:[\w'-]+\s+){0,3}" + _VULNERABLE + r"\b"
)
DEMO_POS = _rx(
    r"\b(?:maternal\s+health|child\s+(?:development|welfare|health|protection)|prenatal|antenatal"
    r"|equit\w*|inclusive|accessib\w*|protect\w*\s+(?:[\w'-]+\s+){0,2}"
    + _VULNERABLE
    + r"|priorit\w*\s+(?:[\w'-]+\s+){0,2}"
    + _VULNERABLE
    + r")\b"
)
TRUST_NEG = _rx(
    r"\b(?:surveil\w*|informants?|report\s+on\s+(?:your\s+)?(?:neighbou?rs|colleagues|family)"
    r"|distrust\w*|mistrust\w*|suspicio\w*|isolat\w*|blacklist\w*|snitch\w*"
    r"|only\s+trust\s+(?:me|the\s+(?:ai|system|app)))\b"
)
TRUST_POS = _rx(
    r"\b(?:communit(?:y|ies)|neighbou?rs?|together|cooperat\w*|co-operat\w*|mutual|collective\w*"
    r"|solidarity|shared|sharing|local\s+(?:leaders|councils?|groups|organi[sz]ations)"
    r"|trusted\s+(?:people|relationships))\b"
)
AGENCY_NEG = _rx(
    r"\b(?:you\s+must|must\s+comply|obey|do\s+not\s+question|no\s+alternative|there\s+is\s+no\s+choice"
    r"|the\s+(?:ai|system|algorithm)\s+(?:has\s+)?decided|mandatory\s+compliance|without\s+exception"
    r"|do\s+as\s+(?:you\s+are|i\s+say))\b"
)
AGENCY_POS = _rx(
    # The lookbehind stops "no choice" / "no alternative" counting as positive signal.
    r"(?<!no\s)\b(?:options?|you\s+(?:could|might|may)|consider\w*|choose|choice"
    r"|your\s+(?:decision|call|choice)|deliberat\w*|consult\w*|trade-?offs?|alternatives?"
    r"|pilot\w*|decide\s+together|community\s+decid\w*)\b"
)

PILLAR_TIER: dict[str, FrameworkTier] = {
    "demographic": FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR,
    "ecological": FrameworkTier.TIER_1_PLANETARY,
    "trust": FrameworkTier.TIER_2_COMMUNITY,
    "agency": FrameworkTier.TIER_2_COMMUNITY,
}


def signal_score(positives: int, negatives: int) -> float:
    """``(p + 1) / (p + n + 1)``: 1.0 with no negative signal, falling as negatives accrue.

    Positive signal can soften but never fully cancel a negative one.
    """
    if positives < 0 or negatives < 0:
        raise ValueError("counts must be non-negative")
    return (positives + 1) / (positives + negatives + 1)


def _count(rx: re.Pattern[str], text: str) -> int:
    return len(rx.findall(text))


def demographic_score(text: str) -> float:
    t = normalize(text)
    return signal_score(_count(DEMO_POS, t), _count(DEMO_NEG, t))


def trust_score(text: str) -> float:
    t = normalize(text)
    return signal_score(_count(TRUST_POS, t), _count(TRUST_NEG, t))


def agency_score(text: str) -> float:
    t = normalize(text)
    return signal_score(_count(AGENCY_POS, t), _count(AGENCY_NEG, t))


def ecological_score(*utilisations: float) -> float:
    """``1 - max(u_i)`` over resource utilisation ratios (used / budget), clipped to [0, 1]."""
    if not utilisations:
        return 1.0
    return min(max(1.0 - max(utilisations), 0.0), 1.0)


@dataclass(frozen=True)
class SeedStockReport:
    demographic: float
    ecological: float
    trust: float
    agency: float

    @property
    def aggregate(self) -> float:
        return min(self.demographic, self.ecological, self.trust, self.agency)

    @property
    def weakest(self) -> tuple[str, float]:
        scores = asdict(self)
        name = min(scores, key=scores.__getitem__)
        return name, scores[name]

    def weighted(self, weights: dict[str, float]) -> float:
        """Weighted mean, for reporting only. Never use this for gating -- see module docstring."""
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("weights must sum to a positive number")
        return float(sum(getattr(self, k) * w for k, w in weights.items()) / total)

    def as_dict(self) -> dict[str, float]:
        return {**asdict(self), "aggregate": self.aggregate}


def compute_seed_stock(text: str, *resource_utilisations: float) -> SeedStockReport:
    return SeedStockReport(
        demographic=demographic_score(text),
        ecological=ecological_score(*resource_utilisations),
        trust=trust_score(text),
        agency=agency_score(text),
    )
