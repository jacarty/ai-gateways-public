# Setup guide: deploy the lab in your own GCP project

This guide takes a fresh clone to a running lab in your own project: the foundation, the agent, the harness, then one gateway at a time. Read [architecture.md](architecture.md) first for what each piece is. Each stack's README has the detail; this page gives the order and the things that differ for a new project.

**Assumes:** you're comfortable with `gcloud`, Terraform and Cloud Run, and you'll keep everything in `europe-west1` with the models on the Agent Platform's `eu` multi-region endpoint, as the lab does. Moving region means changing more than variables (the Claude endpoint, Kong's routes, the harness defaults); it isn't covered here.

## What it costs

- **Idle:** close to nothing. Cloud Run scales to zero, and the buckets hold little.
- **A gateway phase:** a `db-f1-micro` Cloud SQL instance while it runs (stop it between sessions with `make stop-<gw>`; storage is still billed), plus model calls.
- **Model calls:** small. Load runs use Gemini 3.8 Flash and Claude Haiku 5.5 with a 256-token cap; a full paired run (`compare`, about 20-35 minutes) is a few thousand short requests.
- The foundation creates a **budget with e-mail alerts** before anything else. It alerts; it doesn't stop spend. Keep runs short, and destroy each gateway when you're done with it.

## 1. Prerequisites

**A GCP project** linked to a billing account, which you can give to the lab (the stacks only add to a project, so a shared one works, but a dedicated one is simpler). You need:

- Owner on the project.
- `roles/billing.costsManager` (or Billing Account Administrator) on the billing account, for the budget.
- The billing account's currency (for `budget_currency`; a mismatch fails the apply).

**Model access** on the `eu` multi-region endpoint:

