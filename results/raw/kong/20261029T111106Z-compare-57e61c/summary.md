# Compare 20261029T111106Z-compare-57e61c

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.4692 | 2.8836 | +1.414 | 7.913 | 4.2459 | -3.667 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 1.5778 | 2.6618 | +1.084 | 4.6995 | 3.7152 | -0.984 | 1.4334 | 2.6539 | +1.221 | 0.0% | 10.0% |
| claude-nostream-c1 | agent | 0.4293 | 0.4859 | +0.057 | 0.6022 | 1.5593 | +0.957 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4481 | 0.491 | +0.043 | 0.9783 | 0.6782 | -0.300 | 0.2664 | 0.288 | +0.022 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.4692 | 7.913 | 13.5503 | 7.913 |  |  | 0.375 | 21.55 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 2.8836 | 4.2459 | 53.4649 | 4.2459 |  |  | 0.186 | 15.3 | 0.0 | 0/20 |
| direct-gemini-stream-c1 | 20/20 | 1.5778 | 4.6995 | 8.91 | 4.6995 | 1.4334 | 4.1434 | 0.473 | 22.35 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 18/20 | 2.6618 | 3.7152 | 3.7152 | 3.5722 | 2.6539 | 3.7034 | 0.324 | 19.7778 | 0.0 | 0/18 |
| direct-claude-nostream-c1 | 20/20 | 0.4293 | 0.6022 | 0.6764 | 0.6022 |  |  | 2.336 | 45.25 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.4859 | 1.5593 | 2.3296 | 1.5593 |  |  | 1.596 | 46.75 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4481 | 0.9783 | 1.0632 | 0.9783 | 0.2664 | 0.8487 | 1.937 | 42.4 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.491 | 0.6782 | 1.0971 | 0.6782 | 0.288 | 0.3769 | 1.963 | 46.0 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 98.2026 |  |
| agent | claude | 1 | 200 | 1.9511 |  |
