# Audit trail: 20261022T080054Z-scenarios-litellm-audit-747b9f

Window 2026-10-22T08:00:40.234890Z to 2026-10-22T08:02:57.657444Z.

## Each request and its spend-log row

| Case | HTTP | Row joined by | Key alias | Model group | Status | Session | Session = request-log trace | Caller metadata | User agent | IP kind | Content stored | Header names stored | Marker | ID token | Bearer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | response, proxy_server_request | accept, accept-encoding, content-length, content-type, forwarded, host, traceparent, user-agent, x-cloud-trace-context, x-forwarded-for, x-forwarded-proto, x-serverless-authorization | yes | yes | yes |
| session-gemini | 200 | call id | agw-harness | gemini-3.8-flash | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | response, proxy_server_request | accept, accept-encoding, content-length, content-type, forwarded, host, traceparent, user-agent, x-cloud-trace-context, x-forwarded-for, x-forwarded-proto, x-serverless-authorization | yes | yes | yes |
| session-claude-stream | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | response, proxy_server_request | accept, accept-encoding, content-length, content-type, forwarded, host, traceparent, user-agent, x-cloud-trace-context, x-forwarded-for, x-forwarded-proto, x-serverless-authorization | yes | yes | yes |
| session-unknown-model | 403 | caller metadata | agw-harness | — | failure | tagged | no | yes | python-httpx/0.28.1 | link-local (Cloud Run front end) | none | — | no | no | no |
| untagged-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | random | yes | no | python-httpx/0.28.1 | link-local (Cloud Run front end) | response, proxy_server_request | accept, accept-encoding, content-length, content-type, forwarded, host, traceparent, user-agent, x-cloud-trace-context, x-forwarded-for, x-forwarded-proto, x-serverless-authorization | yes | yes | yes |

Session `agw-t6-session`: 4 spend-log rows.

## Other spend-log rows in the window

| Key alias | Model group | Call type | Internal origin | Status |
| --- | --- | --- | --- | --- |
| agw-agent | claude-haiku-5-5 | acompletion | — | success |
| agw-harness | claude-haiku-5-5 | acompletion | — | success |
| agw-agent | claude-haiku-5-5 | acompletion | — | success |

## The agent run

Agent request: HTTP 200, session `agw-t6-agent-20261022T080241`.
- Agent request-log entries for /run: 2 (traces ['aff1dbbd7aed50b8a819b4102f30d98b', '68dbf2f0358f44c84fb846d738838a2f'])
- Gateway request-log entries during the run: 3 (traces ['deb39bb0b9bc18a17c521beb2b3a63df', '30b915c25030688c4561f9befff10ca9', 'e2ad1bb18a642a5c4561f9befff10033'], user agents ['AsyncOpenAI/Python 2.54.0', 'python-httpx/0.28.1'])
- Spend-log rows for key `agw-agent` during the run: 1 (sessions ['deb39bb0b9bc18a17c521beb2b3a63df']; equal to a gateway request-log trace: [True])
- Agent container logs: 2 lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0

## Gateway Cloud Run logs

8 request-log entries, 11 container lines; containing {'prompt_marker': 0, 'session_id': 0, 'id_token_jwt': 0, 'bearer': 0}; naming a caller identity: 0.
