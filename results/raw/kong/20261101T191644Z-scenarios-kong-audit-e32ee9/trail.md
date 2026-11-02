# Test 6 trail (Kong)

Window 2026-11-01T19:16:40.328517Z to 2026-11-01T19:17:50.605737Z: 9 Kong rows, 9 gateway request-log entries, 0 entries naming a Google identity.

Collection: complete.

| Request | Status | Kong row | Joined by | Consumer | Route | Session | Tag | Tokens | Cloud Run entry (by trace) | Prompt logged | Credentials redacted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | found | request id | harness | claude-raw-predict | agw-t6-session | session-claude | 0 | yes (200) | yes | yes |
| session-gemini | 200 | found | request id | harness | gemini-chat | agw-t6-session | session-gemini | 47 | yes (200) | yes | yes |
| session-claude-stream | 200 | found | request id | harness | claude-stream-raw-predict | agw-t6-session | session-claude-stream | 0 | yes (200) | yes | yes |
| session-gemini-wrong-model | 400 | found | request id | harness | gemini-chat | agw-t6-session | session-gemini-wrong-model | 0 | yes (400) | yes | yes |
| session-claude-no-route | 404 | found | request id | - | - | agw-t6-session | session-claude-no-route | - | yes (404) | no | yes |
| untagged-claude | 200 | found | request id | harness | claude-raw-predict | - | - | 0 | yes (200) | yes | yes |

**Agent run** (session `agw-t6-agent-20261101T191649`, HTTP 200): 1 Kong row(s) by consumer `agent` and time, user agent `AsyncAnthropicVertex/Python 1.9.0`; joined to the agent's `/run` by trace: no (its row's traceparent trace 5e8b107cd365cc4781dde73a338c5e7e, the agent's /run trace bc2992d3b02eb90bfbb16eb539fbec1e).

**Admin probe** (a throwaway consumer made and deleted through `/admin-api`):

- 2026-11-01T19:16:50.511000Z POST /admin-api/consumers → 201, consumer `admin`, user agent `curl/8.14.1`
- 2026-11-01T19:16:50.577000Z DELETE /admin-api/consumers/agw-t6-admin-probe-20261101T191650-988727 → 204, consumer `admin`, user agent `curl/8.14.1` (names the probe)

Unjoined Kong rows: 0. Response headers recorded: {"session-claude": {"x-kong-request-id": "52ba156bc45daf2cf79ec33a89be6d3d"}, "session-gemini": {"x-kong-request-id": "d4aa7a11861255447a987126e9622879"}, "session-claude-stream": {"x-kong-request-id": "06a7f47f24c4054f9d2d4741d461c112"}, "session-gemini-wrong-model": {"x-kong-request-id": "cf35b00e99ed432804124617adaf4873"}, "session-claude-no-route": {"x-kong-request-id": "9d8c5b12df19df05ef1d8e1b19659070"}, "untagged-claude": {"x-kong-request-id": "aefe2a0d2dae50071d30c8520f425b36"}}
