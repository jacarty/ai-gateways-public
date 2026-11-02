# kong

Kong Gateway OSS 3.9.3 as gateway 3. It runs as one IAM-authenticated Cloud Run service, `agw-kong`, in `europe-west1`. Every caller needs `roles/run.invoker` and an ID token. Kong keeps its config (services, routes, plugins, consumers, keys) in a small Cloud SQL Postgres, which has a private IP only on foundation's `agw-vpc`. decK keeps that config in step with `config/kong.yaml`. How it works and what was found: [NOTES.md](NOTES.md). Decisions: ADR 0014 (Claude path, keys), 0015 (Postgres, decK), 0016 (private network).

## Layout

```
kong/
├── NOTES.md              # how it works, findings
├── tests.ipynb           # the test matrix by hand (setup, tests 1-6 by hand; test 7 is a probe, `harness/scenarios/kong/probe-ceiling.sh`)
├── deck.sh               # decK diff / sync through the /admin-api route (make diff-kong, sync-kong)
├── config/
│   ├── kong.yaml         # the committed config, synced by decK (no secrets: keys come from DECK_* env vars)
│   ├── bootstrap.yaml    # the Admin API route and admin consumer, imported at every start
│   └── start.sh          # container command: migrations, bootstrap import, then Kong
└── terraform/            # Cloud SQL (private IP), agw-kong-* secrets, Cloud Run, invoker IAM
```

## Deploy, sync, stop, destroy

Run these from the repo root. Apply `foundation/` first. It provides the `agw-gw-kong` service account, the `agw-dockerhub` repo the image comes through, and `agw-vpc` (the subnet for Direct VPC egress, plus the private services access range for Cloud SQL). decK must be on your `PATH`: v1.68.0, the official release tarball checked against its `checksums.txt`.

```bash
cp gateways/kong/terraform/terraform.tfvars.example gateways/kong/terraform/terraform.tfvars   # set your user:…
make deploy-kong        # terraform apply: database, secrets, the agw-kong service
make sync-kong          # decK: make the live config match config/kong.yaml
make status-kong        # URL, database state, and a decK diff (0/0/0 = live config matches the file)
make stop-kong          # stop the database between sessions; make start-kong before the next one
make destroy-kong       # end of phase
```

**What happens at start.** `config/start.sh` reads the schema state from `kong migrations list`, then acts on it:

| State | Action |
| --- | --- |
| New database | Bootstrap |
| New migrations | `up`, then `finish` |
| Pending migrations | `finish` |
| Up to date | Nothing |

It then imports `bootstrap.yaml`: the `/admin-api` route, its ACL, the admin consumer and key, and the global `key-auth`. The import uses fixed IDs, so repeating it just overwrites the same entities. Finally it starts Kong. A start on a migrated database takes about 5 s.

**The config lives in the database, not the image.** Editing `config/kong.yaml` and running `make sync-kong` applies the change at once, with no redeploy. Kong picks it up on its next cache poll, within about 5 s. decK deletes tagged (`agw`) entities that the file doesn't declare, which plain `kong config db_import` never does. `make diff-kong` (exit 2 if they differ) is the check that the live config is the committed file. Run it after closing every test window.

**decK and credentials.** `deck.sh` reads your ID token, the admin key and the caller keys into variables. It hands decK its headers through a pipe (fd 3, behind a `.yaml` symlink), so nothing reaches disk or the command line, and it redacts decK's output. Don't use `DECK_HEADERS`: decK splits it on spaces, and its error then echoes the key.

**Rotating a key.** Run `terraform -chdir=gateways/kong/terraform apply -replace='random_password.key["agent"]'`, or the same with `admin` or `harness`, then `make sync-kong`.
- **Admin key:** a new revision imports it at start, because the bootstrap secret is pinned.
- **Agent or harness key:** decK writes the new value. The agent and the harness job read `latest` only when an instance or execution starts, so force a new agent revision.
- **Kong Manager password:** `-replace='random_password.manager'`, then `make sync-kong`. Kong keeps only a hash, so decK can't compare passwords and would ignore a new one. `deck.sh` therefore derives the credential's id from the password, and removes the old credential before the sync (decK creates before it deletes, and the username `admin` must be unique). Tested 2026-10-28.
- **Never test with a real key in a URL:** Kong's `file-log` and Cloud Run's request log record the full URL, query string included.

## Point the agent and the harness at the gateway

