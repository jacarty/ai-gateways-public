# Scenarios 20261024T141605Z-scenarios-bifrost-audit-fcf408: bifrost-audit

Test 6 (audit fidelity) on Bifrost transports/v2.2.6: four requests a cooperating caller puts in one session (x-bf-session-id) and tags with its own log headers (x-bf-lh-agw-case, x-bf-lh-agw-test), one of them refused (a model the key can't reach: 400), plus one untagged request. Run with run-audit.sh, which also sends one request through the agent (unchanged: it tags nothing) and then collects the trail each request left (Bifrost's logs store, Cloud Run request and container logs) into trail.json and trail.md. record_headers checks whether Bifrost returns a request id a caller could quote. The prompt carries a marker so stored content can be found.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-request-id` | `x-bf-request-id` | `x-bf-session-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 8133bddb-febd-430e-90bb-4e0ab98ceb7e | — | — | 1.2164 |  |
| session-gemini | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | 2360e2c6-5ca8-44f1-ab17-a7f870841d51 | — | — | 3.7141 |  |
| session-claude-stream | claude-haiku-5-5 | yes | status=200 | 1/1 | 200 | claude-haiku-5-5 | 7092c86c-2ce0-4a6b-b3a0-f4099a24aef1 | — | — | 1.1079 |  |
| session-unknown-model | agw-t6-no-such-model | no | status=400 | 1/1 | 400 | — | e5593d48-f0dd-47da-8ce5-c495896d6bcb | — | — | 0.0154 | {"is_bifrost_error":false,"error":{"message":"could not auto resolve a provider  |
| untagged-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | c43d10c1-7aea-493e-b0a8-b92be4f9de9e | — | — | 0.6324 |  |
