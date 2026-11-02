# 0005. Fix the thinking condition: Gemini LOW, Claude off

- Status: Accepted
- Date: 2026-10-14

## Context

Thinking tokens change latency and cost and can use up `max_output_tokens` before the answer. `gemini-3.8-flash` rejects `MINIMAL` with a 400; `LOW` is its floor. Setting it cut Gemini's tokens for a one-line answer from 203 to 54 (plan, Decisions).

## Decision

Every run uses Gemini at thinking level `LOW` and Claude without thinking, a 256-token cap and a two-sentence instruction. Direct calls set Gemini's `thinking_config`. Through a gateway the same intent is sent as OpenAI `reasoning_effort: "low"`, because ADK's LiteLLM path ignores `thinking_config`. Whether each gateway honours it is recorded as a finding (check `thoughtsTokenCount`).

## Consequences

- Latency and cost compare like with like across direct, agent and gateway paths.
- Through the agent, about 1-4 in 50 Gemini requests still used some thinking (direct: none), probably from ADK's added system-prompt text (`results/summary.md`).
- Gateway mode sends `max_completion_tokens` rather than `max_tokens`; each gateway's mapping is a per-gateway comparability check.
