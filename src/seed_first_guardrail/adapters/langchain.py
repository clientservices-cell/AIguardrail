"""Guard any LangChain ``Runnable`` (chat model, chain, agent).

    guarded = GuardedRunnable(ChatAnthropic(model="claude-opus-5") | parser, guardrail)
    result = await guarded.ainvoke({"input": "How should we allocate the village well?"})

    # Or compose it back into LCEL:
    chain = prompt | guarded.as_runnable()

Every string in the input is screened (all dict values, message content and tool calls,
not just the ``input`` key), and so is every output channel, including
``AIMessage.tool_calls`` (review AR-01). Blocked calls raise :class:`GuardrailViolation`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..middleware import SeedFirstGuardrailProxy
from ._channels import generic_value
from ._common import guarded_call


def input_to_text(value: Any) -> str:
    return generic_value(value).text


def output_to_text(value: Any) -> str:
    return generic_value(value).text


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
            generic_value(input),
            lambda: self.runnable.ainvoke(input, config, **kwargs),
            generic_value,
            self.guardrail_options,
            meter_energy=False,
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
