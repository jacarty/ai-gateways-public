# Scenarios 20261024T102132Z-scenarios-bifrost-cost-model-budget-d10e33: bifrost-cost-model-budget

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A $0.0003 budget on Gemini only (a model budget under the key's Vertex provider config; per-model budgets are enterprise-only in LiteLLM). A Gemini request costs about $0.00023: expect 2 through, then Gemini refused with 402 while Claude, with no budget of its own, still answers.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-spend-down | gemini-3.8-flash | no | — | 3/3 | 200, 402 | gemini-3.8-flash | 5.6394 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| gemini-refused | gemini-3.8-flash | no | status=402 | 1/1 | 402 | — | 0.0138 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| claude-still-answers | claude-haiku-5-5 | no | status=200 | 2/2 | 200 | claude-haiku-5-5 | 0.6527 |  |
