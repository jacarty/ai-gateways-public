# Compare 20261024T072947Z-compare-6f69ab

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.1501 | 1.3642 | +0.214 | 1.9525 | 2.257 | +0.305 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 1.5675 | 1.5112 | -0.056 | 2.881 | 2.9528 | +0.072 | 1.4345 | 1.3709 | -0.064 | 0.0% | 5.0% |
| claude-nostream-c1 | agent | 0.4768 | 0.5433 | +0.067 | 1.0295 | 1.2586 | +0.229 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4909 | 0.5599 | +0.069 | 1.3554 | 1.0396 | -0.316 | 0.2853 | 0.344 | +0.059 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.1501 | 1.9525 | 2.0471 | 1.9525 |  |  | 0.774 | 22.05 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 1.3642 | 2.257 | 2.5617 | 2.257 |  |  | 0.655 | 37.95 | 15.4 | 3/20 |
| direct-gemini-stream-c1 | 20/20 | 1.5675 | 2.881 | 3.9608 | 2.881 | 1.4345 | 2.7894 | 0.559 | 21.8 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 19/20 | 1.5112 | 2.9528 | 2.9528 | 2.9528 | 1.3709 | 2.8522 | 0.553 | 25.7895 | 6.8947 | 1/19 |
| direct-claude-nostream-c1 | 20/20 | 0.4768 | 1.0295 | 1.5906 | 1.0295 |  |  | 1.714 | 44.6 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.5433 | 1.2586 | 1.2773 | 1.2586 |  |  | 1.583 | 47.9 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4909 | 1.3554 | 1.6661 | 1.3554 | 0.2853 | 1.1876 | 1.515 | 46.85 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.5599 | 1.0396 | 1.0527 | 1.0396 | 0.344 | 0.7068 | 1.56 | 46.65 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 200 | 46.2234 |  |
| agent | claude | 1 | 200 | 1.2721 |  |
