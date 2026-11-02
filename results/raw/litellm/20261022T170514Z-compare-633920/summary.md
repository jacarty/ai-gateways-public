# Compare 20261022T170514Z-compare-633920

## Paired (same job, alternating blocks)

Each target against `direct` in the same cell. p95 and p99 rest on a few samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the steadier overhead signal.

| Cell | Target | direct p50 s | p50 s | Δ p50 s | direct p95 s | p95 s | Δ p95 s | direct TTFT p50 s | TTFT p50 s | Δ TTFT p50 s | direct errors | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-nostream-c1 | agent | 1.0361 | 1.5699 | +0.534 | 2.9401 | 3.6647 | +0.725 |  |  |  | 0.0% | 0.0% |
| gemini-stream-c1 | agent | 1.1908 | 1.5065 | +0.316 | 2.1255 | 2.2915 | +0.166 | 1.0502 | 1.4091 | +0.359 | 0.0% | 0.0% |
| claude-nostream-c1 | agent | 0.4787 | 0.6064 | +0.128 | 0.9126 | 0.8611 | -0.051 |  |  |  | 0.0% | 0.0% |
| claude-stream-c1 | agent | 0.4877 | 0.6547 | +0.167 | 0.644 | 1.1275 | +0.483 | 0.2601 | 0.4027 | +0.143 | 0.0% | 0.0% |

## All runs

req/s is summed over blocks (each block drains to zero), so it compares between targets of one run, not with `load` or `baseline` runs.

| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s | req/s (blocks) | out tok | think tok | thinking > 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct-gemini-nostream-c1 | 20/20 | 1.0361 | 2.9401 | 2.985 | 2.9401 |  |  | 0.73 | 20.3 | 0.0 | 0/20 |
| agent-gemini-nostream-c1 | 20/20 | 1.5699 | 3.6647 | 3.809 | 3.6647 |  |  | 0.542 | 48.0 | 25.8 | 4/20 |
| direct-gemini-stream-c1 | 20/20 | 1.1908 | 2.1255 | 2.1593 | 2.1255 | 1.0502 | 2.0745 | 0.782 | 21.0 | 0.0 | 0/20 |
| agent-gemini-stream-c1 | 20/20 | 1.5065 | 2.2915 | 9.4874 | 2.2915 | 1.4091 | 1.9932 | 0.535 | 28.6 | 5.1 | 1/20 |
| direct-claude-nostream-c1 | 20/20 | 0.4787 | 0.9126 | 0.9377 | 0.9126 |  |  | 1.921 | 46.25 | None | 0/20 |
| agent-claude-nostream-c1 | 20/20 | 0.6064 | 0.8611 | 0.9087 | 0.8611 |  |  | 1.649 | 46.85 | 0.0 | 0/20 |
| direct-claude-stream-c1 | 20/20 | 0.4877 | 0.644 | 0.7009 | 0.644 | 0.2601 | 0.396 | 2.091 | 45.75 | None | 0/20 |
| agent-claude-stream-c1 | 20/20 | 0.6547 | 1.1275 | 1.2807 | 1.1275 | 0.4027 | 0.8393 | 1.448 | 46.65 | 0.0 | 0/20 |

## Pre-warm

The first attempt per target and model is a cold-start data point.

| Target | Model | Attempt | Status | Latency s | Error |
| --- | --- | --- | --- | --- | --- |
| agent | gemini | 1 | 504 | 60.7577 | upstream request timeout |
| agent | gemini | 2 | 200 | 36.6218 |  |
| agent | claude | 1 | 200 | 18.1651 |  |
