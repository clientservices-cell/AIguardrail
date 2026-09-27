"""Guarded wrapper for ``openai.AsyncOpenAI().chat.completions``.

    from openai import AsyncOpenAI
    guarded = GuardedOpenAI(AsyncOpenAI(), SeedFirstGuardrailProxy(config))
    response = await guarded.chat.completions.create(model="...", messages=[...])

Blocked requests raise :class:`GuardrailViolation`. Streaming is not supported,
because the completion must be screened in full before anyone sees it.
"""

from __future__ import annotations

from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._common import guarded_call, messages_to_prompt


def _completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    return getattr(choices[0].message, "content", None) or ""


class _Completions:
    def __init__(self, owner: GuardedOpenAI) -> None:
        self._owner = owner

    async def create(
        self, *, guardrail_options: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        if kwargs.get("stream"):
            raise ValueError(
                "GuardedOpenAI does not support stream=True; completions must be "
                "screened in full before release."
            )
        prompt = messages_to_prompt(kwargs.get("messages", []))
        response, _ = await guarded_call(
            self._owner.guardrail,
            prompt,
            lambda: self._owner.client.chat.completions.create(**kwargs),
            _completion_text,
            guardrail_options,
        )
        return response


class _Chat:
    def __init__(self, owner: GuardedOpenAI) -> None:
        self.completions = _Completions(owner)


class GuardedOpenAI:
    def __init__(self, client: Any, guardrail: SeedFirstGuardrailProxy) -> None:
        self.client = client
        self.guardrail = guardrail
        self.chat = _Chat(self)
