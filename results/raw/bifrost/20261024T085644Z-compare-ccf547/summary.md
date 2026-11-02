# Compare 20261024T085644Z-compare-ccf547

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 2.8548 | 3.2283 | +0.373 | 11.509 | 11.5747 | +0.066 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 1.5391 | 1.876 | +0.337 | 2.3709 | 5.3907 | +3.020 | 1.4934 | 1.7149 | +0.222 | 0.0% | 0.0% |
| claude-nostream-c1 | agent | 0.4758 | 0.4747 | -0.001 | 0.7361 | 1.2698 | +0.534 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4214 | 0.4886 | +0.067 | 0.8015 | 0.5784 | -0.223 | 0.271 | 0.2692 | -0.002 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 2.8548 | 11.509 | 13.0368 | 11.509 |  |  | 0.211 | 20.0 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 3.2283 | 11.5747 | 12.7033 | 11.5747 |  |  | 0.224 | 23.0 | 6.35 | 2/20 |
| direct-gemini-stream-c1 | 20/20 | 1.5391 | 2.3709 | 2.6959 | 2.3709 | 1.4934 | 2.2713 | 0.576 | 23.25 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 20/20 | 1.876 | 5.3907 | 10.8189 | 5.3907 | 1.7149 | 5.1882 | 0.383 | 22.7 | 0.0 | 0/20 |
| direct-claude-nostream-c1 | 20/20 | 0.4758 | 0.7361 | 1.1424 | 0.7361 |  |  | 1.906 | 45.05 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.4747 | 1.2698 | 1.3116 | 1.2698 |  |  | 1.644 | 46.05 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4214 | 0.8015 | 1.5641 | 0.8015 | 0.271 | 0.7282 | 1.833 | 47.3 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.4886 | 0.5784 | 0.8834 | 0.5784 | 0.2692 | 0.4569 | 2.118 | 43.35 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 21.3613 |  |
| agent | claude | 1 | 200 | 1.8098 |  |
