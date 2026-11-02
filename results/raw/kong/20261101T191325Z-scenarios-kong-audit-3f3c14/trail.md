# Test 6 trail (Kong)

Window 2026-11-01T19:13:21.127823Z to 2026-11-01T19:14:33.330381Z: 9 Kong rows, 9 gateway request-log entries, 0 entries naming a Google identity.

Collection: complete.

| Request | Status | Kong row | Joined by | Consumer | Route | Session | Tag | Tokens | Cloud Run entry (by trace) | Prompt logged | Credentials redacted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | found | request id | harness | claude-raw-predict | agw-t6-session | session-claude | - | yes (200) | no | yes |
| session-gemini | 200 | found | request id | harness | gemini-chat | agw-t6-session | session-gemini | 47 | yes (200) | no | yes |
| session-claude-stream | 200 | found | request id | harness | claude-stream-raw-predict | agw-t6-session | session-claude-stream | - | yes (200) | no | yes |
| session-gemini-wrong-model | 400 | found | request id | harness | gemini-chat | agw-t6-session | session-gemini-wrong-model | 0 | yes (400) | no | yes |
| session-claude-no-route | 404 | found | request id | - | - | agw-t6-session | session-claude-no-route | - | yes (404) | no | yes |
| untagged-claude | 200 | found | request id | harness | claude-raw-predict | - | - | - | yes (200) | no | yes |

**Agent run** (session `agw-t6-agent-20261101T191332`, HTTP 200): 1 Kong row(s) by consumer `agent` and time, user agent `AsyncAnthropicVertex/Python 1.9.0`; joined to the agent's `/run` by trace: no (its row's traceparent trace 554e4927979e1b047643b8f2e0bb1e5b, the agent's /run trace 92a48994b983edd63d3f5eab81a60822).

**Admin probe** (a throwaway consumer made and deleted through `/admin-api`):

- 2026-11-01T19:13:33.239000Z POST /admin-api/consumers → 201, consumer `admin`, user agent `curl/8.14.1`
- 2026-11-01T19:13:33.299000Z DELETE /admin-api/consumers/agw-t6-admin-probe-20261101T191333-987837 → 204, consumer `admin`, user agent `curl/8.14.1` (names the probe)

Unjoined Kong rows: 0. Response headers recorded: {"session-claude": {"x-kong-request-id": "b4e4505c6a43b91b41bf643738ce1c21"}, "session-gemini": {"x-kong-request-id": "97b08a47d7c6f250c5d6f8576cc41347"}, "session-claude-stream": {"x-kong-request-id": "c044c9579c9ea472a3bb1c7b68712f33"}, "session-gemini-wrong-model": {"x-kong-request-id": "b252e24672b0e8292163597b7d375c58"}, "session-claude-no-route": {"x-kong-request-id": "f65b4427b2b54720ce5c9a5b267f2a09"}, "untagged-claude": {"x-kong-request-id": "f7b9ff1def558f7891d5964e422ba529"}}
