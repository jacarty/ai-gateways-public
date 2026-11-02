import pytest

from agw_agent.config import load


def test_direct_defaults():
    s = load({"GOOGLE_CLOUD_PROJECT": "my-gcp-project"})
    assert s.target == "direct"
    assert s.model_location == "eu"
    assert s.gemini_model == "gemini-3.8-flash"
    assert s.claude_model == "claude-haiku-5-5"
    assert s.max_output_tokens == 256
    assert s.gateway_url is None


def test_unknown_target_rejected():
    with pytest.raises(ValueError, match="AGW_TARGET"):
        load({"AGW_TARGET": "proxy", "GOOGLE_CLOUD_PROJECT": "p"})


def test_direct_requires_project():
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        load({})


def test_gateway_requires_url():
    with pytest.raises(ValueError, match="AGW_GATEWAY_URL"):
        load({"AGW_TARGET": "gateway"})


def test_gateway_settings():
    s = load(
        {
            "AGW_TARGET": "gateway",
            "AGW_GATEWAY_URL": "https://gw.example/v1",
            "AGW_GATEWAY_API_KEY": "k",
            "AGW_MAX_OUTPUT_TOKENS": "64",
        }
    )
    assert s.gateway_url == "https://gw.example/v1"
    assert s.gateway_api_key == "k"
    assert s.max_output_tokens == 64


def test_custom_models_and_location():
    s = load(
        {
            "GOOGLE_CLOUD_PROJECT": "p",
            "GOOGLE_CLOUD_LOCATION": "us",
            "AGW_GEMINI_MODEL": "gemini-x",
            "AGW_CLAUDE_MODEL": "claude-y",
        }
    )
    assert (s.model_location, s.gemini_model, s.claude_model) == ("us", "gemini-x", "claude-y")


def test_empty_project_rejected_for_direct():
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        load({"GOOGLE_CLOUD_PROJECT": ""})


def test_gateway_does_not_need_project():
    s = load({"AGW_TARGET": "gateway", "AGW_GATEWAY_URL": "https://gw.example/v1"})
    assert s.project == ""


def test_empty_gateway_url_rejected():
    with pytest.raises(ValueError, match="AGW_GATEWAY_URL"):
        load({"AGW_TARGET": "gateway", "AGW_GATEWAY_URL": ""})


def test_direct_keeps_unused_gateway_url():
    s = load({"GOOGLE_CLOUD_PROJECT": "p", "AGW_GATEWAY_URL": "https://gw.example/v1"})
    assert s.target == "direct"
    assert s.gateway_url == "https://gw.example/v1"


def test_empty_gateway_api_key_becomes_none():
    s = load(
        {
            "AGW_TARGET": "gateway",
            "AGW_GATEWAY_URL": "https://gw.example/v1",
            "AGW_GATEWAY_API_KEY": "",
        }
    )
    assert s.gateway_api_key is None


def test_empty_target_rejected():
    with pytest.raises(ValueError, match="AGW_TARGET"):
        load({"AGW_TARGET": "", "GOOGLE_CLOUD_PROJECT": "p"})


def test_target_is_case_sensitive():
    with pytest.raises(ValueError, match="AGW_TARGET"):
        load({"AGW_TARGET": "Direct", "GOOGLE_CLOUD_PROJECT": "p"})


@pytest.mark.parametrize("value", ["abc", "", "1.5", "12k", "0", "-1", "+32", "1_000"])
def test_invalid_max_output_tokens_rejected(value):
    with pytest.raises(ValueError, match="AGW_MAX_OUTPUT_TOKENS"):
        load({"GOOGLE_CLOUD_PROJECT": "p", "AGW_MAX_OUTPUT_TOKENS": value})


def test_max_output_tokens_tolerates_surrounding_whitespace():
    s = load({"GOOGLE_CLOUD_PROJECT": "p", "AGW_MAX_OUTPUT_TOKENS": " 32 "})
    assert s.max_output_tokens == 32


def test_load_reads_process_environment_by_default(monkeypatch):
    monkeypatch.delenv("AGW_TARGET", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "from-env")
    assert load().project == "from-env"


@pytest.mark.parametrize("url", ["gw.example/v1", "ftp://gw.example", "https://"])
def test_gateway_url_must_be_an_http_url(url):
    with pytest.raises(ValueError, match="must be an http"):
        load({"AGW_TARGET": "gateway", "AGW_GATEWAY_URL": url})


def test_gateway_claude_api_defaults_to_openai():
    assert (
        load(
            {"AGW_TARGET": "gateway", "AGW_GATEWAY_URL": "https://gw.example/v1"}
        ).gateway_claude_api
        == "openai"
    )


def test_unknown_gateway_claude_api_rejected():
    with pytest.raises(ValueError, match="AGW_GATEWAY_CLAUDE_API"):
        load({"GOOGLE_CLOUD_PROJECT": "p", "AGW_GATEWAY_CLAUDE_API": "native"})


def test_anthropic_gateway_claude_api_requires_project():
    env = {
        "AGW_TARGET": "gateway",
        "AGW_GATEWAY_URL": "https://gw.example/v1",
        "AGW_GATEWAY_CLAUDE_API": "anthropic",
    }
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        load(env)
    with pytest.raises(ValueError, match="AGW_GATEWAY_API_KEY"):
        load({**env, "GOOGLE_CLOUD_PROJECT": "p"})
    full = {**env, "GOOGLE_CLOUD_PROJECT": "p", "AGW_GATEWAY_API_KEY": "k"}
    assert load(full).gateway_claude_api == "anthropic"


def test_gateway_claude_api_is_case_sensitive():
    with pytest.raises(ValueError, match="AGW_GATEWAY_CLAUDE_API"):
        load({"GOOGLE_CLOUD_PROJECT": "p", "AGW_GATEWAY_CLAUDE_API": "Anthropic"})
