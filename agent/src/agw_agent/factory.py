"""The one agent definition, instantiated once per model."""

from google.adk.agents import LlmAgent
from google.genai import types

from agw_agent.config import load
from agw_agent.models import ModelKind, build_model

# Short, fixed answers keep token use, cost and latency variance low across runs.
INSTRUCTION = (
    "You are a test agent used to benchmark AI gateways. "
    "Answer the user's question accurately in at most two sentences."
)


# Fixed test condition: Gemini thinks at the lowest level it accepts and Claude
# not at all (its default), so latency and cost compare like with like and
# thinking tokens can't consume the max_output_tokens budget before the answer.
# gemini-3.8-flash rejects MINIMAL ("Thinking level is unsupported"); LOW is its floor.
GEMINI_THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


def make_agent(kind: ModelKind) -> LlmAgent:
    settings = load()
    return LlmAgent(
        name=f"{kind}_agent",
        model=build_model(kind, settings),
        instruction=INSTRUCTION,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=settings.max_output_tokens,
            # ADK's Claude raises on a ThinkingConfig without thinking_budget, and
            # no thinking (its default) is Claude's test condition.
            thinking_config=GEMINI_THINKING if kind == "gemini" else None,
        ),
    )
