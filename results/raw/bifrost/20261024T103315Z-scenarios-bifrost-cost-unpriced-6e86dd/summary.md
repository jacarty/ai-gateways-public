# Scenarios 20261024T103315Z-scenarios-bifrost-cost-unpriced-6e86dd: bifrost-cost-unpriced

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). Needs the test 3 window (README.md): test-claude-unpriced, an alias to the real Claude model whose canonical model_name has no price. Bifrost charges a budget only when cost > 0, so unpriced requests should never spend the $0.0001 budget: expect all of them answered, then priced Claude requests to spend it and be refused.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unpriced-not-charged | test-claude-unpriced | no | status=200 | 3/8 | 200, 402 | claude-haiku-5-5 | 0.0122 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| priced-spends-budget | claude-haiku-5-5 | no | — | 5/5 | 402 | — | 0.0119 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| priced-refused | claude-haiku-5-5 | no | status=402 | 1/1 | 402 | — | 0.0116 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| unpriced-refused-once-spent | test-claude-unpriced | no | status=402 | 1/1 | 402 | — | 0.0124 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
