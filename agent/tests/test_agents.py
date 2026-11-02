import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    monkeypatch.setenv("AGW_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("AGW_CLAUDE_MODEL", "claude-test")


def load_agent_module(name):
    # root_agent is built at import time, so import afresh under the test's env.
    sys.modules.pop(f"agw_agent.agents.{name}.agent", None)
    sys.modules.pop(f"agw_agent.agents.{name}", None)
    return importlib.import_module(f"agw_agent.agents.{name}")


def test_gemini_root_agent(env):
    root = load_agent_module("gemini").agent.root_agent
    assert root.name == "gemini_agent"
    assert root.model == "gemini-test"


def test_claude_root_agent(env):
    root = load_agent_module("claude").agent.root_agent
    assert root.name == "claude_agent"
    assert root.model.model == "claude-test"


def test_app_lists_exactly_gemini_and_claude(env):
    sys.modules.pop("agw_agent.app", None)
    app = importlib.import_module("agw_agent.app").app

    with TestClient(app) as client:
        response = client.get("/list-apps")
    assert response.status_code == 200
    assert sorted(response.json()) == ["claude", "gemini"]
