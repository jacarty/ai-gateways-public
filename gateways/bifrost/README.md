# bifrost

Bifrost (OSS) as gateway 2: one IAM-authenticated Cloud Run service (`agw-bifrost`, `europe-west1`; public URL, every caller needs `roles/run.invoker` and an ID token) with a small Cloud SQL Postgres for its config store (virtual keys, budgets, rate limits) and logs store. How it works and what was found: [NOTES.md](NOTES.md).

## Layout

```
bifrost/
├── NOTES.md              # how it works, findings
├── tests.ipynb           # the test matrix by hand (setup, tests 1-6)
├── config/config.json    # providers, virtual keys, prices, stores (mounted from Secret Manager)
└── terraform/            # Cloud Run, Cloud SQL, agw-bifrost-* secrets, invoker IAM
```

## Deploy, stop, destroy

From the repo root. `foundation/` must be applied first (it provides the `agw-gw-bifrost` service account, the Cloud SQL API and the `agw-ghcr` repo the image is pulled through).

```bash
cp gateways/bifrost/terraform/terraform.tfvars.example gateways/bifrost/terraform/terraform.tfvars   # set your user:…
make deploy-bifrost     # terraform apply
make status-bifrost     # URL and database state
make stop-bifrost       # stop the database between sessions; make start-bifrost before the next one
make destroy-bifrost    # end of phase
```

`config/config.json` is the source of truth (`source_of_truth: config.json`): editing it and running `make deploy-bifrost` makes a new revision with the new config, and at start the sections present in the file replace what the database holds (sections the file leaves out keep their database rows). So a UI change to providers, virtual keys or prices lasts only until the next start, and anything in a section the file leaves out survives a redeploy (seen in test 2: a window's `routing_rules` stayed active); the file therefore declares `routing_rules`, `budgets` and `rate_limits` as empty lists, which a redeploy does clear. Test windows and how to close them: [harness/scenarios/bifrost/README.md](../../harness/scenarios/bifrost/README.md).

## Point the agent and the harness at the gateway

Each caller sends a Bifrost virtual key of its own (`sk-bf-…`) in `Authorization`, and its own ID token in `X-Serverless-Authorization`. Unlike LiteLLM's, the keys need no minting: Terraform generates their values into `agw-bifrost-agent-key` and `agw-bifrost-harness-key`, and `config.json` declares the two virtual keys (`agw-agent`, `agw-harness`) with those values (`env.AGW_BIFROST_AGENT_KEY`, `env.AGW_BIFROST_HARNESS_KEY`). The stack grants `agw-agent` and `agw-harness` read access to their own key, and `run.invoker` on the gateway to whoever `invoker_members` in `terraform.tfvars` lists (the example lists both and you), so all of it goes with `make destroy-bifrost`.

With `GW` from `terraform -chdir=gateways/bifrost/terraform output -raw gateway_url` (the service URL plus `/v1`: Bifrost serves `/v1/chat/completions`):

| Stack | `terraform.tfvars` |
| --- | --- |
| `agent/` | `target = "gateway"`, `gateway_url = "<GW>"`, `gateway_api_key_secret = "agw-bifrost-agent-key"` |
| `harness/` | `gateway_url = "<GW>"`, `gateway_api_key_secret = "agw-bifrost-harness-key"` |

Apply each. The harness job then runs `compare` against the gateway (see `harness/README.md`).

- **Rotating a key:** change it in Terraform (`terraform apply -replace='random_password.caller_key["agent"]'`): the secret gets a new version, and the gateway's revision, which pins it, is replaced with it. The old value stops working as soon as the new gateway revision starts (`vk_rotation_cooldown` defaults to 0), and the agent reads `latest` only when an instance starts, so it gets 401s until you force a new agent revision (or it scales to zero). Bifrost's own `POST /api/governance/virtual-keys/{id}/rotate` (OSS) survives a restart: at start the file's value matches the key's stored previous value, so Bifrost keeps the rotated one (`transports/bifrost-http/lib/config.go`). But the secret then holds a dead value, so rotate in Terraform. Test 5 covers both.
- **Before `make destroy-bifrost`:** set the agent back to `target = "direct"` and clear `gateway_url` and `gateway_api_key_secret` in both stacks, and apply them. `make destroy-bifrost` refuses while `agw-agent` or `agw-harness` still points at this gateway.

## Admin UI and API

User `admin`; the password is in `agw-bifrost-admin-password`:

```bash
gcloud secrets versions access latest --secret agw-bifrost-admin-password --project my-gcp-project
```

Run the proxy where the browser is (`gcloud run services proxy agw-bifrost --project my-gcp-project --region europe-west1 --port 4000`, then <http://localhost:4000>), as for LiteLLM: code-server's port forwarding breaks UIs with absolute paths. `make ui-bifrost` runs the same proxy on the workstation for `curl`. Enterprise pages show a "contact us" view: that is the OSS ceiling, not a fault.

## Cost

A Cloud SQL `db-f1-micro` instance while running (stop it with `make stop-bifrost` between sessions), Cloud Run instance time while an instance is up (CPU always allocated, min 0, max 1), and the model calls themselves. A default `compare` run is well under $1 of model spend.
