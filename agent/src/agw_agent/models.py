"""Builds the model an agent calls, for the baseline or for a gateway."""

from typing import Literal

from anthropic import AsyncAnthropicVertex
from google.adk.models import BaseLlm
from google.adk.models.anthropic_llm import Claude
from google.adk.models.lite_llm import LiteLlm

from agw_agent.auth import GatewayClient, IdToken, anthropic_gateway_http_client, audience_for
from agw_agent.config import Settings

ModelKind = Literal["gemini", "claude"]


def build_model(kind: ModelKind, settings: Settings) -> str | BaseLlm:
    """Return the model for `kind`, pointed at the configured target.

    direct:  Gemini by name (ADK routes it through google-genai, configured by
             GOOGLE_GENAI_USE_ENTERPRISE, GOOGLE_CLOUD_PROJECT and
             GOOGLE_CLOUD_LOCATION), and Claude with its own Vertex client.
    gateway: both through the gateway's OpenAI-compatible API via LiteLLM,
             using the same model names, which each gateway's config maps.
             Each call carries the gateway key (Authorization) and an ID token
             for Cloud Run (X-Serverless-Authorization). With
             AGW_GATEWAY_CLAUDE_API=anthropic, Claude instead keeps the direct
             path's Vertex client, pointed at the gateway (Kong, ADR 0014).
    """
    if kind not in ("gemini", "claude"):
        raise ValueError(f"unknown model kind {kind!r}")
    name = settings.gemini_model if kind == "gemini" else settings.claude_model

    if (
        settings.target == "gateway"
        and kind == "claude"
        and settings.gateway_claude_api == "anthropic"
    ):
        # The same request as the direct baseline (rawPredict / streamRawPredict on
        # <gateway_url>/projects/...), so the gateway passes it through untranslated.
        # The SDK sends access_token as the bearer, which here is the gateway key.
        return Claude(
            model=name,
            client=AsyncAnthropicVertex(
                project_id=settings.project,
                region=settings.model_location,
                base_url=settings.gateway_url,
                access_token=settings.gateway_api_key or "unused",
                http_client=anthropic_gateway_http_client(
                    IdToken(audience_for(settings.gateway_url))
                ),
            ),
        )

    if settings.target == "gateway":
        # ADK's LiteLLM path ignores thinking_config, so Gemini's low thinking is
        # requested the OpenAI way; whether each gateway honours it is a finding.
        extra = {"reasoning_effort": "low"} if kind == "gemini" else {}
        return LiteLlm(
            model=f"openai/{name}",
            api_base=settings.gateway_url,
            # The OpenAI client requires a key even when the gateway ignores it.
            api_key=settings.gateway_api_key or "unused",
            llm_client=GatewayClient(IdToken(audience_for(settings.gateway_url))),
            **extra,
        )

    if kind == "gemini":
        return name

    # An explicit client, so project and region come from the validated Settings
    # rather than ADK reading the environment itself.
    return Claude(
        model=name,
        client=AsyncAnthropicVertex(project_id=settings.project, region=settings.model_location),
    )
