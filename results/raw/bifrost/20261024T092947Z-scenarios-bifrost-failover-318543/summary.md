# Scenarios 20261024T092947Z-scenarios-bifrost-failover-318543: bifrost-failover

Test 2 (routing and failover) on Bifrost transports/v2.2.6. Needs the test window in README.md: key aliases test-gemini-broken, test-gemini-broken-norule and test-claude-broken (model ids that don't exist on the Agent Platform: real upstream errors), the harness key allowed to use them, and two routing rules (governance.routing_rules) that fail test-gemini-broken over to Claude and test-claude-broken over to Gemini. Retries are off (Bifrost's default). Bifrost's mocker plugin is not compiled into the gateway, so no case forces an error on a healthy model; caller-side failover uses the request's own fallbacks list.

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-healthy | gemini-3.8-flash | no | status=200, model=gemini-3.8-flash | 2/2 | 200 | gemini-3.8-flash | 1.1241 |  |
| gemini-broken-rule-falls-back | test-gemini-broken | no | status=200, model=claude-haiku-5-5 | 3/3 | 200 | claude-haiku-5-5 | 1.4718 |  |
| gemini-broken-rule-falls-back-stream | test-gemini-broken | yes | status=200, model=claude-haiku-5-5 | 3/3 | 200 | claude-haiku-5-5 | 0.5642 |  |
| claude-broken-rule-falls-back | test-claude-broken | no | status=200, model=gemini-3.8-flash | 3/3 | 200 | gemini-3.8-flash | 2.5875 |  |
| claude-broken-rule-falls-back-stream | test-claude-broken | yes | status=200, model=gemini-3.8-flash | 2/2 | 200 | gemini-3.8-flash | 2.5307 |  |
| broken-no-fallbacks | test-gemini-broken-norule | no | status=404 | 2/2 | 404 | — | 0.0649 | {"is_bifrost_error":false,"status_code":404,"error":{"type":"NOT_FOUND","message |
| broken-caller-fallbacks | test-gemini-broken-norule | no | status=200, model=claude-haiku-5-5 | 3/3 | 200 | claude-haiku-5-5 | 0.8432 |  |
| broken-caller-fallbacks-stream | test-gemini-broken-norule | yes | status=200, model=claude-haiku-5-5 | 2/2 | 200 | claude-haiku-5-5 | 0.6152 |  |
| healthy-with-caller-fallbacks | gemini-3.8-flash | no | status=200, model=gemini-3.8-flash | 2/2 | 200 | gemini-3.8-flash | 1.7183 |  |
| every-fallback-broken | test-gemini-broken-norule | no | status=404 | 2/2 | 404 | — | 0.048 | {"is_bifrost_error":false,"status_code":404,"error":{"type":"NOT_FOUND","message |
| gemini-healthy-after | gemini-3.8-flash | no | status=200, model=gemini-3.8-flash | 2/2 | 200 | gemini-3.8-flash | 1.7869 |  |
