# Scenarios 20261024T101931Z-scenarios-bifrost-cost-tpm-3d12b5: bifrost-cost-tpm

Test 3 on Bifrost transports/v2.2.6, run through run-cost.sh with a throwaway key (limits in the run's NOTE.md and quota.json). A token limit of 1000 a minute. Checked as usage >= limit before the call, with usage charged after the response: one at a time, the request that crosses is admitted and the next refused; at once, every request that starts below the limit is admitted, so a burst can overshoot (LiteLLM reserved each request's worst case and refused bursts early).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tpm-one-at-a-time | claude-haiku-5-5 | no | — | 12/12 | 200, 429 | claude-haiku-5-5 | 0.4295 | {"type":"token_limited","is_bifrost_error":false,"status_code":429,"error":{"mes |
| tpm-refused | claude-haiku-5-5 | no | status=429 | 1/1 | 429 | — | 0.0111 | {"type":"token_limited","is_bifrost_error":false,"status_code":429,"error":{"mes |
| tpm-at-once | claude-haiku-5-5 | no | — | 12/12 | 200 | claude-haiku-5-5 | 1.0467 |  |
| tpm-refused-after-burst | claude-haiku-5-5 | no | status=429 | 1/1 | 429 | — | 0.0138 | {"type":"token_limited","is_bifrost_error":false,"status_code":429,"error":{"mes |
