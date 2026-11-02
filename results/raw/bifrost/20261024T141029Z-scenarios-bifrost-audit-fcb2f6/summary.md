# Scenarios 20261024T141029Z-scenarios-bifrost-audit-fcb2f6: bifrost-audit

Test 6 (audit fidelity) on Bifrost transports/v2.2.6: four requests a cooperating caller puts in one session (x-bf-session-id) and tags with its own log headers (x-bf-lh-agw-case, x-bf-lh-agw-test), one of them refused (a model the key can't reach: 400), plus one untagged request. Run with run-audit.sh, which also sends one request through the agent (unchanged: it tags nothing) and then collects the trail each request left (Bifrost's logs store, Cloud Run request and container logs) into trail.json and trail.md. record_headers checks whether Bifrost returns a request id a caller could quote. The prompt carries a marker so stored content can be found.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-request-id` | `x-bf-request-id` | `x-bf-session-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 08bceb79-c029-4ed5-8ba0-70f555ffeca3 | — | — | 1.1184 |  |
| session-gemini | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | 5f1b1375-1ee7-401f-bb7d-6bec03d91661 | — | — | 1.5728 |  |
| session-claude-stream | claude-haiku-5-5 | yes | status=200 | 1/1 | 200 | claude-haiku-5-5 | 051f4a18-33f4-4694-9995-15322326a9d4 | — | — | 1.6537 |  |
| session-unknown-model | agw-t6-no-such-model | no | status=400 | 1/1 | 400 | — | 9932969f-b1d5-4340-bb0b-c403bfa632b7 | — | — | 0.0155 | {"is_bifrost_error":false,"error":{"message":"could not auto resolve a provider  |
| untagged-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | cafb1900-44b0-49a7-9f68-3a0925e38f66 | — | — | 0.6741 |  |
