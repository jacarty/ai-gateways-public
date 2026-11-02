# Scenarios 20261018T135642Z-scenarios-litellm-cost-rpm-f0edf1: litellm-cost-rpm

Test 3 (cost control) on LiteLLM v1.103.2: a request-per-minute limit. Run with the t3-rpm key (rpm_limit 3; README.md). Expect the first three requests through, the next refused with a 429 before any model call, and requests allowed again once the 60 s window has passed.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rpm-within-limit | claude-haiku-5-5 | no | status=200 | 3/3 | 200 | claude-haiku-5-5 | 2.6510000000000002e-05, 3.333e-05, 4.752e-05 | 2.6510000000000002e-05, 3.333e-05, 4.752e-05 | — | — | — | claude-haiku-5-5 | 1.4848 |  |
| rpm-over-limit | claude-haiku-5-5 | no | status=429, error_contains=rate limit | 2/2 | 429 | — | 0.0 | 0 | — | — | 60 | — | 0.0211 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
| rpm-after-window | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.00013497 | 2.761e-05 | — | — | — | claude-haiku-5-5 | 1.0 |  |
