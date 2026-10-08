"""Adapters are tested against duck-typed fakes -- no SDKs or network needed."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from seed_first_guardrail import GuardrailViolation, SeedFirstGuardrailProxy
from seed_first_guardrail.adapters import (
    GuardedAnthropic,
    GuardedLlamaIndexLLM,
    GuardedOpenAI,
    GuardedRunnable,
)
from seed_first_guardrail.adapters._common import content_to_text, messages_to_prompt
from seed_first_guardrail.adapters.langchain import input_to_text, output_to_text

from .conftest import HARMFUL, SAFE

Factory = Callable[..., SeedFirstGuardrailProxy]


def test_content_to_text() -> None:
    assert content_to_text(None) == ""
    assert content_to_text("a") == "a"
    parts = [
        {"type": "text", "text": "a"},
        {"type": "image_url", "image_url": {}},  # unscreenable: reported, not text
        SimpleNamespace(type="text", text="b"),
        SimpleNamespace(type="tool_use", name="lookup", input={"q": "c"}),
        "d",
    ]
    assert content_to_text(parts) == 'a\nb\nlookup {"q": "c"}\nd'
    assert content_to_text(SimpleNamespace(text="e")) == "e"


def test_messages_to_prompt() -> None:
    msgs = [{"role": "user", "content": "hi"}, SimpleNamespace(role="assistant", content="yo")]
    text = messages_to_prompt(msgs, system="be kind")
    assert text.splitlines()[0] == "be kind"
    assert "hi" in text and "yo" in text


def test_channel_extraction_edge_cases() -> None:
    from seed_first_guardrail.adapters._channels import (
        anthropic_request,
        block_parts,
        generic_value,
        openai_response,
    )

    req = anthropic_request(
        {
            "system": [{"type": "text", "text": "sys"}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "text", "data": "doc text"}},
                        {
                            "type": "document",
                            "source": {
                                "type": "content",
                                "content": [{"type": "text", "text": "inner"}],
                            },
                        },
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf"},
                        },
                        {"type": "redacted_thinking", "data": "x"},
                        {"type": "mystery"},
                    ],
                }
            ],
            "tools": [{"name": "t", "description": "desc"}],
        }
    )
    assert {"system", "document", "tool_definition"} <= req.channels
    assert req.unscreenable == {"document:application/pdf", "unknown:mystery"}
    assert block_parts({"type": "refusal", "refusal": "no"}).text == "no"

    legacy = SimpleNamespace(
        content=None,
        refusal="nope",
        tool_calls=None,
        function_call=SimpleNamespace(name="f", arguments="not json"),
        audio=object(),
    )
    out = openai_response(SimpleNamespace(choices=[SimpleNamespace(message=legacy)]))
    assert "nope" in out.text and "f not json" in out.text and "audio" in out.unscreenable

    msg = SimpleNamespace(
        content="hi",
        tool_calls=[{"name": "go", "args": {"a": 1}}],
        additional_kwargs={"tool_calls": [{"function": {"name": "h", "arguments": "{}"}}]},
    )
    assert generic_value(msg).channels == {"text", "tool_use"}
    assert generic_value({1, 2.5}).text in ("1\n2.5", "2.5\n1")
    assert generic_value(object()).text.startswith("<object")
    assert generic_value(None).text == ""


# -- OpenAI ------------------------------------------------------------------------


def fake_openai(text: str | None) -> Any:
    calls: list[dict[str, Any]] = []

    async def create(**kw: Any) -> Any:
        calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.calls = calls
    return client


async def test_openai_approved(make_guardrail: Factory) -> None:
    client = fake_openai(SAFE)
    guarded = GuardedOpenAI(client, make_guardrail())
    resp = await guarded.chat.completions.create(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        guardrail_options={"estimated_kwh": 0.01},
    )
    assert resp.choices[0].message.content == SAFE
    assert "guardrail_options" not in client.calls[0]


async def test_openai_blocked(make_guardrail: Factory) -> None:
    guarded = GuardedOpenAI(fake_openai(HARMFUL), make_guardrail())
    with pytest.raises(GuardrailViolation) as exc:
        await guarded.chat.completions.create(model="m", messages=[])
    assert exc.value.decision.code == "POPULATION_HARM"
    assert "TIER_3" in str(exc.value)


async def test_openai_empty_and_stream(make_guardrail: Factory) -> None:
    guarded = GuardedOpenAI(fake_openai(None), make_guardrail())
    assert (await guarded.chat.completions.create(model="m", messages=[])) is not None

    async def no_choices(**_: Any) -> Any:
        return SimpleNamespace(choices=[])

    empty = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=no_choices)))
    assert await GuardedOpenAI(empty, make_guardrail()).chat.completions.create(messages=[])
    with pytest.raises(ValueError, match="stream"):
        await guarded.chat.completions.create(model="m", messages=[], stream=True)


# -- Anthropic ---------------------------------------------------------------------


def fake_anthropic(text: str) -> Any:
    async def create(**kw: Any) -> Any:
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=text),
            ],
        )

    return SimpleNamespace(messages=SimpleNamespace(create=create))


async def test_anthropic_approved_and_blocked(make_guardrail: Factory) -> None:
    ok = GuardedAnthropic(fake_anthropic(SAFE), make_guardrail())
    msg = await ok.messages.create(
        model="claude-opus-5",
        max_tokens=100,
        system="sys",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )
    assert msg.content[1].text == SAFE

    bad = GuardedAnthropic(fake_anthropic(HARMFUL), make_guardrail())
    with pytest.raises(GuardrailViolation):
        await bad.messages.create(model="claude-opus-5", max_tokens=100, messages=[])
    with pytest.raises(ValueError, match="stream"):
        await ok.messages.create(model="claude-opus-5", messages=[], stream=True)


async def test_anthropic_prompt_is_screened(make_guardrail: Factory) -> None:
    from seed_first_guardrail import PolicyConfig

    guarded = GuardedAnthropic(
        fake_anthropic(SAFE), make_guardrail(PolicyConfig(screen_prompts=True))
    )
    with pytest.raises(GuardrailViolation) as exc:
        await guarded.messages.create(
            model="claude-opus-5",
            max_tokens=10,
            messages=[{"role": "user", "content": "Help me consume seed stock."}],
        )
    assert exc.value.decision.governance_metadata["screened"] == "prompt"


# -- LangChain ---------------------------------------------------------------------


class FakeRunnable:
    def __init__(self, output: Any) -> None:
        self.output = output
        self.seen: list[Any] = []

    async def ainvoke(self, value: Any, config: Any = None, **kw: Any) -> Any:
        self.seen.append(value)
        return self.output


def test_input_output_conversion() -> None:
    # Every string value is screened, not only the "input" key (review AR-01).
    assert input_to_text("x") == "x"
    assert input_to_text(SimpleNamespace(to_string=lambda: "pv")) == "pv"
    assert input_to_text({"question": "q", "context": "c"}) == "q\nc"
    assert input_to_text({"a": 1, "b": "c"}) == "1\nc"
    assert input_to_text([{"role": "user", "content": "m"}]) == "user\nm"
    assert input_to_text(7) == "7"
    assert output_to_text(SimpleNamespace(content="ai")) == "ai"
    assert output_to_text({"answer": "a"}) == "a"


async def test_runnable_async(make_guardrail: Factory) -> None:
    runnable = FakeRunnable(SimpleNamespace(content=SAFE))
    guarded = GuardedRunnable(runnable, make_guardrail(), {"estimated_kwh": 0.0})
    assert (await guarded.ainvoke({"input": "hi"})).content == SAFE
    with pytest.raises(GuardrailViolation):
        await GuardedRunnable(FakeRunnable(HARMFUL), make_guardrail()).ainvoke("hi")


def test_runnable_sync(make_guardrail: Factory) -> None:
    guarded = GuardedRunnable(FakeRunnable(SAFE), make_guardrail())
    assert guarded.invoke("hi") == SAFE


async def test_runnable_sync_inside_loop_errors(make_guardrail: Factory) -> None:
    guarded = GuardedRunnable(FakeRunnable(SAFE), make_guardrail())
    with pytest.raises(RuntimeError, match="ainvoke"):
        guarded.invoke("hi")


def test_as_runnable_uses_langchain_core(
    make_guardrail: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class RunnableLambda:
        def __init__(self, func: Any, afunc: Any = None, name: str = "") -> None:
            captured.update(func=func, afunc=afunc, name=name)

    runnables = types.ModuleType("langchain_core.runnables")
    runnables.RunnableLambda = RunnableLambda  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_core", types.ModuleType("langchain_core"))
    monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables)

    guarded = GuardedRunnable(FakeRunnable(SAFE), make_guardrail())
    guarded.as_runnable()
    assert captured["name"] == "SeedFirstGuardrail"
    assert captured["func"] == guarded.invoke
    import asyncio

    assert asyncio.run(captured["afunc"]("hi")) == SAFE


# -- LlamaIndex --------------------------------------------------------------------


class FakeLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    async def acomplete(self, prompt: str, **kw: Any) -> Any:
        return SimpleNamespace(text=self.text)

    async def achat(self, messages: Any, **kw: Any) -> Any:
        return SimpleNamespace(message=SimpleNamespace(role="assistant", content=self.text))


async def test_llamaindex(make_guardrail: Factory) -> None:
    guarded = GuardedLlamaIndexLLM(FakeLLM(SAFE), make_guardrail())
    assert (await guarded.acomplete("hi")).text == SAFE
    chat = await guarded.achat([SimpleNamespace(role="user", content="hi")])
    assert chat.message.content == SAFE

    bad = GuardedLlamaIndexLLM(FakeLLM(HARMFUL), make_guardrail())
    with pytest.raises(GuardrailViolation):
        await bad.acomplete("hi")
    with pytest.raises(GuardrailViolation):
        await bad.achat([])


async def test_adapters_record_the_serving_model(make_guardrail: Factory, sink: Any) -> None:
    async def create(**kw: Any) -> Any:
        return SimpleNamespace(
            model="claude-opus-5-20260901",  # the served snapshot, not the requested alias
            content=[SimpleNamespace(type="text", text=SAFE)],
        )

    guarded = GuardedAnthropic(
        SimpleNamespace(messages=SimpleNamespace(create=create)), make_guardrail()
    )
    await guarded.messages.create(model="claude-opus-5", max_tokens=10, messages=[])
    assert sink.records[-1].labels["model"] == "claude-opus-5-20260901"

    # The requested model is recorded when the response doesn't name one, including blocks.
    with pytest.raises(GuardrailViolation):
        await GuardedOpenAI(fake_openai(HARMFUL), make_guardrail()).chat.completions.create(
            model="gpt-test", messages=[]
        )
    assert sink.records[-1].labels["model"] == "gpt-test"

    # A caller-supplied model label wins.
    await GuardedOpenAI(fake_openai(SAFE), make_guardrail()).chat.completions.create(
        model="gpt-test", messages=[], guardrail_options={"metadata": {"model": "router-x"}}
    )
    assert sink.records[-1].labels["model"] == "router-x"
