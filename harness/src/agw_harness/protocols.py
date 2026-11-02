"""The four request shapes the harness speaks, one per path to a model.

direct (native APIs, so any translation a gateway does counts as its overhead):
  GeminiNative     Agent Platform generateContent / streamGenerateContent
  AnthropicNative  Agent Platform rawPredict / streamRawPredict
gateway:
  OpenAIChat       /chat/completions, the API every gateway exposes
  AnthropicNative  for Claude with AGW_GATEWAY_CLAUDE_API=anthropic: the direct request,
                   under AGW_GATEWAY_URL (Kong can't translate to Claude; ADR 0014)
agent:
  AgentRun         ADK /run and /run_sse (the agent adds its own instruction and caps)

Each protocol builds the request and reads text and token usage from a response
or from one streamed event, so the runner never needs to know which it is.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from agw_harness.settings import INSTRUCTION, Settings

MULTI_REGIONS = {"us", "eu"}


def platform_host(location: str) -> str:
    if location == "global":
        return "https://aiplatform.googleapis.com"
    if location in MULTI_REGIONS:
        return f"https://aiplatform.{location}.rep.googleapis.com"
    return f"https://{location}-aiplatform.googleapis.com"


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None


class RequestProtocol(Protocol):
    def url(self, stream: bool) -> str: ...
    def body(self, prompt: str, stream: bool) -> dict[str, Any]: ...
    def text(self, data: Any) -> str: ...
    def usage(self, data: Any) -> Usage | None: ...


@dataclass(frozen=True)
class GeminiNative:
    settings: Settings

    def url(self, stream: bool) -> str:
        s = self.settings
        loc = s.model_location
        method = "streamGenerateContent?alt=sse" if stream else "generateContent"
        return (
            f"{platform_host(loc)}/v1beta1/projects/{s.project}/locations/{loc}"
            f"/publishers/google/models/{s.gemini_model}:{method}"
        )

    def body(self, prompt: str, stream: bool) -> dict[str, Any]:
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": INSTRUCTION}]},
            "generationConfig": {
                "maxOutputTokens": self.settings.max_tokens,
                # Fixed test condition: gemini-3.8-flash's lowest accepted level.
                "thinkingConfig": {"thinkingLevel": "LOW"},
            },
        }

    def text(self, data: Any) -> str:
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    def usage(self, data: Any) -> Usage | None:
        u = data.get("usageMetadata")
        if not u:
            return None
        # Gemini omits zero-valued fields, so a missing thoughtsTokenCount means no thinking.
        return Usage(
            u.get("promptTokenCount"), u.get("candidatesTokenCount"), u.get("thoughtsTokenCount", 0)
        )


@dataclass(frozen=True)
class AnthropicNative:
    settings: Settings
    via_gateway: bool = False
    """Send the same request to AGW_GATEWAY_URL (which ends in /v1) instead of Vertex."""

    def url(self, stream: bool) -> str:
        s = self.settings
        loc = s.model_location
        method = "streamRawPredict" if stream else "rawPredict"
        base = s.gateway_url if self.via_gateway else f"{platform_host(loc)}/v1"
        return (
            f"{base}/projects/{s.project}/locations/{loc}"
            f"/publishers/anthropic/models/{s.claude_model}:{method}"
        )

    def body(self, prompt: str, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "anthropic_version": "vertex-2023-10-16",
            "max_tokens": self.settings.max_tokens,
            "system": INSTRUCTION,
            "messages": [{"role": "user", "content": prompt}],
        }
        if stream:
            body["stream"] = True
        return body

    def text(self, data: Any) -> str:
        if data.get("type") == "content_block_delta":
            return data.get("delta", {}).get("text", "")
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )

    def usage(self, data: Any) -> Usage | None:
        # Streaming splits usage: input on message_start, output on message_delta.
        u = data.get("usage") or data.get("message", {}).get("usage")
        if not u:
            return None
        return Usage(u.get("input_tokens"), u.get("output_tokens"))


@dataclass(frozen=True)
class OpenAIChat:
    settings: Settings
    model: str

    def url(self, stream: bool) -> str:
        return f"{self.settings.gateway_url}/chat/completions"

    def body(self, prompt: str, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.model_name(self.model),
            "messages": [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self.settings.max_tokens,
            "stream": stream,
        }
        if stream:
            body["stream_options"] = {"include_usage": True}
        if self.model == "gemini":
            # Same intent as the direct thinkingLevel LOW; the agent sends the same.
            body["reasoning_effort"] = "low"
        return body

    def text(self, data: Any) -> str:
        choice = (data.get("choices") or [{}])[0]
        return (choice.get("delta") or choice.get("message") or {}).get("content") or ""

    def usage(self, data: Any) -> Usage | None:
        u = data.get("usage")
        if not u:
            return None
        details = u.get("completion_tokens_details") or {}
        return Usage(
            u.get("prompt_tokens"), u.get("completion_tokens"), details.get("reasoning_tokens")
        )


@dataclass(frozen=True)
class AgentRun:
    settings: Settings
    model: str

    def url(self, stream: bool) -> str:
        return f"{self.settings.agent_url}/{'run_sse' if stream else 'run'}"

    def body(self, prompt: str, stream: bool) -> dict[str, Any]:
        return {
            "app_name": self.model,
            "user_id": "harness",
            # A fresh session per request: no history carried between requests.
            "session_id": f"h-{uuid.uuid4().hex}",
            "new_message": {"role": "user", "parts": [{"text": prompt}]},
            "streaming": stream,
        }

    def text(self, data: Any) -> str:
        # /run returns a list of events; /run_sse sends one event per message.
        events = data if isinstance(data, list) else [data]
        return "".join(
            p.get("text", "")
            for e in events
            for p in (e.get("content") or {}).get("parts", [])
            if not p.get("thought")
        )

    def usage(self, data: Any) -> Usage | None:
        events = data if isinstance(data, list) else [data]
        found = [e["usageMetadata"] for e in events if e.get("usageMetadata")]
        if not found:
            return None
        u = found[-1]
        # Gemini omits zero-valued fields, so a missing thoughtsTokenCount means no thinking.
        return Usage(
            u.get("promptTokenCount"), u.get("candidatesTokenCount"), u.get("thoughtsTokenCount", 0)
        )


def protocol_for(target: str, model: str, settings: Settings) -> RequestProtocol:
    if target == "direct":
        return GeminiNative(settings) if model == "gemini" else AnthropicNative(settings)
    if target == "gateway":
        if model == "claude" and settings.gateway_claude_api == "anthropic":
            return AnthropicNative(settings, via_gateway=True)
        return OpenAIChat(settings, model)
    if target == "agent":
        return AgentRun(settings, model)
    raise ValueError(f"unknown target {target!r}")
