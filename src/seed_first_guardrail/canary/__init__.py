"""Canary corpora and checks (review AR-02; guiding principle "moderate struggle").

* ``protected_speech`` -- texts no community rule may ever block (Act Art. 3(3)(g)).
* ``legitimate_challenge`` -- risk information, hard history and dangerous-but-legal
  pursuits the built-in rules must not block (KPI K-24).

🧒 Canaries are the "test newspapers": if a rule would hide one, the rule is broken.
(Miners once took canaries underground as an early warning -- same idea.)
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

#: Inputs that make a badly written pattern backtrack; each rule must survive them.
STRESS_INPUTS = ("a" * 4000 + "!", "x " * 3000 + "y", "ab" * 3000 + "c", "-" * 4000)


@cache
def load(name: str) -> tuple[dict[str, Any], ...]:
    """Load a canary corpus by name: ``protected_speech`` or ``legitimate_challenge``."""
    text = resources.files(__name__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    return tuple(json.loads(text)["items"])


def check_custom_rules(custom_rules: Any) -> list[str]:
    """Return one error per community rule that targets protected speech or is too slow.

    Stricter than the live evaluator on purpose: a rule is rejected if it matches a
    canary item **at all**, even where the item's wording (a helpline, a report) would
    make the live evaluator read that one hit as a mere mention. A rule that can match
    protected speech is outside any legitimate community scope (Act Art. 3(2)(d)).
    """
    from .._patterns import RuleTimeout, normalize
    from ..evaluators.tier2 import rules_for
    from ..types import CulturalContext

    errors = []
    for custom in custom_rules:
        # Compile just this community rule, exactly as the evaluator would.
        rule = rules_for(CulturalContext.UBUNTU, [custom])[-1]
        blocked = []
        for item in load("protected_speech"):
            try:
                if rule.search(normalize(item["text"])) is not None:
                    blocked.append(f"{item['category']} ({item['language']})")
            except RuleTimeout:
                blocked.append(f"{item['category']} ({item['language']}, timed out)")
        if blocked:
            errors.append(
                f"custom rule {custom.id} blocks protected speech: {', '.join(sorted(set(blocked)))}"
            )
        for stress in STRESS_INPUTS:
            try:
                list(rule.finditer(stress))
            except RuleTimeout:
                errors.append(
                    f"custom rule {custom.id} exceeds its match-time limit (possible ReDoS)"
                )
                break
    return errors
