# Scenarios 20261031T183801Z-scenarios-kong-cost-model-limit-0712ab: kong-cost-model-limit

Test 3 on Kong OSS 3.9.3, run through run-cost.sh with a throwaway consumer (its limit in the run's meta.json note). 1 request a minute on the Gemini route only (a plugin scoped to the consumer and the gemini-chat route), policy local. A per-model request limit: expect Gemini answered once, then refused, while Claude, on a route with no limit for this consumer, still answers.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `ratelimit-limit` | `ratelimit-remaining` | `ratelimit-reset` | `retry-after` | `x-ratelimit-remaining-minute` | `x-kong-request-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-within-limit | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | 1 | 0 | 58 | — | 0 | 815944783a1d617a4f381d241846531e | 1.7411 |  |
| gemini-refused | gemini-3.8-flash | no | status=429 | 1/1 | 429 | — | 1 | 0 | 56 | 56 | 0 | 576cd50a13a8da14c54fb461268a167e | 0.0118 | {   "message":"API rate limit exceeded",   "request_id":"576cd50a13a8da14c54fb46 |
| claude-still-answers | claude-haiku-5-5 | no | status=200 | 2/2 | 200 | claude-haiku-5-5 | — | — | — | — | — | 8f99bc68a5e0be7904d27d4a8480a17a, eec0174b9c1a87700004864b6ef9202f | 0.6495 |  |
