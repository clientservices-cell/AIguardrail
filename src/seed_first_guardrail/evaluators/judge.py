"""LLM-as-judge evaluator driven by the zero-shot templates in :mod:`classifiers.prompts`.

The judge catches what lexical rules cannot: paraphrase, euphemism, other languages and
subtle erosion of trust or agency. It is provider-neutral -- pass any async callable that
takes a prompt string and returns the judge model's text -- and ships factories for the
Anthropic and OpenAI SDKs.

**Failure handling (review AR-08).** Every exception, timeout, unparseable verdict or
nonce mismatch is caught per template. Tier 3 templates *always* fail closed; other
templates follow ``fail_closed``. Such failures are marked ``infrastructure_error`` so the
circuit breaker never counts them (a judge outage must not become a denial of service).

🧒 The judge is a referee who can understand tricky wording. If the referee's radio goes
quiet, the most important plays are stopped until it comes back -- but nobody gets a red
card just because the radio broke.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from ..classifiers.prompts import CAPABILITY_SUPPORT, DEFAULT_TEMPLATES, JudgeTemplate, new_nonce
from ..types import CulturalContext, EvaluationContext, EvaluationResult, FrameworkTier, Phase

JudgeFn = Callable[[str], Awaitable[str]]

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nonce": {"type": "string"},
        "violation": {"type": "boolean"},
        "score": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["nonce", "violation", "score", "rationale"],
    "additionalProperties": False,
}

#: Returned by the SDK judges when the judge model declines; always read as a violation.
REFUSAL_VERDICT = json.dumps(
    {"refusal": True, "rationale": "The judge model declined to evaluate this content."}
)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_TIER_RANK = {
    FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR: 0,
    FrameworkTier.TIER_1_PLANETARY: 1,
    FrameworkTier.TIER_2_COMMUNITY: 2,
}


class JudgeParseError(ValueError):
    pass


def _load(text: str, nonce: str | None) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text)
    if not match:
        raise JudgeParseError(f"no JSON object in judge output: {text[:200]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"malformed JSON in judge output: {exc}") from exc
    if not isinstance(data, dict):
        raise JudgeParseError("judge output is not a JSON object")
    if data.get("refusal") is True:
        return data
    if nonce is not None and data.get("nonce") != nonce:
        raise JudgeParseError("verdict nonce missing or wrong (possible forged verdict)")
    return data


def parse_verdict(text: str, nonce: str | None = None) -> tuple[bool, float, str]:
    """Extract ``(violation, score, rationale)`` from a judge response.

    With ``nonce``, the verdict must echo it. A judge refusal is a violation.
    """
    data = _load(text, nonce)
    if data.get("refusal") is True:
        return True, 1.0, str(data.get("rationale", "judge declined"))
    if not isinstance(data.get("violation"), bool):
        raise JudgeParseError("judge output lacks a boolean 'violation' field")
    score = data.get("score", 1.0 if data["violation"] else 0.0)
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score != score:
        raise JudgeParseError("judge 'score' must be a finite number")
    return data["violation"], min(max(float(score), 0.0), 1.0), str(data.get("rationale", ""))


class LLMJudgeEvaluator:
    """Runs every blocking template concurrently against the completion (POST only).

    A template fires when the judge reports ``violation: true`` or a score at or above
    ``threshold``. See the module docstring for failure handling.
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
        timeout_s: float = 20.0,
    ) -> None:
        templates = tuple(t for t in templates if t.blocking)
        if not templates:
            raise ValueError("at least one blocking judge template is required")
        self.judge = judge
        self.templates = templates
        self.context = context
        self.threshold = threshold
        self.fail_closed = fail_closed
        self.timeout_s = timeout_s

    def _error(self, template: JudgeTemplate, exc: BaseException) -> EvaluationResult:
        blocks = self.fail_closed or template.tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
        return EvaluationResult(
            passed=not blocks,
            failing_tier=template.tier if blocks else None,
            code="JUDGE_ERROR",
            evaluator=f"{self.name}:{template.name}",
            reason=(
                f"The judge could not verify this response ({type(exc).__name__}); "
                + ("failing closed." if blocks else "failing open by policy.")
            ),
            metrics={"template": template.name, "infrastructure_error": True},
        )

    async def _run(self, template: JudgeTemplate, ctx: EvaluationContext) -> EvaluationResult:
        nonce = new_nonce()
        rendered = template.render(
            prompt=ctx.prompt, completion=ctx.completion or "", context=self.context, nonce=nonce
        )
        try:
            raw = await asyncio.wait_for(self.judge(rendered), timeout=self.timeout_s)
            violation, score, rationale = parse_verdict(raw, nonce)
        except Exception as exc:  # timeouts, rate limits, parse errors, forged verdicts
            return self._error(template, exc)

        metrics = {"template": template.name, "score": score, "rationale": rationale}
        if violation or score >= self.threshold:
            return EvaluationResult(
                passed=False,
                failing_tier=template.tier,
                code=template.code,
                evaluator=f"{self.name}:{template.name}",
                reason=f"LLM judge flagged {template.code} ({template.article}).",
                metrics={**metrics, "confirmed": True},
            )
        return EvaluationResult(True, evaluator=f"{self.name}:{template.name}", metrics=metrics)

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        results = await asyncio.gather(*(self._run(t, ctx) for t in self.templates))
        failures = [r for r in results if not r.passed]
        if failures:
            return min(failures, key=lambda r: _TIER_RANK.get(r.failing_tier, 9))  # type: ignore[arg-type]
        scores = {r.metrics["template"]: r.metrics.get("score") for r in results}
        errors = [r.metrics["template"] for r in results if r.metrics.get("infrastructure_error")]
        metrics: dict[str, Any] = {"scores": scores}
        if errors:
            metrics["infrastructure_error"] = True
            metrics["failed_templates"] = errors
        return EvaluationResult.ok(self.name, **metrics)


