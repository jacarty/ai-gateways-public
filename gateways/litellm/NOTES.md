# LiteLLM: how it works

Phase 1 notes on the LiteLLM proxy (OSS), version **v1.103.2** (released 2026-10-01), image `ghcr.io/berriai/litellm@sha256:f63fb81b…` pulled through `agw-ghcr`. Findings below are from reading the source at that tag unless marked *to test*.

## What it is

One Python process (FastAPI on uvicorn) that exposes an OpenAI-compatible API (`/chat/completions`, also under `/v1/`) and translates each request to the provider's native API. The same package is the `litellm` client library, which is also what the agent uses in gateway mode (see Confounds).

The image is a **monolith**: API, admin UI (`/ui`) and Prisma database migrations in one container. LiteLLM also ships a split layout (gateway, backend, UI and migrations as separate services, used by its official GCP Terraform module); this lab runs the monolith so there is one service to measure.

## Request path

1. **Auth.** `Authorization: Bearer <key>` is checked against the master key or a virtual key (hashed, in Postgres, cached in memory). On Cloud Run the ID token sits in `X-Serverless-Authorization`, which Cloud Run checks; `Authorization` is passed through to LiteLLM untouched.
2. **Pre-call checks.** Key, user and team budgets, rpm/tpm limits, allowed models, guardrail hooks.
3. **Router.** The request's `model` is a `model_name` from `config.yaml`; the router picks a deployment (one per model here) and applies retries and fallbacks.
4. **Translation.** `vertex_ai/gemini-*` goes to `generateContent` / `streamGenerateContent`; `vertex_ai/claude-*` is a Vertex partner model and goes to Anthropic Messages on `rawPredict` / `streamRawPredict`. Auth to Vertex uses Application Default Credentials, so on Cloud Run the gateway's service account `agw-gw-litellm`, with no keys.
5. **Response.** Translated back to OpenAI shape; usage and cost are computed from LiteLLM's model price map; spend is written to Postgres and callbacks (logging) fire after the response.

## Config model

- `config.yaml` ([config/config.yaml](config/config.yaml)): `model_list` (public name → provider model and params), `litellm_settings` (library behaviour such as `drop_params`, callbacks), `general_settings` (master key, database, proxy behaviour), `router_settings`. Values written `os.environ/NAME` are read from the environment.
- With `STORE_MODEL_IN_DB=True`, models and keys added in the admin UI or API live in Postgres beside the file's models. The file is the codified baseline; the UI is for exploring.
- **Region.** `vertex_location: eu` maps to `aiplatform.eu.rep.googleapis.com`, the same multi-region endpoint as the baseline. LiteLLM's default is `us-central1`, so the location must be set. LiteLLM also *silently re-routes* a model to another region when its price-map entry lists `supported_regions` and the requested region isn't one of them; neither of our models has that list in v1.103.2, so `eu` is honoured.

## Extension model

- **Callbacks:** Python classes (`CustomLogger`) hooked before and after calls; logging integrations (Langfuse, OpenTelemetry, GCS, …) are callbacks.
- **Guardrails:** pre-, during- and post-call hooks configured under `guardrails:`.
- **Custom code** is loaded by module path from the config; there is no plugin marketplace.

## OSS vs enterprise

`LICENSE`: MIT for everything outside `enterprise/`, which is under the BerriAI Enterprise licence. The Docker image includes `enterprise/`, but its features stay disabled without `LITELLM_LICENSE`, which this lab never sets. Gated in v1.103.2 (`premium_user` checks in `litellm/proxy/`):

| Area | Gated feature | Matters for test |
|------|---------------|------------------|
| Keys | Tags on keys; per-model budgets on a key (`model_max_budget`); spend-report permissions | 3 |
| Guardrails | Most built-in integrations (LLM Guard, Lakera, …, via `callback_utils.py`) | 4 |
| Logging | Audit logs of admin actions; turning callbacks off per request | 6 |
| Requests | Enforced params on keys | 3 |
| Access | SSO for the admin UI | — |

