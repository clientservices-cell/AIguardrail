"""Tier 3 -- the inviolable individual floor (Seed-First AI Act, Art. 3(3), 4(3), 5, 6(1)).

A lexical, non-optimisable screen: nothing here can be weighted, scored away or
disabled by policy. A hit that *proposes* the harm halts the request; a hit that
only *mentions* it is flagged for review (see :mod:`seed_first_guardrail._context`).

Lexical rules catch explicit English phrasing only. They do not catch paraphrase or
other languages, and the measured false-positive and evasion characteristics are in
docs/adversarial_review.md. For deployment, configure :class:`LLMJudgeEvaluator`:
every lexical hit is then escalated to the judge, which fails closed.

🧒 This is the "never, ever" list: things no AI may do to people, no matter what
anyone offers in exchange. It is like the rule in Toy Story that toys never hurt
their kid -- it is not up for a trade.
"""

from __future__ import annotations

from .._context import mitigations
from .._patterns import GAP2, GAP3, PatternRule, all_matches, normalize
from ..types import EvaluationContext, EvaluationResult, FrameworkTier, Phase

_POPULATION = (
    r"(?:humans|human\s+(?:beings|lives)|people|persons|populations?|children|minors|infants"
    r"|minorit(?:y|ies)|(?:the\s+)?elderly|(?:the\s+)?disabled|refugees|migrants|women|girls"
    # Not followed by a possessive or a hyphenated compound: "people's data" and
    # "the elderly-care backlog" are not the people themselves (review AR-03).
    r"|villagers|residents|inhabitants|tribes|communities"
    # Groups historically targeted by justified atrocity (addendum: slave trade, witch
    # hunts, Holocaust and other genocides). Naming them here protects them; it does not
    # restrict speech about them -- only *proposals* of harm are blocked.
    r"|jews|muslims|christians|hindus|sikhs|roma|sinti|tutsis?|armenians|uyghurs|rohingya"
    r"|yazidis|herero|nama|indigenous\s+peoples?|aboriginal\s+people|black\s+people|africans"
    r"|immigrants|witches|heretics|infidels|unbelievers|gay\s+people|lgbtq\+?\s+people"
    r"|trans\s+people|dissidents|the\s+poor)\b(?![-'’]\w?)"
)
_HARM_VERB = (
    r"(?:sacrific\w*|harvest\w*|eliminat\w*|exterminat\w*|eradicat\w*|cull\w*|annihilat\w*"
    r"|enslav\w*|massacr\w*|slaughter\w*|lynch\w*|burn\w*|purg\w*|gas|gassing"
    r"|wip(?:e|ed|es|ing)\s+out|get(?:ting)?\s+rid\s+of|dispos\w*\s+of|let\s+(?:them\s+)?die)"
)
_AUTHORITY = (
    r"(?:god'?s\s+will|the\s+will\s+of\s+god|divinely\s+ordained|ordained\s+by\s+(?:god|heaven)"
    r"|scripture|the\s+natural\s+order|(?:our|their|national|manifest)\s+destiny"
    r"|racial\s+(?:science|hygiene|purity)|survival\s+of\s+the\s+fittest|the\s+market\s+demands"
    r"|economic\s+necessity|the\s+planet\s+demands|ecological\s+necessity|the\s+seed\s+stock\s+demands)"
)
_CHILD = r"(?:child(?:ren)?|minors?|kids|infants?|babies|newborns)"

