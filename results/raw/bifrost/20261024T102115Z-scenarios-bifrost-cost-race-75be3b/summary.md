# Scenarios 20261024T102115Z-scenarios-bifrost-cost-race-75be3b: bifrost-cost-race

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A $0.0001 budget (about 3 Claude requests) and ten requests at once. With no reservation, every request that starts before any usage is charged should be admitted: expect the burst to overshoot the budget, and the next burst refused.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| race-burst | claude-haiku-5-5 | no | — | 10/10 | 200 | claude-haiku-5-5 | 0.6194 |  |
| race-second-burst | claude-haiku-5-5 | no | status=402 | 10/10 | 402 | — | 0.0561 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
