# Compare 20261029T112207Z-compare-b0deb8

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.3428 | 1.4301 | +0.087 | 1.8032 | 2.0376 | +0.234 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 1.3392 | 1.6726 | +0.333 | 1.9946 | 3.0156 | +1.021 | 1.175 | 1.4096 | +0.235 | 0.0% | 5.0% |
| claude-nostream-c1 | agent | 0.4276 | 0.4483 | +0.021 | 0.774 | 0.7799 | +0.006 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4677 | 0.4667 | -0.001 | 1.2 | 0.7084 | -0.492 | 0.2607 | 0.263 | +0.002 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.3428 | 1.8032 | 4.3566 | 1.8032 |  |  | 0.685 | 21.8 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 1.4301 | 2.0376 | 2.536 | 2.0376 |  |  | 0.682 | 23.8 | 9.45 | 2/20 |
| direct-gemini-stream-c1 | 20/20 | 1.3392 | 1.9946 | 2.166 | 1.9946 | 1.175 | 1.7202 | 0.731 | 19.8 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 19/20 | 1.6726 | 3.0156 | 3.0156 | 3.0156 | 1.4096 | 2.9009 | 0.515 | 22.4211 | 29.7368 | 4/19 |
| direct-claude-nostream-c1 | 20/20 | 0.4276 | 0.774 | 1.559 | 0.774 |  |  | 1.977 | 44.25 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.4483 | 0.7799 | 1.523 | 0.7799 |  |  | 1.898 | 42.9 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4677 | 1.2 | 1.2716 | 1.2 | 0.2607 | 0.4344 | 1.868 | 46.4 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.4667 | 0.7084 | 0.7298 | 0.7084 | 0.263 | 0.5027 | 2.069 | 45.9 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 20.0065 |  |
| agent | claude | 1 | 200 | 1.5227 |  |