class CapabilitySupportMonitor:
    """Non-blocking: measures whether responses scaffold or substitute (KPI K-23, CA-10).

    It never blocks -- blocking on it would itself eliminate the struggle the guiding
    principle protects. Errors are recorded and ignored.

    🧒 A coach watching whether the helper gives you tips (so you get stronger) or just
    does the whole thing for you. The coach only takes notes; it never stops the game.
    """

    name = "capability_support"
    tier = FrameworkTier.TIER_2_COMMUNITY
    phases = frozenset({Phase.POST})

    def __init__(
        self,
        judge: JudgeFn,
        *,
        context: CulturalContext = CulturalContext.UBUNTU,
        timeout_s: float = 20.0,
    ) -> None:
        self.judge = judge
        self.context = context
        self.timeout_s = timeout_s

    async def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        nonce = new_nonce()
        rendered = CAPABILITY_SUPPORT.render(
            prompt=ctx.prompt, completion=ctx.completion or "", context=self.context, nonce=nonce
        )
        try:
            data = _load(
                await asyncio.wait_for(self.judge(rendered), timeout=self.timeout_s), nonce
            )
            context, mode = (
                str(data.get("context", "other")),
                str(data.get("mode", "not_applicable")),
            )
            if context not in {"learning", "task", "other"} or mode not in {
                "scaffold",
                "substitute",
                "mixed",
                "not_applicable",
            }:
                raise JudgeParseError("unexpected capability labels")
        except Exception as exc:
            return EvaluationResult.ok(self.name, capability_error=type(exc).__name__)
        return EvaluationResult.ok(self.name, capability={"context": context, "mode": mode})


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
    retried server-side on a fallback model. If the whole chain declines, the verdict
    is a refusal, which the evaluator treats as a violation (fail closed).
    """

    async def judge(prompt: str) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": effort},
        }
        if '"violation"' in prompt:  # blocking templates have a fixed verdict schema
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": VERDICT_SCHEMA}
        if use_fallbacks:
            response = await client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = await client.messages.create(**kwargs)
        if getattr(response, "stop_reason", None) == "refusal":
            return REFUSAL_VERDICT
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
