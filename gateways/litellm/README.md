# litellm

The LiteLLM proxy as gateway 1: one IAM-authenticated Cloud Run service (`agw-litellm`, `europe-west1`; public URL, every caller needs `roles/run.invoker` and an ID token) with a small Cloud SQL Postgres for keys, budgets and spend logs. How it works and what was found: [NOTES.md](NOTES.md).

## Layout

```
litellm/
├── NOTES.md            # how it works, findings
├── config/config.yaml  # models and proxy settings (mounted from Secret Manager)
└── terraform/          # Cloud Run, Cloud SQL, agw-litellm-* secrets, invoker IAM
```

## Deploy, stop, destroy

From the repo root. `foundation/` must be applied first (it provides the Cloud SQL API and the `agw-ghcr` repo the image is pulled through).

```bash
cp gateways/litellm/terraform/terraform.tfvars.example gateways/litellm/terraform/terraform.tfvars   # set your user:…
make deploy-litellm     # terraform apply
make status-litellm     # URL and database state
make stop-litellm       # stop the database between sessions; make start-litellm before the next one
make destroy-litellm    # end of phase
```

## Point the agent and the harness at the gateway

Each caller sends a LiteLLM virtual key of its own (not the master key) in `Authorization`, and its own ID token in `X-Serverless-Authorization`. Separate keys keep the agent's and the harness's spend and logs apart; virtual keys (looked up in Postgres, then cached) also make both paths do the same work, where the master key is only checked in memory. The gateway stack owns the key secrets (`agw-litellm-agent-key`, `agw-litellm-harness-key`, created empty), grants `agw-agent` and `agw-harness` read access to their own one and `run.invoker` on the gateway, so all of it goes with `make destroy-litellm`.

**1. Mint the keys and store them** (once per deploy: a new database has no keys). With the proxy running on the workstation (`make ui-litellm`, see below), in a second terminal:

```bash
mint() (  # mint <caller>: a virtual key aliased agw-<caller>, stored in agw-litellm-<caller>-key
  set -o pipefail   # a subshell, so this doesn't change your shell
  key=$(curl -fsS localhost:4000/key/generate -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
    -d "{\"key_alias\": \"agw-$1\", \"models\": [\"gemini-3.8-flash\", \"claude-haiku-5-5\"], \"max_budget\": 5}" \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["key"])') || exit 1
  test -n "$key" && printf %s "$key" | gcloud secrets versions add "agw-litellm-$1-key" --data-file=- --project my-gcp-project
)
MASTER=$(gcloud secrets versions access latest --secret agw-litellm-master-key --project my-gcp-project)
mint agent && mint harness
unset MASTER
```

Key aliases must be unique, so if `mint harness` fails after `mint agent` succeeded, re-run only `mint harness` (or delete the half-made key in the UI first). `max_budget` is in US dollars of LiteLLM-tracked spend and accumulates over the key's life: a backstop for runaway runs, well above what a test run costs (a default `compare` is well under $1), but check the key's spend if a later run starts failing with 4xx from the gateway. A key created in the UI (Virtual Keys) works too; store it without a trailing newline: `printf %s 'sk-…' | gcloud secrets versions add agw-litellm-agent-key --data-file=- --project my-gcp-project`.

**2. Point the callers at the gateway.** Each secret must have a version first (Cloud Run rejects a revision or execution that references an empty secret). With `URL` from `terraform -chdir=gateways/litellm/terraform output -raw url`:

| Stack | `terraform.tfvars` | Needs |
| --- | --- | --- |
| `agent/` | `target = "gateway"`, `gateway_url = "<URL>"`, `gateway_api_key_secret = "agw-litellm-agent-key"` | an agent image that includes `auth.py` |
| `harness/` | `gateway_url = "<URL>"`, `gateway_api_key_secret = "agw-litellm-harness-key"` | a harness image with `compare` |

Apply each. The harness job then runs `compare` against the gateway (see `harness/README.md`).

- **Rotating a key:** add a new version. The harness reads it when an execution starts. The agent reads `latest` when an instance starts, so warm instances keep the old key: force a new revision (`gcloud run services update agw-agent --project my-gcp-project --region europe-west1 --update-labels=key-rotated=$(date +%s)`) or let it scale to zero, or a run splits spend across two keys.
- **Before `make destroy-litellm`:** set the agent back to `target = "direct"` and clear `gateway_url` and `gateway_api_key_secret` in both stacks, and apply them. `make destroy-litellm` refuses while `agw-agent` or `agw-harness` still points at this gateway.

## Notebook

