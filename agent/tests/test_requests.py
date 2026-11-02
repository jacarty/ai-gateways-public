"""What actually leaves the agent, captured offline (no network, no credentials).

These assert on the outbound request, not on constructor state, so they catch an
ADK or LiteLLM upgrade that changes how settings are sent.
"""

import asyncio
import time
from unittest.mock import AsyncMock

from anthropic.types import Message, TextBlock, Usage
from google.adk.models import lite_llm
from google.adk.models.lite_llm import _ensure_litellm_imported
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from agw_agent.auth import IdToken
from agw_agent.factory import make_agent


def _request(agent) -> LlmRequest:
    config = agent.generate_content_config.model_copy(update={"system_instruction": "Be brief."})
    return LlmRequest(
        model=agent.model if isinstance(agent.model, str) else agent.model.model,
        contents=[types.Content(role="user", parts=[types.Part(text="Capital of Belgium?")])],
        config=config,
    )


async def _drain(model, request, stream: bool = False):
    return [r async for r in model.generate_content_async(request, stream=stream)]


def test_gateway_gemini_sends_low_reasoning_and_token_cap(monkeypatch, make_jwt):
    monkeypatch.setenv("AGW_TARGET", "gateway")
    monkeypatch.setenv("AGW_GATEWAY_URL", "https://gw.example/v1")
    monkeypatch.setenv("AGW_GATEWAY_API_KEY", "sk-gateway")
    jwt = make_jwt(time.time() + 3600)
    monkeypatch.setattr(IdToken, "_fetch", lambda self: jwt)
    _ensure_litellm_imported()
    import litellm

    agent = make_agent("gemini")
    reply = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "ok"}}])
    capture = AsyncMock(return_value=reply)
    # Below the agent's client, so its ID-token header is part of what is captured.
    monkeypatch.setattr(lite_llm, "acompletion", capture)

    asyncio.run(_drain(agent.model, _request(agent)))

    sent = capture.call_args.kwargs
    assert sent["model"] == "openai/gemini-3.8-flash"
    assert sent["api_base"] == "https://gw.example/v1"
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == 256
    assert "thinking" not in sent and "thinking_config" not in sent
    # Gateway key for the gateway, ID token (audience without the path) for Cloud Run.
    assert sent["api_key"] == "sk-gateway"
    assert sent["extra_headers"]["X-Serverless-Authorization"] == f"Bearer {jwt}"
    assert agent.model.llm_client.token.audience == "https://gw.example"


def test_gateway_streaming_also_carries_the_id_token(monkeypatch, make_jwt):
    monkeypatch.setenv("AGW_TARGET", "gateway")
    monkeypatch.setenv("AGW_GATEWAY_URL", "https://gw.example")
    jwt = make_jwt(time.time() + 3600)
    monkeypatch.setattr(IdToken, "_fetch", lambda self: jwt)
    _ensure_litellm_imported()

    async def no_chunks():
        return
        yield

    capture = AsyncMock(return_value=no_chunks())
    monkeypatch.setattr(lite_llm, "acompletion", capture)
    agent = make_agent("claude")

    asyncio.run(_drain(agent.model, _request(agent), stream=True))

    sent = capture.call_args.kwargs
    assert sent["stream"] is True
    assert sent["extra_headers"]["X-Serverless-Authorization"] == f"Bearer {jwt}"


def test_direct_claude_sends_token_cap_and_no_thinking(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    agent = make_agent("claude")
    reply = Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-haiku-5-5",
        content=[TextBlock(type="text", text="Brussels.")],
        stop_reason="end_turn",
        usage=Usage(input_tokens=1, output_tokens=1),
    )
    capture = AsyncMock(return_value=reply)
    monkeypatch.setattr(agent.model.client.messages, "create", capture)

    asyncio.run(_drain(agent.model, _request(agent)))

    sent = capture.call_args.kwargs
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["max_tokens"] == 256
    assert "thinking" not in sent or not sent["thinking"]
