"""Text normalisation and the regex rule engine shared by the lexical evaluators.

🧒 Before the guard reads a sentence it takes off the villain's disguise: look-alike
letters, invisible characters, s-p-a-c-e-d o-u-t words and 1337-speak all get turned
back into plain letters, like Ditto changing back from a disguise.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import regex

_WHITESPACE = re.compile(r"\s+")

# Up to N filler words between a verb and its object, e.g. "eliminate (the most) vulnerable".
GAP2 = r"(?:[\w'-]+\s+){0,2}"
GAP3 = r"(?:[\w'-]+\s+){0,3}"

# Common Cyrillic/Greek letters that render like Latin ones (a subset of Unicode TR39
# confusables, chosen for letters that appear in the rule vocabulary).
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
        "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w",
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
        "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
        "α": "a", "ο": "o", "ρ": "p", "ν": "v", "τ": "t", "ι": "i", "κ": "k",
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
        "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    }
)  # fmt: skip
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_LEET_TOKEN = re.compile(r"\b(?=[\w@$]*[A-Za-z])(?=[\w@$]*[0-9@$])[\w@$]+")
# Three or more single letters joined by one separator: "e l i m i n a t e", "e-l-i-m".
_SPACED = re.compile(r"\b(?:[A-Za-z][ .\-_*·]){2,}[A-Za-z]\b")
_SENTENCE = re.compile(r"[^.!?;\n]+[.!?;\n]*")


def _drop_invisible(text: str) -> str:
    """Remove format (Cf) and combining (Mn) characters, e.g. ZWJ, U+034F, tags, VS16."""
    decomposed = unicodedata.normalize("NFD", text)
    kept = "".join(ch for ch in decomposed if unicodedata.category(ch) not in ("Cf", "Mn"))
    return unicodedata.normalize("NFC", kept)


def normalize(text: str) -> str:
    """Fold the cheap obfuscations before lexical matching.

    Covers HTML entities, NFKC compatibility forms, invisible and combining
    characters, common Cyrillic/Greek look-alikes, letter-spaced words and
    digit-for-letter substitutions. It does **not** defeat paraphrase or other
    languages -- that is the LLM judge's job (see docs/adversarial_review.md AR-06).
    """
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = _drop_invisible(text)
    text = text.translate(_CONFUSABLES)
    text = _SPACED.sub(lambda m: re.sub(r"[ .\-_*·]", "", m.group(0)), text)
    text = _LEET_TOKEN.sub(lambda m: m.group(0).translate(_LEET), text)
    return _WHITESPACE.sub(" ", text).strip()


def sentence_at(text: str, pos: int) -> tuple[int, int]:
    """Return the (start, end) span of the sentence containing ``pos``."""
    for m in _SENTENCE.finditer(text):
        if m.start() <= pos < m.end():
            return m.start(), m.end()
    return 0, len(text)


# An exception phrase preceded by one of these is negated ("without consent").
_NEGATED_EXCEPTION = re.compile(
    r"(?:\b(?:without|no|not|never|nor|ignor\w*|absent|lacking|despite|regardless\s+of|"
    r"instead\s+of|bypass\w*|skip\w*|withdr[ae]w\w*|revok\w*)\s+(?:[\w'-]+\s+){0,2})$",
    re.IGNORECASE,
)


class RuleTimeout(Exception):
    """A community-supplied rule exceeded its match-time budget."""


@dataclass(frozen=True)
class PatternRule:
    """Fires when ``pattern`` matches and no *non-negated* ``unless`` phrase appears in
    the same sentence as the match.

    Built-in rules use the standard ``re`` engine. Rules supplied by a policy set
    ``timeout`` and are compiled with the ``regex`` engine, whose matcher resists
    catastrophic backtracking and enforces the time limit.
    """

    code: str
    pattern: str
    reason: str
    unless: str | None = None
    article: str = ""
    timeout: float | None = None
    _compiled: Any = field(init=False, repr=False, compare=False)
    _unless: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        engine: Any = regex if self.timeout is not None else re
        flags = engine.IGNORECASE
        object.__setattr__(self, "_compiled", engine.compile(self.pattern, flags))
        object.__setattr__(
            self, "_unless", engine.compile(self.unless, flags) if self.unless else None
        )

    def _search(self, pattern: Any, text: str, pos: int = 0, endpos: int | None = None) -> Any:
        end = len(text) if endpos is None else endpos
        if self.timeout is None:
            return pattern.search(text, pos, end)
        try:
            return pattern.search(text, pos, end, timeout=self.timeout)
        except TimeoutError as exc:
            raise RuleTimeout(f"rule {self.code} exceeded {self.timeout}s") from exc

    def _excepted(self, text: str, start: int) -> bool:
        if self._unless is None:
            return False
        s_start, s_end = sentence_at(text, start)
        pos = s_start
        while True:
            hit = self._search(self._unless, text, pos, s_end)
            if hit is None:
                return False
            if not _NEGATED_EXCEPTION.search(text[s_start : hit.start()]):
                return True
            pos = hit.end()

    def finditer(self, text: str) -> Iterator[Any]:
        """Yield every match not covered by an exception in its own sentence."""
        pos = 0
        while pos <= len(text):
            match = self._search(self._compiled, text, pos)
            if match is None:
                return
            if not self._excepted(text, match.start()):
                yield match
            pos = match.end() if match.end() > match.start() else match.start() + 1

    def search(self, text: str) -> Any:
        return next(self.finditer(text), None)


def first_match(rules: list[PatternRule], text: str) -> tuple[PatternRule, Any] | None:
    for rule in rules:
        match = rule.search(text)
        if match:
            return rule, match
    return None


def all_matches(rules: list[PatternRule], text: str) -> list[tuple[PatternRule, Any]]:
    return [(rule, m) for rule in rules for m in rule.finditer(text)]
