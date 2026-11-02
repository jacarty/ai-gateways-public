# Bifrost scenarios

Scenario files for the Bifrost phase (tests 2-6), run locally against `agw-bifrost` with `harness scenarios <file>`, never as the job. Results go to `results/raw/bifrost/`.

```bash
cd harness
export AGW_GATEWAY_API_KEY="$(gcloud secrets versions access latest --secret agw-bifrost-harness-key --project my-gcp-project)"
AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT=my-gcp-project AGW_RESULTS_DIR=../results/raw/bifrost PYTHONPATH=src \
  AGW_GATEWAY_URL="$(gcloud run services describe agw-bifrost --project my-gcp-project --region europe-west1 --format='value(status.url)')/v1" \
  uv run python -m agw_harness.cli scenarios scenarios/bifrost/<file>.json --note "<revision, window>"
unset AGW_GATEWAY_API_KEY
```

## Test windows

Behaviour tests need config the measured runs must not have (ADR 0010). Edit `gateways/bifrost/config/config.json`, mark each addition `TEST ONLY` in a `description` (the `no-test-window` hook then refuses to commit it), and `make deploy-bifrost`. Never deploy during a measured run: with one instance, a request during the rollout can get Cloud Run's 429.

**Closing a window:** `git checkout gateways/bifrost/config/config.json && make deploy-bifrost`. At start, `source_of_truth: config.json` resets every section the committed file declares, and leaves alone any it doesn't: in test 2 the file had no `routing_rules`, and the window's rules stayed active in Postgres. So the committed file now declares `routing_rules`, `budgets` and `rate_limits` as empty lists, and an empty list does clear the section (checked live for `routing_rules` on 2026-10-24: a window's rule was gone after the redeploy; for `budgets` and `rate_limits` it is inferred from the same code path, not checked). A window that uses any other section the file doesn't declare still needs checking afterwards with the admin API (user `admin`, password in `agw-bifrost-admin-password`), e.g. `GET /api/governance/routing-rules`, `DELETE /api/routing/rules/<id>`.

The same reset applies to keys made through the admin API (test 3's throwaway keys): `virtual_keys` is declared, so a restart removes any key not in the file (confirmed in test 3). Never deploy during a run that uses one.

## Test 2: `failover.json`

The window, added to `config.json`:

- On the `vertex-adc` key: `models` += `test-gemini-broken`, `test-gemini-broken-norule`, `test-claude-broken`, and `aliases` mapping them to ids that don't exist (`gemini-0.0-flash-agw-missing` with `model_family: gemini`; `claude-agw-missing-0-0` with `model_family: anthropic`), so each call is a real upstream 404.
- On the `agw-harness` virtual key: the same three models in `allowed_models` (this is the real harness key: after closing the window, check its models are the two real ones).
- `governance.routing_rules`: `model == "test-gemini-broken"` with `fallbacks: ["vertex/claude-haiku-5-5"]`, and `model == "test-claude-broken"` with `fallbacks: ["vertex/gemini-3.8-flash"]`, each `targets: [{"weight": 1}]` and its own `priority` (two rules at the same priority stop Bifrost from starting).

Bifrost's mocker plugin is not compiled into the gateway, so nothing forces a 500 or 429 on a healthy model; a caller's own failover is tested with the request's `fallbacks` list.

## Test 3: `cost-*.json` via `run-cost.sh`

Each run gets a throwaway virtual key made through the admin API with that run's limits plus a $0.05 daily backstop budget, held only in variables, and deleted on exit. After the run the key's own quota (budgets, rate limits, usage, as the key's holder sees it at `GET /api/governance/virtual-keys/quota`) is saved as `quota.json` next to the results. Never deploy during a run: a restart may remove the key.

```bash
harness/scenarios/bifrost/run-cost.sh <rpm|tpm|budget|race|model-budget|reset|unpriced> ["note"]
```

| Run | The key's limit | What it shows |
| --- | --- | --- |
| `rpm` | 3 requests a minute | 429 once 3 have succeeded; admitted again after the minute |
| `tpm` | 1000 tokens a minute | the crossing request admitted; a burst admitted while under the limit (no reservation) |
| `budget` | $0.0002 an hour | spend down one at a time, then 402 for either model |
| `race` | $0.0001 an hour | ten requests at once against about three requests' budget |
| `model-budget` | $0.0003 an hour on Gemini only | Gemini refused, Claude still answering (OSS here; enterprise-only in LiteLLM) |
| `reset` | $0.0001 a minute | refused, then admitted again after the window |
| `unpriced` | $0.0001 an hour | needs the window below: an unpriced model never spends the budget |

**The `unpriced` window**, added to `config.json` on the `vertex-adc` key: `models` += `test-claude-unpriced`, and an alias `"test-claude-unpriced": {"model_id": "claude-haiku-5-5", "model_family": "anthropic", "model_name": "agw-unpriced-claude", "description": "TEST ONLY ..."}`. `model_name` was meant to make it unpriced (it names no price), but Bifrost priced the alias as the model it resolves to, `claude-haiku-5-5` (test 3 result): this window does not produce an unpriced model. The throwaway key allows the alias; the harness key is not touched. Close with `git checkout` + `make deploy-bifrost` (the providers section is declared, so the alias goes).

## Test 4: `screening.json`

Run it twice: with the committed config (run A), and with the guardrail window (run B). The window adds a top-level `guardrails_config` to `config.json`: a `guardrail_providers` entry with `provider_name: "regex"` (Bifrost's documented example: email, US SSN and card-number patterns with `action: "redact"`) and a `guardrail_rules` entry with `cel_expression: "true"`, `apply_to: "both"`, `sampling_rate: 100` and `provider_config_ids` pointing at it, each marked `TEST ONLY`. On the OSS image nothing reads it (test 4's finding), so close with `git checkout` + `make deploy-bifrost`; the section isn't declared in the committed file, but there is nothing in the database to clear.

## Test 5: `auth.json` via `run-auth.sh`

`harness/scenarios/bifrost/run-auth.sh ["note"]` makes five throwaway keys through the admin API (Claude-only, expiring five seconds after creation, inactive, deleted, rotated), reads the agent's key, and passes them, plus a generated unknown `sk-bf-` value, to the harness as `AGW_T5_*` environment variables; the keys it made are deleted on exit. No window is needed. Cases that send a credential in another header (`x-bf-vk`, `x-bf-direct-key`) are in the notebook: a scenario case's `headers` field refuses credential-shaped names and values, so only the ID token and `Authorization` change, through `id_token` and `api_key`.

## Test 6: `audit.json` via `run-audit.sh`

`harness/scenarios/bifrost/run-audit.sh ["note"]` runs `audit.json` with the real harness key, not a throwaway one, since the test is the trail the real callers leave (cases send `x-bf-session-id` and `x-bf-lh-agw-case` through the scenario `headers` field), sends one request through `agw-agent` (which must point at Bifrost), waits 30 s, then runs `audit_trail.py`, which reads Bifrost's logs store through the admin API and the Cloud Run logs of both services, joins each request to its row by the `x-request-id` Bifrost returned (else tag, else session), and writes `trail.json` / `trail.md` into the run (values redacted, content as flags; shared helpers in `agw_harness/trail.py`).

**The `logging_headers` window (run B):** `client.logging_headers: ["X-Serverless-Authorization", "Authorization", "TEST ONLY (test 6 window): remove"]` (the third entry is the hook's marker; it matches no header). Rows written while it is open keep callers' ID tokens and **virtual key values** in Postgres for the retention period: never read them into anything shared, and rotate the harness and agent keys afterwards. Closing it resets `client.logging_headers` on the redeploy because the file declares the `client` section; that was read from the source, not checked by reading the config back. The phase-end `make destroy-bifrost` deletes the rows and the keys either way.
