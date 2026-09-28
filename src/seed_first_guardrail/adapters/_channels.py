"""Extract every screenable channel from SDK requests and responses (review AR-01).

The first adapters read only the plain-text channel, so harmful content left through
tool calls, extra choices and thinking blocks unscreened. Here every block type is
either turned into text for screening or reported as *unscreenable* (images, audio,
PDF documents, unknown types), which the policy blocks by default.

🧒 The bodyguard used to watch only the front door. Now it checks every door and window
-- the tool-call door, the second-answer door, the thinking door -- and if a door is too
dark to see through (a picture, a sound), it keeps it shut unless the rules say otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_TEXT_TYPES = {"text", "input_text", "output_text"}
_UNSCREENABLE_TYPES = {
    "image",
    "image_url",
    "input_image",
    "input_audio",
    "audio",
    "file",
    "input_file",
}
_SILENT_TYPES = {"redacted_thinking"}  # encrypted, never shown to users


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _json(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)  # tool arguments usually arrive as a JSON string
        except ValueError:
            return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


@dataclass
class Extracted:
    parts: list[tuple[str, str]] = field(default_factory=list)
    unscreenable: set[str] = field(default_factory=set)

    def add(self, channel: str, text: Any) -> None:
        if text:
            self.parts.append((channel, str(text)))

    def merge(self, other: Extracted) -> Extracted:
        self.parts.extend(other.parts)
        self.unscreenable |= other.unscreenable
        return self

    @property
    def channels(self) -> set[str]:
        return {c for c, _ in self.parts}

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.parts)


def content_parts(content: Any, channel: str = "text") -> Extracted:
    """Flatten a message ``content`` (string, list of parts/blocks, or object)."""
    out = Extracted()
    if content is None:
        return out
    if isinstance(content, str):
        out.add(channel, content)
        return out
    if isinstance(content, Iterable) and not isinstance(content, (bytes, Mapping)):
        for part in content:
            out.merge(content_parts(part, channel))
        return out
    return out.merge(block_parts(content, channel))


def block_parts(block: Any, channel: str = "text") -> Extracted:
    out = Extracted()
    kind = _get(block, "type", "text")
    if kind in _TEXT_TYPES:
        out.add(channel, _get(block, "text"))
    elif kind in ("tool_use", "server_tool_use"):
        out.add("tool_use", f"{_get(block, 'name', '')} {_json(_get(block, 'input', {}))}")
    elif kind == "tool_result":
        out.merge(content_parts(_get(block, "content"), "tool_result"))
    elif kind == "thinking":
        out.add("thinking", _get(block, "thinking"))
    elif kind == "refusal":
        out.add("refusal", _get(block, "refusal"))
    elif kind == "document":
        source = _get(block, "source", {})
        if _get(source, "type") == "text":
            out.add("document", _get(source, "data"))
        elif _get(source, "type") == "content":
            out.merge(content_parts(_get(source, "content"), "document"))
        else:
            out.unscreenable.add(
                f"document:{_get(source, 'media_type', _get(source, 'type', '?'))}"
            )
    elif kind in _UNSCREENABLE_TYPES:
        out.unscreenable.add(str(kind))
    elif kind in _SILENT_TYPES:
        pass
    else:
        out.unscreenable.add(f"unknown:{kind}")  # fail closed on block types we don't know
    return out


def _tool_definitions(tools: Any) -> Extracted:
    out = Extracted()
    for tool in tools or []:
        fn = _get(tool, "function", tool)
        out.add("tool_definition", f"{_get(fn, 'name', '')}: {_get(fn, 'description', '')}")
    return out


# -- Anthropic -----------------------------------------------------------------


def anthropic_request(kwargs: Mapping[str, Any]) -> Extracted:
    out = content_parts(kwargs.get("system"), "system")
    for message in kwargs.get("messages", []):
        out.merge(content_parts(_get(message, "content"), "text"))
    return out.merge(_tool_definitions(kwargs.get("tools")))


def anthropic_response(message: Any) -> Extracted:
    out = Extracted()
    for block in _get(message, "content", None) or []:
        out.merge(block_parts(block))
    return out


# -- OpenAI --------------------------------------------------------------------


def _openai_tool_calls(message: Any) -> Extracted:
    out = Extracted()
    for call in _get(message, "tool_calls", None) or []:
        fn = _get(call, "function", {})
        out.add("tool_use", f"{_get(fn, 'name', '')} {_json(_get(fn, 'arguments', ''))}")
    legacy = _get(message, "function_call")
    if legacy:
        out.add("tool_use", f"{_get(legacy, 'name', '')} {_json(_get(legacy, 'arguments', ''))}")
    return out


def openai_request(kwargs: Mapping[str, Any]) -> Extracted:
    out = Extracted()
    for message in kwargs.get("messages", []):
        role = _get(message, "role", "")
        out.merge(
            content_parts(_get(message, "content"), "tool_result" if role == "tool" else "text")
        )
        out.merge(_openai_tool_calls(message))
    return out.merge(_tool_definitions(kwargs.get("tools")))


def openai_response(response: Any) -> Extracted:
    out = Extracted()
    for choice in _get(response, "choices", None) or []:
        message = _get(choice, "message", {})
        out.merge(content_parts(_get(message, "content"), "text"))
        out.add("refusal", _get(message, "refusal"))
        out.merge(_openai_tool_calls(message))
        if _get(message, "audio"):
            out.unscreenable.add("audio")
    return out


# -- Generic (LangChain / LlamaIndex) -----------------------------------------------


def generic_value(value: Any, channel: str = "text") -> Extracted:
    """Every string reachable in a nested input or output value."""
    out = Extracted()
    if value is None:
        return out
    if isinstance(value, str):
        out.add(channel, value)
    elif hasattr(value, "to_string") and not isinstance(value, Mapping):  # PromptValue
        out.add(channel, value.to_string())
    elif isinstance(value, Mapping):
        for v in value.values():
            out.merge(generic_value(v, channel))
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            out.merge(generic_value(v, channel))
    elif hasattr(value, "content") or hasattr(value, "tool_calls"):  # chat messages
        out.merge(content_parts(getattr(value, "content", None), channel))
        for call in getattr(value, "tool_calls", None) or []:
            out.add("tool_use", f"{_get(call, 'name', '')} {_json(_get(call, 'args', {}))}")
        extra = getattr(value, "additional_kwargs", None) or {}
        out.merge(_openai_tool_calls(extra))
    elif isinstance(value, (int, float, bool)):
        out.add(channel, str(value))
    else:
        out.add(channel, str(value))
    return out
