"""Guard a LlamaIndex LLM (``llama_index.core.llms.LLM``).

    guarded = GuardedLlamaIndexLLM(Anthropic(model="claude-opus-5"), guardrail)
    response = await guarded.acomplete("Draft a water-sharing plan")
    chat = await guarded.achat([ChatMessage(role="user", content="...")])

Screens message content and tool calls in both directions (review AR-01). Blocked calls
raise :class:`GuardrailViolation`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._channels import Extracted, generic_value
from ._common import guarded_call


def _completion(response: Any) -> Extracted:
    return generic_value(getattr(response, "text", "") or "")


def _chat(response: Any) -> Extracted:
    return generic_value(getattr(response, "message", None))


class GuardedLlamaIndexLLM:
    def __init__(
        self,
        llm: Any,
        guardrail: SeedFirstGuardrailProxy,
        guardrail_options: dict[str, Any] | None = None,
    ) -> None:
        self.llm = llm
        self.guardrail = guardrail
        self.guardrail_options = guardrail_options

    async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
        response, _ = await guarded_call(
            self.guardrail,
            generic_value(prompt),
            lambda: self.llm.acomplete(prompt, **kwargs),
            _completion,
            self.guardrail_options,
            meter_energy=False,
        )
        return response

    async def achat(self, messages: Sequence[Any], **kwargs: Any) -> Any:
        response, _ = await guarded_call(
            self.guardrail,
            generic_value(list(messages)),
            lambda: self.llm.achat(messages, **kwargs),
            _chat,
            self.guardrail_options,
            meter_energy=False,
        )
        return response