Each caller sends its own Kong key in `Authorization` (`Bearer <key>`). Kong's `key-auth` compares the whole header, so each credential is stored as `Bearer <key>`. Each caller also sends its own ID token in `X-Serverless-Authorization`. Terraform generates the key values into `agw-kong-agent-key` and `agw-kong-harness-key`. The stack grants `agw-agent` and `agw-harness` read access to their own key, and grants `run.invoker` to `invoker_members`.

**Claude goes to Kong in its own Vertex format.** Kong's AI Proxy can't translate to Claude on Vertex (ADR 0014). Both callers therefore set `gateway_claude_api = "anthropic"`, and send Claude the direct baseline's `rawPredict` request under the gateway URL. Gemini stays on `/v1/chat/completions`.

Get `GW` from `terraform -chdir=gateways/kong/terraform output -raw gateway_url`. It is the service URL plus `/v1`.

| Stack | `terraform.tfvars` |
| --- | --- |
| `agent/` | `target = "gateway"`, `gateway_url = "<GW>"`, `gateway_api_key_secret = "agw-kong-agent-key"`, `gateway_claude_api = "anthropic"` |
| `harness/` | `gateway_url = "<GW>"`, `gateway_api_key_secret = "agw-kong-harness-key"`, `gateway_claude_api = "anthropic"` |

**Before `make destroy-kong`:** set the agent back to `target = "direct"`, and clear `gateway_url` and `gateway_api_key_secret` in both stacks. Set `gateway_claude_api` back to `"openai"`, then apply both. `make destroy-kong` refuses while `agw-agent` or `agw-harness` still points at this gateway.

## Routes

| Path (under the service URL) | Plugin | What it does |
| --- | --- | --- |
| `POST /v1/chat/completions` | `ai-proxy`, `llm/v1/chat`, provider `gemini` | Translates OpenAI chat to Gemini `generateContent` on `aiplatform.eu.rep.googleapis.com`. It forces `max_tokens: 256` (Kong drops `max_completion_tokens`) and logs tokens and cost |
| `POST /v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/claude-haiku-5-5:rawPredict` (and `:streamRawPredict`) | `ai-proxy`, `preserve`, provider `gemini` | Passes Claude's native request through to the same Vertex URL, adding Kong's GCP token. It needs `model.name`, or Kong breaks the response |
| `/admin-api` | `acl` (group `admin`) | The loopback Admin API (`127.0.0.1:8001`), for decK and the test scripts |
| `/manager` | `basic-auth` (user `admin`) | Kong Manager OSS, the admin UI (Kong on `127.0.0.1:8002`) |
| `/manager-api` | `basic-auth` (user `admin`) | The Admin API as Kong Manager calls it from the browser |
| `GET /manager/kconfig.js` | `pre-function` | Kong Manager's runtime config, with the API URL taken from the page's own host (see below). No secrets, so it loads before the login |
| `GET /` (exactly) | `pre-function` | A relative `302` to `/manager`. Kong's `redirect` plugin only takes an absolute URL, which would leave the proxy |

The global `key-auth` (with `hide_credentials`, header only) covers every route except four. The two Manager routes swap it for the `admin` login, because Manager can't send a key. `GET /manager/kconfig.js` and the `/` redirect answer before any auth: both are fixed responses with no secrets. The model routes accept only the `callers` group (agent, harness and throwaway keys), and `/admin-api` only `admin`.

Kong calls Vertex as `agw-gw-kong` through the metadata server, with no key. It reaches Postgres over TLS with `pg_ssl_verify` on, against the instance's own CA (the `agw-kong-db-ca` secret). Kong's Postgres client checks the chain, not the hostname, so the private IP verifies. The secret holds `server_ca_cert[0]`; after a Cloud SQL CA rotation, re-apply to pick up the new CA.

## Admin UI and API

**Kong Manager OSS, the admin UI, at `/manager`.** Run the proxy on the machine with the browser, as for LiteLLM and Bifrost:

```bash
gcloud run services proxy agw-kong --project my-gcp-project --region europe-west1 --port 4000
```

Open <http://localhost:4000/> (it redirects to `/manager`) and log in as `admin`. The password is in `agw-kong-manager-password`:

```bash
gcloud secrets versions access latest --secret agw-kong-manager-password --project my-gcp-project
```

