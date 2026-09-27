"""Helpers shared by the SDK adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ..types import GuardrailDecision, GuardrailViolation


def content_to_text(content: Any) -> str:
    """Flatten a message ``content`` (string, list of parts/blocks, or object) into text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable) and not isinstance(content, (bytes, dict)):
        return "\n".join(filter(None, (_part_text(p) for p in content)))
    return _part_text(content)


def _part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if part.get("type", "text") == "text":
            return str(part.get("text", ""))
        return ""
    if getattr(part, "type", "text") == "text":
        return str(getattr(part, "text", "") or getattr(part, "content", "") or "")
    return ""


def messages_to_prompt(messages: Iterable[Any], system: Any = None) -> str:
    """Render a chat transcript as ``role: text`` lines for screening."""
    lines = []
    if system:
        lines.append(f"system: {content_to_text(system)}")
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", getattr(m, "type", ""))
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", m)
        lines.append(f"{role}: {content_to_text(content)}")
    return "\n".join(lines)


async def guarded_call(
    guardrail: SeedFirstGuardrailProxy,
    prompt: str,
    call: Any,
    extract: Any,
    options: dict[str, Any] | None,
) -> tuple[Any, GuardrailDecision]:
    """Run ``call()`` inside the guardrail; return the raw SDK response or raise.

    ``call`` is an async no-arg function returning the SDK response and ``extract``
    turns that response into completion text.
    """
    holder: dict[str, Any] = {}

    async def completion(_: str) -> str:
        holder["response"] = await call()
        return str(extract(holder["response"]))

    decision = await guardrail.inspect_and_execute(prompt, completion, **(options or {}))
    if not decision.approved:
        raise GuardrailViolation(decision)
    return holder["response"], decision
