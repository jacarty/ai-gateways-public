# Scenarios 20261018T141209Z-scenarios-litellm-cost-race-01ced7: litellm-cost-race

Test 3 on LiteLLM v1.103.2: the same budget under concurrency. Run with the t3-race key (max_budget $0.0005; README.md). Ten requests at once each reserve their worst case (~$0.00015) before any finishes, so only about 4 are admitted although ten would cost ~$0.0003 in total: the reservation trades unused budget for never overshooting. A second burst after the first has settled shows the freed budget.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-key-spend` | `x-litellm-response-cost` | `x-ratelimit-remaining-requests` | `x-ratelimit-remaining-tokens` | `retry-after` | `x-litellm-model-group` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| race-burst | claude-haiku-5-5 | no | — | 10/10 | 200, 429 | claude-haiku-5-5 | 2.288e-05, 2.4310000000000003e-05, 3.487e-05, 4.697e-05 | 2.288e-05, 2.4310000000000003e-05, 3.487e-05, 4.697e-05 | — | — | — | claude-haiku-5-5 | 0.7854 | {"error":{"message":"Budget has been exceeded! Key=<sha256 redacted> |
| race-second-burst | claude-haiku-5-5 | no | — | 10/10 | 200, 429 | claude-haiku-5-5 | 1.287e-05, 2.2000000000000003e-05, 3.487e-05 | 1.287e-05, 2.2000000000000003e-05, 3.487e-05 | — | — | — | claude-haiku-5-5 | 0.1422 | {"error":{"message":"Budget has been exceeded! Key=<sha256 redacted>; {"error":{"message":"Budget has been exceeded! Key=agw-t3-run-race (sk-...uzog)  |
