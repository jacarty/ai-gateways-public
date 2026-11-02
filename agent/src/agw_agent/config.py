"""Runtime settings, read from environment variables.

The agent's code never changes between runs; only these settings do. That is
what keeps the baseline and every gateway comparable.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

TARGETS = ("direct", "gateway")
# How Claude reaches a gateway: its OpenAI API (LiteLLM, Bifrost), or Claude's own
# Vertex API passed through (Kong, which can't translate to Claude; ADR 0014).
GATEWAY_CLAUDE_APIS = ("openai", "anthropic")


@dataclass(frozen=True)
class Settings:
    target: str
    """"direct" calls the models on the Agent Platform; "gateway" calls AGW_GATEWAY_URL."""
    project: str
    model_location: str
    """Where the models are called: "eu" is the EU multi-region endpoint."""
    gemini_model: str
    claude_model: str
    max_output_tokens: int
    gateway_url: str | None
    """OpenAI-compatible base URL of the gateway under test."""
    gateway_api_key: str | None
    gateway_claude_api: str
    """"openai" sends Claude to the gateway's OpenAI API; "anthropic" sends Claude's own
    Vertex request (rawPredict) to the gateway, as the direct baseline does."""


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default)).strip()
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return int(raw)


def load(env: Mapping[str, str] = os.environ) -> Settings:
    target = env.get("AGW_TARGET", "direct")
    if target not in TARGETS:
        raise ValueError(f"AGW_TARGET must be one of {TARGETS}, got {target!r}")

    project = env.get("GOOGLE_CLOUD_PROJECT", "")
    if target == "direct" and not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required when AGW_TARGET=direct")

    gateway_url = env.get("AGW_GATEWAY_URL") or None
    if target == "gateway" and not gateway_url:
        raise ValueError("AGW_GATEWAY_URL is required when AGW_TARGET=gateway")
    if gateway_url:
        parts = urlsplit(gateway_url)
        # The ID token's audience is built from the scheme and host.
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError(f"AGW_GATEWAY_URL must be an http(s) URL, got {gateway_url!r}")

    gateway_claude_api = env.get("AGW_GATEWAY_CLAUDE_API", "openai")
    if gateway_claude_api not in GATEWAY_CLAUDE_APIS:
        raise ValueError(
            f"AGW_GATEWAY_CLAUDE_API must be one of {GATEWAY_CLAUDE_APIS}, "
            f"got {gateway_claude_api!r}"
        )
    native_claude = target == "gateway" and gateway_claude_api == "anthropic"
    # The Vertex request path names the project, even through a gateway.
    if native_claude and not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required when AGW_GATEWAY_CLAUDE_API=anthropic")
    # The key is the SDK's bearer: without one every call would be a runtime 401.
    if native_claude and not env.get("AGW_GATEWAY_API_KEY"):
        raise ValueError("AGW_GATEWAY_API_KEY is required when AGW_GATEWAY_CLAUDE_API=anthropic")

    return Settings(
        target=target,
        project=project,
        model_location=env.get("GOOGLE_CLOUD_LOCATION", "eu"),
        gemini_model=env.get("AGW_GEMINI_MODEL", "gemini-3.8-flash"),
        claude_model=env.get("AGW_CLAUDE_MODEL", "claude-haiku-5-5"),
        max_output_tokens=_positive_int(env, "AGW_MAX_OUTPUT_TOKENS", 256),
        gateway_url=gateway_url,
        gateway_api_key=env.get("AGW_GATEWAY_API_KEY") or None,
        gateway_claude_api=gateway_claude_api,
    )
