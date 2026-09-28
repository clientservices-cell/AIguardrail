"""Helpers shared by the SDK adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from ..evaluators.tier1 import estimate_inference_kwh
from ..middleware import SeedFirstGuardrailProxy
from ..types import GuardrailDecision, GuardrailViolation
from ._channels import Extracted, content_parts, generic_value


def content_to_text(content: Any) -> str:
    """Flatten a message ``content`` (string, list of parts/blocks, or object) into text."""
    return content_parts(content).text


def messages_to_prompt(messages: Iterable[Any], system: Any = None) -> str:
    """Render a chat transcript (every channel) as text for screening."""
    out = content_parts(system, "system")
    for m in messages:
        out.merge(generic_value(m))
    return out.text


def _usage_tokens(response: Any) -> int | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if isinstance(total, int):
        return total
    parts = [
        getattr(usage, k, None)
        for k in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")
    ]
    counted = [p for p in parts if isinstance(p, int)]
    return sum(counted) if counted else None


async def guarded_call(
    guardrail: SeedFirstGuardrailProxy,
    request: Extracted,
    call: Callable[[], Awaitable[Any]],
    extract: Callable[[Any], Extracted],
    options: dict[str, Any] | None,
    *,
    meter_energy: bool = True,
) -> tuple[Any, GuardrailDecision]:
    """Run ``call()`` inside the guardrail; return the raw SDK response or raise.

    Screens every channel of the request and the response. Content that cannot be
    inspected is refused unless the policy sets ``unscreenable_content='allow'``.
    Energy is reconciled from the response's token usage when available.
    """
    opts = dict(options or {})
    metadata = dict(opts.pop("metadata", None) or {})
    channels: list[str] = sorted(request.channels) or ["text"]
    metadata["channels"] = channels  # the same list object is extended after the call
    block_unscreenable = guardrail.config.unscreenable_content == "block"
    who = {k: opts.get(k) for k in ("principal", "tenant")}

    if request.unscreenable and block_unscreenable:
        decision = guardrail.block_unscreenable(
            request.text, sorted(request.unscreenable), metadata=metadata, **who
        )
        raise GuardrailViolation(decision)

    holder: dict[str, Any] = {}

    async def completion(_: str) -> str:
        holder["response"] = await call()
        extracted = extract(holder["response"])
        holder["unscreenable"] = extracted.unscreenable
        channels.extend(sorted(extracted.channels - set(channels)))
        return extracted.text

    decision = await guardrail.inspect_and_execute(
        request.text, completion, metadata=metadata, **opts
    )
    if not decision.approved:
        raise GuardrailViolation(decision)
    if holder.get("unscreenable") and block_unscreenable:
        raise GuardrailViolation(
            guardrail.block_unscreenable(
                request.text, sorted(holder["unscreenable"]), metadata=metadata, **who
            )
        )
    if meter_energy:
        tokens = _usage_tokens(holder["response"])
        if tokens is not None:
            guardrail.record_actual_energy(
                decision, estimate_inference_kwh(tokens), tenant=who["tenant"], metadata=metadata
            )
    return holder["response"], decision
