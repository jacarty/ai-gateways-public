# ai-gateways

## Project Overview

A hands-on learning lab: build, run and break three open-source AI gateways on GCP — LiteLLM, Bifrost and Kong OSS — one at a time, in front of the same ADK agent calling Gemini and Claude on Gemini Enterprise Agent Platform (formerly Vertex AI). The goal is learning how each gateway is set up and configured. Each gateway gets the same learning loop and the same seven-test matrix against a direct-to-model baseline. The outputs are a "how it works" note per gateway, a results table with an OSS-ceiling table, takeaways (what each gateway turned out to be good at), an architecture layout and a setup guide.

**Plan / PRD:** `docs/plan-v0.1.md` (revised after day-1 research)
**Day-1 checks:** `docs/day1-checks.md` — region, model and OSS-edition findings
**Results:** `results/summary.md` — opens with "Across the three gateways" (one line per gateway per test, plus an OSS-ceiling table); then the Phase 0 baseline and LiteLLM (Phase 1), Bifrost (Phase 2) and Kong (Phase 3), each with tests 1-7 and the OSS-ceiling section; raw runs in `results/raw/<gateway>/`, each with a `NOTE.md`
**Takeaways:** `docs/takeaways.md` — what each gateway turned out to be good at, from the results (Phase 4)
**Gateway notes:** `gateways/<gw>/NOTES.md` — the "how it works" note (LiteLLM, Bifrost and Kong written)
**Decisions:** `docs/decisions/` — ADRs, indexed in its README
**Architecture:** `docs/architecture.md` — components, measured paths, identities and roles, per-gateway shape, network, Terraform stacks
**Setup guide:** `docs/setup-guide.md` — clone-to-running in a new GCP project (replacing the project ID, foundation, agent, harness, a gateway, teardown)

---

## Rules

These are non-negotiable. They apply to every session regardless of scope.

- **Never commit directly to main.** Always create a feature or fix branch and open a PR. No exceptions.
- **Before pushing, verify only intended files are staged.** Run `git status` and `git diff --cached --name-only` before every commit. Do not include unrelated config files, lockfile churn, or editor artefacts.
- **Run lint + tests + build locally before opening a PR.** `pre-commit run --all-files` and both pytest suites; there is no CI.
- **Never commit secrets, service-account keys or Terraform state.** Gateways authenticate to the models with service accounts; keys, if used at all for test 5, stay in Secret Manager.
- **Spend control comes first.** No deploys until the foundation budget + alert is live. Use Gemini Flash and Claude Haiku with low `max_tokens` for load tests; keep bursts short.
- **Build images only with `scripts/build-image.sh`, from committed code.** It refuses uncommitted changes under the component and prints a digest-pinned `image = ...` line; deploys use the digest, never a tag. Exception: upstream gateway images are not built; they are pulled through the `agw-ghcr` or `agw-dockerhub` remote repo and deployed by digest, pinned to releases at least two weeks old.
- **One gateway at a time.** Each phase ends with `terraform destroy` of that gateway's stack. Only `foundation/`, `agent/` and `harness/` persist between phases.
- **Keep runs comparable.** Same agent, region, models, prompts and harness target setting for every run. Commit raw output to `results/raw/<gateway>/`.
- **OSS editions only.** No paid editions, licences, subscriptions or trials of LiteLLM, Bifrost or Kong.
- **Scope is three OSS gateways and agent-to-model traffic only.** No Agent Gateway or Model Armor; no MCP/tool traffic, A2A, or client-to-agent ingress; no models outside Gemini and Claude on the Agent Platform.

---

## Architecture

```
[Harness: Cloud Run job agw-harness] ─┬─→ [Gateway under test: LiteLLM | Bifrost | Kong OSS] ─┬─→ [Agent Platform: Gemini Flash, Claude Haiku 5.5]
                                      │                                                       └─→ [Cloud Logging]  (audit fidelity)
[ADK agent: Cloud Run agw-agent] ◄────┤  (harness → agent → gateway: short end-to-end runs)
                                      └─→ baseline paths: harness → model (direct), harness → agent → model
```

Measured paths (harness targets `direct`, `agent`, `gateway`):

| Target | Path | Request format |
|--------|------|----------------|
| `direct` | harness → model | Native APIs (Gemini `generateContent`, Claude `rawPredict`), so any translation a gateway does counts as its overhead |
| `agent` | harness → `agw-agent` → model (or gateway) | ADK `/run` and `/run_sse`; ID token |
| `gateway` | harness → gateway → model | OpenAI `/chat/completions` at `AGW_GATEWAY_URL` |

