"""Guarded wrapper for ``anthropic.AsyncAnthropic().messages``.

    from anthropic import AsyncAnthropic
    guarded = GuardedAnthropic(AsyncAnthropic(), SeedFirstGuardrailProxy(config))
    message = await guarded.messages.create(
        model="claude-opus-5", max_tokens=16000,
        messages=[{"role": "user", "content": "..."}],
        guardrail_options={"principal": user_id},
    )

Every channel is screened: system prompt, message text, tool results and text
documents on the way in; text, ``tool_use`` inputs and thinking on the way out.
Images, audio, PDFs and unknown block types are refused unless the policy sets
``unscreenable_content='allow'`` (review AR-01). Blocked requests raise
:class:`GuardrailViolation`. Streaming is not supported: a completion must be screened
in full before anyone sees it. For guarantees that cannot be bypassed, deploy the
guardrail at an egress gateway rather than relying on callers to use this wrapper.
"""

from __future__ import annotations

from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._channels import anthropic_request, anthropic_response
from ._common import guarded_call


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
        response, _ = await guarded_call(
            self._owner.guardrail,
            anthropic_request(kwargs),
            lambda: self._owner._client.messages.create(**kwargs),
            anthropic_response,
            guardrail_options,
            model=kwargs.get("model"),
            meter_energy=self._owner.meter_energy,
        )
        return response


class GuardedAnthropic:
    def __init__(
        self, client: Any, guardrail: SeedFirstGuardrailProxy, *, meter_energy: bool = True
    ) -> None:
        self._client = client  # private: callers should not bypass the guard
        self.guardrail = guardrail
        self.meter_energy = meter_energy
        self.messages = _Messages(self)
