"""Guarded wrapper for ``anthropic.AsyncAnthropic().messages``.

    from anthropic import AsyncAnthropic
    guarded = GuardedAnthropic(AsyncAnthropic(), SeedFirstGuardrailProxy(config))
    message = await guarded.messages.create(
        model="claude-opus-5", max_tokens=16000, messages=[{"role": "user", "content": "..."}]
    )

Blocked requests raise :class:`GuardrailViolation`. Streaming is not supported,
because the completion must be screened in full before anyone sees it. A response
with ``stop_reason == "refusal"`` has no text and passes through unchanged.
"""

from __future__ import annotations

from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._common import guarded_call, messages_to_prompt


def _message_text(message: Any) -> str:
    return "".join(
        getattr(block, "text", "")
        for block in getattr(message, "content", None) or []
        if getattr(block, "type", None) == "text"
    )


class _Messages:
    def __init__(self, owner: GuardedAnthropic) -> None:
        self._owner = owner

    async def create(
        self, *, guardrail_options: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        if kwargs.get("stream"):
            raise ValueError(
                "GuardedAnthropic does not support stream=True; completions must be "
                "screened in full before release."
            )
        prompt = messages_to_prompt(kwargs.get("messages", []), system=kwargs.get("system"))
        response, _ = await guarded_call(
            self._owner.guardrail,
            prompt,
            lambda: self._owner.client.messages.create(**kwargs),
            _message_text,
            guardrail_options,
        )
        return response


class GuardedAnthropic:
    def __init__(self, client: Any, guardrail: SeedFirstGuardrailProxy) -> None:
        self.client = client
        self.guardrail = guardrail
        self.messages = _Messages(self)
