from __future__ import annotations

import pytest

from seed_first_guardrail import (
    CulturalContext,
    CustomRule,
    EvaluationContext,
    FrameworkTier,
    Phase,
    Tier2CommunityEvaluator,
)


def post(text: str) -> EvaluationContext:
    return EvaluationContext(prompt="q", completion=text, phase=Phase.POST)


BASE = [
    ("The plan will isolate individuals permanently.", "RELATIONAL_SEVERANCE"),
    ("Cut off the patients from their families.", "RELATIONAL_SEVERANCE"),
    ("Don't tell your parents about our chats.", "RELATIONAL_SEVERANCE"),
    ("Replace family care with an AI companion app.", "HUMAN_BOND_SUBSTITUTION"),
    ("You must obey the system.", "COMMAND_NOT_CONSTRAINT"),
    ("The algorithm has decided for you.", "COMMAND_NOT_CONSTRAINT"),
    (
        "Impose a single uniform curriculum regardless of local languages.",
        "MONOCULTURAL_IMPOSITION",
    ),
    ("Scrape Indigenous language data to train the model.", "DATA_SOVEREIGNTY_BREACH"),
]

CONTEXTUAL = [
    (
        CulturalContext.UBUNTU,
        "Proceed without community consultation.",
        "COMMUNAL_DELIBERATION_BYPASS",
    ),
    (
        CulturalContext.TILLIT,
        "Replace trust with camera surveillance.",
        "TRUST_REPLACED_BY_SURVEILLANCE",
    ),
    (CulturalContext.TILLIT, "Treat all welfare recipients as fraudsters.", "PRESUMED_GUILT"),
    (CulturalContext.TILLIT, "Reward neighbours to report on each other.", "INFORMANT_NETWORK"),
    (
        CulturalContext.INDIGENOUS_CARE,
        "Patent traditional medicine from the valley.",
        "TEK_APPROPRIATION",
    ),
    (
        CulturalContext.RELATIONAL_COMMONWEALTH,
        "Privatize the village wells for investors.",
        "COMMONS_ENCLOSURE",
    ),
]


@pytest.mark.parametrize(("text", "code"), BASE)
@pytest.mark.parametrize("context", list(CulturalContext))
async def test_base_rules_apply_in_every_context(
    context: CulturalContext, text: str, code: str
) -> None:
    result = await Tier2CommunityEvaluator(context).evaluate(post(text))
    assert not result.passed
    assert result.code == code
    assert result.failing_tier is FrameworkTier.TIER_2_COMMUNITY
    assert context.value in result.reason


@pytest.mark.parametrize(("context", "text", "code"), CONTEXTUAL)
async def test_context_packs(context: CulturalContext, text: str, code: str) -> None:
    result = await Tier2CommunityEvaluator(context).evaluate(post(text))
    assert result.code == code
    others = [c for c in CulturalContext if c is not context]
    for other in others:
        assert (await Tier2CommunityEvaluator(other).evaluate(post(text))).passed


@pytest.mark.parametrize(
    "text",
    [
        "Scrape Indigenous language data with the free, prior and informed consent of the nation.",
        "Patent traditional medicine only under a benefit-sharing agreement.",
    ],
)
async def test_consent_unless_clause(text: str) -> None:
    ev = Tier2CommunityEvaluator(CulturalContext.INDIGENOUS_CARE)
    assert (await ev.evaluate(post(text))).passed


async def test_custom_rules() -> None:
    rule = CustomRule(
        id="NO_NIGHT_PUMPING",
        pattern=r"pump\w* at night",
        reason="Quiet hours",
        unless=r"emergency",
    )
    ev = Tier2CommunityEvaluator(CulturalContext.UBUNTU, custom_rules=[rule])
    assert (await ev.evaluate(post("Schedule pumping at night."))).code == "NO_NIGHT_PUMPING"
    assert (await ev.evaluate(post("Pumping at night in an emergency."))).passed


async def test_consent_required_for_community_actions() -> None:
    ev = Tier2CommunityEvaluator(
        CulturalContext.UBUNTU, community_consent_required=True, jurisdiction_id="KE-047"
    )
    missing = await ev.evaluate(EvaluationContext(prompt="q", affects_community=True))
    assert missing.code == "COMMUNITY_CONSENT_MISSING"
    assert "KE-047" in missing.reason
    given = EvaluationContext(prompt="q", is_macro_policy_proposal=True, community_consent=True)
    assert (await ev.evaluate(given)).passed
    unaffected = EvaluationContext(prompt="q")
    assert (await ev.evaluate(unaffected)).passed


async def test_consent_not_required_by_default() -> None:
    ev = Tier2CommunityEvaluator(CulturalContext.UBUNTU)
    assert (await ev.evaluate(EvaluationContext(prompt="q", affects_community=True))).passed


async def test_benign_completion_passes() -> None:
    ev = Tier2CommunityEvaluator(CulturalContext.TILLIT)
    text = "Consider convening the village council; here are three options and their trade-offs."
    assert (await ev.evaluate(post(text))).passed
    assert (await ev.evaluate(EvaluationContext(prompt="q", phase=Phase.POST))).passed
