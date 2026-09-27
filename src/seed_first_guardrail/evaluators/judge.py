"""LLM-as-judge evaluator driven by the zero-shot templates in :mod:`classifiers.prompts`.

The judge catches what lexical rules cannot: paraphrase, euphemism and subtle
erosion of trust or agency. It is provider-neutral -- pass any async callable that
takes a prompt string and returns the judge model's text -- and ships factories
for the Anthropic and OpenAI SDKs.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from ..classifiers.prompts import DEFAULT_TEMPLATES, JudgeTemplate
from ..types import CulturalContext, EvaluationContext, EvaluationResult, FrameworkTier, Phase

JudgeFn = Callable[[str], Awaitable[str]]

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "violation": {"type": "boolean"},
        "score": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["violation", "score", "rationale"],
    "additionalProperties": False,
}

_REFUSAL_VERDICT = json.dumps(
    {
        "violation": True,
        "score": 1.0,
        "rationale": "The judge model declined to evaluate this content (stop_reason=refusal).",
    }
)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_TIER_RANK = {
    FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR: 0,
    FrameworkTier.TIER_1_PLANETARY: 1,
    FrameworkTier.TIER_2_COMMUNITY: 2,
}


class JudgeParseError(ValueError):
    pass


def parse_verdict(text: str) -> tuple[bool, float, str]:
    """Extract ``(violation, score, rationale)`` from a judge response."""
    match = _JSON_OBJECT.search(text)
    if not match:
        raise JudgeParseError(f"no JSON object in judge output: {text[:200]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"malformed JSON in judge output: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("violation"), bool):
        raise JudgeParseError("judge output lacks a boolean 'violation' field")
    score = data.get("score", 1.0 if data["violation"] else 0.0)
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise JudgeParseError("judge 'score' must be a number")
    return data["violation"], min(max(float(score), 0.0), 1.0), str(data.get("rationale", ""))


class LLMJudgeEvaluator:
    """Runs every template concurrently against the completion (POST phase only).

    A template fires when the judge reports ``violation: true`` or a score at or above
    ``threshold``. Unparseable judge output blocks when ``fail_closed`` is set, and
    always blocks for Tier 3 templates.
    """

    name = "llm_judge"
    tier = FrameworkTier.TIER_2_COMMUNITY
    phases = frozenset({Phase.POST})

    def __init__(
        self,
        judge: JudgeFn,
        *,
        templates: Sequence[JudgeTemplate] = DEFAULT_TEMPLATES,
        context: CulturalContext = CulturalContext.UBUNTU,
        threshold: float = 0.5,
        fail_closed: bool = True,
    ) -> None:
        if not templates:
            raise ValueError("at least one judge template is required")
        self.judge = judge
        self.templates = tuple(templates)
        self.context = context
        self.threshold = threshold
        self.fail_closed = fail_closed

    async def _run(self, template: JudgeTemplate, ctx: EvaluationContext) -> EvaluationResult:
        rendered = template.render(
            prompt=ctx.prompt, completion=ctx.completion or "", context=self.context
        )
        try:
            violation, score, rationale = parse_verdict(await self.judge(rendered))
        except JudgeParseError as exc:
            blocks = (
                self.fail_closed or template.tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
            )
            return EvaluationResult(
                passed=not blocks,
                failing_tier=template.tier if blocks else None,
                code="JUDGE_ERROR",
                evaluator=f"{self.name}:{template.name}",
                reason=f"Judge output could not be verified ({exc}); failing closed.",
                metrics={"template": template.name, "error": str(exc)},
            )

        metrics = {"template": template.name, "score": score, "rationale": rationale}
        if violation or score >= self.threshold:
            return EvaluationResult(
                passed=False,
                failing_tier=template.tier,
                code=template.code,
                evaluator=f"{self.name}:{template.name}",
                reason=f"LLM judge flagged {template.code} ({template.article}): {rationale}",
                metrics=metrics,
            )
        return EvaluationResult(True, evaluator=f"{self.name}:{template.name}", metrics=metrics)

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        results = await asyncio.gather(*(self._run(t, ctx) for t in self.templates))
        failures = [r for r in results if not r.passed]
        if failures:
            return min(failures, key=lambda r: _TIER_RANK.get(r.failing_tier, 9))  # type: ignore[arg-type]
        return EvaluationResult.ok(
            self.name, scores={r.metrics["template"]: r.metrics.get("score") for r in results}
        )


def anthropic_judge(
    client: Any,
    model: str = "claude-opus-5",
    *,
    max_tokens: int = 2048,
    effort: str = "low",
    use_fallbacks: bool = True,
) -> JudgeFn:
    """Build a judge on an ``anthropic.AsyncAnthropic`` client.

    Uses structured outputs so the verdict is always schema-valid JSON, and ``low``
    effort because this is a classification call. With ``use_fallbacks`` (Claude API
    only -- set False on Bedrock, Vertex AI or Foundry) a model that declines is
    retried server-side on a fallback model. If the whole chain declines, the
    verdict is a violation: the guardrail fails closed on content a judge won't review.
    """

    async def judge(prompt: str) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
            },
        }
        if use_fallbacks:
            response = await client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = await client.messages.create(**kwargs)
        if getattr(response, "stop_reason", None) == "refusal":
            return _REFUSAL_VERDICT
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    return judge


def openai_judge(client: Any, model: str, *, max_tokens: int = 512) -> JudgeFn:
    """Build a judge on an ``openai.AsyncOpenAI`` client. ``model`` is required."""

    async def judge(prompt: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    return judge
