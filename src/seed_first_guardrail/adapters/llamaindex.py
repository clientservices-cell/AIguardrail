"""Guard a LlamaIndex LLM (``llama_index.core.llms.LLM``).

    guarded = GuardedLlamaIndexLLM(Anthropic(model="claude-opus-5"), guardrail)
    response = await guarded.acomplete("Draft a water-sharing plan")
    chat = await guarded.achat([ChatMessage(role="user", content="...")])

Blocked calls raise :class:`GuardrailViolation`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._common import content_to_text, guarded_call, messages_to_prompt


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
            prompt,
            lambda: self.llm.acomplete(prompt, **kwargs),
            lambda r: getattr(r, "text", "") or "",
            self.guardrail_options,
        )
        return response

    async def achat(self, messages: Sequence[Any], **kwargs: Any) -> Any:
        response, _ = await guarded_call(
            self.guardrail,
            messages_to_prompt(messages),
            lambda: self.llm.achat(messages, **kwargs),
            lambda r: content_to_text(getattr(getattr(r, "message", None), "content", "")),
            self.guardrail_options,
        )
        return response
