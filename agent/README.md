# agent

The one ADK agent, held constant across the baseline and every gateway. It runs as a private Cloud Run service (`agw-agent`) in `europe-west1` and serves two ADK apps from a single image:

| App | Model | Direct endpoint |
| --- | --- | --- |
| `gemini` | `gemini-3.8-flash` | EU multi-region (`eu`) |
| `claude` | `claude-haiku-5-5` | EU multi-region (`eu`) |

Neither model has a `europe-west1` endpoint, so both are called on the EU multi-region endpoint (`aiplatform.eu.rep.googleapis.com`). Only the settings change between runs, never the code:

| Variable | Meaning |
| --- | --- |
| `AGW_TARGET` | `direct` (baseline) or `gateway` |
| `AGW_GATEWAY_URL` | Gateway's OpenAI-compatible base URL, when `gateway` |
| `AGW_GATEWAY_API_KEY` | Gateway key, sent as `Authorization` (from the `gateway_api_key_secret` secret on Cloud Run) |
| `AGW_GATEWAY_CLAUDE_API` | `openai` (default): Claude through the gateway's OpenAI API. `anthropic`: Claude keeps the direct path's Vertex client, sent to `<AGW_GATEWAY_URL>/projects/.../claude-haiku-5-5:rawPredict` with the gateway key as its bearer (Kong; needs `GOOGLE_CLOUD_PROJECT`) |
| `AGW_MAX_OUTPUT_TOKENS` | Cap per call (default 256) |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_ENTERPRISE` | Direct model access |

In `gateway` mode both apps call the gateway through LiteLLM with the same model names, which each gateway's config maps to the real models.

**Gateway auth.** Gateways run on Cloud Run with IAM auth, so every call carries two credentials: the gateway key in `Authorization` (who you are to the gateway: budgets, limits) and an ID token for the gateway's URL in `X-Serverless-Authorization` (which Cloud Run checks; `agw-agent` must be in the gateway's `invoker_members`). The token is minted from the agent's service account through the metadata server and refreshed before it expires (`auth.py`). It only works on Cloud Run: run locally, the token belongs to whatever identity the local metadata server or key file has.

**Fixed test condition: thinking.** Gemini runs at the `LOW` thinking level, the lowest `gemini-3.8-flash` accepts (it rejects `MINIMAL` with a 400), and Claude without thinking (its default). Latency and cost then compare like with like, and thinking can't use up `max_output_tokens` before the answer. Direct calls set Gemini's `thinking_config`; through a gateway the same intent is sent as OpenAI's `reasoning_effort: "low"`, and whether each gateway honours it is recorded as a finding (check `thoughtsTokenCount` in responses).

## Layout

```
src/agw_agent/
  config.py        # settings from env
  models.py        # direct vs gateway model selection
  auth.py          # ID token for gateway calls (X-Serverless-Authorization)
  factory.py       # the one agent definition
  agents/{gemini,claude}/agent.py   # one ADK app per model
  app.py           # ASGI entry point (ADK API server)
tests/             # pytest
Dockerfile         # digest-pinned bases, uv.lock, non-root
cloudbuild.yaml    # Cloud Build: build + push
terraform/         # Cloud Run service + invoker IAM (state prefix: agent)
```

## Develop

The workstation home is gcsfuse, so keep uv's environment on local disk (see the gcsfuse pitfall in AGENTS.md):

```bash
cd agent
export UV_PROJECT_ENVIRONMENT=/var/tmp/agw-agent-venv
uv sync --locked
uv run pytest
```

## Build (Cloud Build)

There is no Docker on the workstation; Cloud Build runs the Dockerfile as the `agw-build` service account. Whoever submits the build needs `iam.serviceAccountUser` on `agw-build`, `cloudbuild.builds.editor`, and object create on the staging bucket (project Owner covers all three).

Build only committed code, so the tag names exactly what is in the image. From the repo root:

```bash
scripts/build-image.sh agent
```

It refuses to run if `agent/` has uncommitted changes (gcloud uploads the working tree, not the commit), tags the image with the current commit, and prints the digest-pinned `image = …` line for the next step. Tags are mutable, so deploys always use the digest.

## Deploy

Put the printed `image = …@sha256:…` line in `terraform.tfvars`; Terraform rejects a tag.

```bash
cd agent/terraform
cp terraform.tfvars.example terraform.tfvars   # first time: set image and invoker_members
terraform init -backend-config=../../foundation/terraform/backend.hcl
terraform plan
terraform apply
```

## Call it

The service is IAM-authenticated (its URL is public, but not open): callers need `roles/run.invoker` (from `invoker_members`) and an ID token. `invoker_members` refuses `allUsers` and `allAuthenticatedUsers`.

```bash
URL=$(terraform -chdir=agent/terraform output -raw url)
TOKEN=$(gcloud auth print-identity-token)

for app in gemini claude; do
  curl -s -X POST "$URL/run" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"app_name\":\"$app\",\"user_id\":\"smoke\",\"session_id\":\"smoke-$app-$(date +%s)\",
         \"new_message\":{\"role\":\"user\",\"parts\":[{\"text\":\"What is the capital of Belgium?\"}]}}" \
    | python3 -m json.tool | head -40
done
```

Sessions are created automatically and held in memory; each benchmark request should use a fresh `session_id`.
