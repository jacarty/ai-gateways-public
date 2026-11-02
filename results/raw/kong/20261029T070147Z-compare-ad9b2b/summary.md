# Compare 20261029T070147Z-compare-ad9b2b

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | gateway | 1.7358 | 2.7077 | +0.972 | 4.7784 | 14.1532 | +9.375 |  |  |  | 0.0% | 1.0% |
| gemini-nostream-c5 | gateway | 1.7307 | 2.4542 | +0.724 | 5.3717 | 4.287 | -1.085 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | gateway | 1.732 | 2.6457 | +0.914 | 3.9906 | 7.8274 | +3.837 | 1.5807 | 2.6451 | +1.064 | 0.0% | 0.0% |
| gemini-stream-c5 | gateway | 1.4299 | 2.1537 | +0.724 | 1.971 | 3.1724 | +1.201 | 1.2589 | 2.153 | +0.894 | 0.0% | 0.0% |
| claude-nostream-c1 | gateway | 0.4773 | 0.5763 | +0.099 | 1.3279 | 1.5435 | +0.216 |  |  |  | 0.0% | 0.0% |
| claude-nostream-c5 | gateway | 0.5042 | 0.493 | -0.011 | 1.3118 | 1.1049 | -0.207 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | gateway | 0.4933 | 0.537 | +0.044 | 1.2867 | 1.0219 | -0.265 | 0.2843 | 0.3064 | +0.022 | 0.0% | 0.0% |
| claude-stream-c5 | gateway | 0.483 | 0.5242 | +0.041 | 1.1318 | 1.5166 | +0.385 | 0.274 | 0.3075 | +0.033 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 100/100 | 1.7358 | 4.7784 | 11.4005 | 4.7784 |  |  | 0.441 | 22.15 | 0.0 | 0/100 |
| gateway-gemini-nostream-c1 | 99/100 | 2.7077 | 14.1532 | 41.1669 | 14.1532 |  |  | 0.212 | 18.3232 | None | unknown |
| direct-gemini-nostream-c5 | 100/100 | 1.7307 | 5.3717 | 9.79 | 5.3717 |  |  | 1.698 | 21.23 | 0.0 | 0/100 |
| gateway-gemini-nostream-c5 | 100/100 | 2.4542 | 4.287 | 5.2521 | 4.287 |  |  | 1.686 | 18.14 | None | unknown |
| direct-gemini-stream-c1 | 100/100 | 1.732 | 3.9906 | 21.404 | 3.9906 | 1.5807 | 3.7088 | 0.39 | 21.92 | 0.0 | 0/100 |
| gateway-gemini-stream-c1 | 100/100 | 2.6457 | 7.8274 | 10.0982 | 7.8274 | 2.6451 | 7.8266 | 0.315 | None | None | unknown |
| direct-gemini-stream-c5 | 100/100 | 1.4299 | 1.971 | 2.2641 | 1.971 | 1.2589 | 1.7977 | 3.066 | 21.51 | 0.0 | 0/100 |
| gateway-gemini-stream-c5 | 100/100 | 2.1537 | 3.1724 | 3.2968 | 3.1724 | 2.153 | 3.1713 | 2.124 | None | None | unknown |
| direct-claude-nostream-c1 | 100/100 | 0.4773 | 1.3279 | 1.5968 | 1.3279 |  |  | 1.687 | 46.34 | None | 0/100 |
| gateway-claude-nostream-c1 | 100/100 | 0.5763 | 1.5435 | 2.2362 | 1.5435 |  |  | 1.428 | 46.16 | None | unknown |
| direct-claude-nostream-c5 | 100/100 | 0.5042 | 1.3118 | 1.6025 | 1.3118 |  |  | 6.698 | 47.35 | None | 0/100 |
| gateway-claude-nostream-c5 | 100/100 | 0.493 | 1.1049 | 1.6277 | 1.1049 |  |  | 7.533 | 46.02 | None | unknown |
| direct-claude-stream-c1 | 100/100 | 0.4933 | 1.2867 | 2.0566 | 1.2867 | 0.2843 | 1.1164 | 1.639 | 46.95 | None | 0/100 |
| gateway-claude-stream-c1 | 100/100 | 0.537 | 1.0219 | 1.6364 | 1.0219 | 0.3064 | 0.9713 | 1.659 | 46.4 | None | unknown |
| direct-claude-stream-c5 | 100/100 | 0.483 | 1.1318 | 1.6644 | 1.1318 | 0.274 | 0.8994 | 7.163 | 46.23 | None | 0/100 |
| gateway-claude-stream-c5 | 100/100 | 0.5242 | 1.5166 | 1.7273 | 1.5166 | 0.3075 | 1.366 | 6.956 | 47.1 | None | unknown |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| gateway | gemini | 1 | 200 | 1.8316 |  |
| gateway | claude | 1 | 200 | 0.9736 |  |
