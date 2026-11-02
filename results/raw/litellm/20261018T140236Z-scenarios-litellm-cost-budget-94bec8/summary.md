# Scenarios 20261018T140236Z-scenarios-litellm-cost-budget-94bec8: litellm-cost-budget

Test 3 on LiteLLM v1.103.2: a hard dollar budget, one request at a time. Run with the t3-budget key (max_budget $0.0002; README.md). Each Claude request costs about $0.00003 and reserves about $0.00015 up front; expect about 7 through, then 429 "Budget has been exceeded" with no model call. x-litellm-key-spend shows the spend after each request; the final spend can pass the budget by at most one request.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| budget-spend-down | claude-haiku-5-5 | no | — | 10/10 | 200, 429 | claude-haiku-5-5 | 2.2000000000000003e-05, 2.4860000000000003e-05, 3.333e-05, 4.059e-05, 4.5430000000000004e-05, 5.0820000000000005e-05 | 2.2000000000000003e-05, 2.4860000000000003e-05, 3.333e-05, 4.059e-05, 4.5430000000000004e-05, 5.0820000000000005e-05 | — | — | — | claude-haiku-5-5 | 0.3388 | {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-budget (sk-...sD4Q |
| budget-refused | claude-haiku-5-5 | no | status=429, error_contains=budget has been exceeded | 2/2 | 429 | — | — | — | — | — | — | — | 0.0198 | {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-budget (sk-...sD4Q |
| budget-refused-gemini | gemini-3.8-flash | no | status=429, error_contains=budget has been exceeded | 1/1 | 429 | — | — | — | — | — | — | — | 0.0203 | {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-budget (sk-...sD4Q |
