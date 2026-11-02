# Scenarios 20261024T101746Z-scenarios-bifrost-cost-rpm-beba9b: bifrost-cost-rpm

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A request limit of 3 a minute. Bifrost checks usage >= limit before each call and counts a request only after it succeeds, so expect 3 answered, then 429 with no model call, then answered again once the minute has passed (resets are swept every 10 s).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rpm-within-limit | claude-haiku-5-5 | no | status=200 | 3/3 | 200 | claude-haiku-5-5 | 0.8797 |  |
| rpm-over-limit | claude-haiku-5-5 | no | status=429 | 2/2 | 429 | — | 0.0125 | {"type":"request_limited","is_bifrost_error":false,"status_code":429,"error":{"m |
| rpm-after-window | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.4454 |  |