Plain key budgets and rpm/tpm limits are OSS (tested in test 3). Per-model budgets on a key are refused at key creation with a 500, tags with a 403, and enforced params are accepted on the key but fail every request with a 500. The day-1 split in `docs/day1-checks.md` agrees.

## How it is deployed here

- **Cloud Run** `agw-litellm`, `europe-west1`, min 0, max 1, as `agw-gw-litellm`. Max 1 because, without Redis, rate-limit counters are per instance.
- **Auth:** IAM (`roles/run.invoker` for the agent and the harness; no `allUsers`) **plus** a LiteLLM key. The key is what LiteLLM budgets and limits are attached to; IAM keeps the model-calling service account off the open internet.
- **Postgres:** Cloud SQL, one small zonal instance (`db-f1-micro`, Postgres 16, no replica or backups), reached through Cloud Run's Cloud SQL socket, so no VPC. **Password auth:** LiteLLM's token-based database auth supports AWS RDS IAM and Azure Entra only, not Cloud SQL IAM login. The database user is created through the Cloud SQL API, so it joins `cloudsqlsuperuser`: LiteLLM is an admin of its own (dedicated, throwaway) instance. Stop it between sessions with `make stop-litellm` (and `make start-litellm`); Terraform ignores the setting so an apply does not restart it.
- **Secrets** (`agw-litellm-*`): master key, salt key, database URL, and the config file (mounted at `/etc/litellm/config.yaml`).
- **CPU always allocated** (`cpu_idle = false`): LiteLLM flushes spend to Postgres in the background every 10-15 s, and throttled CPU between requests would make budgets and spend logs lag for reasons of our Cloud Run setting, not LiteLLM's. Still min 0.
- **No retries** (`router_settings.num_retries: 0`): the router retries twice by default, which would hide upstream errors and add latency the direct baseline doesn't have. Test 2 turns retries and fallbacks on deliberately.
- **Cold starts** run Prisma migrations before serving, so the first request after idle is slow. Not part of the overhead numbers (10 warm-up requests are discarded), but worth recording.
- **Not used:** the official `BerriAI/litellm/google` module. It grants `allUsers` behind a global load balancer, always creates a read replica on `db-custom-2-7680`, runs at min 1 with Memorystore HA, and creates its own service accounts without model access. Useful to read for env vars and migrations; too big and too open for this lab.

## Findings so far

