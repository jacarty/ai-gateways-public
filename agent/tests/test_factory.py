import pytest
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from agw_agent.factory import INSTRUCTION, make_agent


def test_gemini_thinks_at_low_level(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    config = make_agent("gemini").generate_content_config
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert config.max_output_tokens == 256


def test_claude_has_no_thinking_config(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    assert make_agent("claude").generate_content_config.thinking_config is None


def test_agent_names_and_instruction(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    gemini, claude = make_agent("gemini"), make_agent("claude")
    assert (gemini.name, claude.name) == ("gemini_agent", "claude_agent")
    assert gemini.instruction == claude.instruction == INSTRUCTION


def test_max_output_tokens_follows_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    monkeypatch.setenv("AGW_MAX_OUTPUT_TOKENS", "32")
    for kind in ("gemini", "claude"):
        assert make_agent(kind).generate_content_config.max_output_tokens == 32


def test_gateway_agents_use_litellm_and_keep_thinking_rules(monkeypatch):
    monkeypatch.setenv("AGW_TARGET", "gateway")
    monkeypatch.setenv("AGW_GATEWAY_URL", "https://gw.example/v1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    gemini, claude = make_agent("gemini"), make_agent("claude")
    assert isinstance(gemini.model, LiteLlm) and isinstance(claude.model, LiteLlm)
    assert gemini.generate_content_config.thinking_config is not None
    assert claude.generate_content_config.thinking_config is None


def test_invalid_config_fails_agent_creation(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("AGW_TARGET", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        make_agent("gemini")
