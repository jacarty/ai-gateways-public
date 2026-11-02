# Scenarios 20261101T191644Z-scenarios-kong-audit-e32ee9: kong-audit

Test 6 (audit fidelity) on Kong OSS 3.9.3: five requests a cooperating caller tags with its own headers (x-agw-session, x-agw-case; Kong's file-log keeps every request header), two of them refused by Kong (Gemini asked for a model its route doesn't serve: 400; Claude at a model path with no route: 404), plus one untagged request. The 404 is refused before routing and authentication, so its Kong row has no route, service or consumer: only the caller's own tag says whose it was. Claude in native Vertex format (AGW_GATEWAY_CLAUDE_API=anthropic). Run with run-audit.sh, which also sends one request through the agent (unchanged: it tags nothing), makes and deletes one throwaway consumer through /admin-api (the admin change an auditor would ask about), and then collects the trail (Kong's file-log rows and Cloud Run's request logs for the gateway and the agent, all in Cloud Logging) into trail.json and trail.md. record_headers checks the request id Kong returns. The prompt carries a marker so stored content can be found.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-kong-request-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 52ba156bc45daf2cf79ec33a89be6d3d | 0.7807 |  |
| session-gemini | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | d4aa7a11861255447a987126e9622879 | 1.6498 |  |
| session-claude-stream | claude-haiku-5-5 | yes | status=200 | 1/1 | 200 | claude-haiku-5-5 | 06a7f47f24c4054f9d2d4741d461c112 | 0.4629 |  |
| session-gemini-wrong-model | agw-t6-no-such-model | no | status=400 | 1/1 | 400 | — | cf35b00e99ed432804124617adaf4873 | 0.0144 | {"error":{"message":"cannot use own model - must be: gemini-3.8-flash"}} |
| session-claude-no-route | agw-t6-no-such-model | no | status=404 | 1/1 | 404 | — | 9d8c5b12df19df05ef1d8e1b19659070 | 0.0112 | {   "message":"no Route matched with those values",   "request_id":"9d8c5b12df19 |
| untagged-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | aefe2a0d2dae50071d30c8520f425b36 | 0.7098 |  |
