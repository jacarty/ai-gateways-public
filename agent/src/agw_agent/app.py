"""ASGI entry point: ADK's API server, serving one app per directory in agents/.

Callers pick the model by app name ("gemini" or "claude") on /run or /run_sse.
"""

import os
from pathlib import Path

from google.adk.cli.fast_api import get_fast_api_app

from agw_agent.config import load

# Fail at container start, not on the first request, if the settings are wrong.
settings = load()

if settings.target == "direct":
    # google-genai reads these itself; pin them to the Settings values so Gemini
    # and Claude can never end up on different endpoints.
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.model_location)
    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
else:
    # LiteLLM is imported lazily on the first request (~3.5 s), a cost the direct
    # baseline never pays; import it now so gateway runs start on equal terms.
    # The bundled cost map avoids a fetch from GitHub during that import.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from google.adk.models.lite_llm import _ensure_litellm_imported  # private, ADK 2.10

    _ensure_litellm_imported()

AGENTS_DIR = Path(__file__).parent / "agents"

app = get_fast_api_app(
    agents_dir=str(AGENTS_DIR),
    web=False,
    # Sessions live in memory: each benchmark request starts its own session.
    session_service_uri="memory://",
    auto_create_session=True,
)