- **Agent:** small ADK agent (Python) on Cloud Run (`agw-agent`, IAM-authenticated: public URL, `roles/run.invoker` required; min-instances 0), serving two ADK apps, `gemini` and `claude`, from one image. Env vars switch it between direct-to-model and the current gateway (`AGW_TARGET`); the code never changes. See `agent/README.md`.
- **Harness:** Python load harness, run as a Cloud Run job (`agw-harness`) in `europe-west1` as the `agw-harness` service account, next to what it measures. It writes raw results to a gcsfuse-mounted results bucket; you copy a run into `results/raw/<gateway>/` and commit it. One httpx client per run (per target per cell in `compare`); 10 warm-up requests discarded; fixed prompts, 256-token cap, thinking condition. Commands: `baseline`/`load` (one target), `compare --targets direct,gateway` (paired run: targets alternate in ABBA-ordered blocks within each cell, re-warm per block, per-model prewarm of Cloud Run targets recorded in `meta.json`) and `report <run_dir>` (re-prints the tables for any run dir). ID tokens come from the metadata server in a job and from `gcloud` on the workstation (`AGW_ID_TOKEN_SOURCE=auto|metadata|gcloud`, recorded in `meta.json`). `scenarios <file>` (tests 2-6) sends named cases to the gateway and records which model answered, the status and chosen headers against each case's expectation (`pause_s` and `concurrent` per case; per-case credentials: `id_token: false`, `api_key`; per-case extra request `headers`, e.g. Bifrost's `x-bf-session-id`, never credential-shaped names or values). Test 4 expands one gateway-neutral case set, `harness/scenarios/screening-cases.json`, and classes each answer blocked, masked, leaked, withheld, passed or error (ADR 0011). Files live in `harness/scenarios/<gw>/` and run locally, never as the job: `run-cost.sh` (test 3), `run-auth.sh` (test 5) and `run-audit.sh` (test 6) mint throwaway keys (Kong's `probe-ceiling.sh`, test 7, only reads the Admin API), and `audit_trail.py` collects test 6's trail, with the redaction, address-kind and Cloud Run log helpers shared in `trail.py` (ADR 0012; Kong's collector reads Cloud Logging only, ADR 0017). For gateway runs the job sends a per-caller virtual key (`gateway_api_key_secret`, an `agw-<gw>-harness-key`; empty while on direct). See `harness/README.md`.
- **Gateways:** OSS containers on Cloud Run, min-instances 0, one region. LiteLLM was built and fully tested (Phase 1): `agw-litellm` (IAM-authenticated public URL plus a LiteLLM key; max 1 instance) with Cloud SQL Postgres for keys and budgets; its stack was destroyed on 2026-10-24. See `gateways/litellm/README.md`. Bifrost was built and fully tested (Phase 2); its stack was destroyed on 2026-10-24: `agw-bifrost` (same shape: IAM-authenticated URL plus a virtual key, max 1 instance, Cloud SQL Postgres 16 for both stores; ADR 0013), release `transports/v2.2.6` pulled through `agw-ghcr`, see `gateways/bifrost/README.md`. Its tests 1-7 are done (`results/summary.md`); after it, the agent and the harness job went back to direct. Kong was built and fully tested (Phase 3); its stack was destroyed on 2026-11-01: `agw-kong` (same shape: IAM-authenticated URL plus a Kong key, max 1 instance), Kong OSS 3.9.3 pulled through `agw-dockerhub`, Cloud SQL Postgres 16 on a private IP on foundation's `agw-vpc` reached over Direct VPC egress, config synced from `config/kong.yaml` by decK (ADRs 0014-0016, `gateways/kong/README.md`). Claude goes to Kong in its own Vertex format (`AGW_GATEWAY_CLAUDE_API=anthropic` for the agent and the harness). Kong Manager OSS (the admin UI) was on at `/manager` behind an `admin` login, like LiteLLM's and Bifrost's UIs, opened through `gcloud run services proxy`. Its tests 1 (with its agent path) to 7 are done (`results/summary.md`); after it, the agent and the harness job went back to direct, with `gateway_claude_api = "openai"`.
- **Models:** `gemini-3.8-flash` and `claude-haiku-5-5`, both on the EU multi-region endpoint (`GOOGLE_CLOUD_LOCATION=eu`, host `aiplatform.eu.rep.googleapis.com`). Neither has a single-region endpoint. Larger models for spot checks only.
- **Thinking is a fixed test condition:** Gemini `LOW` (its floor; it rejects `MINIMAL`), Claude off. Through gateways it is sent as `reasoning_effort: "low"`; whether each gateway honours it is a finding.
- **Auth:** each gateway calls the models with a service account; test 5 compares keys vs workload identity. Callers of Cloud Run services (agent, gateways) send ID tokens.
- **Project:** `my-gcp-project`, a lab project separate from workstations. It may hold other work: keep IAM additive, prefix names (`agw-`), and name gateway secrets `agw-<gw>-*` (the only ones that gateway's service account can read).
- **Region:** Belgium (`europe-west1`) for all deployed resources; model calls go to the `eu` multi-region. London was dropped: no regional Claude endpoint.
- **IaC:** Terraform, remote state in a GCS bucket created by `foundation/`, one state prefix per stack (`agent`, `harness`, later `gateways/<gw>`).
- **Language:** Python (managed with uv) for the agent and the harness; nothing else outside Terraform.
- **CI/CD:** none yet. Linting runs locally as pre-commit hooks (`.pre-commit-config.yaml`): hygiene, gitleaks, terraform fmt/validate, ruff, plus commit-message and branch-name checks (`.githooks/`). Wiz PR scanning to be added later. Deploys are manual.

---

## Repository Structure

Phases 0 (Setup), 1 (LiteLLM), 2 (Bifrost) and 3 (Kong; stack destroyed 2026-11-01) are complete. Phase 4 (write-up: the "Across the three gateways" section of `results/summary.md`, `docs/takeaways.md`, `docs/architecture.md` and `docs/setup-guide.md`) completes with its PR. Present: `foundation/`, `agent/`, `harness/`, `scripts/`, `results/`, `docs/`, `gateways/litellm/`, `gateways/bifrost/` and `gateways/kong/` exist.

```
ai-gateways/
├── AGENTS.md                 # This file
├── foundation/terraform/     # persists all project: APIs, budget + alert, service accounts
│                             #   (agent, gateways, build, harness), state bucket, image repo,
│                             #   agw-ghcr / agw-dockerhub (remote repos proxying ghcr.io and
│                             #   Docker Hub), build source bucket,
│                             #   results bucket; Cloud SQL API. Applied.
├── agent/                    # the one ADK agent (Python, uv), on Cloud Run
│   ├── src/agw_agent/        # config, model selection, agents/{gemini,claude}
│   ├── tests/                # pytest
│   ├── Dockerfile, cloudbuild.yaml
│   └── terraform/            # Cloud Run service + invoker IAM
├── harness/                  # load harness (Python, uv), as a Cloud Run job
│   ├── src/agw_harness/      # cli, runner, protocols (direct|agent|gateway), auth, stats, settings, scenarios, trail
│   ├── scenarios/            # screening-cases.json: the shared test 4 case set
│   │   └── <gw>/             # scenario files for tests 2-6; litellm/: failover.json, cost-*.json,
│   │                         #   screening.json, auth.json, audit.json, run-cost.sh / run-auth.sh /
│   │                         #   run-audit.sh (throwaway keys per run), audit_trail.py, README.md;
│   │                         #   bifrost/: the same set (failover, cost-*, screening, auth, audit
│   │                         #   JSON, run-*.sh, audit_trail.py), README.md (test windows);
│   │                         #   kong/: failover.json, cost-*.json, screening.json, auth.json,
│   │                         #   audit.json, run-cost.sh / run-auth.sh (throwaway consumers),
│   │                         #   run-audit.sh, audit_trail.py, probe-ceiling.sh (test 7),
│   │                         #   README.md (test windows as decK syncs)
│   ├── tests/                # pytest
│   ├── Dockerfile, cloudbuild.yaml
│   └── terraform/            # Cloud Run job + results bucket mount
├── scripts/build-image.sh    # the only way images are built (Cloud Build, digest output)
├── results/
│   ├── raw/<gateway>/        # timestamped raw output, committed (baseline/, litellm/, bifrost/, kong/)
│   └── summary.md            # cross-gateway table (+ OSS-ceiling table), then baseline and per-gateway results
├── .githooks/, .pre-commit-config.yaml   # local lint, commit-message and branch-name checks
├── .github/                  # CODEOWNERS, issue/PR templates, SECURITY.md (no workflows yet)
├── docs/
│   ├── plan-v0.1.md          # project plan
│   ├── architecture.md       # architecture layout: components, IAM, network, stacks
│   ├── setup-guide.md        # deploy the lab in your own GCP project
│   ├── day1-checks.md
│   ├── decisions/            # ADRs (index in README.md)
│   └── takeaways.md          # what each gateway turned out to be good at (Phase 4)
├── gateways/                 # one self-contained folder per gateway
│   ├── litellm/              #   NOTES.md ("how it works"), README.md (deploy, proxy), tests.ipynb
│   │                         #   (manual walkthrough of tests 1-6), config/, terraform/
│   ├── bifrost/              #   NOTES.md, README.md, tests.ipynb (tests 1-6 by hand), config/config.json, terraform/
│   └── kong/                 #   NOTES.md, README.md, tests.ipynb (setup, tests 1-6 by hand; test 7 is the `probe-ceiling.sh` probe), deck.sh, config/{kong.yaml,bootstrap.yaml,start.sh}, terraform/ (Postgres, decK)
└── Makefile                  # plan-/deploy-/destroy-/start-/stop-/status-/ui-<gw> (GATEWAYS := litellm bifrost kong), diff-/sync-kong
```

---

## Key Patterns

- **Per-gateway learning loop:** Understand (write `NOTES.md`) → Hand-build (one agent→Gemini call, then one agent→Claude call) → Codify (Terraform) → Test (shared matrix, write up surprises).
- **Config test windows:** behaviour tests (failover, unpriced model, guardrails, stored prompts) need config the measured runs must not have. Add it to `gateways/<gw>/config/` marked `TEST ONLY`, deploy, run, remove, redeploy (ADR 0010). On Kong a window is a decK sync of a `TEST ONLY` `kong.yaml`, then a sync of the committed one and `make diff-kong` (ADR 0015). The `no-test-window` pre-commit hook rejects any `TEST ONLY` in a gateway config, so a window can't be committed.
- **Throwaway keys:** tests 3, 5 and 6 mint short-lived keys with their own limits, hold them in variables or env vars (never on disk or the command line), and delete them on exit; the harness and agent keys are never used for behaviour tests, except test 5's one agent-key case (to show a key works from any caller; LiteLLM and Bifrost ran the same case) and test 6, which audits the real callers' trail (`run-audit.sh` uses the harness key; rotate it after a `logging_headers` window).
- **Concept order, every gateway:** unified API and request translation → routing and failover → rate limits and budgets → guardrails → logging.
- **Single target setting:** the harness reads its target(s) (`direct`, `agent` or `gateway` plus `AGW_GATEWAY_URL`; `compare` takes a list), so every test runs unchanged against the baseline or any gateway.
- **Paired baselines:** every gateway run includes a direct baseline measured in the same job, because upstream Gemini latency drifts (ADR 0007). `harness compare` does this: the targets take turns in blocks, so drift lands on both, and its summary gives the deltas against the first target.
- **Self-contained gateway folders:** each `gateways/<gw>/` has its own Terraform stack and state prefix, so a phase ends with one `terraform destroy`.

**Shared test matrix**

| # | Test | What is measured |
|---|------|------------------|
| 1 | Overhead | p50/p95 added latency, TTFT when streaming, throughput at modest concurrency, vs direct-to-model |
| 2 | Routing and failover | Gemini → Claude and back, on a forced error or 429 |
| 3 | Cost control | Token budgets and rate limits; hard or advisory |
| 4 | Inline screening | Shared injection + PII set; each case blocked, logged or invisible |
| 5 | Identity and secrets | Agent→gateway and gateway→model auth: keys or workload identity |
| 6 | Audit fidelity | Whether logs can reconstruct a single agent run |
| 7 | OSS ceiling | What each test needed that only the paid tier provides |

---

## Testing

| Level | Tool | Scope |
|-------|------|-------|
| Lint / static | ruff, terraform fmt + validate, secret scanner (via pre-commit) | All Python and Terraform |
| Unit | pytest (via uv) | Agent and harness code (each has its own `tests/`) |
| Integration | The harness itself | Shared seven-test matrix against baseline and each gateway |
| E2E | Harness → agent → gateway | Short end-to-end overhead runs (keep brief to limit spend) |

Install hooks once per clone: `uv tool install pre-commit==4.6.2 && pre-commit install` (pre-commit, commit-msg and pre-push stages).
Run all lint locally: `pre-commit run --all-files` (the commit-msg and pre-push hooks run only at commit and push time). Hooks need `terraform` 1.16.x and `go` on PATH (gitleaks builds from source). Agent and harness tests: `cd agent && uv run pytest`, `cd harness && uv run pytest` (with `UV_PROJECT_ENVIRONMENT` on local disk; see the gcsfuse pitfall). Build, deploy and call commands: `agent/README.md` and `harness/README.md`.

---

## Git Workflow

**Branch strategy:** Feature branches → PR → merge to main.

```
main                    ← protected
└── feat/<slug>         ← feature work, e.g. feat/p1-litellm-terraform
└── fix/<slug>          ← bug fixes
└── ci/<slug>           ← CI and tooling, e.g. ci/p0-lint
└── docs/<slug>         ← docs-only changes (still via PR)
```

Branch types are Conventional Commits types; the `pre-push` hook rejects anything else. Commit messages must be Conventional Commits (`commit-msg` hook).

---

## Deployment

Manual, from a workstation, via Terraform, wrapped per gateway in the root `Makefile` (`make deploy-<gw>`, `make destroy-<gw>`).

**Apply order:** `foundation/` → `agent/` → `harness/` (the harness job reads the agent's URL). Gateways follow, each at the start of its phase and destroyed at its end.

1. `foundation/` first: APIs, budget + alert, service accounts, state bucket, image repo, `agw-ghcr` and `agw-dockerhub` pull-through repos, results bucket. Applied once, kept for the project.
2. `agent/`: deployed once, repointed by config.
3. `harness/`: the Cloud Run job; its service account `agw-harness` must be in the agent's `invoker_members`.
4. `gateways/<gw>/`: `make deploy-<gw>` at the start of a phase, `make destroy-<gw>` at the end. `make stop-<gw>` / `make start-<gw>` stop and start its Cloud SQL database between sessions (Terraform ignores the activation policy); `make ui-<gw>` proxies the gateway to localhost with your ID token (`gcloud run services proxy`) for `curl`; for the admin UI run the same proxy on your laptop. `make destroy-<gw>` refuses while `agw-agent` or the `agw-harness` job still references the gateway URL or an `agw-<gw>-` secret (repoint or clear them in `agent/` and `harness/`, apply, then retry; callers that don't exist are skipped). The gateway stack owns per-caller key secrets (LiteLLM: `agw-litellm-agent-key`, `agw-litellm-harness-key`, minted by hand after a deploy; Bifrost: `agw-bifrost-agent-key`, `agw-bifrost-harness-key`, generated by Terraform; Kong: `agw-kong-agent-key`, `agw-kong-harness-key`, `agw-kong-admin-key` and `agw-kong-manager-password`, generated by Terraform, written into Kong by `make sync-kong`). Details: `gateways/<gw>/README.md`.
5. **Closing a gateway phase** (after its final PR merges, before the next phase starts): set `AGW_TARGET` back to `direct` in `agent/` and clear `gateway_url` / `gateway_api_key_secret` in `harness/` (after Kong also set `gateway_claude_api` back to `openai` in both), `terraform apply` both, then `make destroy-<gw>`; Cloud SQL must be running (`make start-<gw>` first). The `run-*.sh` scripts read URLs and secrets with `gcloud`, not Terraform state, so they work without `terraform init`.

**Build-by-digest flow** (agent, harness, any custom gateway image):

```bash
git commit ...                          # build only committed code
scripts/build-image.sh <component>      # Cloud Build as agw-build; tags the commit, prints the digest
# paste the printed image = "...@sha256:..." line into <component>/terraform/terraform.tfvars
cd <component>/terraform && terraform init -backend-config=../../foundation/terraform/backend.hcl && terraform apply
```

**Running the harness and keeping results:**

```bash
gcloud run jobs execute agw-harness --project my-gcp-project --region europe-west1 --wait [--args=...]
# paired gateway run; ^@^ makes @ the --args separator so "direct,gateway" survives (gcloud splits on commas):
gcloud run jobs execute agw-harness --project my-gcp-project --region europe-west1 --wait \
  --args=^@^compare@--targets@direct,gateway
gcloud storage cp -r gs://my-gcp-project-ai-gateways-results/<run_id> results/raw/<gateway>/
```

**Operational notes**

- Always pass `--project my-gcp-project` to `gcloud`; the workstation default project differs.
- ID tokens expire after an hour. The harness mints and refreshes its own; do not paste a token into a long run.
- The recorded baseline took about 30-40 minutes as one job execution; a default `compare` (direct + gateway) took about 20 minutes (LiteLLM, 2026-10-17) and 26 minutes (Bifrost, 2026-10-24). The job timeout is the harness `timeout_s` variable (default 7200 s); a timeout kills the job with no retry, and `summary.md` keeps the finished cells.
- `python -m agw_harness.cli report <run_dir>` re-prints a run's tables (works on copies under `results/raw/`).

**Phase gates:** Setup (done) → budget alert live, baseline numbers recorded (`results/summary.md`). Each gateway → note written, matrix run, `terraform destroy`. Write-up → results table, takeaways, architecture doc and setup guide merged.

---

## Common Pitfalls & Constraints

- **Claude has no single-region endpoint in Europe** for Haiku 5.5 — use the EU multi-region endpoint. Haiku 4.5 retires from Oct 15, 2026; don't build on it.
- **Claude quota** on the EU multi-region endpoint was confirmed working for `my-gcp-project` (the agent's first `claude` call answered). Re-check only in a new project.
- **Gemini latency drifts** (8-31 s outliers on `eu`, tails that moved by seconds between runs). Pair every gateway run with a direct baseline measured in the same job; never compare against `results/summary.md` alone. See ADR 0007.
- **OSS feature gaps:** LiteLLM's built-in guardrails (content filter, LLM judge, custom code) are OSS, but choosing them per key is paid, as are JWT auth, key rotation and the admin audit log (test 7, `results/summary.md`); Bifrost's guardrails are enterprise-only, and a `guardrails_config` on OSS is accepted and silently ignored (test 4: no error, no log line, no screening); Kong OSS lacks failover (AI Proxy Advanced), token rate limits and PII detection (`ai-sanitizer`): its OSS screening is a regex deny list (`ai-prompt-guard`) or an LLM rewrite of the request (`ai-request-transformer`, test 4). Kong's gates are loud: an enterprise plugin fails validation with `plugin '<name>' not enabled; add it to the 'plugins' configuration property`, which reads as a config fix but there is no code in the OSS image to enable (test 7). Record what is actually missing in the OSS-ceiling column. First-pass split, from vendor docs, is in `docs/day1-checks.md`.
- **Bifrost's enterprise API routes answer HTTP 200 with the UI page.** On OSS, `/api/guardrails/...`, `/api/audit-logs` and the like don't exist and fall through to the admin UI's HTML with a 200, the same as any unknown path. Check the content type before reading a 200 as success (test 7).
- **Cloud Run can't pull from ghcr.io, and Docker Hub pulls are rate-limited.** Pull upstream gateway images through the `agw-ghcr` remote repo (`ghcr_repository` output of `foundation/`) or, for Kong's `kong/kong`, `agw-dockerhub` (`dockerhub_repository`), and deploy by digest.
- **LiteLLM defaults `vertex_location` to `us-central1`.** Set it (to `eu`) per model in `config.yaml`, or calls miss the EU endpoint.
- **Bifrost's OpenAI API is under `/v1`.** `gateway_url` for the agent and `AGW_GATEWAY_URL` must end in `/v1`.
- **Bifrost's live price file is wrong for us.** Its datasheet (`getbifrost.ai/datasheet`) has Gemini 3.8 Flash at half price, and Bifrost never applies the regional uplift. The config sets both EU prices (`pricing_overrides`; ADR 0009).
- **Send `reasoning_effort` to Gemini only.** Bifrost turns `reasoning_effort` on Claude into adaptive thinking (its live datasheet says Haiku 5.5 supports it). The harness and agent already send it to Gemini only, matching the baseline (Claude thinking off); keep any new caller the same.
- **Every Bifrost cold start downloads its model catalog from getbifrost.ai** (about 22 s of a ~28 s start).
- **Bifrost's image is statically linked,** so custom `.so` plugins need a rebuilt Bifrost, not just a plugin.
- **First apply of a Cloud SQL gateway can race the `cloudsql.client` grant:** the service hangs at the database connection. The Bifrost stack waits 60 s (`time_sleep`); LiteLLM's does not.
- **Bifrost resets only the config sections the committed file declares.** `source_of_truth: config.json` left test 2's window `routing_rules` active in Postgres because the file had no such section; it now declares `routing_rules`, `budgets` and `rate_limits` as empty lists, which do clear them on a redeploy. A window in any other undeclared section needs checking with the admin API, and a restart removes admin-API keys not in the file, so never deploy during a run using one (`harness/scenarios/bifrost/README.md`).
- **Bifrost fallbacks can't be opted out of and keep the caller's parameters.** A routing rule's fallbacks override the caller's `fallbacks` (`[]` doesn't disable them), and a Claude → Gemini failover runs Gemini with no `reasoning_effort`, so it thinks at its default (137 reasoning tokens of a 256 cap in test 2). The OSS image has no mocker plugin, so no error can be forced on a healthy model.
- **Bifrost budgets don't reserve, so bursts overshoot.** A request is admitted while usage is under the limit and charged after it answers: ten at once spent 3.1× a budget of three (test 3). A budget's real ceiling is the limit plus one burst. The self-service quota endpoint lags the enforced counters.
- **Bifrost's refusals and logs mislead in two places.** A key restricted to Claude asking for a bare `gemini-3.8-flash` gets a 400 "could not auto resolve a provider", not the 403 that `vertex/gemini-3.8-flash` gets; and that 400 leaves no log row, though governance 403s and 429s do. A request's log row id is the `x-request-id` its response returned (test 5, test 6).
- **Bifrost `logging_headers` stores callers' credentials.** Naming `X-Serverless-Authorization` or `Authorization` there makes every log row keep the ID token or the virtual key value, for the 365-day retention (test 6, run B). Never read such rows into anything shared; rotate the keys afterwards. By default no header is stored, but content (prompts and answers) is.
- **`max_instances = 1` means a deploy can fail a request:** during a rollout Cloud Run may return its own 429 "no available instance". Never deploy during a measured run.
- **Cloud SQL must be running for plan, deploy and destroy.** After `make stop-<gw>`, run `make start-<gw>` first; the Makefile enforces it and the gateway can't start without its database.
- **Gateway admin UIs need the proxy on the laptop.** code-server forwards workstation ports under `/proxy/<port>/`, which breaks UIs with absolute paths (LiteLLM's). Run `gcloud run services proxy` where the browser is; the devcontainer image includes the `cloud-run-proxy` component for workstation-side `curl`.
- **Kong OSS can't translate to Claude on Vertex.** Its `gemini` provider only builds `publishers/google` URLs, and only that provider gets GCP credentials; Vertex's OpenAI-compatible endpoint doesn't serve Claude in `eu`. Claude goes through Kong as a native `rawPredict` pass-through (`route_type: preserve`, `upstream_url`), so callers send Anthropic format to Kong. Kong also drops `max_completion_tokens` and `reasoning_effort` for Gemini (`gateways/kong/NOTES.md`), so Gemini thinks at its default level (+0.7 to +1.0 s in test 1, some answers cut at the cap) and its stream arrives in one burst (TTFT = whole response).
- **decK splits `DECK_HEADERS` on spaces,** so `Authorization:Bearer <key>` breaks and decK's error echoes the key fragment (it exposed Kong's admin key once; rotated). Pass headers in a decK config file instead: open a pipe as fd 3 and point a `.yaml` symlink at `/dev/fd/3` (decK picks the parser from the extension), so nothing is written to disk or the command line (`gateways/kong/README.md`).
- **Kong can't use Cloud Run's `/cloudsql` socket.** Its CLI (migrations, `db_import`) can, but Kong's `init` phase uses LuaSocket, which can't open `unix:` paths; Kong reaches Postgres over TCP on a private IP (ADR 0016). A `preserve` route also needs `model.name`, or Kong turns Vertex's 200 into a 502.
- **Never test "is a key in the URL refused?" with a real key.** Kong's `file-log` and Cloud Run's request log record the full URL, query string included, so the key lands in Cloud Logging even when refused (it happened once with the harness key, which was rotated). Use a made-up value.
- **After a Kong deploy, `agw-kong` can answer 429 "no available instance" for minutes.** On 2026-10-25 Cloud Run started no instance for about 7 minutes after a rollout (max 1 instance, Direct VPC egress); the cause is unconfirmed. Wait for a 200 before a measured run, and give decK its 60 s timeout (`deck.sh`).
- **Kong OSS limits are request counts, and bursts overshoot them.** `rate-limiting` counts in fixed clock windows, in the instance's memory (`local`), and adds to the count after admitting a request, so 9 of 10 at once got through a limit of 3 in the notebook (the recorded run held at 3 by timing; test 3). Token and cost limits are enterprise, and Kong's logged Gemini cost leaves out thinking (15-17× low in test 3's caps requests). Throwaway consumers (tests 3, 5, 6) go through `/admin-api` tagged `agw-throwaway`, which decK ignores (ADR 0015).
- **Kong's `ai-request-transformer` breaks the translated Gemini route.** Once it has run, Kong skips translating a non-streaming answer, so an OpenAI caller gets Vertex's native `generateContent` JSON with a 200 (every Gemini case in test 4 run C; streaming untested). It masks only on `preserve` routes (Claude), at a second model call per request.
- **Kong forwards nearly every caller header upstream.** Only hop-by-hop headers are dropped, and `ai-proxy` replaces `Authorization` (the Kong key) with Kong's Google token; the caller's ID token (signature replaced by Cloud Run), custom headers, `X-Forwarded-For` and Kong's `X-Consumer-*` go to the model on both routes (test 5's echo window, a loopback stand-in for Vertex). Kong also stores caller keys in clear: never display Admin API key output.
- **Kong's `log_payloads` needs `log_statistics`, and misses `preserve` streams.** `ai-proxy` writes payloads only when statistics are on (the Claude routes have them off), and never a streamed Claude answer; Claude rows log 0 tokens even then. Rows and payloads land in Cloud Logging (30-day `_Default` bucket), not a Kong store; `kong.yaml` overwrites `X-Serverless-Authorization` in `file-log`, which would otherwise keep every ID token (test 6, ADR 0017).
- **gcloud splits `--args` on commas.** `--args=compare,--targets,direct,gateway` becomes four args. Use the alternate delimiter: `--args=^@^compare@--targets@direct,gateway`.
- **Local harness runs need gcloud ID tokens.** On the cloud workstation (itself a Cloud Run service) or a GCE VM (the devbox), the metadata server mints tokens as the machine's own account and the agent/gateway return 403. `AGW_ID_TOKEN_SOURCE=auto` picks `metadata` only in the job (`CLOUD_RUN_JOB`) or with a service-account key file in `GOOGLE_APPLICATION_CREDENTIALS`, and `gcloud` everywhere else; the `run-*.sh` scripts also set `gcloud` explicitly.
- **LiteLLM's price map can be wrong.** In v1.103.2 it has Gemini 3.8 Flash at half the Cloud Billing catalogue price and lacks Haiku 5.5, so spend would read low or have no basis. Gateway configs set model prices explicitly (ADR 0009); budgets are only as right as the price.
- **`store_prompts_in_spend_logs` stores callers' ID tokens.** With it on, each spend-log row keeps the request headers, including the Google ID token. Rows written in a window stay in Cloud SQL until `make destroy-litellm`: never read them into anything shared (ADR 0012 keeps only redacted flags).
- **LiteLLM licence gates fail four ways, and audit logs drop silently.** A 403 naming the feature, a 500 at key creation or use, a key accepted then failing every request, and a silent no-op (`/audit` stays empty with `store_audit_logs` on). Don't read an empty result as "nothing happened"; see the OSS-ceiling section in `results/summary.md`.
- **Spend logs are written in batches (~10 s).** A test that reads `/spend/logs` or Cloud Logging right after a request finds nothing; `audit_trail.py` retries until every request shows up.
- **Local runs need fresh credentials.** `run-*.sh` need a current `gcloud auth login` (ID tokens, secrets), and on the devbox a fresh `gcloud auth application-default login` once reauth expires (the `direct` target uses ADC). Symptoms are reauth errors or 403s mid-run.
- **Guardrails are global in OSS.** Per-key guardrails are enterprise-only, so an open test window screens every caller, the agent included; and the LLM judge fails open (a broken judge looks like `passed`). Close windows promptly and check `x-litellm-applied-guardrails`.
- **LiteLLM's first calls are slow.** After scale-to-zero the first request takes about 47 s (past the 60 s request timeout on a bad day), and the first Claude call on each new instance about 16 s. `compare`'s prewarm (180 s timeout, 3 tries) absorbs both and records them; don't read them as overhead.
- **Cloud workstation home is gcsfuse** (not the GCE VM, where home is a normal disk). uv can't create tool dirs or venvs there ("Function not implemented"). Keep `UV_TOOL_DIR`, `UV_CACHE_DIR`, `UV_PROJECT_ENVIRONMENT` and `PRE_COMMIT_HOME` under `/var/tmp`. There is no Docker locally either: build images with Cloud Build.
- **ADK lists only directory apps:** each app is `agents/<name>/agent.py` defining `root_agent`; single-file agents load but don't appear in `/list-apps`.
- **Renames:** Vertex AI is now Gemini Enterprise Agent Platform and Agent Engine is now Agent Runtime, but Terraform resources keep `google_vertex_ai_*` names and many docs still use the old names.

---

## Updating this document

This file should reflect the current state of the codebase. If you notice drift between this document and reality, fix it — stale context is worse than no context.
