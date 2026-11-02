# Scenarios 20261024T102157Z-scenarios-bifrost-cost-reset-0a2109: bifrost-cost-reset

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A $0.0001 budget that resets every minute. Spend it, be refused, wait, and be admitted again: shows when a reset actually lands (swept every 10 s; an expired window is skipped, not denied, until swept).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reset-spend-down | claude-haiku-5-5 | no | — | 5/5 | 200, 402 | claude-haiku-5-5 | 0.4698 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| reset-refused | claude-haiku-5-5 | no | status=402 | 1/1 | 402 | — | 0.0136 | {"type":"budget_exceeded","is_bifrost_error":false,"status_code":402,"error":{"m |
| reset-after-window | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 1.0911 |  |
