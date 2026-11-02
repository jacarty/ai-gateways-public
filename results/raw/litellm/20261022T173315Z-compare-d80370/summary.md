# Compare 20261022T173315Z-compare-d80370

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.0871 | 1.1308 | +0.044 | 1.9868 | 2.5039 | +0.517 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 0.8262 | 1.2038 | +0.378 | 2.586 | 19.4724 | +16.886 | 0.6836 | 1.1363 | +0.453 | 0.0% | 5.0% |
| claude-nostream-c1 | agent | 0.5535 | 0.5988 | +0.045 | 0.7877 | 0.9577 | +0.170 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4628 | 0.5952 | +0.132 | 0.9365 | 0.9443 | +0.008 | 0.4067 | 0.4123 | +0.006 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.0871 | 1.9868 | 2.8896 | 1.9868 |  |  | 0.818 | 22.6 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 1.1308 | 2.5039 | 5.5208 | 2.5039 |  |  | 0.711 | 24.25 | 0.0 | 0/20 |
| direct-gemini-stream-c1 | 20/20 | 0.8262 | 2.586 | 4.0539 | 2.586 | 0.6836 | 2.5529 | 0.801 | 22.3 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 19/20 | 1.2038 | 19.4724 | 19.4724 | 2.7455 | 1.1363 | 19.3537 | 0.414 | 20.3684 | 10.8947 | 2/19 |
| direct-claude-nostream-c1 | 20/20 | 0.5535 | 0.7877 | 0.9657 | 0.7877 |  |  | 1.765 | 43.9 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.5988 | 0.9577 | 1.0255 | 0.9577 |  |  | 1.666 | 46.25 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4628 | 0.9365 | 1.0533 | 0.9365 | 0.4067 | 0.654 | 1.68 | 47.15 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.5952 | 0.9443 | 1.524 | 0.9443 | 0.4123 | 0.5877 | 1.552 | 45.95 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 20.1013 |  |
| agent | claude | 1 | 200 | 1.4637 |  |
