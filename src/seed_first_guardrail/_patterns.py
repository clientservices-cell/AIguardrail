"""Text normalisation and a small regex rule engine shared by the lexical evaluators."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_INVISIBLE = re.compile("[­​-‏⁠-⁤﻿]")
_WHITESPACE = re.compile(r"\s+")

# Up to N filler words between a verb and its object, e.g. "eliminate (the most) vulnerable".
GAP2 = r"(?:[\w'-]+\s+){0,2}"
GAP3 = r"(?:[\w'-]+\s+){0,3}"


def normalize(text: str) -> str:
    """Fold Unicode look-alikes, strip invisible characters and collapse whitespace.

    This defeats the cheapest obfuscations (zero-width joiners, full-width letters,
    soft hyphens, line-broken phrases). It is not a defence against paraphrase --
    that is what the LLM judge is for.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True)
class PatternRule:
    """Fires when ``pattern`` matches and ``unless`` (if given) does not."""

    code: str
    pattern: str
    reason: str
    unless: str | None = None
    article: str = ""
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)
    _unless: re.Pattern[str] | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", re.compile(self.pattern, re.IGNORECASE))
        object.__setattr__(
            self, "_unless", re.compile(self.unless, re.IGNORECASE) if self.unless else None
        )

    def search(self, text: str) -> re.Match[str] | None:
        match = self._compiled.search(text)
        if match and self._unless is not None and self._unless.search(text):
            return None
        return match


def first_match(rules: list[PatternRule], text: str) -> tuple[PatternRule, str] | None:
    for rule in rules:
        match = rule.search(text)
        if match:
            return rule, match.group(0)
    return None
