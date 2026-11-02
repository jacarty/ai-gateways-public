# Audit trail: 20261022T162854Z-scenarios-litellm-audit-0b6e8e

Window 2026-10-22T16:28:40.475186Z to 2026-10-22T16:30:50.902699Z.

## Each request and its spend-log row

| Case | HTTP | Row joined by | Key alias | Model group | Status | Session | Session = request-log trace | Caller metadata | User agent | IP kind | Content stored | Header names stored | Marker | ID token | Bearer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | no | — | — | none | — | no | no | no |
| session-gemini | 200 | call id | agw-harness | gemini-3.8-flash | success | tagged | no | no | — | — | none | — | no | no | no |
| session-claude-stream | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | no | — | — | none | — | no | no | no |
| session-unknown-model | 403 | caller metadata | agw-harness | — | failure | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| untagged-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | random | yes | no | — | — | none | — | no | no | no |

Session `agw-t6-session`: 4 spend-log rows.

## Other spend-log rows in the window

| Key alias | Model group | Call type | Internal origin | Status |
| --- | --- | --- | --- | --- |
| agw-agent | claude-haiku-5-5 | acompletion | — | success |

## The agent run

Agent request: HTTP 200, session `agw-t6-agent-20261022T162948`.
- Agent request-log entries for /run: 1 (traces ['d5e8efd6914837cb3c94c8e3eb82cac2'])
- Gateway request-log entries during the run: 1 (traces ['a412a581f12d80e791e1889e6a39e3f7'], user agents ['AsyncOpenAI/Python 2.54.0'])
- Spend-log rows for key `agw-agent` during the run: 1 (sessions ['a412a581f12d80e791e1889e6a39e3f7']; equal to a gateway request-log trace: [True])
- Agent container logs: 13 lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0

## Gateway Cloud Run logs

6 request-log entries, 31 container lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0.
