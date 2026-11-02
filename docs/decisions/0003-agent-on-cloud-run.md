# 0003. Host the ADK agent on Cloud Run

- Status: Accepted
- Date: 2026-10-14 (decided 2026-10-13)

## Context

The agent must stay identical across the baseline and all gateways. The alternative was Agent Runtime (formerly Vertex AI Agent Engine).

## Decision

The agent runs as a private Cloud Run service (`agw-agent`, min-instances 0, IAM-authenticated) serving two ADK apps, `gemini` and `claude`, from one image. Environment variables (`AGW_TARGET`, `AGW_GATEWAY_URL`, ...) switch it between direct-to-model and a gateway; the code never changes. In gateway mode both apps call the gateway through LiteLLM's client using the same model names, which each gateway's config maps to the real models.

Reasons recorded in the plan: the same platform as the gateways makes the agent-to-gateway path identical for all three, and ID-token auth gives test 5 a clean workload-identity case.

## Consequences

- Cloud Run limits shape agent-path load tests (at most 2 instances, concurrency 20, 60 s request timeout), so the main overhead number comes from harness to gateway, with a shorter end-to-end agent run.
- Images need building without local Docker (ADR 0004).
- ADK only lists directory apps, so each app is `agents/<name>/agent.py` defining `root_agent`.
