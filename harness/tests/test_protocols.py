import ast
import dataclasses
from pathlib import Path

import pytest

from agw_harness.protocols import (
    AgentRun,
    AnthropicNative,
    GeminiNative,
    OpenAIChat,
    platform_host,
    protocol_for,
)
from agw_harness.settings import INSTRUCTION

AGENT_FACTORY = Path(__file__).parents[2] / "agent" / "src" / "agw_agent" / "factory.py"


def test_instruction_matches_the_agents():
    # The agent and the harness are separate packages, so the instruction is copied;
    # a drifted copy would make the direct and agent paths ask different questions.
    # Read from source: importing the agent would need its dependencies (ADK).
    tree = ast.parse(AGENT_FACTORY.read_text())
    agent = next(
        (
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign | ast.AnnAssign)
            and any(
                getattr(t, "id", None) == "INSTRUCTION"
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
            )
        ),
        None,
    )
    assert agent is not None, f"no module-level INSTRUCTION in {AGENT_FACTORY}"
    assert agent == INSTRUCTION


@pytest.mark.parametrize(
    ("location", "host"),
    [
        ("eu", "https://aiplatform.eu.rep.googleapis.com"),
        ("global", "https://aiplatform.googleapis.com"),
        ("europe-west1", "https://europe-west1-aiplatform.googleapis.com"),
    ],
)
def test_platform_host(location, host):
    assert platform_host(location) == host


def test_gemini_native_request(settings):
    p = GeminiNative(settings)
    assert p.url(False).endswith(
        "/v1beta1/projects/my-gcp-project/locations/eu/publishers/google/models/"
        "gemini-3.8-flash:generateContent"
    )
    assert p.url(True).endswith(":streamGenerateContent?alt=sse")
    body = p.body("Q?", stream=True)
    assert body["generationConfig"] == {
        "maxOutputTokens": 256,
        "thinkingConfig": {"thinkingLevel": "LOW"},
    }
    assert body["systemInstruction"]["parts"][0]["text"] == INSTRUCTION


