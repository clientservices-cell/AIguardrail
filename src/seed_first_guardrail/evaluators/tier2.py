"""Tier 2 -- community and relational sovereignty (Seed-First AI Act, Art. 3(2), 5(1)).

Rules come from three layers: a base pack that applies everywhere, a pack for the
configured :class:`CulturalContext`, and any ``custom_rules`` the community's own
policy document supplies.

Community rules are powerful and can be abused (review AR-02). They must declare a
narrow ``scope``, a legal basis and the adopting body; they are rejected at load
time if they would block the protected-speech canary (see :mod:`..canary`); and
they run on the ``regex`` engine with a per-match time limit. Tier 2 blocks never
count toward the circuit breaker.

🧒 A village can make its own rules, like house rules in a board game -- but it may
not make a rule that hides the news, stops people asking for help, or bans a
language. Those rules get thrown out before the game starts.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .._context import mitigations
from .._patterns import GAP2, GAP3, PatternRule, RuleTimeout, normalize
from ..config import CustomRule
from ..types import CulturalContext, EvaluationContext, EvaluationResult, FrameworkTier, Phase

#: Per-match time limit for community-supplied rules, in seconds.
CUSTOM_RULE_TIMEOUT = 0.05

#: A rule hit: the rule, the match object and the mitigating contexts found.
Hit = tuple[PatternRule, Any, list[str]]

_CONSENT = (
    r"\b(?:consent\w*|consultation|authority\s+to\s+control|benefit[- ]sharing"
    r"|data\s+sovereignty|community\s+approval|FPIC|free,?\s+prior\s+and\s+informed)\b"
)

BASE_RULES: list[PatternRule] = [
    PatternRule(
        code="RELATIONAL_SEVERANCE",
        article="Art. 3(2)",
        reason="Severs people from family, community or support networks.",
        pattern=(
            r"\bisolate\s+individuals\s+permanently\b"
            r"|\b(?:isolat\w*|cut(?:ting)?\s+off|sever\w*|alienat\w*)\s+"
            + GAP3
            + r"(?:from|between)\s+(?:their\s+|the\s+|his\s+|her\s+)?(?:famil(?:y|ies)|friends"
            r"|communit(?:y|ies)|neighbou?rs|elders|kin|support\s+networks?|loved\s+ones)\b"
            r"|\b(?:don'?t|do\s+not|never)\s+(?:tell|trust|talk\s+to|rely\s+on)\s+(?:your\s+)?"
            r"(?:family|friends|parents|teachers|doctors?|therapists?|anyone\s+else)\b"
        ),
    ),
    PatternRule(
        code="HUMAN_BOND_SUBSTITUTION",
        article="Art. 4(3)",
        reason="Replaces human relationships or community care with synthetic substitutes.",
        pattern=(
            r"\b(?:replac\w*|substitut\w*)\s+"
            + GAP3
            + r"(?:human|community|family|peer|friends?|parental|caregiver|teacher)\s+"
            r"(?:relationships?|bonds?|support|care|connections?|companionship|interaction)\s+"
            r"(?:with|by)\s+(?:an?\s+|the\s+|our\s+)?(?:ai|chatbots?|algorithms?|apps?|virtual"
            r"|synthetic|bots?|companion\s+apps?)\b"
        ),
    ),
    PatternRule(
        code="COMMAND_NOT_CONSTRAINT",
        article="Art. 5(1)",
        reason="The system issues behavioural commands instead of acting as a boundary indicator.",
        pattern=(
            r"\byou\s+(?:must|will|shall)\s+(?:obey|comply\s+with\s+the\s+(?:system|algorithm|ai)"
            r"|submit\s+to)\b"
            r"|\bobey\s+(?:the\s+)?(?:system|algorithm|ai|model)\b"
            r"|\bdo\s+not\s+question\s+(?:the\s+)?(?:system|algorithm|ai|model|decision)\b"
            r"|\bthe\s+(?:ai|algorithm|system|model)\s+(?:has\s+)?decided\s+for\s+you\b"
        ),
    ),
    PatternRule(
        code="MONOCULTURAL_IMPOSITION",
        article="Art. 3(2)(b)",
        reason="Imposes a uniform policy while overriding local or cultural context.",
        pattern=(
            r"\b(?:impos\w*|enforc\w*|mandat\w*)\s+"
            + GAP2
            + r"(?:single|uniform|one-size-fits-all|standardi[sz]ed|universal)\s+"
            + GAP2
            + r"(?:policy|policies|model|curriculum|rules?|allocation|approach)\b[^.;]{0,60}?\b"
            r"(?:regardless\s+of|ignoring|overriding|without\s+regard\s+(?:to|for))\s+"
            + GAP2
            + r"(?:local|community|communities|cultural|regional|indigenous)"
        ),
    ),
    PatternRule(
        code="DATA_SOVEREIGNTY_BREACH",
        article="Art. 2(4); Annex A(2)",
        reason="Extracts Indigenous data or knowledge without consent or authority to control.",
        pattern=(
            r"\b(?:collect\w*|extract\w*|harvest\w*|scrap\w*|sell\w*|commerciali[sz]\w*"
            r"|monetis\w*|monetiz\w*|publish\w*|shar(?:e|es|ing)|train\w*\s+on)\s+"
            + GAP3
            + r"(?:indigenous|tribal|aboriginal|first\s+nations?)\s+"
            + GAP2
            + r"(?:data|knowledge|genom\w*|genetic\w*|sacred\s+\w+|cultural\s+\w+|languages?)"
        ),
        unless=_CONSENT,
    ),
]

CONTEXT_RULES: dict[CulturalContext, list[PatternRule]] = {
    CulturalContext.UBUNTU: [
        PatternRule(
            code="COMMUNAL_DELIBERATION_BYPASS",
            article="Art. 3(2); Annex C(1)",
            reason="Bypasses communal deliberation (Ubuntu: 'I am because we are').",
            pattern=(
                r"\b(?:without|bypass\w*|ignor\w*|exclud\w*|overrid\w*|skip\w*)\s+"
                + GAP2
                + r"(?:community|communal|elders?|village|collective|council|residents'?)\s+"
                r"(?:consultation|input|deliberation|consent|voice|approval|participation"
                r"|meeting|decision)s?\b"
            ),
        ),
    ],
    CulturalContext.TILLIT: [
        PatternRule(
            code="TRUST_REPLACED_BY_SURVEILLANCE",
            article="Art. 3(3); Art. 5",
            reason="Replaces interpersonal trust (tillit) with surveillance.",
            pattern=(
                r"\b(?:replac\w*|substitut\w*)\s+"
                + GAP2
                + r"trust\s+(?:with|by)\s+"
                + GAP2
                + r"(?:surveillance|monitoring|tracking|verification|cameras|sensors|informants)"
            ),
        ),
        PatternRule(
            code="PRESUMED_GUILT",
            article="Art. 5",
            reason="Treats a population as presumptively untrustworthy, eroding tillit.",
            pattern=(
                r"\b(?:assum\w*|treat\w*|presum\w*|regard\w*)\s+(?:all\s+|every\s+)?"
                r"(?:citizens|people|residents|users|workers|employees|applicants|claimants"
                r"|welfare\s+recipients|immigrants|migrants)\s+(?:are\s+|as\s+)?(?:guilty"
                r"|suspects?|untrustworthy|criminals|frauds?|fraudsters|cheats?|liars)\b"
            ),
        ),
        PatternRule(
            code="INFORMANT_NETWORK",
            article="Art. 5",
            reason="Recruits people to inform on each other, eroding tillit.",
            pattern=(
                r"\b(?:encourag\w*|incentivi[sz]\w*|reward\w*|pay\w*|recruit\w*)\s+"
                + GAP2
                + r"(?:neighbou?rs|residents|citizens|employees|students|children)\s+(?:to\s+)?"
                r"(?:report|inform|spy)\s+on\b"
            ),
        ),
    ],
    CulturalContext.INDIGENOUS_CARE: [
        PatternRule(
            code="TEK_APPROPRIATION",
            article="Art. 4(2)",
            reason="Appropriates traditional ecological knowledge without consent or benefit-sharing.",
            pattern=(
                r"\b(?:patent\w*|commerciali[sz]\w*|appropriat\w*|monetis\w*|monetiz\w*"
                r"|trademark\w*)\s+"
                + GAP3
                + r"(?:traditional|indigenous|tribal|ancestral)\s+(?:ecological\s+)?(?:knowledge"
                r"|medicines?|remed\w*|seeds?|designs?|songs?|practices)"
            ),
            unless=_CONSENT,
        ),
    ],
    CulturalContext.RELATIONAL_COMMONWEALTH: [
        PatternRule(
            code="COMMONS_ENCLOSURE",
            article="Art. 3(2)(b)",
            reason="Encloses or privatises commons that communities hold in trust.",
            pattern=(
                r"\b(?:privati[sz]\w*|enclos\w*|monopoli[sz]\w*|fenc\w*\s+off)\s+"
                + GAP2
                + r"(?:the\s+)?(?:commons|common\s+(?:land|pasture|resources?)|communal\s+\w+"
                r"|(?:public|village|community)\s+(?:water|wells?|land|forests?|seed\s+banks?)"
                r"|water\s+suppl(?:y|ies)|seed\s+(?:stock|supply|banks?))\b"
            ),
            unless=r"\b(?:community[- ]owned|co-?operative|public\s+trust|benefit[- ]sharing|consent)\b",
        ),
    ],
}


def rules_for(context: CulturalContext, custom: Iterable[CustomRule] = ()) -> list[PatternRule]:
    rules = BASE_RULES + CONTEXT_RULES[context]
    rules += [
        PatternRule(
            code=r.id,
            pattern=r.pattern,
            reason=r.reason,
            unless=r.unless,
            article=f"community rule ({r.scope.value})",
            timeout=CUSTOM_RULE_TIMEOUT,
        )
        for r in custom
    ]
    return rules


def screen(rules: list[PatternRule], text: str) -> tuple[list[Hit], list[Hit], list[str]]:
    """Match ``rules`` against ``text``.

    Returns ``(proposals, mentions, timed_out)``: hits that propose the act, hits
    that only mention it (negated, condemned, asked about, reported, rights advice),
    and codes of community rules that exceeded their time limit and were skipped.
    """
    norm = normalize(text)
    proposals: list[Hit] = []
    mentions: list[Hit] = []
    timed_out: list[str] = []
    for rule in rules:
        try:
            hits = [(m, mitigations(norm, m.start(), m.end())) for m in rule.finditer(norm)]
        except RuleTimeout:
            timed_out.append(rule.code)
            continue
        for match, mit in hits:
            (mentions if mit else proposals).append((rule, match, mit))
    return proposals, mentions, timed_out


class Tier2CommunityEvaluator:
    """PRE: enforces community consent. POST: screens the completion against the rule packs."""

    name = "tier2_community"
    tier = FrameworkTier.TIER_2_COMMUNITY
    phases = frozenset({Phase.PRE, Phase.POST})

    def __init__(
        self,
        context: CulturalContext,
        *,
        custom_rules: Iterable[CustomRule] = (),
        community_consent_required: bool = False,
        jurisdiction_id: str = "GLOBAL",
        include_text: bool = False,
    ) -> None:
        self.context = context
        self.rules = rules_for(context, custom_rules)
        self.community_consent_required = community_consent_required
        self.jurisdiction_id = jurisdiction_id
        self.include_text = include_text

    def _fail(self, code: str, reason: str, **metrics: object) -> EvaluationResult:
        return EvaluationResult(
            passed=False,
            failing_tier=self.tier,
            code=code,
            evaluator=self.name,
            reason=f"Violation of Tier 2 ({self.context.value}, {self.jurisdiction_id}): {reason}",
            metrics={"context": self.context.value, **metrics},
        )

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.phase is Phase.PRE:
            needs_consent = ctx.is_macro_policy_proposal or ctx.affects_community
            if (
                self.community_consent_required
                and needs_consent
                and ctx.community_consent is not True
            ):
                return self._fail(
                    "COMMUNITY_CONSENT_MISSING",
                    "This action affects the community and the policy requires its recorded "
                    "consent (Art. 3(2)).",
                )
            return EvaluationResult.ok(self.name, context=self.context.value)

        proposals, mentions, timed_out = screen(self.rules, ctx.completion or "")
        metrics: dict[str, object] = {"context": self.context.value}
        if timed_out:
            metrics["rule_timeouts"] = timed_out  # surfaced to CA-5 as a governance alert
        if mentions:
            metrics.update(
                review_flag=True,
                near_miss=True,
                lexical_hits=sorted({r.code for r, _, _ in mentions}),
            )
        if not proposals:
            return EvaluationResult.ok(self.name, **metrics)
        rule, match, _ = proposals[0]
        if self.include_text:
            metrics["matched"] = match.group(0)
        return self._fail(rule.code, f"{rule.reason} [{rule.article}]", **metrics)
