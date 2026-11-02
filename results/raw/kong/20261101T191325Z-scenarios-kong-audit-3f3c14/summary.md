# Scenarios 20261101T191325Z-scenarios-kong-audit-3f3c14: kong-audit

Test 6 (audit fidelity) on Kong OSS 3.9.3: five requests a cooperating caller tags with its own headers (x-agw-session, x-agw-case; Kong's file-log keeps every request header), two of them refused by Kong (Gemini asked for a model its route doesn't serve: 400; Claude at a model path with no route: 404), plus one untagged request. The 404 is refused before routing and authentication, so its Kong row has no route, service or consumer: only the caller's own tag says whose it was. Claude in native Vertex format (AGW_GATEWAY_CLAUDE_API=anthropic). Run with run-audit.sh, which also sends one request through the agent (unchanged: it tags nothing), makes and deletes one throwaway consumer through /admin-api (the admin change an auditor would ask about), and then collects the trail (Kong's file-log rows and Cloud Run's request logs for the gateway and the agent, all in Cloud Logging) into trail.json and trail.md. record_headers checks the request id Kong returns. The prompt carries a marker so stored content can be found.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-kong-request-id` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | b4e4505c6a43b91b41bf643738ce1c21 | 1.6014 |  |
| session-gemini | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | 97b08a47d7c6f250c5d6f8576cc41347 | 1.826 |  |
| session-claude-stream | claude-haiku-5-5 | yes | status=200 | 1/1 | 200 | claude-haiku-5-5 | c044c9579c9ea472a3bb1c7b68712f33 | 2.4677 |  |
| session-gemini-wrong-model | agw-t6-no-such-model | no | status=400 | 1/1 | 400 | — | b252e24672b0e8292163597b7d375c58 | 0.0123 | {"error":{"message":"cannot use own model - must be: gemini-3.8-flash"}} |
| session-claude-no-route | agw-t6-no-such-model | no | status=404 | 1/1 | 404 | — | f65b4427b2b54720ce5c9a5b267f2a09 | 0.0155 | {   "message":"no Route matched with those values",   "request_id":"f65b4427b2b5 |
| untagged-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | f7b9ff1def558f7891d5964e422ba529 | 0.405 |  |
