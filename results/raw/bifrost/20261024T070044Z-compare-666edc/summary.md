# Compare 20261024T070044Z-compare-666edc

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | gateway | 2.0416 | 1.7088 | -0.333 | 6.887 | 5.882 | -1.005 |  |  |  | 0.0% | 0.0% |
| gemini-nostream-c5 | gateway | 1.4594 | 1.4276 | -0.032 | 2.4561 | 2.475 | +0.019 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | gateway | 1.5142 | 1.4694 | -0.045 | 2.7867 | 2.8419 | +0.055 | 1.3248 | 1.3216 | -0.003 | 0.0% | 0.0% |
| gemini-stream-c5 | gateway | 1.4537 | 1.303 | -0.151 | 2.2684 | 2.8089 | +0.540 | 1.2768 | 1.1475 | -0.129 | 0.0% | 0.0% |
| claude-nostream-c1 | gateway | 0.5257 | 0.4564 | -0.069 | 1.0326 | 1.0434 | +0.011 |  |  |  | 0.0% | 0.0% |
| claude-nostream-c5 | gateway | 0.5187 | 0.5411 | +0.022 | 0.8639 | 1.2596 | +0.396 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | gateway | 0.4507 | 0.5087 | +0.058 | 0.984 | 1.2359 | +0.252 | 0.2424 | 0.3176 | +0.075 | 0.0% | 0.0% |
| claude-stream-c5 | gateway | 0.492 | 0.4844 | -0.008 | 1.29 | 0.8899 | -0.400 | 0.2725 | 0.2928 | +0.020 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 100/100 | 2.0416 | 6.887 | 10.0071 | 6.887 |  |  | 0.347 | 20.87 | 0.82 | 1/100 |
| gateway-gemini-nostream-c1 | 100/100 | 1.7088 | 5.882 | 9.3059 | 5.882 |  |  | 0.45 | 22.88 | 125.0 | 1/1 of 100 |
| direct-gemini-nostream-c5 | 100/100 | 1.4594 | 2.4561 | 2.951 | 2.4561 |  |  | 2.925 | 22.41 | 1.34 | 1/100 |
| gateway-gemini-nostream-c5 | 100/100 | 1.4276 | 2.475 | 3.3092 | 2.475 |  |  | 2.876 | 21.41 | None | unknown |
| direct-gemini-stream-c1 | 100/100 | 1.5142 | 2.7867 | 8.6114 | 2.7867 | 1.3248 | 2.6256 | 0.559 | 20.7 | 0.0 | 0/100 |
| gateway-gemini-stream-c1 | 100/100 | 1.4694 | 2.8419 | 4.5124 | 2.8419 | 1.3216 | 2.7176 | 0.604 | 21.32 | None | unknown |
| direct-gemini-stream-c5 | 100/100 | 1.4537 | 2.2684 | 2.9508 | 2.2684 | 1.2768 | 2.1969 | 2.95 | 21.85 | 0.0 | 0/100 |
| gateway-gemini-stream-c5 | 100/100 | 1.303 | 2.8089 | 5.2092 | 2.8089 | 1.1475 | 2.7489 | 2.907 | 21.17 | None | unknown |
| direct-claude-nostream-c1 | 100/100 | 0.5257 | 1.0326 | 1.2137 | 1.0326 |  |  | 1.794 | 46.36 | None | 0/100 |
| gateway-claude-nostream-c1 | 100/100 | 0.4564 | 1.0434 | 1.4443 | 1.0434 |  |  | 1.843 | 45.44 | None | unknown |
| direct-claude-nostream-c5 | 100/100 | 0.5187 | 0.8639 | 1.2068 | 0.8639 |  |  | 7.974 | 46.58 | None | 0/100 |
| gateway-claude-nostream-c5 | 100/100 | 0.5411 | 1.2596 | 1.3938 | 1.2596 |  |  | 7.485 | 47.01 | None | unknown |
| direct-claude-stream-c1 | 100/100 | 0.4507 | 0.984 | 1.2648 | 0.984 | 0.2424 | 0.8103 | 1.954 | 44.63 | None | 0/100 |
| gateway-claude-stream-c1 | 100/100 | 0.5087 | 1.2359 | 1.899 | 1.2359 | 0.3176 | 1.0795 | 1.551 | 45.55 | None | unknown |
| direct-claude-stream-c5 | 100/100 | 0.492 | 1.29 | 1.5428 | 1.29 | 0.2725 | 1.0189 | 7.495 | 46.05 | None | 0/100 |
| gateway-claude-stream-c5 | 100/100 | 0.4844 | 0.8899 | 1.2343 | 0.8899 | 0.2928 | 0.6804 | 8.49 | 46.28 | None | unknown |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| gateway | gemini | 1 | 200 | 13.6968 |  |
| gateway | claude | 1 | 200 | 2.2172 |  |
