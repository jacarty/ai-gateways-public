# 0001. Scope: three OSS gateways, agent-to-model traffic only

- Status: Accepted
- Date: 2026-10-14

## Context

The original idea included Gemini Agent Gateway and Model Armor. Day-1 research (`docs/day1-checks.md`) showed that the three OSS gateways already fill the learning loop and the seven-test matrix, and that vendor-written comparisons are the gap this repo addresses. The plan was revised on 2026-10-12.

## Decision

The project covers LiteLLM, Bifrost and Kong OSS only, in front of one ADK agent calling Gemini and Claude on the Agent Platform. Gemini Agent Gateway and Model Armor move to a separate project. Only agent-to-model traffic is in scope: no MCP or tool traffic, A2A, or client-to-agent ingress. Only free OSS editions are used, with no paid licences or trials; what each test needed from a paid tier is recorded in the OSS-ceiling column.

## Consequences

- Three phases of gateway work plus write-up (milestones in `docs/plan-v0.1.md`).
- Screening (test 4) is expected to hit the OSS ceiling on all three gateways, and tests 2 and 3 on Kong. These are results, not failures.
