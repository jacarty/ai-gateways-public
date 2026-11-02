# Scenarios 20261018T135825Z-scenarios-litellm-cost-tpm-ba57d7: litellm-cost-tpm

Test 3 on LiteLLM v1.103.2: a token-per-minute limit. Run with the t3-tpm key (tpm_limit 1000; README.md). LiteLLM reserves input plus max_completion_tokens (256) before each call and settles to actual use after it, so one at a time about 9 requests fit (~100 tokens each), at once only about 3 (~300 reserved each), and a request whose cap alone exceeds the limit is refused without a call. Cases without a status expectation are read from their status mix.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tpm-one-at-a-time | claude-haiku-5-5 | no | — | 12/12 | 200, 429 | claude-haiku-5-5 | 0.0, 2.2000000000000003e-05, 2.816e-05, 3.663e-05, 3.7840000000000004e-05, 3.927e-05, 4.125e-05, 4.5980000000000004e-05 | 0, 2.2000000000000003e-05, 2.816e-05, 3.663e-05, 3.7840000000000004e-05, 3.927e-05, 4.125e-05, 4.5980000000000004e-05 | — | — | 60 | claude-haiku-5-5 | 0.3227 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
| tpm-refused | claude-haiku-5-5 | no | status=429, error_contains=rate limit | 1/1 | 429 | — | 0.0 | 0 | — | — | 60 | — | 0.0237 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
| tpm-at-once | claude-haiku-5-5 | no | — | 6/6 | 200, 429 | claude-haiku-5-5 | 0.00025113, 0.00027709, 0.00028391, 0.00030525 | 0, 2.5960000000000002e-05, 3.278e-05, 5.4120000000000004e-05 | — | — | 60 | claude-haiku-5-5 | 0.2081 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
| tpm-cap-above-limit | claude-haiku-5-5 | no | status=429 | 1/1 | 429 | — | 0.00036399 | 0 | — | — | 60 | — | 0.0748 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
| tpm-normal-request-still-fits | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.0003905 | 2.6510000000000002e-05 | — | — | — | claude-haiku-5-5 | 1.1739 |  |
