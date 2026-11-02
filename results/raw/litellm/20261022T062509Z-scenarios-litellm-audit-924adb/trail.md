# Audit trail: 20261022T062509Z-scenarios-litellm-audit-924adb

Window 2026-10-22T06:24:56.094485Z to 2026-10-22T06:27:09.526137Z.

## Each request and its spend-log row

| Case | HTTP | Row joined by | Key alias | Model group | Status | Session | Session = request-log trace | Caller metadata | User agent | IP kind | Content stored | Header names stored | Marker | ID token | Bearer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| session-gemini | 200 | call id | agw-harness | gemini-3.8-flash | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| session-claude-stream | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| session-unknown-model | 403 | caller metadata | agw-harness | — | failure | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| untagged-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | random | yes | no | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |

Session `agw-t6-session`: 4 spend-log rows.

## Other spend-log rows in the window

None.

## The agent run

Agent request: HTTP 503, session `agw-t6-agent-20261022T062623`.
- Agent request-log entries for /run: 1 (traces ['ad282dc981b1e5562d0c0fbe13c4c657'])
- Gateway request-log entries during the run: 2 (traces ['1ad5f994eaed0eed5cb1b4be5c85f6ac', 'c06fb6b4898d4e645cb1b4be5c85f3be'], user agents ['python-httpx/0.28.1'])
- Spend-log rows for key `agw-agent` during the run: 0 (sessions []; equal to a gateway request-log trace: [])
- Agent container logs: 2 lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0

## Gateway Cloud Run logs

5 request-log entries, 48 container lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0.
