# Scenarios 20261031T183502Z-scenarios-kong-cost-rpm-7ebac2: kong-cost-rpm

Test 3 on Kong OSS 3.9.3, run through run-cost.sh with a throwaway consumer (its limit in the run's meta.json note). Kong's rate-limiting plugin on the consumer: 3 requests a minute, policy local (counted in the instance's memory; windows are clock minutes, and run-cost.sh starts the run just after one turns). Expect 3 answered, then Kong's 429 'API rate limit exceeded' with no model call, then answered again in the next minute. Kong OSS limits requests only: there is no token or spend limit (ai-rate-limiting-advanced is enterprise).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `ratelimit-limit` | `ratelimit-remaining` | `ratelimit-reset` | `retry-after` | `x-ratelimit-remaining-minute` | `x-kong-request-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rpm-within-limit | claude-haiku-5-5 | no | status=200 | 3/3 | 200 | claude-haiku-5-5 | 3 | 0, 1, 2 | 55, 56, 57 | — | 0, 1, 2 | 7bcd3918a7911f5d06b1f35115fc1952, 7f75597306cb915d7eae3a0197aa5c67, 81e26f47e3163b1544894e74c85c0e74 | 1.1636 |  |
| rpm-over-limit | claude-haiku-5-5 | no | status=429, error_contains=API rate limit exceeded | 2/2 | 429 | — | 3 | 0 | 54 | 54 | 0 | 298bd9734d804c6a284bb63560a5df0c, fae3a707ee12680ac65fb47759fc292d | 0.0131 | {   "message":"API rate limit exceeded",   "request_id":"298bd9734d804c6a284bb63; {   "message":"API rate limit exceeded",   "request_id":"fae3a707ee12680ac65fb47 |
| rpm-over-limit-other-model | gemini-3.8-flash | no | status=429 | 1/1 | 429 | — | 3 | 0 | 54 | 54 | 0 | 2edd2a6d723b91645309d007b802a06e | 0.0114 | {   "message":"API rate limit exceeded",   "request_id":"2edd2a6d723b91645309d00 |
| rpm-after-window | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 3 | 2 | 49 | — | 2 | 58d8463ab6a0844ec758226872499361 | 0.5015 |  |
