import base64
import json

import pytest

PREFIXES = ("AGW_", "GOOGLE_CLOUD_", "GOOGLE_GENAI_", "LITELLM_")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every test from settings exported in the developer's shell."""
    import os

    for name in list(os.environ):
        if name.startswith(PREFIXES):
            monkeypatch.delenv(name)


@pytest.fixture
def make_jwt():
    """Builds an unsigned JWT with the given expiry (the agent only reads `exp`)."""

    def make(exp: float, sub: str = "agw-agent") -> str:
        def part(d: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

        return f"{part({'alg': 'RS256'})}.{part({'exp': exp, 'sub': sub})}.sig"

    return make
