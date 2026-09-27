"""Guard any LangChain ``Runnable`` (chat model, chain, agent).

    guarded = GuardedRunnable(ChatAnthropic(model="claude-opus-5") | parser, guardrail)
    result = await guarded.ainvoke("How should we allocate the village well?")

    # Or compose it back into LCEL:
    chain = prompt | guarded.as_runnable()

Blocked calls raise :class:`GuardrailViolation`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._common import content_to_text, guarded_call, messages_to_prompt


def input_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if hasattr(value, "to_string"):  # PromptValue
        return str(value.to_string())
    if isinstance(value, dict):
        for key in ("input", "question", "query", "prompt"):
            if key in value:
                return input_to_text(value[key])
        return "\n".join(f"{k}: {input_to_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return messages_to_prompt(value)
    return str(value)


def output_to_text(value: Any) -> str:
    if hasattr(value, "content"):  # AIMessage
        return content_to_text(value.content)
    if isinstance(value, dict):
        for key in ("output", "answer", "text", "result"):
            if key in value:
                return output_to_text(value[key])
    return str(value)


class GuardedRunnable:
    def __init__(
        self,
        runnable: Any,
        guardrail: SeedFirstGuardrailProxy,
        guardrail_options: dict[str, Any] | None = None,
    ) -> None:
        self.runnable = runnable
        self.guardrail = guardrail
        self.guardrail_options = guardrail_options

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        result, _ = await guarded_call(
            self.guardrail,
            input_to_text(input),
            lambda: self.runnable.ainvoke(input, config, **kwargs),
            output_to_text,
            self.guardrail_options,
        )
        return result

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        """Synchronous entry point. Use :meth:`ainvoke` inside a running event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(input, config, **kwargs))
        raise RuntimeError("GuardedRunnable.invoke() called inside an event loop; use ainvoke()")

    def as_runnable(self) -> Any:
        """Return a ``langchain_core`` ``RunnableLambda`` (requires the ``langchain`` extra)."""
        from langchain_core.runnables import RunnableLambda

        async def _call(value: Any) -> Any:
            return await self.ainvoke(value)

        return RunnableLambda(self.invoke, afunc=_call, name="SeedFirstGuardrail")
