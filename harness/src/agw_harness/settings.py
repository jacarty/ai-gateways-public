"""Harness settings, read from environment variables.

Request shape is fixed here, not per run, so every target gets the same work:
the same prompts, token cap, system instruction and thinking condition.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

TARGETS = ("direct", "agent", "gateway")
MODELS = ("gemini", "claude")
ID_TOKEN_SOURCES = ("auto", "metadata", "gcloud")
# How Claude reaches the gateway target: its OpenAI API (LiteLLM, Bifrost), or the
# direct baseline's own rawPredict request under AGW_GATEWAY_URL (Kong; ADR 0014).
GATEWAY_CLAUDE_APIS = ("openai", "anthropic")

# Same instruction the agent uses (agent/src/agw_agent/factory.py), so direct and
# gateway requests ask for the same short answers the agent path produces.
INSTRUCTION = (
    "You are a test agent used to benchmark AI gateways. "
    "Answer the user's question accurately in at most two sentences."
)

# Fixed, short factual questions, rotated across requests.
PROMPTS = (
    "What is the capital of Belgium?",
    "How many continents are there?",
    "What gas do plants absorb from the air?",
    "Who wrote Pride and Prejudice?",
    "What is the boiling point of water at sea level in Celsius?",
    "What is the largest planet in the solar system?",
    "In which year did the first person walk on the Moon?",
    "What is the chemical symbol for gold?",
    "How many sides does a hexagon have?",
    "What language is spoken in Brazil?",
)


@dataclass(frozen=True)
class Settings:
    project: str
    model_location: str
    gemini_model: str
    claude_model: str
    max_tokens: int
    agent_url: str | None
    gateway_url: str | None
    gateway_api_key: str | None
    results_dir: str
    image: str
    gateway_claude_api: str = "openai"
    """"openai": Claude through the gateway's /chat/completions; "anthropic": the same
    rawPredict request as the direct target, sent to the gateway (Kong passes it through)."""
    id_token_source: str = "gcloud"
    """"metadata": service-account credentials (the job, or a key file), gcloud only as a
    fallback; "gcloud": the gcloud user's identity token (everywhere else)."""

    def model_name(self, model: str) -> str:
        return self.gemini_model if model == "gemini" else self.claude_model


def load(env: Mapping[str, str] = os.environ) -> Settings:
    max_tokens = env.get("AGW_MAX_TOKENS", "256").strip()
    if not max_tokens.isdigit() or int(max_tokens) <= 0:
        raise ValueError(f"AGW_MAX_TOKENS must be a positive integer, got {max_tokens!r}")
    source = env.get("AGW_ID_TOKEN_SOURCE", "auto")
    if source not in ID_TOKEN_SOURCES:
        raise ValueError(f"AGW_ID_TOKEN_SOURCE must be one of {ID_TOKEN_SOURCES}, got {source!r}")
    gateway_claude_api = env.get("AGW_GATEWAY_CLAUDE_API", "openai")
    if gateway_claude_api not in GATEWAY_CLAUDE_APIS:
        raise ValueError(
            f"AGW_GATEWAY_CLAUDE_API must be one of {GATEWAY_CLAUDE_APIS}, "
            f"got {gateway_claude_api!r}"
        )
    if source == "auto":
        # Only the harness job (Cloud Run sets CLOUD_RUN_JOB) should mint tokens from the
        # metadata server. Anywhere else with one (a cloud workstation, a Compute Engine
        # VM) it answers as that machine's service account, not the developer, and Cloud
        # Run gateways and the agent return 403; so local runs use gcloud. A configured
        # service-account key file always wins: that identity was chosen on purpose, and
        # fetch_id_token uses it (a user-credentials file there is skipped by google-auth,
        # which then asks the metadata server: set AGW_ID_TOKEN_SOURCE=gcloud instead).
        in_the_job = bool(env.get("CLOUD_RUN_JOB"))
        keyfile = bool(env.get("GOOGLE_APPLICATION_CREDENTIALS"))
        source = "metadata" if in_the_job or keyfile else "gcloud"
    return Settings(
        project=env.get("AGW_PROJECT", ""),
        model_location=env.get("AGW_MODEL_LOCATION", "eu"),
        gemini_model=env.get("AGW_GEMINI_MODEL", "gemini-3.8-flash"),
        claude_model=env.get("AGW_CLAUDE_MODEL", "claude-haiku-5-5"),
        max_tokens=int(max_tokens),
        agent_url=(env.get("AGW_AGENT_URL") or "").rstrip("/") or None,
        gateway_url=(env.get("AGW_GATEWAY_URL") or "").rstrip("/") or None,
        gateway_api_key=env.get("AGW_GATEWAY_API_KEY") or None,
        results_dir=env.get("AGW_RESULTS_DIR", "results-out"),
        image=env.get("AGW_IMAGE", "local"),
        gateway_claude_api=gateway_claude_api,
        id_token_source=source,
    )


def require(settings: Settings, target: str) -> None:
    """Fail before a run starts if the target is missing what it needs."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}, got {target!r}")
    if target == "direct" and not settings.project:
        raise ValueError("AGW_PROJECT is required for the direct target")
    if target == "agent" and not settings.agent_url:
        raise ValueError("AGW_AGENT_URL is required for the agent target")
    if target == "gateway" and not settings.gateway_url:
        raise ValueError("AGW_GATEWAY_URL is required for the gateway target")
    # Claude's Vertex request path names the project, even through a gateway.
    if target == "gateway" and settings.gateway_claude_api == "anthropic" and not settings.project:
        raise ValueError("AGW_PROJECT is required with AGW_GATEWAY_CLAUDE_API=anthropic")