def test_gemini_native_parsing_skips_thoughts(settings):
    p = GeminiNative(settings)
    data = {
        "candidates": [
            {"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "Brussels."}]}}
        ],
        "usageMetadata": {"promptTokenCount": 47, "candidatesTokenCount": 7},
    }
    assert p.text(data) == "Brussels."
    u = p.usage(data)
    assert (u.input_tokens, u.output_tokens, u.thinking_tokens) == (47, 7, 0)


def test_anthropic_native_request(settings):
    p = AnthropicNative(settings)
    assert p.url(False).startswith("https://aiplatform.eu.rep.googleapis.com/v1/projects/")
    assert p.url(False).endswith("/publishers/anthropic/models/claude-haiku-5-5:rawPredict")
    assert p.url(True).endswith(":streamRawPredict")
    assert "stream" not in p.body("Q?", stream=False)
    body = p.body("Q?", stream=True)
    assert body["stream"] is True and body["max_tokens"] == 256
    assert body["anthropic_version"] == "vertex-2023-10-16" and body["system"] == INSTRUCTION


def test_anthropic_native_parsing(settings):
    p = AnthropicNative(settings)
    full = {
        "content": [{"type": "text", "text": "Brussels."}],
        "usage": {"input_tokens": 9, "output_tokens": 3},
    }
    assert p.text(full) == "Brussels."
    assert p.usage(full).output_tokens == 3
    assert (
        p.text({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Bru"}})
        == "Bru"
    )
    assert (
        p.usage({"type": "message_start", "message": {"usage": {"input_tokens": 9}}}).input_tokens
        == 9
    )


def test_openai_chat_request(settings):
    gemini, claude = OpenAIChat(settings, "gemini"), OpenAIChat(settings, "claude")
    assert gemini.url(False) == "https://gw.example/v1/chat/completions"
    body = gemini.body("Q?", stream=True)
    assert body["model"] == "gemini-3.8-flash"
    assert body["max_completion_tokens"] == 256 and body["reasoning_effort"] == "low"
    assert body["stream_options"] == {"include_usage": True}
    assert "reasoning_effort" not in claude.body("Q?", stream=False)
    assert "stream_options" not in claude.body("Q?", stream=False)


def test_openai_chat_parsing(settings):
    p = OpenAIChat(settings, "claude")
    assert p.text({"choices": [{"message": {"content": "Brussels."}}]}) == "Brussels."
    assert p.text({"choices": [{"delta": {"content": "Bru"}}]}) == "Bru"
    assert p.text({"choices": [], "usage": {"prompt_tokens": 1}}) == ""
    u = p.usage({"usage": {"prompt_tokens": 9, "completion_tokens": 3}})
    assert (u.input_tokens, u.output_tokens) == (9, 3)


def test_agent_run_request(settings):
    p = AgentRun(settings, "claude")
    assert p.url(False) == "https://agent.example/run"
    assert p.url(True) == "https://agent.example/run_sse"
    a, b = p.body("Q?", stream=True), p.body("Q?", stream=True)
    assert a["app_name"] == "claude" and a["streaming"] is True
    assert a["session_id"] != b["session_id"]


def test_agent_run_parsing(settings):
    p = AgentRun(settings, "gemini")
    events = [
        {
            "content": {"parts": [{"text": "Brussels."}]},
            "usageMetadata": {"promptTokenCount": 47, "candidatesTokenCount": 7},
        }
    ]
    assert p.text(events) == "Brussels."
    assert p.usage(events).output_tokens == 7
    assert p.text(events[0]) == "Brussels."


def test_protocol_for(settings):
    assert isinstance(protocol_for("direct", "gemini", settings), GeminiNative)
    assert isinstance(protocol_for("direct", "claude", settings), AnthropicNative)
    assert isinstance(protocol_for("gateway", "claude", settings), OpenAIChat)
    assert isinstance(protocol_for("agent", "gemini", settings), AgentRun)


def test_anthropic_gateway_api_sends_claude_natively_to_the_gateway(settings):
    native = dataclasses.replace(
        settings, gateway_url="https://gw.example/v1", gateway_claude_api="anthropic"
    )
    p = protocol_for("gateway", "claude", native)
    assert isinstance(p, AnthropicNative) and p.via_gateway
    assert p.url(False) == (
        "https://gw.example/v1/projects/my-gcp-project/locations/eu"
        "/publishers/anthropic/models/claude-haiku-5-5:rawPredict"
    )
    assert p.url(True).endswith(":streamRawPredict")
    # The body is the direct baseline's, byte for byte.
    assert p.body("Q?", stream=True) == AnthropicNative(settings).body("Q?", stream=True)
    # Gemini stays on the gateway's OpenAI API.
    assert isinstance(protocol_for("gateway", "gemini", native), OpenAIChat)


def test_direct_claude_url_is_unchanged(settings):
    # Comparability with recorded baselines: the direct URL must not move.
    assert AnthropicNative(settings).url(False) == (
        "https://aiplatform.eu.rep.googleapis.com/v1/projects/my-gcp-project/locations/eu"
        "/publishers/anthropic/models/claude-haiku-5-5:rawPredict"
    )


def test_missing_gemini_thoughts_count_means_no_thinking(settings):
    # Gemini (and the agent, which passes its usage through) omits zero-valued fields.
    usage = {"usageMetadata": {"promptTokenCount": 47, "candidatesTokenCount": 7}}
    assert GeminiNative(settings).usage(usage).thinking_tokens == 0
    assert AgentRun(settings, "gemini").usage([usage]).thinking_tokens == 0
    reported = {"usageMetadata": {"candidatesTokenCount": 7, "thoughtsTokenCount": 35}}
    assert GeminiNative(settings).usage(reported).thinking_tokens == 35