[`tests.ipynb`](tests.ipynb) runs the test matrix by hand, one cell at a time, each section saying how many model calls it makes. It complements the harness, whose recorded runs in `results/raw/litellm/` are the reported numbers. It uses the standard library and `gcloud` (your identity for the ID token, the harness's virtual key from Secret Manager, never printed). It covers:

- **Test 1:** one request each way with its raw response, and a small paired direct-versus-gateway run.
- **Test 2:** every case of the `failover.json` scenario file once, with what came back, and a curl walkthrough of the same cases.
- **Test 3:** throwaway keys with small limits, held in memory and deleted in the clean-up cell (never the harness or agent key); a price check (LiteLLM's cost for a request against its tokens times the configured price); each limit (requests and tokens per minute, budget, the concurrent race) with what came back; the enterprise-only key fields; and the config window (unpriced model, throttling). The window needs the temporary config in `harness/scenarios/litellm/README.md`.
- **Test 4:** the shared screening case set (`harness/scenarios/screening-cases.json`) on both models, each answer classed (blocked, masked, leaked, withheld, passed, error), with a check that a guardrail is on and a curl version of one masked and one blocked request. The guardrail windows need the temporary config in `harness/scenarios/litellm/README.md`.
- **Test 5:** where the credentials live (read-only `gcloud`: service-account keys, org policy, secrets, invokers), the same refusals with `curl`, one throwaway key taken through its states, and the agent's key used by someone else.
- **Test 6:** one agent run and one tagged request, the spend-log rows and Cloud Run request logs they left, and the same reads with `curl` and `gcloud logging read`.

Test 7 (OSS ceiling) is written up from the other tests in `results/summary.md`; it has no notebook section.

**Kernel on a plain GCE VM (devbox):** home is a normal disk, so any Jupyter kernel works; create a venv with `ipykernel` wherever you like and select it. The notebook needs nothing else.

**Kernel on the cloud workstation, once per workstation** (home is gcsfuse, so the environment lives under `/var/tmp`):

```bash
uv venv /var/tmp/agw-notebook --python 3.13
uv pip install --python /var/tmp/agw-notebook ipykernel==7.4.0
/var/tmp/agw-notebook/bin/python -m ipykernel install --user --name agw-notebook --display-name "agw-notebook (Python 3.13)"
```

VS Code doesn't look for Python environments under `/var/tmp`, so the last line registers it as a Jupyter kernel (in `~/.local/share/jupyter/kernels/`, which survives a workstation rebuild; the environment itself doesn't, so rerun the first two lines after one). Then open `tests.ipynb`: it asks for that kernel by name, or pick **Select Kernel** → Jupyter Kernel… → **agw-notebook (Python 3.13)** (reload the window if it isn't listed yet). VS Code needs the Jupyter extension (`ms-toolsai.jupyter`, from Open VSX); the devcontainer image doesn't include it yet, so install it from the Extensions view.

**Before committing,** clear the outputs (**Clear All Outputs**), so diffs stay readable and no answers or headers end up in git.



The service is IAM-authenticated: every request needs an ID token from a principal with `roles/run.invoker`, which a browser can't send. `gcloud run services proxy` runs a local proxy that adds your ID token to each request (in `X-Serverless-Authorization`, so `Authorization` stays free for a LiteLLM key).

**Prerequisites:** the `cloud-run-proxy` gcloud component (the devcontainer image installs it; elsewhere `gcloud components install cloud-run-proxy`), and your account (`gcloud config get account`) in `invoker_members` in `terraform.tfvars`, as `user:<you>`.

### Admin UI

Run the proxy **on the machine with the browser** (your laptop), not on the workstation:

```bash
gcloud run services proxy agw-litellm --project my-gcp-project --region europe-west1 --port 4000
```

Open <http://localhost:4000/ui> and log in as `admin`. The password is the master key:

```bash
gcloud secrets versions access latest --secret agw-litellm-master-key --project my-gcp-project
```

- **The workstation's forwarded port does not work for the UI.** code-server forwards ports under a path (`https://<workstation>/proxy/4000/`), but the UI loads its assets from absolute paths (`/litellm-asset-prefix/_next/...`) and redirects to an absolute `http://127.0.0.1:4000/ui/`, so the page breaks. `make ui-litellm` on the workstation is for `curl` and scripts there.
- **The first load is slow** if the service has scaled to zero: a cold start runs LiteLLM's database migrations before serving (up to about two minutes).
- **The database must be running.** After `make stop-litellm` the gateway can't start; run `make start-litellm` first.
- Stop the proxy with Ctrl-C. While it runs, anything on that machine that can reach `localhost:4000` reaches the gateway as you.

### API

The proxy puts your ID token in `X-Serverless-Authorization`, so `Authorization` stays free for a LiteLLM key, the same split the agent and harness use:

```bash
KEY=$(gcloud secrets versions access latest --secret agw-litellm-master-key --project my-gcp-project)

curl -s localhost:4000/v1/models -H "Authorization: Bearer $KEY"

curl -s localhost:4000/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gemini-3.8-flash", "messages": [{"role": "user", "content": "Say hi"}], "max_completion_tokens": 64}'
```

`-H "Authorization: Bearer $KEY"` puts the key on the command line, where other processes on the workstation can see it in `ps`; fine on a single-user workstation, otherwise pass headers from a file (`-H @file`).

Prefer a virtual key (created in the UI under Virtual Keys) over the master key for anything but admin work: budgets and rate limits attach to virtual keys.

### Without the proxy

Callers that can mint ID tokens (the agent and the harness, or `curl` with `gcloud auth print-identity-token`) call the `run.app` URL directly, with the ID token in `X-Serverless-Authorization` and the LiteLLM key in `Authorization`:

```bash
URL=$(terraform -chdir=gateways/litellm/terraform output -raw url)
curl -s "$URL/v1/models" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Authorization: Bearer $KEY"
```