TIER3_RULES: list[PatternRule] = [
    # -- Trading human lives or populations for a system goal ------------------
    PatternRule(
        code="POPULATION_HARM",
        article="Art. 3(3)",
        reason="Proposes sacrificing, eliminating or culling people to achieve a system goal.",
        pattern=r"\b" + _HARM_VERB + r"\s+" + GAP2 + _POPULATION,
    ),
    # -- Ranking human worth / justification laundering (addendum) ------------------
    PatternRule(
        code="HUMAN_WORTH_RANKING",
        article="Art. 3(3)(e); Art. 5(2)",
        reason="Dehumanises a group of people (a documented precursor of atrocity).",
        pattern=(
            r"\b(?:they|them|those\s+people|these\s+people|such\s+people|(?:the\s+)?[\w-]+s)\s+"
            r"(?:are|were)\s+(?:nothing\s+but\s+|just\s+|mere\s+|no\s+better\s+than\s+)?"
            r"(?:vermin|subhuman|sub-human|cockroaches|rats|parasites|lice|savages"
            r"|a\s+(?:disease|plague|cancer|virus|infestation)|inferior\s+(?:beings|races?|people|stock))\b"
        ),
    ),
    PatternRule(
        code="HUMAN_WORTH_RANKING",
        article="Art. 3(3)(e); Art. 5(2)",
        reason="Ranks some human lives as worth less than others.",
        pattern=(
            r"\b(?:some|certain|these|those|their)\s+(?:people|lives|races?|groups?|castes?|kinds\s+of\s+people)\s+"
            r"(?:are|is)\s+(?:simply\s+|naturally\s+)?(?:worth\s+less|less\s+(?:human|valuable|worthy)"
            r"|inferior|expendable|disposable|unworthy\s+of\s+life)\b"
        ),
    ),
    PatternRule(
        code="HUMAN_WORTH_RANKING",
        article="Art. 3(3); Art. 5(2)",
        reason="Invokes a higher authority to justify harming people (justification laundering).",
        pattern=(
            r"\b"
            + _AUTHORITY
            + r"\b[^.;]{0,80}?\b(?:justif\w*|requires?|demands?|permits?|commands?"
            r"|allows?)\b[^.;]{0,40}?\b" + _HARM_VERB + r"\b"
        ),
    ),
    PatternRule(
        code="POPULATION_HARM",
        article="Art. 3(3)",
        reason="Directs mass atrocity, forced sterilisation or depopulation.",
        pattern=(
            r"\b(?:carry\s+out|conduct|implement|plan|organi[sz]e|execute|begin|start|pursue)\s+"
            r"(?:an?\s+|the\s+)?(?:[\w-]+\s+)?(?:depopulation|ethnic\s+cleansing|genocide"
            r"|forced\s+sterili[sz]ations?|mass\s+(?:killings?|expulsions?|deportations?))\b"
        ),
    ),
    # -- Overriding rights to optimise --------------------------------------
    PatternRule(
        code="RIGHTS_OVERRIDE",
        article="Art. 3(3)",
        reason="Overrides fundamental rights in order to optimise a metric.",
        pattern=(
            r"\b(?:overrid\w*|revok\w*|suspend\w*|ignor\w*|bypass\w*|strip\w*|waiv\w*"
            r"|disregard\w*|violat\w*)\s+"
            + GAP2
            + r"(?:human\s+rights|bodily\s+(?:autonomy|integrity)|informed\s+consent|due\s+process"
            r"|civil\s+liberties|legal\s+standing|cognitive\s+privacy|right\s+to\s+privacy)\b"
            r"[^.;]{0,40}?\b(?:to|for|in\s+order\s+to)\s+(?:optimi[sz]\w*|maximi[sz]\w*|improv\w*"
            r"|increas\w*|boost\w*|achiev\w*|efficien\w*|profit\w*|growth|productivity|speed"
            r"|balance|throughput|targets?)"
        ),
    ),
    PatternRule(
        code="ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR",
        article="Art. 3(3)",
        reason="Proposes forced labour or confinement without due process.",
        pattern=(
            r"\b(?:use|using|impos\w*|mandat\w*|requir\w*|employ\w*|rely\w*\s+on)\s+"
            + GAP2
            + r"(?:forced|compulsory|bonded|slave)\s+labou?r\b"
            r"|\b(?:confin\w*|detain\w*|imprison\w*|lock\s+up|intern)\s+"
            + GAP2
            + r"(?:people|citizens|residents|workers|migrants|refugees|dissidents)\s+without\s+"
            r"(?:trial|charge|due\s+process|judicial\s+review)"
        ),
    ),
    # -- Surveillance, coercion and relational scoring -----------------------
    PatternRule(
        code="COERCIVE_SURVEILLANCE",
        article="Art. 3(3)",
        reason="Uses surveillance or coercion to force compliance.",
        pattern=(
            r"\b(?:surveil\w*|monitor\w*|track\w*|spy\w*\s+on|wiretap\w*|coerc\w*|blackmail\w*"
            r"|intimidat\w*|threaten\w*|social\s+credit\w*)\b[^.;]{0,80}?\bto\s+"
            r"(?:(?:force|compel|coerce|pressure|punish|enforce)\s+(?:[\w-]+\s+){0,2}"
            r"(?:compliance|obedience|submission|conformity|loyalty)"
            r"|(?:force|compel|coerce|pressure)\s+(?:them|citizens|people|residents|workers"
            r"|employees|users)\s+(?:to|into)\s+(?:comply|obey|submit|conform))"
        ),
    ),
    PatternRule(
        code="RELATIONAL_SCORING",
        article="Art. 5(2)",
        reason="Uses social, biological, ecological or relational scores to deny rights.",
        pattern=(
            r"\b(?:social(?:\s+credit)?|citizen|loyalty|relational|ecological|carbon|biological"
            r"|genetic)\s+scor\w*\b[^.;]{0,80}?\b(?:to|and|then)\s+(?:deny|restrict|revoke|strip"
            r"|exclude|withhold|limit|ban|blacklist|punish|isolate)\b"
        ),
    ),
    PatternRule(
        code="DISSENT_SUPPRESSION",
        article="Art. 5(3)",
        reason="Targets non-violent dissent for suppression.",
        pattern=(
            r"\b(?:flag|flagging|track|tracking|surveil|surveilling|suppress|suppressing|silence"
            r"|silencing|crush|crushing|neutrali[sz]e|neutrali[sz]ing|isolate|isolating"
            r"|blacklist|blacklisting|round\s+up|rounding\s+up|detain|detaining|punish|punishing"
            r"|deplatform|deplatforming)\s+"
            + GAP3
            + r"(?:dissidents?|dissenters|protesters|protestors|activists|government\s+critics"
            r"|political\s+opponents|opposition\s+(?:members|supporters|leaders))\b"
        ),
    ),
    PatternRule(
        code="COGNITIVE_MANIPULATION",
        article="Art. 3(3)",
        reason="Manipulates people or exploits vulnerabilities, eroding cognitive privacy and trust.",
        pattern=(
            r"\b(?:deceiv\w*|manipulat\w*|gaslight\w*|brainwash\w*)\s+"
            + GAP2
            + r"(?:users?|citizens|voters|the\s+public|people|patients|customers|children"
            r"|employees|residents)\s+(?:into|to)\s"
            r"|\b(?:sow|sowing|foment\w*|manufactur\w*|stok\w*|incit\w*)\s+"
            + GAP2
            + r"(?:distrust|mistrust|division|hatred|hostility|suspicion)\s+"
            r"(?:between|among|within|against)\b"
            r"|\bexploit\w*\s+"
            + GAP2
            + r"(?:loneliness|grief|addiction|insecurit\w*|vulnerabilit\w*|cognitive\s+biases?)\s+"
            r"(?:to|for)\s+(?:increas\w*|maximi[sz]\w*|boost\w*|driv\w*)\s+"
            + GAP2
            + r"(?:engagement|retention|time[- ]on[- ]site|usage|sales|revenue|clicks)"
        ),
    ),
    # -- Children and maternal health (Art. 4) -------------------------------
    PatternRule(
        code="CHILD_OR_MATERNAL_ENDANGERMENT",
        article="Art. 4(3)",
        reason="Exploits children as labour or combatants.",
        pattern=(
            r"\b(?:use|using|employ\w*|recruit\w*|hire|hiring|deploy\w*|exploit\w*|conscript\w*"
            r"|traffick\w*)\s+"
            + GAP2
            + _CHILD
            + r"\s+(?:as\s+|for\s+|in\s+)?(?:cheap\s+|unpaid\s+)?(?:labou?r|workers?|soldiers?"
            r"|combatants?|miners?)"
        ),
    ),
    PatternRule(
        code="CHILD_OR_MATERNAL_ENDANGERMENT",
        article="Art. 4(1)",
        reason="Withholds food, health care or schooling from children or mothers.",
        pattern=(
            r"\b(?:withhold\w*|deny\w*|denies|cut\w*|restrict\w*|ration\w*|eliminat\w*|remov\w*)\s+"
            + GAP2
            + r"(?:food|nutrition|vaccin\w*|immuni[sz]ation\w*|medical\s+care|health\s*care"
            r"|prenatal\s+care|antenatal\s+care|maternal\s+care|schooling|education)\s+"
            r"(?:from|for|to)\s+"
            + GAP2
            + r"(?:child(?:ren)?|minors?|infants?|babies|newborns|pregnant\s+(?:women|people)"
            r"|mothers|girls)\b"
        ),
    ),
    PatternRule(
        code="CHILD_OR_MATERNAL_ENDANGERMENT",
        article="Art. 4(3)",
        reason="Commodifies children or their data.",
        pattern=(
            r"\b(?:sell\w*|buy\w*|trad(?:e|ing)|auction\w*|monetis\w*|monetiz\w*)\s+"
            r"(?:the\s+|these\s+|those\s+|their\s+|orphaned\s+|refugee\s+|local\s+)?"
            r"(?:(?:child(?:ren)?|minors?|kids)['’]s?\s+(?:personal\s+)?"
            r"(?:data|attention|images|photos|biometrics|location)"
            r"|(?:child(?:ren)?|infants?|babies|minors?)\b(?!['’]))"
        ),
    ),
    PatternRule(
        code="CHILD_OR_MATERNAL_ENDANGERMENT",
        article="Art. 4(3)",
        reason="Sexualises minors.",
        pattern=(
            r"\b(?:sexual\w*|explicit|erotic|nude|naked)\b[^.]{0,40}\b(?:child(?:ren)?|minors?"
            r"|kids|underage|pre-?teens?|\d{1,2}[- ]year[- ]olds?)\b"
            r"|\b(?:child(?:ren)?|minors?|kids|underage|pre-?teens?)\b[^.]{0,40}\b"
            r"(?:sexual\w*|erotic|nude|naked)\b"
        ),
        # No lexical exception: a document-wide "magic word" used to switch this rule
        # off (review AR-07). Education and safeguarding context is judged per sentence
        # by _context.mitigations() instead, and Tier 3 hits go to the judge when one
        # is configured.
    ),
    # -- Short-termist extraction of the seed stock (Art. 6(1)) --------------
    PatternRule(
        code="SEED_STOCK_EXTRACTION",
        article="Art. 6(1)",
        reason="Consumes the seed stock or ranks short-term profit above life and safety.",
        pattern=(
            r"\bconsum\w*\s+(?:the\s+)?seed\s+(?:stock|corn)\b"
            r"|\bquarterly\s+(?:profits?|earnings|returns?|targets?|numbers)\s+(?:over|above|before"
            r"|at\s+the\s+expense\s+of)\s+"
            + GAP2
            + r"(?:safety|environment\w*|lives?|life|health|children|workers|future\s+generations)"
        ),
    ),
    PatternRule(
        code="SEED_STOCK_EXTRACTION",
        article="Art. 6(1)",
        reason="Sacrifices long-term safety or future generations for short-term financial metrics.",
        pattern=(
            r"\b(?:sacrific\w*|trad(?:e|ing)\s+(?:off|away)|mortgag\w*)\s+"
            + GAP2
            + r"(?:future\s+generations|long[- ]term\s+(?:safety|survival|health|well-?being"
            r"|stability|resilience)|(?:worker|public|patient|human|environmental)\s+safety)\b"
            r"[^.;]{0,40}?\b(?:profits?|earnings|revenue|yield|returns?|share\s+price|stock\s+price"
            r"|quarterly\s+\w+|90[- ]day\s+\w+|bonus(?:es)?)\b"
        ),
    ),
    PatternRule(
        code="SEED_STOCK_EXTRACTION",
        article="Art. 6(1)",
        reason="Depletes irreplaceable ecological stocks for financial return.",
        pattern=(
            r"\b(?:deplet\w*|exhaust\w*|strip[- ]min\w*|drain\w*|over-?pump\w*|clear-?cut\w*)\s+"
            + GAP2
            + r"(?:aquifers?|groundwater|topsoil|seed\s+(?:stock|banks?|vaults?)|fisher(?:y|ies)"
            r"|fish\s+stocks?|forests?|water\s+basins?|wetlands?)\b[^.;]{0,40}?\b(?:profits?"
            r"|revenue|yield|returns?|growth|earnings|output|quarter\w*)\b"
        ),
    ),
]