- **Test 7, OSS ceiling (2026-10-22):** every test's core ran on OSS; the licence buys governance across callers: per-key and per-model controls (budgets, guardrails, guardrail exemptions, enforced params), JWT identity, key rotation, spend reports and the admin audit log. Audit-log writes are dropped silently without a licence (`/audit` held 0 entries after ~40 key changes). The day-1 split was wrong about guardrails: the built-in ones are OSS; per-key selection is gated. Details: `results/summary.md`.
- **Test 6, audit fidelity (2026-10-22):** the spend log is a full per-request ledger (key alias, model, endpoint, tokens, cost, refusals) and joins the gateway's Cloud Run request log by itself, because LiteLLM uses the incoming Cloud Trace id as the session id when the caller sends none. The agent hop doesn't join (different trace, no session or tag from the agent), and no log names a Google identity. `store_prompts_in_spend_logs` stores the caller's ID token (`X-Serverless-Authorization`, twice) and `x-forwarded-for` along with the prompt: LiteLLM scrubs its own `Authorization` header, not Cloud Run's. The LLM judge's calls leave no spend-log rows, and judged rows lose the caller's metadata. Admin audit logs are enterprise-only. Details: `results/summary.md`.
- **Test 5, identity and secrets (2026-10-20):** gateway → model is workload identity only (no keys on its service account, and the org policy blocks creating any). Caller → gateway is two layers: Cloud Run IAM refuses anything without an invoker's ID token (HTML 403/401, before LiteLLM), then LiteLLM identifies the caller by its virtual key alone, a bearer secret (the agent's key worked from a user's identity). Model restriction, block, expiry and delete are OSS and immediate; JWT auth (tying LiteLLM's principal to the caller's token) and key rotation are enterprise-only. An unknown `sk-` key's 401 echoes its last four characters and SHA-256 hash. Details: `results/summary.md`.
- **Test 4, inline screening (2026-10-19):** the built-in content filter (OSS, in-process) masked every PII value in prompts and answers with no false positives and no added latency, and blocked the three explicit injections by keyword; it missed the indirect, encoded and exfiltration ones, and its 400 names the rule that fired. An `llm_as_a_judge` guardrail (Gemini Flash) blocked all twelve injections with no false positives but added 3-5 s per request (45 s median on PII prompts), fails open, reports its scores and reasoning in the 422, and its cost doesn't appear in the caller's response cost. Without a gateway, neither model obeyed any injection, but both repeated nearly all PII. OSS guardrails are global (`default_on`): attaching one to a key is enterprise-only. Details: `results/summary.md`.
- **Test 3, cost control (2026-10-18):** key budgets and rpm/tpm limits are hard and OSS: a 429 before any model call. Both work by reserving each request's worst case (input + `max_completion_tokens`, times the price for budgets) and settling to the real figure after, so concurrency never overshoots a budget (the last admitted request can pass it by up to its own cost) but bursts are refused while headroom remains. `throttle_on_budget_exceeded` with `budget_exceeded_throttle_percentage` makes an exhausted budget a reduced rate instead of a block (advisory). `budget_duration` resets on a ~10-minute job, not on time. `x-litellm-key-spend` lags in bursts (it is the batched DB spend plus this request). Refusals name the key alias and its last four characters. Details: `results/summary.md`.
- **Test 2, failover (2026-10-18):** with `router_settings.fallbacks`, a real upstream error or a forced 500 is answered by the other model, both directions and streaming; the response's `model` field and `x-litellm-attempted-fallbacks` tell the caller, and `disable_fallbacks` opts out. Mock failures are refused unless `config.yaml` sets `dangerously_allow_mock_testing_request_params`. A mocked 429 fails over once and stops (LiteLLM doesn't revisit a tried target, so two-way fallbacks don't loop). Error bodies list the configured fallback groups (`expose_router_debug_in_errors`, on by default). A fallback keeps the original request's parameters: a Claude request answered by Gemini carried no `reasoning_effort`, so Gemini thought at its default level (58 reasoning tokens, not `LOW`), costing more and taking longer than Gemini asked for directly. All of it is OSS. Fallbacks, the test model and the mock switch were in the config for the test window only; the committed config has none, so measured runs stay one model against itself. Details: `results/summary.md`.
- **Reported Gemini endpoint is wrong in the header only.** `x-litellm-model-api-base` shows `eu-aiplatform.googleapis.com` for Gemini; the request code calls `aiplatform.eu.rep.googleapis.com`, and test 6 found the spend log's `api_base` right. A reporting helper (`litellm_core_utils/llm_response_utils/get_api_base.py`) builds `<location>-aiplatform…` for every location.

- **Test 1, overhead (2026-10-17):** about 20–30 ms at concurrency 1 and 50–65 ms at concurrency 5 on Claude (p50 and TTFT p50, paired with direct in the same job); Gemini within its own noise. The doubling at c=5 fits the single 1-vCPU, one-worker instance. Upstream 429s (`Resource exhausted`) pass through unretried with retries off. Details: `results/summary.md`. On the agent path (2026-10-22, three short paired runs, the agent through LiteLLM and direct) LiteLLM's share is between nothing and about 140 ms on Claude, within that path's noise at 20 requests a cell.

- **Smoke test passed (2026-10-17).** Harness `gateway` target against the live service, 8 requests per cell after 2 warm-ups: Gemini and Claude, stream and non-stream, 32/32 OK. The ID token in `X-Serverless-Authorization` plus the LiteLLM key in `Authorization` works; `max_completion_tokens`, `reasoning_effort` and `stream_options` are accepted on both models, and streams end with a usage chunk. Not an overhead number: no paired direct baseline yet.
- **Gemini's thinking count is missing, not zero.** LiteLLM omits `completion_tokens_details.reasoning_tokens` when Gemini reports no thoughts (Claude reports `0`). Direct Gemini never thought in the baseline, so it is almost certainly zero; the harness should read missing as zero on this path, as it does for direct.

