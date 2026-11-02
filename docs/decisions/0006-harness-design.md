# 0006. Harness design: native APIs for direct, one client, Cloud Run job

- Status: Accepted
- Date: 2026-10-14

## Context

Test 1 measures what a gateway adds. The harness must give every target the same work, avoid adding its own noise, and run close to what it measures.

## Decision

- **Targets:** `direct`, `agent` and `gateway`. Direct uses each model's native API on the `eu` endpoint (Gemini `generateContent`/`streamGenerateContent`, Claude `rawPredict`/`streamRawPredict`), deliberately not OpenAI format, so any translation a gateway performs counts as its overhead. Agent uses ADK `/run` and `/run_sse`. Gateway uses OpenAI `/chat/completions`.
- **One httpx client** for all targets. Credentials are fetched before the clock starts, ID tokens are minted and refreshed by the harness, and 10 warm-up requests per cell are discarded.
- **Same work everywhere:** 10 rotated fixed prompts, the agent's instruction, a 256-token cap and the thinking condition (ADR 0005).
- **Metrics:** latency percentiles over successful requests, plus `latency_all_s` that also counts failed requests that were sent, so a target cannot look faster by failing slow requests fast. TTFT is the first streamed event carrying answer text. The run exits non-zero when more than 5% of requests fail.
- **Cloud Run job** (`agw-harness`, 1 vCPU, 3600 s timeout, `europe-west1`) running as its own service account. It writes to a gcsfuse-mounted results bucket; runs are copied into `results/raw/` and committed.
- **Baseline grid:** both models, streaming and not, concurrency 1 and 5; 200 requests per cell direct, 50 via the agent.

## Consequences

- The job's 1 vCPU and fixed timeout limit larger grids and higher concurrency.
- The 60 s httpx timeout is a gap between reads, not a total.
- Failover and screening scenarios (tests 2 and 4) are not built yet.
