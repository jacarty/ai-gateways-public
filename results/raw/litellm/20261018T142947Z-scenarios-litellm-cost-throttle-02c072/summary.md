# Scenarios 20261018T142947Z-scenarios-litellm-cost-throttle-02c072: litellm-cost-throttle

Test 3 config window on LiteLLM v1.103.2: throttle instead of block. Needs litellm_settings.budget_exceeded_throttle_percentage: 0.5 in config.yaml and the t3-throttle key (rpm_limit 4, max_budget $0.00001, throttle_on_budget_exceeded; README.md). After the first request the key is over budget; instead of a budget 429 it keeps working at half its rpm (2 a minute), then gets a rate-limit 429.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| throttle-spend-budget | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 2.4310000000000003e-05 | 2.4310000000000003e-05 | — | — | — | claude-haiku-5-5 | 0.5202 |  |
| throttle-within-half-rpm | claude-haiku-5-5 | no | status=200 | 2/2 | 200 | claude-haiku-5-5 | 5.0270000000000005e-05, 7.128e-05 | 2.5960000000000002e-05, 4.697e-05 | — | — | — | claude-haiku-5-5 | 0.5723 |  |
| throttle-over-half-rpm | claude-haiku-5-5 | no | status=429, error_contains=rate limit | 1/1 | 429 | — | 2.431e-05 | 0 | — | — | 60 | — | 0.0191 | {"error":{"message":"Rate limit exceeded for api_key: <sha256 redacted> |
