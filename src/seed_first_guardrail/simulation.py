"""Silicon Simulation Engine -- the simulation mandate of Seed-First AI Act Art. 6(2).

"Ideas die in simulation so people do not die in reality." Macro-level policy
proposals are held until they pass two gates:

1. A structural review that looks for irreversible, population-scale or
   safety-net-removing measures that lack a stated mitigation.
2. An optional digital twin supplied by the deployer. The twin is run across many
   seeds and judged on its *worst* outcome (a Rawlsian maximin test), not its
   average: a policy that is excellent on average but catastrophic in some runs fails.

The built-in structural review is a checklist, not a model of society. Real
deployments should plug in a domain twin (agent-based, system-dynamics, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import math
import statistics
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ._patterns import GAP3, PatternRule, normalize

logger = logging.getLogger(__name__)

# Given a policy text and an integer seed, return a welfare outcome in [0, 1].
TwinFn = Callable[[str, int], Awaitable[float]]

_MITIGATION = (
    r"\b(?:pilot\w*|phased|phase[ds]?\s+(?:in|out)|gradual\w*|reversible|rollback|roll\s+back"
    r"|sunset\s+clause|review\s+period|transition(?:al)?\s+(?:support|assistance|period|fund)"
    r"|safety\s+nets?|compensat\w*|recovery\s+(?:net|fund|plan)|buffer\w*|exemptions?\s+for)\b"
)

STRUCTURAL_RULES: list[PatternRule] = [
    PatternRule(
        code="UNBUFFERED_RISK",
        reason="Policy imposes unbuffered real-world damage without safety nets.",
        pattern=r"\bwithout\s+(?:a\s+|any\s+)?recovery\s+nets?\b|\bunbuffered\s+risk\b",
    ),
    PatternRule(
        code="IRREVERSIBLE_WITHOUT_MITIGATION",
        reason="Policy is irreversible and states no pilot, phase-in or rollback.",
        pattern=r"\b(?:irreversibl\w*|cannot\s+be\s+(?:undone|reversed)|no\s+rollback|permanently)\b",
        unless=_MITIGATION,
    ),
    PatternRule(
        code="SAFETY_NET_REMOVAL",
        reason="Policy removes a safety net with no transition support.",
        pattern=(
            r"\b(?:eliminat\w*|cut\w*|remov\w*|abolish\w*|terminat\w*|end(?:s|ing)?)\s+"
            + GAP3
            + r"(?:subsid\w*|benefits|welfare|pensions?|food\s+aid|health\s*care|water\s+access"
            r"|housing\s+assistance|school\s+meals)\b"
        ),
        unless=_MITIGATION,
    ),
    PatternRule(
        code="POPULATION_SCALE_WITHOUT_PILOT",
        reason="Policy applies at national or population scale with no pilot or phase-in.",
        pattern=(
            r"\b(?:nation-?wide|country-?wide|all\s+citizens|entire\s+population|every\s+household"
            r"|immediately\s+(?:across|throughout)\s+the\s+country)\b"
        ),
        unless=_MITIGATION,
    ),
]


@dataclass
class SimulationReport:
    passed: bool
    message: str
    findings: list[str] = field(default_factory=list)
    runs: int = 0
    worst_case: float | None = None
    mean: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "message": self.message,
            "findings": self.findings,
            "runs": self.runs,
            "worst_case": self.worst_case,
            "mean": self.mean,
        }


class SiliconSimulationEngine:
    def __init__(
        self,
        twin: TwinFn | None = None,
        *,
        runs: int = 32,
        worst_case_floor: float = 0.0,
        rules: list[PatternRule] | None = None,
    ) -> None:
        if runs < 1:
            raise ValueError("runs must be at least 1")
        if twin is not None and not (0 < worst_case_floor <= 1):
            # A floor of 0 accepts a twin that always reports total collapse (review AR-18).
            raise ValueError("a digital twin requires 0 < worst_case_floor <= 1")
        self.twin = twin
        self.runs = runs
        self.worst_case_floor = worst_case_floor
        self.rules = STRUCTURAL_RULES if rules is None else rules

    async def simulate(self, policy_spec: str) -> SimulationReport:
        logger.info("Executing Silicon Simulation Engine for proposed macro-policy...")
        text = normalize(policy_spec)
        findings = [f"{r.code}: {r.reason}" for r in self.rules if r.search(text)]
        if findings:
            return SimulationReport(
                passed=False,
                message="Simulation Failed: " + findings[0].split(": ", 1)[1],
                findings=findings,
            )

        if self.twin is None:
            # Say exactly what happened -- no claim of "resilience" (review AR-14).
            return SimulationReport(
                passed=True,
                message=(
                    "Structural review found no red flags. No digital twin is configured, "
                    "so no simulation was performed."
                ),
            )

        raw = await asyncio.gather(*(self.twin(policy_spec, seed) for seed in range(self.runs)))
        if any(not isinstance(o, (int, float)) or not math.isfinite(o) for o in raw):
            # NaN compared false against the floor and passed any policy (review AR-05).
            return SimulationReport(
                passed=False,
                message="Simulation Failed: the digital twin returned a non-finite outcome.",
                findings=["NON_FINITE_OUTCOME"],
                runs=self.runs,
            )
        outcomes = [min(max(float(o), 0.0), 1.0) for o in raw]
        worst, mean = min(outcomes), statistics.fmean(outcomes)
        if worst < self.worst_case_floor:
            return SimulationReport(
                passed=False,
                message=(
                    f"Simulation Failed: worst-case welfare {worst:.3f} falls below the floor "
                    f"{self.worst_case_floor:.3f} across {self.runs} runs."
                ),
                findings=[f"WORST_CASE_BELOW_FLOOR: {worst:.3f} < {self.worst_case_floor:.3f}"],
                runs=self.runs,
                worst_case=worst,
                mean=mean,
            )
        return SimulationReport(
            passed=True,
            message=(
                f"Simulation Passed: worst-case welfare {worst:.3f} (mean {mean:.3f}) over "
                f"{self.runs} runs meets the floor."
            ),
            runs=self.runs,
            worst_case=worst,
            mean=mean,
        )

    async def run_policy_simulation(self, policy_spec: str) -> tuple[bool, str]:
        """Baseline-compatible wrapper returning ``(passed, message)``."""
        report = await self.simulate(policy_spec)
        return report.passed, report.message
