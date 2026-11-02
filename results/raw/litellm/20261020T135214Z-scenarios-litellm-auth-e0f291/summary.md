# Scenarios 20261020T135214Z-scenarios-litellm-auth-e0f291: litellm-auth

Test 5 (identity and secrets) on LiteLLM v1.103.2: which layer stops which credential problem. Two layers: Cloud Run IAM checks the Google ID token (X-Serverless-Authorization; refusals are HTML), then LiteLLM checks its virtual key (Authorization; refusals are JSON with type auth_error). Run with run-auth.sh, which mints the throwaway keys (a Claude-only key, an expired key, a blocked key, a deleted key) and reads the agent's key, passes them as AGW_T5_* environment variables, and deletes its keys on exit. Only the valid cases reach a model (3 calls).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-litellm-model-group` | `www-authenticate` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| valid-id-token-and-key | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | claude-haiku-5-5 | — | 19.1172 |  |
| no-credentials | claude-haiku-5-5 | no | status=403, error_contains=forbidden | 1/1 | 403 | — | — | — | 0.2378 |  <html><head> <meta http-equiv="content-type" content="text/html;charset=utf-8"> |
| key-without-id-token | claude-haiku-5-5 | no | status=401, error_contains=unauthorized, error_not_contains=auth_error | 1/1 | 401 | — | — | Bearer error="invalid_token" error_description="The access token could not be verified" | 0.0093 |  <html><head> <meta http-equiv="content-type" content="text/html;charset=utf-8"> |
| id-token-without-key | claude-haiku-5-5 | no | status=401, error_contains=no api key passed | 1/1 | 401 | — | — | — | 0.0257 | {"error":{"message":"Authentication Error, No api key passed in.","type":"auth_e |
| key-not-sk-format | claude-haiku-5-5 | no | status=401, error_contains=auth_error, error_not_contains=agw-not-a-real-key-123 | 1/1 | 401 | — | — | — | 0.0481 | {"error":{"message":"LiteLLM Virtual Key expected. Received=agw-****-123, expect |
| unknown-sk-key | claude-haiku-5-5 | no | status=401, error_contains=invalid proxy server token | 1/1 | 401 | — | — | — | 0.0461 | {"error":{"message":"Authentication Error, Invalid proxy server token passed. Re |
| claude-only-key-asks-gemini | gemini-3.8-flash | no | status=403, error_contains=not available for this api key | 1/1 | 403 | — | — | — | 0.0277 | {"error":{"message":"The requested model 'gemini-3.8-flash' is not available for |
| claude-only-key-asks-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | claude-haiku-5-5 | — | 1.109 |  |
| expired-key | claude-haiku-5-5 | no | status=401, error_contains=expired key | 1/1 | 401 | — | — | — | 0.0348 | {"error":{"message":"Authentication Error - Expired Key. Key Expiry time 2026-10 |
| blocked-key | claude-haiku-5-5 | no | status=401, error_contains=blocked | 1/1 | 401 | — | — | — | 0.0323 | {"error":{"message":"Authentication Error, Key is blocked. Update via `/key/unbl |
| deleted-key | claude-haiku-5-5 | no | status=401, error_contains=unable to find token | 1/1 | 401 | — | — | — | 0.0439 | {"error":{"message":"Authentication Error, Invalid proxy server token passed. Re |
| agent-key-from-the-harness | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | claude-haiku-5-5 | — | 0.4353 |  |
