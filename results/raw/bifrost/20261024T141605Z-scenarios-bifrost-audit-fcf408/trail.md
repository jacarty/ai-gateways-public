# Test 6 trail (Bifrost)

Window 2026-10-24T14:16:01.494728Z to 2026-10-24T14:16:51.233323Z: 5 log rows, 12 gateway request-log entries, 0 entries naming a Google identity.

| Request | Status | Log row | Joined by | Key | Session | Tag | Cloud Run trace (by time) | Content stored | ID token stored |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | found | request id | agw-harness | agw-t6-session | session-claude | 4f8a870726c7b191af933976a2bfda6a | yes | yes |
| session-gemini | 200 | found | request id | agw-harness | agw-t6-session | session-gemini | 762832c1c8a9f5f4af933976a2bfdc5d | yes | yes |
| session-claude-stream | 200 | found | request id | agw-harness | agw-t6-session | session-claude-stream | a7ffc05fd2fc5206af933976a2bfdf69 | yes | yes |
| session-unknown-model | 400 | none | - | - | - | - | - | no | no |
| untagged-claude | 200 | found | request id | agw-harness | - | - | c0d0bdf8011abf2eaf933976a2bfdd97 | yes | yes |

**Agent run** (session `agw-t6-agent-20261024T141614`, HTTP 200): gateway row found by key and time (`agw-agent`, user agent `AsyncOpenAI/Python 2.54.0`); nearest gateway request-log trace 98db4f22c762e4d35aabc014ab1f006c. Nothing in the row names the agent's own session or trace.

Unjoined rows: 0. Response headers recorded: {"session-claude": {"x-request-id": "8133bddb-febd-430e-90bb-4e0ab98ceb7e"}, "session-gemini": {"x-request-id": "2360e2c6-5ca8-44f1-ab17-a7f870841d51"}, "session-claude-stream": {"x-request-id": "7092c86c-2ce0-4a6b-b3a0-f4099a24aef1"}, "session-unknown-model": {"x-request-id": "e5593d48-f0dd-47da-8ce5-c495896d6bcb"}, "untagged-claude": {"x-request-id": "c43d10c1-7aea-493e-b0a8-b92be4f9de9e"}}