How it's wired:
- **Kong Manager OSS has no login of its own**: user accounts and RBAC are enterprise. It calls the Admin API from the browser, so it can't send the admin key that `/admin-api` requires. Kong serves it on loopback (`127.0.0.1:8002`, path `/manager`), and its Admin API calls go to a second route, `/manager-api`.
- **The login** is Kong's OSS `basic-auth` plugin on both routes, which gives the browser's username and password prompt, as LiteLLM's and Bifrost's UIs have. Kong stores the password hashed. Cloud Run IAM still applies first: only `invoker_members` can reach the URL at all.
- **The `key-auth` override on these routes reads a header nothing sends** (`key_names: [x-agw-no-key]`). With `key_names: [authorization]`, its `hide_credentials` stripped the `Basic` login header before `basic-auth` ran, so even the right password got a 401.
- **Kong Manager 3.9.0.0 can't use a relative API URL.** It prefixes `ADMIN_API_URL` with only the protocol (`src/config.ts:39`), so `/manager-api` became `http:///manager-api`, and every page but Overview failed with "could not be retrieved". Kong now serves Manager's `kconfig.js` itself, setting the URL to `window.location.host + '/manager-api'`. That works through the proxy on any port, and on a domain later.
- **No real domain yet:** the `run.app` URL can't be opened directly in a browser, because it needs an ID token on every request. With IAP in front (tech debt), the same Manager should work on a domain, because `kconfig.js` takes the API's host from the page. That's untested.
- **Cross-site protection.** The browser keeps the `admin` login for the proxy's origin, and Kong's Admin API echoes any `Origin` with credentials allowed (no `admin_gui_url` set). So a page on another site could otherwise read `/manager-api`, where keys come back in clear, or post forms to it. A `pre-function` on both Manager routes therefore does three things. It refuses anything the browser marks cross-site (`Sec-Fetch-Site`). It refuses writes that aren't JSON, which forms can't send. And it drops `Origin`, so the Admin API never grants CORS. Checked 2026-10-28: a cross-site read gets 403, a form post 415, and Manager itself works.
- **The Manager password is as powerful as the admin key.** `/manager-api` is the full Admin API. There's no rate limit on the login, but the password is 32 random characters. Rotating the admin key doesn't change it, so rotate both if either may have leaked.
- **Changes made in Manager carry no `agw` tag,** so decK neither deletes them nor reports them in `make diff-kong`. Use Manager to look and compare, and make changes through `kong.yaml` and `make sync-kong`.

**The Admin API** is Kong's loopback API (`127.0.0.1:8001`), reached only through the `/admin-api` route. It needs your ID token (or the proxy), plus the admin key in `Authorization`. The admin key is in `agw-kong-admin-key`; read it into a variable, never onto the command line:

```bash
A="$(gcloud secrets versions access latest --secret agw-kong-admin-key --project my-gcp-project)"
```

`make ui-kong` runs `gcloud run services proxy` on `http://localhost:4000`. The proxy adds your ID token without touching `Authorization`, so the Kong key passes through (checked 2026-10-28). With the proxy running:

```bash
curl -s -H @<(printf "Authorization: Bearer $A\n") http://localhost:4000/admin-api/status     # database reachable, connections
curl -s -H @<(printf "Authorization: Bearer $A\n") http://localhost:4000/admin-api/services   # also routes, plugins, consumers
```

Without the proxy, call the service URL and add `X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token)` in the same `printf`. The model routes work the same way, with a caller key instead of the admin key.

**Credentials come back in clear.** `GET /admin-api/key-auths` and `/admin-api/consumers/<name>/key-auth` return every key as plaintext `Bearer <key>` (checked 2026-10-28). OSS Kong stores credentials unencrypted; the encrypted `key-auth-enc` is enterprise. Never print those responses, or anything that includes them, into a terminal or a shared file. Filter the `key` field out first (`jq 'del(.data[].key)'`).

**Changes go through decK**, not hand-made Admin API calls. decK deletes any `agw`-tagged entity the file doesn't declare, and `make diff-kong` reports a hand-made change as drift. Throwaway test keys (tests 3, 5, 6) are the exception: their scripts create them through the Admin API without the `agw` tag, so decK leaves them alone, and delete them on exit (ADR 0015).

## Cost

| What | Billed when |
| --- | --- |
| Cloud SQL `db-f1-micro` | While running. Stop it with `make stop-kong` between sessions |
| Cloud Run instance time | While an instance is up (CPU always allocated, min 0, max 1) |
| Model calls | Per call |

The network (Direct VPC egress and private services access) has no running cost. Note that through Kong, Gemini thinks at its default level, which uses most of the 256-token cap and is billed (NOTES.md).
