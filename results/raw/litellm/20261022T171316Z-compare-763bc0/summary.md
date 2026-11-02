# Compare 20261022T171316Z-compare-763bc0

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.1667 | 1.1572 | -0.010 | 1.8025 | 2.6211 | +0.819 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 0.9586 | 1.287 | +0.328 | 2.1156 | 2.2231 | +0.107 | 0.8284 | 1.1358 | +0.307 | 0.0% | 0.0% |
| claude-nostream-c1 | agent | 0.5054 | 0.595 | +0.090 | 0.7292 | 1.4623 | +0.733 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.5578 | 0.6301 | +0.072 | 0.9217 | 1.6599 | +0.738 | 0.3229 | 0.415 | +0.092 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.1667 | 1.8025 | 2.2926 | 1.8025 |  |  | 0.824 | 21.9 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 1.1572 | 2.6211 | 3.2352 | 2.6211 |  |  | 0.7 | 32.95 | 11.85 | 2/20 |
| direct-gemini-stream-c1 | 20/20 | 0.9586 | 2.1156 | 2.7121 | 2.1156 | 0.8284 | 2.0515 | 0.819 | 20.9 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 20/20 | 1.287 | 2.2231 | 2.7476 | 2.2231 | 1.1358 | 2.0001 | 0.698 | 32.1 | 10.1 | 2/20 |
| direct-claude-nostream-c1 | 20/20 | 0.5054 | 0.7292 | 0.7865 | 0.7292 |  |  | 1.928 | 45.7 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.595 | 1.4623 | 2.1391 | 1.4623 |  |  | 1.365 | 49.0 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.5578 | 0.9217 | 1.4364 | 0.9217 | 0.3229 | 0.8886 | 1.62 | 44.2 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.6301 | 1.6599 | 1.675 | 1.6599 | 0.415 | 1.3837 | 1.295 | 45.45 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 3.1606 |  |
| agent | claude | 1 | 200 | 2.4265 |  |
