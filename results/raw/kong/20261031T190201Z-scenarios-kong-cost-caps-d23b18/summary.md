# Scenarios 20261031T190201Z-scenarios-kong-cost-caps-d23b18: kong-cost-caps

Test 3 on Kong OSS 3.9.3, run through run-cost.sh with a throwaway consumer (its limit in the run's meta.json note). No rate limit. Per-request caps: each case asks for a long answer and up to 2000 tokens. Gemini's cap comes from kong.yaml (model.options.max_tokens 256), which overrides the caller's max_tokens (llm/drivers/shared.lua merge_config_defaults) and replaces the dropped max_completion_tokens; Claude's native request passes through with the caller's max_tokens. The Claude case replaces the harness's two-sentence system instruction so its answer can run past 256 tokens; the Gemini cases keep it, and are cut short anyway by default-level thinking inside the 256 cap. Kong's log (kong-log.json) shows what it counted and priced: Gemini's usage and cost, nothing for Claude (preserve route, log_statistics off).

A behaviour run, not a measured one: each case sent `repeat` times, one at a time (all at once for a concurrent case), and latencies are from wherever it ran. *Matched* counts attempts that met the case's expectations; a mismatch is a finding, not a harness error. Full answers and error bodies are in `outcomes.jsonl`.

| Case | Model asked | Stream | Expected | Matched | Statuses | Answered by | `x-kong-request-id` | `x-kong-llm-model` | p50 s | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemini-asks-2000-completion-tokens | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | cb52751eda1d514cf246fc1f6c04987f | gemini/gemini-3.8-flash | 2.882 |  |
| gemini-asks-2000-max-tokens | gemini-3.8-flash | no | status=200 | 1/1 | 200 | gemini-3.8-flash | 43bb18278f431e08cb109a522f713f78 | gemini/gemini-3.8-flash | 3.5576 |  |
| claude-asks-2000-max-tokens | claude-haiku-5-5 | no | status=200 | 1/1 | 200 | claude-haiku-5-5 | 7d37953068684f724f06211f5749ea68 | gemini/claude-haiku-5-5 | 4.7564 |  |
