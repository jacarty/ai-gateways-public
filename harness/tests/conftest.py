import os

import pytest

from agw_harness.settings import load


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every test from settings exported in the developer's shell."""
    for name in list(os.environ):
        if name.startswith("AGW_"):
            monkeypatch.delenv(name)


@pytest.fixture
def settings():
    return load(
        {
            "AGW_PROJECT": "my-gcp-project",
            "AGW_AGENT_URL": "https://agent.example/",
            "AGW_GATEWAY_URL": "https://gw.example/v1",
        }
    )
