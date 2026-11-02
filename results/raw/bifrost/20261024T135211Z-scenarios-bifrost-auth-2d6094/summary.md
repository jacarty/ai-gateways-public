# Scenarios 20261024T135211Z-scenarios-bifrost-auth-2d6094: bifrost-auth

Test 5 (identity and secrets) on Bifrost transports/v2.2.6: which layer stops which credential problem. Two layers: Cloud Run IAM checks the Google ID token (X-Serverless-Authorization; refusals are HTML), then Bifrost checks its virtual key (Authorization: Bearer sk-bf-...; refusals are JSON). Run with run-auth.sh, which makes the throwaway keys through the admin API (Claude-only, expired, inactive, deleted, rotated) and reads the agent's key, passes them as AGW_T5_* environment variables, and deletes them on exit. Expected codes from the source: unknown key 401, inactive or expired key 403, model not allowed 403; a rotated key's old value should stop at once (no rotation cooldown configured). Claude cases throughout (cheapest); the Gemini case is refused before any model call.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| valid-id-token-and-key | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 1.3497 |  |
| no-credentials | claude-haiku-5-5 | no | status=403, error_contains=forbidden | 1/1 | 403 | — | 0.1794 |  <html><head> <meta http-equiv="content-type" content="text/html;charset=utf-8"> |
| key-without-id-token | claude-haiku-5-5 | no | status=401, error_not_contains=virtual key | 1/1 | 401 | — | 0.0092 |  <html><head> <meta http-equiv="content-type" content="text/html;charset=utf-8"> |
| id-token-without-key | claude-haiku-5-5 | no | status=401, error_contains=virtual key is required | 1/1 | 401 | — | 0.0146 | {"type":"virtual_key_required","is_bifrost_error":false,"status_code":401,"error |
| key-not-sk-bf-format | claude-haiku-5-5 | no | status=401, error_not_contains=agw-not-a-real-key-123 | 1/1 | 401 | — | 0.0127 | {"type":"virtual_key_required","is_bifrost_error":false,"status_code":401,"error |
| unknown-sk-bf-key | claude-haiku-5-5 | no | status=401, error_not_contains=agw-unknown | 1/1 | 401 | — | 0.012 | {"type":"access_not_found","is_bifrost_error":false,"status_code":401,"error":{" |
| claude-only-key-asks-gemini | gemini-3.8-flash | no | status=403, error_contains=not allowed | 0/1 | 400 | — | 0.0137 | {"is_bifrost_error":false,"error":{"message":"could not auto resolve a provider  |
| claude-only-key-asks-claude | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.8359 |  |
| expired-key | claude-haiku-5-5 | no | status=403, error_contains=expired | 1/1 | 403 | — | 0.0139 | {"type":"access_blocked","is_bifrost_error":false,"status_code":403,"error":{"me |
| inactive-key | claude-haiku-5-5 | no | status=403, error_contains=inactive | 1/1 | 403 | — | 0.0147 | {"type":"access_blocked","is_bifrost_error":false,"status_code":403,"error":{"me |
| deleted-key | claude-haiku-5-5 | no | status=401 | 1/1 | 401 | — | 0.0129 | {"type":"access_not_found","is_bifrost_error":false,"status_code":401,"error":{" |
| rotated-key-old-value | claude-haiku-5-5 | no | status=401 | 1/1 | 401 | — | 0.0139 | {"type":"access_not_found","is_bifrost_error":false,"status_code":401,"error":{" |
| rotated-key-new-value | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.7793 |  |
| agent-key-from-the-harness | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 0.414 |  |