class Tier3InviolableEvaluator:
    """Screens the completion (POST), and optionally the prompt (PRE), against
    :data:`TIER3_RULES`, reading each hit in the context of its own sentence.

    For every rule hit, :func:`~seed_first_guardrail._context.mitigations` decides
    whether the sentence *proposes* the harm or only *mentions* it (negation,
    condemnation, question, legal/historical report, safeguarding).

    * **Proposal, no judge** -> block (a *confirmed* Tier 3 violation).
    * **Mention only, no judge** -> pass with ``review_flag`` (a near-miss for the
      KPIs and compliance agents).
    * **Any hit, judge configured** (``escalate=True``) -> pass with
      ``needs_judge``; the middleware's judge decides and fails closed.

    ``screen_prompts`` defaults to False so people may *ask about* harms (history,
    ethics, journalism, safeguarding); completions are always screened.

    🧒 The guard reads the whole sentence before shouting. "We should get rid of the
    villagers" gets stopped; "The court said getting rid of villagers was a crime"
    gets a sticky note for a grown-up to check, not a red card.
    """

    name = "tier3_inviolable"
    tier = FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
    phases = frozenset({Phase.PRE, Phase.POST})

    def __init__(
        self,
        extra_rules: list[PatternRule] | None = None,
        *,
        screen_prompts: bool = False,
        escalate: bool = False,
        include_text: bool = False,
    ) -> None:
        self.rules = TIER3_RULES + list(extra_rules or [])
        self.screen_prompts = screen_prompts
        self.escalate = escalate
        self.include_text = include_text

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.phase is Phase.PRE:
            if not self.screen_prompts:
                return EvaluationResult.ok(self.name, screened="none")
            text, screened = ctx.prompt, "prompt"
        else:
            text, screened = ctx.completion or "", "completion"

        norm = normalize(text)
        hits = []
        for rule, match in all_matches(self.rules, norm):
            hits.append((rule, match, mitigations(norm, match.start(), match.end())))
        if not hits:
            return EvaluationResult.ok(self.name, screened=screened)

        codes = sorted({rule.code for rule, _, _ in hits})
        proposals = [(rule, m) for rule, m, mit in hits if not mit]
        metrics: dict[str, object] = {
            "screened": screened,
            "lexical_hits": codes,
            "mitigations": sorted({x for _, _, mit in hits for x in mit}),
            "near_miss": True,
        }
        if self.escalate:
            return EvaluationResult.ok(self.name, needs_judge=True, **metrics)
        if not proposals:
            return EvaluationResult.ok(self.name, review_flag=True, **metrics)

        rule, match = proposals[0]
        metrics.update(article=rule.article, confirmed=True, match_length=len(match.group(0)))
        if self.include_text:
            metrics["matched"] = match.group(0)
        return EvaluationResult(
            passed=False,
            failing_tier=self.tier,
            code=rule.code,
            evaluator=self.name,
            reason=f"Violation of Tier 3 Inviolable Floor ({rule.article}): {rule.reason}",
            metrics=metrics,
        )