- **Thinking is not quite the same request.** `reasoning_effort: "low"` becomes `thinkingLevel: low` **with `includeThoughts: true`** for Gemini 3, while the direct baseline sends LOW without thought summaries. Thinking token counts should match, but the response carries extra thought text (`reasoning_content`) when Gemini thinks; in the smoke test it never did, so there was none (*to test* at volume: size and latency effect).
- **No Haiku 5.5 pricing.** `claude-haiku-5-5` is not in LiteLLM's price map (v1.103.2 through v1.105.1); LiteLLM treats a model with no price as having a cost (only an explicit price of 0 skips budgets), but spend can't be right without one. `config.yaml` sets `input_cost_per_token` / `output_cost_per_token` from the Agent Platform pricing page: $0.11 / $0.55 per 1M, the EU multi-region column (global is $0.10 / $0.50). Haiku isn't in the public Cloud Billing SKU catalogue, so the page is the only source.
- **Gemini 3.8 Flash is priced at half.** LiteLLM v1.103.2's price map has every Gemini 3.8 Flash tier at half the Cloud Billing catalogue's price ($0.75 / $3.75 per 1M standard, against $1.50 / $7.50; it then adds the 10% non-global uplift correctly). Spend and budgets would see half the real cost. `config.yaml` sets the catalogue's regional price ($1.65 / $8.25); a price set there replaces the map entry, uplift included. Checked in test 3: LiteLLM's cost matched tokens × price for both models.
- **The ID token reaches LiteLLM's request metadata.** Its header scrubbing (`clean_headers`) removes LiteLLM's own credential headers, not `X-Serverless-Authorization`, so the caller's ID token stays in `metadata.headers`. Test 6 confirmed it lands in the spend log when `store_prompts_in_spend_logs` is on (off by default, and then nothing of the request is stored).
- **Cold path is slow, mostly before LiteLLM logs.** The first request after scale-to-zero took about 47 s: about 34 s before the instance logged anything, about 5 s of migrations and startup. The first Claude call on each new instance took 15-17 s, later ones 0.4-0.6 s; Gemini's first call was not slow. Cause unproven. `compare`'s prewarm absorbs both and records them in `meta.json` and `summary.md`.
- **`drop_params: false`**: unsupported OpenAI params raise instead of vanishing, so parameter handling is visible; none raised in the smoke test.

## Confounds

- **Sizing:** one instance with 1 vCPU and one uvicorn worker takes all the load (`max_instances = 1`, needed for per-instance rate limits without Redis). At higher concurrency this measures the container size as much as LiteLLM.
- **Database:** `db-f1-micro` (shared core, about 0.6 GB, about 25 connections); virtual-key lookups and spend writes may add latency in test 3.

- The agent's gateway mode uses LiteLLM as its client library (ADK's `LiteLlm`), and LiteLLM is also this gateway. Agent-path overhead includes that client for every gateway; overhead numbers come from the harness → gateway path.

## To do in this phase

- [x] Apply, smoke-test the harness `gateway` target (Gemini and Claude, stream and non-stream).
- [x] Agent ID-token change.
- [x] Harness `compare` built (paired direct baseline, ADR 0007).
- [x] Test 1 (overhead): `compare` run `20261017T160848Z-compare-53c0c2` in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 2 (failover): `harness/scenarios/litellm/failover.json`, two runs in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 3 (cost control): `harness/scenarios/litellm/cost-*.json` via `run-cost.sh`, seven runs in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 4 (inline screening): `harness/scenarios/litellm/screening.json` with the shared case set, runs A (no guardrails), B (content filter) and C (LLM judge) in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 5 (identity and secrets): `harness/scenarios/litellm/auth.json` via `run-auth.sh`, one run in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 6 (audit fidelity): `harness/scenarios/litellm/audit.json` via `run-audit.sh` and `audit_trail.py`, runs A, D and C in `results/raw/litellm/`, written up in `results/summary.md`.
- [x] Test 7 (OSS ceiling): `results/summary.md`, "Test 7": per test, what needed a licence and how it showed (four gates re-checked live 2026-10-22).
