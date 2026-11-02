import pytest
from google.adk.models.anthropic_llm import Claude
from google.adk.models.lite_llm import LiteLlm

from agw_agent.auth import GatewayClient
from agw_agent.config import load
from agw_agent.models import build_model

DIRECT = {"GOOGLE_CLOUD_PROJECT": "my-gcp-project"}
GATEWAY = {"AGW_TARGET": "gateway", "AGW_GATEWAY_URL": "https://gw.example/v1"}


def test_direct_gemini_is_a_model_name():
    assert build_model("gemini", load(DIRECT)) == "gemini-3.8-flash"


def test_direct_claude_uses_eu_multi_region_host():
    model = build_model("claude", load(DIRECT))
    assert isinstance(model, Claude)
    assert model.model == "claude-haiku-5-5"
    assert str(model.client.base_url).startswith("https://aiplatform.eu.rep.googleapis.com/")


def test_gateway_routes_both_models_through_litellm():
    for kind, name in (("gemini", "gemini-3.8-flash"), ("claude", "claude-haiku-5-5")):
        model = build_model(kind, load(GATEWAY))
        assert isinstance(model, LiteLlm)
        assert model.model == f"openai/{name}"
        assert model._additional_args["api_base"] == "https://gw.example/v1"
        assert isinstance(model.llm_client, GatewayClient)
        assert "llm_client" not in model._additional_args


def test_gateway_asks_gemini_for_low_reasoning_only():
    gemini = build_model("gemini", load(GATEWAY))
    claude = build_model("claude", load(GATEWAY))
    assert gemini._additional_args["reasoning_effort"] == "low"
    assert "reasoning_effort" not in claude._additional_args


def test_gateway_api_key_is_passed_through():
    model = build_model("gemini", load({**GATEWAY, "AGW_GATEWAY_API_KEY": "secret"}))
    assert model._additional_args["api_key"] == "secret"


def test_gateway_without_api_key_uses_placeholder():
    # The OpenAI client refuses to build without a key, even if the gateway ignores it.
    for env in (GATEWAY, {**GATEWAY, "AGW_GATEWAY_API_KEY": ""}):
        assert build_model("claude", load(env))._additional_args["api_key"] == "unused"


def test_gateway_uses_custom_model_names():
    env = {**GATEWAY, "AGW_GEMINI_MODEL": "g-custom", "AGW_CLAUDE_MODEL": "c-custom"}
    assert build_model("gemini", load(env)).model == "openai/g-custom"
    assert build_model("claude", load(env)).model == "openai/c-custom"


def test_direct_custom_model_names():
    env = {**DIRECT, "AGW_GEMINI_MODEL": "g-custom", "AGW_CLAUDE_MODEL": "c-custom"}
    assert build_model("gemini", load(env)) == "g-custom"
    assert build_model("claude", load(env)).model == "c-custom"


def test_direct_claude_follows_configured_location():
    model = build_model("claude", load({**DIRECT, "GOOGLE_CLOUD_LOCATION": "europe-west1"}))
    assert "europe-west1" in str(model.client.base_url)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError, match="unknown model kind"):
        build_model("gpt", load(DIRECT))


NATIVE = {
    **GATEWAY,
    "AGW_GATEWAY_CLAUDE_API": "anthropic",
    "AGW_GATEWAY_API_KEY": "kong-key",
    "GOOGLE_CLOUD_PROJECT": "my-gcp-project",
}


def test_anthropic_gateway_api_sends_claude_natively_to_the_gateway():
    model = build_model("claude", load(NATIVE))
    assert isinstance(model, Claude)
    assert model.model == "claude-haiku-5-5"
    assert str(model.client.base_url) == "https://gw.example/v1/"
    assert model.client.access_token == "kong-key"


def test_anthropic_gateway_api_leaves_gemini_on_the_openai_path():
    model = build_model("gemini", load(NATIVE))
    assert isinstance(model, LiteLlm)
    assert model._additional_args["reasoning_effort"] == "low"


def test_anthropic_gateway_request_is_the_baseline_rawpredict(monkeypatch, make_jwt):
    """End to end through the SDK, against a mock transport: path, key and ID token."""
    import asyncio
    import time

    import httpx2

    from agw_agent import models
    from agw_agent.auth import IdToken, anthropic_gateway_http_client

    jwt = make_jwt(time.time() + 3600)
    monkeypatch.setattr(IdToken, "_fetch", lambda self: jwt)
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), headers=dict(request.headers), body=request.content)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "hi"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    monkeypatch.setattr(
        models,
        "anthropic_gateway_http_client",
        lambda token: anthropic_gateway_http_client(token, transport=httpx2.MockTransport(handler)),
    )
    client = build_model("claude", load(NATIVE)).client
    asyncio.run(
        client.messages.create(
            model="claude-haiku-5-5", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
        )
    )
    assert seen["url"] == (
        "https://gw.example/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/claude-haiku-5-5:rawPredict"
    )
    assert seen["headers"]["authorization"] == "Bearer kong-key"
    assert seen["headers"]["x-serverless-authorization"] == f"Bearer {jwt}"
    assert b'"anthropic_version":"vertex-2023-10-16"' in seen["body"]


def test_openai_mode_claude_still_uses_litellm():
    for env in (GATEWAY, {**GATEWAY, "AGW_GATEWAY_CLAUDE_API": "openai"}):
        assert isinstance(build_model("claude", load(env)), LiteLlm)


def test_anthropic_mode_leaves_direct_claude_unchanged():
    model = build_model("claude", load({**DIRECT, "AGW_GATEWAY_CLAUDE_API": "anthropic"}))
    assert str(model.client.base_url).startswith("https://aiplatform.eu.rep.googleapis.com/")
    assert model.client.access_token is None


def test_anthropic_gateway_stream_goes_to_streamrawpredict(monkeypatch, make_jwt):
    import asyncio
    import time

    import httpx2

    from agw_agent import models
    from agw_agent.auth import IdToken, anthropic_gateway_http_client

    jwt = make_jwt(time.time() + 3600)
    monkeypatch.setattr(IdToken, "_fetch", lambda self: jwt)
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), headers=dict(request.headers))
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        )

    monkeypatch.setattr(
        models,
        "anthropic_gateway_http_client",
        lambda token: anthropic_gateway_http_client(token, transport=httpx2.MockTransport(handler)),
    )
    client = build_model("claude", load(NATIVE)).client

    async def go():
        stream = await client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=16,
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        async for _ in stream:
            pass

    asyncio.run(go())
    assert seen["url"].endswith("/claude-haiku-5-5:streamRawPredict")
    assert seen["headers"]["x-serverless-authorization"] == f"Bearer {jwt}"