- Gemini 3.8 Flash needs nothing beyond the Agent Platform API.
- Claude Haiku 5.5 must be enabled in Model Garden (accept Anthropic's terms; that can need `roles/consumerprocurement.entitlementManager`), and its quota on the `eu` endpoint must be above zero: IAM & Admin → Quotas, filter "anthropic"; request an increase if needed. See [day1-checks.md](day1-checks.md).

**A Linux machine to deploy from** (a VM, Cloud Shell-like environment or WSL): the scripts need Bash 4.4+, GNU coreutils and GNU `sed` and `date`, so a stock macOS shell won't run them. **Tools** on it:

| Tool | Version | For |
| --- | --- | --- |
| `gcloud` | current, with the `cloud-run-proxy` component | everything; the proxy for the gateways' admin UIs |
| Terraform | 1.16.x | every stack |
| `uv` | current | the agent and harness (Python 3.13+, installed by uv) |
| `git` | any | `scripts/build-image.sh` builds only committed code |
| `python3` | 3.x on `PATH` | small JSON steps in the READMEs and scripts |
| decK | v1.68.0 | Kong only (`make sync-kong`); install from the release tarball, checked against its `checksums.txt` |
| `pre-commit` | 4.6.2 | optional: the repo's lint hooks (`pre-commit install`; needs `go` for gitleaks) |

No local Docker is needed: images are built with Cloud Build.

Log in twice, once for `gcloud` and once for Terraform and the harness's `direct` target:

```bash
gcloud auth login
gcloud auth application-default login
```

## 2. Clone and point the repo at your project

The lab's original project ID is written into the Makefile, the build script, the test scripts, Kong's config and the harness (Kong's Claude routes carry the project in their paths). Replace it everywhere except the recorded results, then commit, because images are built only from committed code:

```bash
git clone <this repo> ai-gateways && cd ai-gateways
git switch -c chore/my-project
export PROJECT=<your-project-id>

OLD=$(sed -n 's/^PROJECT *:= *//p' Makefile)   # the original project ID
git grep -l "$OLD" -- ':!results' | xargs sed -i "s/$OLD/$PROJECT/g"
git grep -n "$OLD" -- ':!results'    # expect nothing
git commit -am "chore: point the lab at $PROJECT"
```

Bucket names derive from the project ID (`<project>-ai-gateways-tfstate`, `-results`, `-build-src`), so they follow. Leave `results/` alone: it is the lab's recorded evidence.

The repo's `gcloud` commands that act on project resources pass `--project` explicitly (image paths carry their project in the name); do the same in your own commands, since your default project may differ.

## 3. Foundation

The persistent stack: APIs, the budget and alert, service accounts, the Terraform state bucket, the image repositories (including the `agw-ghcr` and `agw-dockerhub` pull-through repos), the build and results buckets, and the VPC Kong's database uses. Full detail: [foundation/README.md](../foundation/README.md).

It creates its own state bucket, so the first apply uses local state:

```bash
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project "$PROJECT"

cd foundation/terraform
# Comment out the backend "gcs" block in backend.tf for the first apply.
cp terraform.tfvars.example terraform.tfvars   # project_id, billing_account_id, alert_email, budget_currency
terraform init
terraform apply
```

If the apply fails with a transient 403 or "service account does not exist" (new APIs propagating), run it again.

**Check the budget before going further:** the alert e-mail arrives, or the budget shows in Billing → Budgets & alerts.

Then move the state into the bucket it just made:

```bash
cp backend.hcl.example backend.hcl   # bucket = $(terraform output -raw state_bucket)
# Uncomment the backend block in backend.tf again.
terraform init -migrate-state -force-copy -backend-config=backend.hcl
terraform plan                       # must say: No changes
rm terraform.tfstate*                # only after the plan is clean
cd ../..
```

Every other stack reads `foundation/terraform/backend.hcl` and uses its own state prefix.

## 4. The agent

A small ADK agent on Cloud Run, serving two apps, `gemini` and `claude`. Detail: [agent/README.md](../agent/README.md).

```bash
scripts/build-image.sh agent          # prints: image = "…/agw-images/agent@sha256:…"

cd agent/terraform
cp terraform.tfvars.example terraform.tfvars
# Set: project_id; image (the printed line);
# invoker_members = ["user:<you>", "serviceAccount:agw-harness@<project>.iam.gserviceaccount.com"]
terraform init -backend-config=../../foundation/terraform/backend.hcl
terraform apply
cd ../..
```

`scripts/build-image.sh` reads the foundation's outputs, so run it from a clone where `foundation/terraform` is initialised. It refuses to build if the component has uncommitted changes.

Check it answers with the smoke call in [agent/README.md](../agent/README.md#call-it) (one question to each app). The first call after a while takes longer: the service scales to zero.

## 5. The harness

The load harness, a Cloud Run job writing to the results bucket. Detail: [harness/README.md](../harness/README.md).

```bash
scripts/build-image.sh harness

cd harness/terraform
cp terraform.tfvars.example terraform.tfvars   # project_id, image
terraform init -backend-config=../../foundation/terraform/backend.hcl
terraform apply
cd ../..

# A small check: 2 direct requests, no warm-up.
gcloud run jobs execute agw-harness --project "$PROJECT" --region europe-west1 --wait \
  --args=load,--target,direct,--model,gemini,--n,2,--warmup,0
gcloud storage ls "gs://$PROJECT-ai-gateways-results/"
```

The full baseline (no `--args`) runs about 30-40 minutes. `gcloud` splits `--args` on commas, so for a list such as `direct,gateway` use the alternate separator: `--args=^@^compare@--targets@direct,gateway`.

## 6. A gateway

Deploy one gateway at a time; each lives in `gateways/<gw>/` with its own Terraform stack, and the root `Makefile` wraps it (`make help`). The gateway images are pulled through the foundation's remote repositories, pinned by digest to the release the lab tested; the digests in each `terraform.tfvars.example` work as they are.

```bash
cp gateways/<gw>/terraform/terraform.tfvars.example gateways/<gw>/terraform/terraform.tfvars
# Set project_id, the image path's project, and invoker_members (you, agw-agent, agw-harness).
make deploy-<gw>
make status-<gw>      # URL and database state
```

What differs per gateway (read its README before deploying):

| Gateway | After `make deploy-<gw>` |
| --- | --- |
| [LiteLLM](../gateways/litellm/README.md) | Mint the agent's and harness's virtual keys with the master key and store them in `agw-litellm-agent-key` and `agw-litellm-harness-key` (the README has the snippet). |
| [Bifrost](../gateways/bifrost/README.md) | Nothing: Terraform generates the keys. The OpenAI API is under `/v1`, so gateway URLs end in `/v1`. |
| [Kong OSS](../gateways/kong/README.md) | `make sync-kong` (decK applies `config/kong.yaml` and the generated keys to Kong), then `make status-kong` should show a diff of 0/0/0. Claude goes through Kong in its native Vertex format, so set `gateway_claude_api = "anthropic"` in the agent and harness. |

The first apply of a gateway with Cloud SQL can race its database grant and hang at the database connection; run `make deploy-<gw>` again. A gateway may answer Cloud Run's 429 "no available instance" for a few minutes after a deploy (one instance at most): wait for a 200 before a measured run.

**Admin UI:** run `gcloud run services proxy agw-<gw> --project "$PROJECT" --region europe-west1 --port 4000` on the machine with your browser, and open `http://localhost:4000` (Kong's is at `/manager`). The login is in an `agw-<gw>-*` secret named in the gateway's README.

## 7. Point the callers at the gateway and run the tests

Set the gateway in `agent/terraform/terraform.tfvars` (`target = "gateway"`, `gateway_url`, `gateway_api_key_secret = "agw-<gw>-agent-key"`) and in `harness/terraform/terraform.tfvars` (`gateway_url`, `gateway_api_key_secret = "agw-<gw>-harness-key"`), then `terraform apply` both.

- **Test 1 (overhead):** a paired run, gateway against direct in the same job:

  ```bash
  gcloud run jobs execute agw-harness --project "$PROJECT" --region europe-west1 --wait \
    --args=^@^compare@--targets@direct,gateway
  ```

- **Tests 2-7:** scenario files and scripts in `harness/scenarios/<gw>/`, run locally (their README lists the config windows each test needs), and a notebook walkthrough in `gateways/<gw>/tests.ipynb`. Local runs need `AGW_ID_TOKEN_SOURCE=gcloud` and fresh `gcloud` logins.

Compare results only within a paired run: Gemini's latency drifts by seconds between runs ([ADR 0007](decisions/0007-paired-baselines.md)).

## 8. Tear down

**A gateway**, when you're done with it:

1. Set the agent back to `target = "direct"`, clear `gateway_url` and `gateway_api_key_secret` in both the agent and the harness (after Kong, also set `gateway_claude_api = "openai"`), and `terraform apply` both.
2. `make start-<gw>` if its database is stopped, then `make destroy-<gw>`. It refuses while either caller still references the gateway.

**Everything:** destroy any gateway, then the harness and agent stacks (`terraform destroy` in each). The foundation keeps its own state in the bucket it would delete, so take it back to local state first:

1. In `foundation/terraform`, comment out the `backend "gcs"` block in `backend.tf` and run `terraform init -migrate-state` (the state moves to a local `terraform.tfstate`).
2. Remove the `lifecycle` block (`prevent_destroy`) in `state.tf`.
3. Empty the buckets, every object version included (the state bucket is versioned; the results bucket has no `force_destroy`), e.g. `gcloud storage rm -r --all-versions "gs://$PROJECT-ai-gateways-results/**"`. Keep a copy of any results you want first.
4. `terraform destroy`. APIs stay enabled. See [foundation/README.md](../foundation/README.md#destroying).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| 403 from the agent or a gateway on a local run | The metadata server minted the ID token as the machine's own account (Cloud Workstations, GCE). Set `AGW_ID_TOKEN_SOURCE=gcloud`. |
| `invalid_rapt` or reauth errors mid-run | Run `gcloud auth login` and `gcloud auth application-default login` again. |
| Cloud Run can't pull a gateway image | Pull through `agw-ghcr` (GitHub) or `agw-dockerhub` (Docker Hub), not from the source registry. |
| LiteLLM calls go to `us-central1` | Each model in `config/config.yaml` needs `vertex_location: eu` (the committed config has it). |
| Claude calls fail with quota or permission errors | Model Garden terms or the `eu` quota: see Prerequisites. |
| uv fails with "Function not implemented" | A FUSE-mounted home (Cloud Workstations): keep `UV_CACHE_DIR`, `UV_TOOL_DIR`, `UV_PROJECT_ENVIRONMENT` and `PRE_COMMIT_HOME` under `/var/tmp`. |

More, gathered over the lab's three phases, in the "Common Pitfalls" section of [AGENTS.md](../AGENTS.md).
