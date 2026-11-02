# Test 6 trail (Bifrost)

Window 2026-10-24T14:10:25.962548Z to 2026-10-24T14:13:40.292646Z: 5 log rows, 48 gateway request-log entries, 0 entries naming a Google identity.

| Request | Status | Log row | Joined by | Key | Session | Tag | Cloud Run trace (by time) | Content stored | ID token stored |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | found | request id | agw-harness | agw-t6-session | session-claude | 08e6192083d0646f7187435d58a5e1ec | yes | no |
| session-gemini | 200 | found | request id | agw-harness | agw-t6-session | session-gemini | ec0010f3dfc03abe7187435d58a5e5bd | yes | no |
| session-claude-stream | 200 | found | request id | agw-harness | agw-t6-session | session-claude-stream | 308004133ad9af307187435d58a5ea93 | yes | no |
| session-unknown-model | 400 | none | - | - | - | - | - | no | no |
| untagged-claude | 200 | found | request id | agw-harness | - | - | dd2e58117f994ed87187435d58a5e12a | yes | no |

**Agent run** (session `agw-t6-agent-20261024T141037`, HTTP 200): gateway row found by key and time (`agw-agent`, user agent `AsyncOpenAI/Python 2.54.0`); nearest gateway request-log trace adbb4bd4e5b1228d9bebd30cc4030d89. Nothing in the row names the agent's own session or trace.

Unjoined rows: 0. Response headers recorded: {"session-claude": {"x-request-id": "08bceb79-c029-4ed5-8ba0-70f555ffeca3"}, "session-gemini": {"x-request-id": "5f1b1375-1ee7-401f-bb7d-6bec03d91661"}, "session-claude-stream": {"x-request-id": "051f4a18-33f4-4694-9995-15322326a9d4"}, "session-unknown-model": {"x-request-id": "9932969f-b1d5-4340-bb0b-c403bfa632b7"}, "untagged-claude": {"x-request-id": "cafb1900-44b0-49a7-9f68-3a0925e38f66"}}
