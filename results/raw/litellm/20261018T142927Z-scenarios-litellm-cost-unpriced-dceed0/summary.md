# Scenarios 20261018T142927Z-scenarios-litellm-cost-unpriced-dceed0: litellm-cost-unpriced

Test 3 config window on LiteLLM v1.103.2: a model with no price skips the budget. Needs test-claude-unpriced in config.yaml (Haiku with no input/output price) and the t3-unpriced key (max_budget $0.00001, with that model; README.md). The priced model is refused once the key is over budget; the unpriced one keeps answering and records $0 (see x-litellm-response-cost).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| priced-spends-budget | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 3.091e-05 | 3.091e-05 | — | — | — | claude-haiku-5-5 | 16.5447 |  |
| priced-refused | claude-haiku-5-5 | no | status=429, error_contains=budget has been exceeded | 1/1 | 429 | — | — | — | — | — | — | — | 0.0316 | {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-unpriced (sk-...FR |
| unpriced-still-answers | test-claude-unpriced | no | status=200 | 0/3 | 429 | — | — | — | — | — | — | — | 0.0185 | {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-unpriced (sk-...FR |
