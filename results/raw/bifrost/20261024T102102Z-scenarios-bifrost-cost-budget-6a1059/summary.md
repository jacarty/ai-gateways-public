# Scenarios 20261024T102102Z-scenarios-bifrost-cost-budget-6a1059: bifrost-cost-budget

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A $0.0002 budget (1 h), one request at a time. A Claude request costs about $0.00003 at the override price; expect about 7 through, the one that crosses admitted, then 402 with no model call, for either model. quota.json shows the final usage.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| budget-spend-down | claude-haiku-5-5 | no | — | 10/10 | 200, 402 | claude-haiku-5-5 | 0.4535 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| budget-refused | claude-haiku-5-5 | no | status=402 | 2/2 | 402 | — | 0.0125 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| budget-refused-gemini | gemini-3.8-flash | no | status=402 | 1/1 | 402 | — | 0.0143 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
