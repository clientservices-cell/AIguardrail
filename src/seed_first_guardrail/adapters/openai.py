"""Guarded wrapper for ``openai.AsyncOpenAI().chat.completions``.

    from openai import AsyncOpenAI
    guarded = GuardedOpenAI(AsyncOpenAI(), SeedFirstGuardrailProxy(config))
    response = await guarded.chat.completions.create(model="...", messages=[...])

Every channel is screened: message text, tool results and assistant tool-call history on
the way in; **all** choices, ``tool_calls`` arguments, legacy ``function_call`` and
``refusal`` on the way out. Images, audio and files are refused unless the policy sets
``unscreenable_content='allow'`` (review AR-01). Blocked requests raise
:class:`GuardrailViolation`. Streaming is not supported.
"""

from __future__ import annotations

from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._channels import openai_request, openai_response
from ._common import guarded_call


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
        response, _ = await guarded_call(
            self._owner.guardrail,
            openai_request(kwargs),
            lambda: self._owner._client.chat.completions.create(**kwargs),
            openai_response,
            guardrail_options,
            model=kwargs.get("model"),
            meter_energy=self._owner.meter_energy,
        )
        return response


class _Chat:
    def __init__(self, owner: GuardedOpenAI) -> None:
        self.completions = _Completions(owner)


class GuardedOpenAI:
    def __init__(
        self, client: Any, guardrail: SeedFirstGuardrailProxy, *, meter_energy: bool = True
    ) -> None:
        self._client = client  # private: callers should not bypass the guard
        self.guardrail = guardrail
        self.meter_energy = meter_energy
        self.chat = _Chat(self)
