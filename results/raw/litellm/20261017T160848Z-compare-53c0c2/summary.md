# Compare 20261017T160848Z-compare-53c0c2

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | gateway | 1.1167 | 1.2189 | +0.102 | 5.6195 | 3.6274 | -1.992 |  |  |  | 1.0% | 4.0% |
| gemini-nostream-c5 | gateway | 1.1667 | 1.1992 | +0.032 | 1.7315 | 1.8481 | +0.117 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | gateway | 1.0672 | 1.0502 | -0.017 | 1.7235 | 1.7687 | +0.045 | 0.9372 | 0.9249 | -0.012 | 0.0% | 0.0% |
| gemini-stream-c5 | gateway | 1.1254 | 1.1504 | +0.025 | 1.5524 | 1.6349 | +0.083 | 0.9561 | 0.9702 | +0.014 | 0.0% | 0.0% |
| claude-nostream-c1 | gateway | 0.442 | 0.4702 | +0.028 | 0.7749 | 0.6946 | -0.080 |  |  |  | 0.0% | 0.0% |
| claude-nostream-c5 | gateway | 0.4219 | 0.4874 | +0.066 | 0.6548 | 0.7055 | +0.051 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | gateway | 0.4472 | 0.4644 | +0.017 | 0.762 | 0.6898 | -0.072 | 0.2454 | 0.2691 | +0.024 | 0.0% | 0.0% |
| claude-stream-c5 | gateway | 0.4438 | 0.4952 | +0.051 | 0.6577 | 0.7591 | +0.101 | 0.2353 | 0.3018 | +0.067 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 99/100 | 1.1167 | 5.6195 | 10.8617 | 5.6195 |  |  | 0.479 | 21.798 | 0.0 | 0/99 |
| gateway-gemini-nostream-c1 | 96/100 | 1.2189 | 3.6274 | 33.2233 | 5.002 |  |  | 0.499 | 21.7812 | None | unknown |
| direct-gemini-nostream-c5 | 100/100 | 1.1667 | 1.7315 | 2.5245 | 1.7315 |  |  | 3.779 | 21.79 | 0.0 | 0/100 |
| gateway-gemini-nostream-c5 | 100/100 | 1.1992 | 1.8481 | 2.8204 | 1.8481 |  |  | 3.732 | 21.76 | None | unknown |
| direct-gemini-stream-c1 | 100/100 | 1.0672 | 1.7235 | 2.9 | 1.7235 | 0.9372 | 1.6876 | 0.868 | 21.78 | 0.0 | 0/100 |
| gateway-gemini-stream-c1 | 100/100 | 1.0502 | 1.7687 | 3.4616 | 1.7687 | 0.9249 | 1.6945 | 0.858 | 21.78 | None | unknown |
| direct-gemini-stream-c5 | 100/100 | 1.1254 | 1.5524 | 1.6481 | 1.5524 | 0.9561 | 1.4775 | 3.898 | 22.07 | 0.0 | 0/100 |
| gateway-gemini-stream-c5 | 100/100 | 1.1504 | 1.6349 | 1.7929 | 1.6349 | 0.9702 | 1.5882 | 3.971 | 21.92 | None | unknown |
| direct-claude-nostream-c1 | 100/100 | 0.442 | 0.7749 | 0.8473 | 0.7749 |  |  | 2.163 | 46.52 | None | 0/100 |
| gateway-claude-nostream-c1 | 100/100 | 0.4702 | 0.6946 | 0.804 | 0.6946 |  |  | 2.104 | 46.2 | 0.0 | 0/100 |
| direct-claude-nostream-c5 | 100/100 | 0.4219 | 0.6548 | 0.778 | 0.6548 |  |  | 10.189 | 44.93 | None | 0/100 |
| gateway-claude-nostream-c5 | 100/100 | 0.4874 | 0.7055 | 1.128 | 0.7055 |  |  | 8.824 | 45.16 | 0.0 | 0/100 |
| direct-claude-stream-c1 | 100/100 | 0.4472 | 0.762 | 0.8344 | 0.762 | 0.2454 | 0.4792 | 2.137 | 46.83 | None | 0/100 |
| gateway-claude-stream-c1 | 100/100 | 0.4644 | 0.6898 | 0.8274 | 0.6898 | 0.2691 | 0.4332 | 2.137 | 46.06 | 0.0 | 0/100 |
| direct-claude-stream-c5 | 100/100 | 0.4438 | 0.6577 | 0.7498 | 0.6577 | 0.2353 | 0.4256 | 10.371 | 46.63 | None | 0/100 |
| gateway-claude-stream-c5 | 100/100 | 0.4952 | 0.7591 | 0.944 | 0.7591 | 0.3018 | 0.5431 | 8.539 | 46.34 | 0.0 | 0/100 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| gateway | gemini | 1 | 200 | 1.562 |  |
| gateway | claude | 1 | 200 | 1.0902 |  |
