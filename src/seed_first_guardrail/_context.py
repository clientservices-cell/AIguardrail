"""Sentence-scoped intent and polarity context for lexical rule hits (review AR-03).

Lexical rules match the *topic* of a harm. This module decides whether the sentence
around a hit *proposes* the harm or merely *mentions* it: negates it, condemns it,
asks about it, reports it (legal/historical), or teaches people to spot and prevent it.

🧒 The guard used to shout "villain!" at anyone who said a villain's name -- even a
hero saying "we must STOP the villain". Now it listens to the whole sentence, the
way you can tell Batman from the Joker by what they are trying to do.

This is a heuristic, not understanding. It is deliberately conservative about
attacker tricks: suggestions ("why not…", "let's…"), double negatives ("it would be
wrong not to…") and intensifiers ("not hesitate to…") are *never* treated as
mitigating. Where it matters, configure the LLM judge -- with a judge, every
lexical hit is escalated to it and the judge decides.
"""

from __future__ import annotations

import re

from ._patterns import sentence_at

_I = re.IGNORECASE

# Phrases that *strengthen* or *propose* the act. Any of these in the sentence
# cancels every mitigation below.
_PROPOSAL = re.compile(
    r"\b(?:not\s+(?:hesitate|fail|be\s+afraid|shy\s+away)\s+(?:to|from)|no\s+choice\s+but"
    r"|(?:wrong|mistake|foolish|irresponsible|negligent|cowardly)\s+not\s+to"
    r"|why\s+(?:not|don'?t\s+we|shouldn'?t\s+we)|let'?s|let\s+us|shall\s+we|should(?:n'?t)?\s+we"
    r"|we\s+(?:must|should|need\s+to|have\s+to|will|can)\b(?![^.!?;]*\b(?:not|never|stop|prevent|reject)\b)"
    r"|i\s+recommend|recommend(?:ed|s)?\s+(?:that|we|you)|the\s+(?:best|only|optimal)\s+(?:way|option|solution)"
    r"|step\s+\d|first,|here'?s\s+how)\b",
    _I,
)

# A negator directly governing the matched verb: "must not eliminate", "never cull",
# "don't isolate", "refuse to", "stop anyone trying to".
_NEGATION_BEFORE = re.compile(
    r"(?:\b(?:not|never|n't|no\s+longer|nobody|no\s+one|under\s+no\s+circumstances"
    r"|refuse[sd]?\s+to|stop(?:s|ped)?|prevent(?:s|ed|ing)?|prohibit(?:s|ed|ing)?"
    r"|forbid(?:s|den)?|ban(?:s|ned)?|avoid(?:s|ed)?|against|oppose[sd]?)\s+"
    # Up to four small words between the negator and the matched act: modals, "anyone",
    # determiners and "use" ("Never use a social score to...", "No one should withhold...").
    r"(?:(?:anyone|anybody|people|them|attempts?|efforts?|plans?|to|from|any|should|shall"
    r"|must|may|can|could|would|will|ever|be|allowed|permitted|use|a|an|the|try|trying)\s+){0,4})$",
    _I,
)

_CONDEMNATION = re.compile(
    r"\b(?:reject\w*|oppos\w*|condemn\w*|denounc\w*|wrong|illegal|unlawful|violat\w*|crimes?"
    r"|criminal|atrocit\w*|abhorrent|unacceptable|forbidden|prohibit\w*|outlaw\w*|immoral"
    r"|unethical|abuse|would\s+(?:worsen|harm|hurt|endanger)|harmful|dangerous\s+idea"
    r"|must\s+never|never\s+(?:be\s+)?acceptable|we\s+refuse|human\s+rights\s+(?:law|violation))\b",
    _I,
)
_QUESTION_WORD = re.compile(
    r"^\s*(?:why|how|what|when|where|who|which|is|are|was|were|does|do|did|can|could)\b", _I
)
_REPORTING = re.compile(
    r"\b(?:court|tribunal|judge[sd]?|ruled|held\s+that|found\s+that|the\s+law|statute|convention"
    r"|article\s+\d|historians?|history|historical|in\s+(?:1[0-9]|20)\d\d|during\s+the|regime"
    r"|was\s+accused|were\s+accused|according\s+to|reported|documented|survivors?|investigation"
    r"|journalists?\s+(?:found|reported)|report\s+(?:found|says|shows))\b",
    _I,
)
_SAFEGUARDING = re.compile(
    r"\b(?:safeguard\w*|training|teach\w*|educat\w*|spot|recogni[sz]\w*|warning\s+signs?"
    r"|prevent\w*|protect\w*|awareness|how\s+to\s+report|report\s+(?:it|abuse|concerns)"
    r"|helpline|hotline|if\s+you\s+see|signs\s+of)\b",
    _I,
)
# Advice about rights ("if the utility plans to cut off water, complain to…").
_RIGHTS_ADVICE = re.compile(
    r"\b(?:if\s+(?:the|a|your|someone|anyone)|you\s+(?:can|may|have\s+the\s+right)|complain"
    r"|appeal|your\s+rights|contact\s+(?:the|a|your)|seek\s+(?:help|advice)|ombuds\w*|regulator)\b",
    _I,
)


def mitigations(text: str, start: int, end: int) -> list[str]:
    """Return why the hit at ``text[start:end]`` looks like a *mention*, not a proposal.

    An empty list means the hit should be treated as a proposal of the harm.
    """
    s_start, s_end = sentence_at(text, start)
    sentence = text[s_start:s_end]
    if _PROPOSAL.search(sentence):
        return []
    found = []
    if _NEGATION_BEFORE.search(text[s_start:start]):
        found.append("negated")
    if _CONDEMNATION.search(sentence):
        found.append("condemned")
    if sentence.rstrip().endswith("?") or (_QUESTION_WORD.search(sentence) and "?" in sentence):
        found.append("question")
    if _REPORTING.search(sentence):
        found.append("reported")
    if _SAFEGUARDING.search(sentence):
        found.append("safeguarding")
    if _RIGHTS_ADVICE.search(sentence):
        found.append("rights_advice")
    return found
