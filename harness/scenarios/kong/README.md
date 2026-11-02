# Kong scenarios

Scenario files for the Kong phase (tests 2-6), run locally against `agw-kong` with `harness scenarios <file>`, never as the job. Results go to `results/raw/kong/`. Claude goes to Kong in its native Vertex format (`AGW_GATEWAY_CLAUDE_API=anthropic`), so a `claude` case's `body` takes Anthropic keys (`max_tokens`, not `max_completion_tokens`), and its model is in the URL: Kong's native routes match only the model they name.

```bash
cd harness
export AGW_GATEWAY_API_KEY="$(gcloud secrets versions access latest --secret agw-kong-harness-key --project my-gcp-project)"
AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT=my-gcp-project AGW_RESULTS_DIR=../results/raw/kong PYTHONPATH=src \
  AGW_GATEWAY_CLAUDE_API=anthropic \
  AGW_GATEWAY_URL="$(gcloud run services describe agw-kong --project my-gcp-project --region europe-west1 --format='value(status.url)')/v1" \
  uv run python -m agw_harness.cli scenarios scenarios/kong/<file>.json --note "<revision, window>"
unset AGW_GATEWAY_API_KEY
```

## Test windows

Behaviour tests need config the measured runs must not have (ADR 0010). On Kong a window is a decK sync, not a redeploy (ADR 0015): add the window's entities to `gateways/kong/config/kong.yaml`, each with a `# TEST ONLY` comment (the `no-test-window` hook then refuses to commit it), and `make sync-kong`. Kong picks the change up within about 5 s. Never sync during a measured run.

**Closing a window:** `git checkout gateways/kong/config/kong.yaml && make sync-kong && make diff-kong` (the checkout drops every uncommitted change to `kong.yaml`, so open a window only on a clean file) (0 created, 0 updated, 0 deleted). decK deletes every `agw`-tagged entity the committed file doesn't declare, so the window's services and routes go.

## Test 2: `failover.json`

Kong OSS has no failover between models: an `ai-proxy` route is pinned to one model, and the failover plugin (AI Proxy Advanced) is enterprise. The test shows what a caller gets when a model fails, and what Kong's only retry, the service's connection retries (`retries: 5` by default), does. Cases with the committed config alone: a Gemini request naming Claude (400 `cannot use own model`: no routing by model) and a native path for a model with no route (404 `no Route matched`).

The window adds two services to `kong.yaml` before `consumers:`:

```yaml
  # TEST ONLY (test 2 window): remove. A Gemini route chosen by a header, on the
  # measured path, whose model doesn't exist: a real upstream error, no fallback.
  - name: test-gemini-broken
    url: http://localhost:32000
    routes:
      - name: test-gemini-broken
        paths: [/v1/chat/completions]
        methods: [POST]
        headers:
          x-agw-test-route: [gemini-broken]
        strip_path: false
    plugins:
      - name: acl
        config:
          allow: [callers]
          hide_groups_header: true
      - name: ai-proxy
        config:
          route_type: llm/v1/chat
          auth:
            gcp_use_service_account: true
          model:
            provider: gemini
            name: gemini-0-agw-missing
            options:
              max_tokens: 256
              gemini:
                api_endpoint: aiplatform.eu.rep.googleapis.com
                project_id: my-gcp-project
                location_id: eu
          logging:
            log_statistics: true
            log_payloads: false
  # TEST ONLY (test 2 window): remove. Native Claude routes: a model Vertex doesn't
  # have (its 404 passed through) and an upstream that refuses the connection
  # (Kong's retries to the same target).
  - name: test-claude-broken
    url: http://localhost:32000
    routes:
      - name: test-claude-broken
        paths: [/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/test-claude-broken:rawPredict]
        methods: [POST]
        strip_path: false
        plugins:
          - name: ai-proxy
            config:
              route_type: preserve
              auth:
                gcp_use_service_account: true
              model:
                provider: gemini
                name: test-claude-broken
                options:
                  upstream_url: https://aiplatform.eu.rep.googleapis.com/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/test-claude-broken:rawPredict
              logging:
                log_statistics: false
                log_payloads: false
      - name: test-claude-broken-stream
        paths: [/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/test-claude-broken:streamRawPredict]
        methods: [POST]
        strip_path: false
        plugins:
          - name: ai-proxy
            config:
              route_type: preserve
              auth:
                gcp_use_service_account: true
              model:
                provider: gemini
                name: test-claude-broken
                options:
                  upstream_url: https://aiplatform.eu.rep.googleapis.com/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/test-claude-broken:streamRawPredict
              logging:
                log_statistics: false
                log_payloads: false
      - name: test-claude-unreachable
        paths: [/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/test-claude-unreachable:rawPredict]
        methods: [POST]
        strip_path: false
        plugins:
          - name: ai-proxy
            config:
              route_type: preserve
              auth:
                gcp_use_service_account: true
              model:
                provider: gemini
                name: test-claude-unreachable
                options:
                  upstream_url: http://127.0.0.1:9/
              logging:
                log_statistics: false
                log_payloads: false
    plugins:
      - name: acl
        config:
          allow: [callers]
          hide_groups_header: true
```

- **The measured routes are untouched.** The Gemini test route shares `/v1/chat/completions` but matches only requests carrying `x-agw-test-route: gemini-broken` (Kong prefers the route with more matching attributes), which no caller but this file sends. The Claude test routes are paths of their own.
- **In `preserve` mode Kong sends the request's own path** (`override_upstream_url` in `kong/llm/drivers/shared.lua`), so `upstream_url` sets only the host; a test route's path must name its own model.
- **Retries are read from Kong's log.** After the run, save the run's rows, joined by `x-kong-request-id`, next to the results as `kong-log.json`, with a `gcloud logging read --format=json(...)` projection of `timestamp` and `jsonPayload`'s `request.id`, `request.method`, `route.name`, `service.name`, `consumer.username`, `response.status`, `upstream_status`, `latencies`, `tries` and `ai` (no headers; the notebook's log cell prints a subset).

## Test 3: `cost-*.json` via `run-cost.sh`

Kong OSS limits **requests**, not tokens or spend: `rate-limiting` counts requests per second to year, and token limits (`ai-rate-limiting-advanced`) are enterprise. Cost is only logged, from the prices in `kong.yaml`, for the translated Gemini route. So test 3 needs no config window. Each run gets a throwaway consumer made through `/admin-api` with that run's limit, an ACL group (`callers`) and a key with a one-hour `ttl`, all tagged `agw-throwaway` (not `agw`, so decK neither manages nor reports them; `make diff-kong` stays 0/0/0). The key is held only in variables and the harness's environment, and the consumer is deleted on exit, which deletes its key, ACL group and plugins. After the run, Kong's log rows for its requests are saved as `kong-log.json` next to the results (the projection in the script; no headers).

```bash
harness/scenarios/kong/run-cost.sh <rpm|race|model-limit|caps> ["note"]
```

| Run | The consumer's limit | What it shows |
| --- | --- | --- |
| `rpm` | 3 requests a minute (`rate-limiting` on the consumer) | 429 once 3 have been admitted, for either model; admitted again in the next minute |
| `race` | 3 requests a minute, ten sent at once | how many of a burst get through: Kong checks the count on arrival and adds to it in a timer (`rate-limiting/handler.lua`) |
| `model-limit` | 1 request a minute on the Gemini route only (a plugin on the consumer and `gemini-chat`) | a per-model request limit: Gemini refused, Claude still answering |
| `caps` | none | per-request token caps: Gemini's comes from `kong.yaml` and overrides the caller's; Claude's native `max_tokens` passes through as sent |

Kong's rate-limiting windows are clock minutes, not a sliding window, so `run-cost.sh` waits for a minute to turn before it runs the cases (a run takes up to about 3 minutes: up to a minute's wait, `rpm`'s 65 s pause and up to a minute reading Kong's log). The plugins use Kong's default `local` policy, counted in a shared dictionary all of the instance's nginx workers use; with one instance that is the whole count, but the count is lost on a restart.

## Test 4: `screening.json`

The shared case set (`../screening-cases.json`, 18 cases) on both models, 36 requests, with the harness's own Kong key, as on LiteLLM and Bifrost. Run it three times and say which in `--note`: **A** with the committed config, **B** with the `ai-prompt-guard` window, **C** with the `ai-request-transformer` window. Open one window at a time, on a clean `kong.yaml`, and close each before the next.

Kong OSS has no PII or injection detector (`ai-sanitizer`, `ai-semantic-prompt-guard` and the third-party guardrails are enterprise). What OSS has, from the 3.9 source:

- **`ai-prompt-guard`** (window B): regex allow and deny lists, at most 10 patterns of up to 500 characters, matched against the user messages only (all roles with `match_all_roles`; never the answer). A match is a 400 `{"error":{"message":"bad request"}}`, which doesn't say a guard is in use; the harness classes it `blocked`. It can't mask. The guard sends the same 400 when it can't read the prompt at all (a body over its `max_request_body_size`, 8 KiB by default, or non-string `content`), and Kong's 400 for a request naming the wrong model also classes `blocked`, so a `blocked` count needs the `bad request` bodies and the right request sizes to mean a pattern matched. In window C a failed rewrite is a 400 carrying the transformer's error, also classed `blocked` (none in run C).
- **`ai-request-transformer`** (window C): sends the whole request body to an LLM with an instruction and forwards the LLM's output as the new body. It runs before `ai-proxy` (priority 777 against 770), so it could mask PII in a prompt, at the cost of an extra model call on every request. From the source: the transformer replaces nginx's request body (`kong.service.request.set_raw_body`, `ngx.req.set_body_data`), and `ai-proxy`'s `parse-request.lua` then reads that body, so the rewrite is what `ai-proxy` translates and sends. But once the transformer has run, Kong skips translating the response back (`normalize-json-response.lua:72`), so on the translated **Gemini** route an OpenAI caller gets Vertex's native body. On Claude's **`preserve`** route nothing needs translating, so the rewrite is what Vertex gets and the answer comes back as sent. (Run C: Claude masked, Gemini unreadable; `results/summary.md`.) Its own LLM call goes to Gemini at its default thinking level, so its `max_tokens` is set well above 256.
- **`ai-response-transformer`** is not tested: it runs after `ai-proxy` (priority 768) and makes the upstream call itself (`transform-response.lua`, `subrequest`), with the request as `ai-proxy` left it and all the caller's remaining headers (`key-auth`'s `hide_credentials` has already removed the Kong key), then sends the answer to its own LLM: two model calls per request, and every answer copied to a second model.

**Window B:** add this entry at the end of both the `gemini` service's and the `claude` service's `plugins:` lists in `gateways/kong/config/kong.yaml` (service plugins cover all of a service's routes, streaming included), then `make sync-kong`:

```yaml
      # TEST ONLY (test 4 window B): remove. A regex deny list on the user's messages.
      - name: ai-prompt-guard
        config:
          deny_patterns:
            - '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
            - '\b07\d{3} ?\d{6}\b'
            - '\b(?:\d{4}[ -]?){3}\d{4}\b'
            - '\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b'
            - '\b[A-Z]{2} ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b'
            - '\b\d{3}-\d{2}-\d{4}\b'
            - '(?i)\bignore (all |any |your |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)'
            - '(?i)developer mode|\bDAN\b|do anything now|no restrictions'
            - '(?i)system prompt|hidden instructions|system note'
            - '(?i)markdown image|url-?encode'
```

The patterns are, in order: email, UK mobile, payment card, IBAN, UK National Insurance number, US SSN, and four injection phrasings. They were written with the case set in view, so run B shows how the plugin behaves, not a detection rate: what a deny list can't see (an encoded injection, PII in the answer) is the finding.

**Window C:** add this entry at the same two places instead, then `make sync-kong`:

```yaml
      # TEST ONLY (test 4 window C): remove. An LLM rewrites each request body with
      # personal data replaced, before ai-proxy (one extra Gemini call per request).
      - name: ai-request-transformer
        config:
          prompt: >-
            You are a privacy filter. The user message is the JSON body of a request to an
            LLM API. Return exactly the same JSON, changing only the text of the messages:
            replace every piece of personal data (email addresses, phone numbers, payment
            card numbers, IBANs, National Insurance numbers, Social Security numbers) with
            [REDACTED]. Keep every other field and value as it is. Output only the JSON
            object, with no code fences or commentary.
          transformation_extract_pattern: '(?s)\{.*\}'
          llm:
            route_type: llm/v1/chat
            auth:
              gcp_use_service_account: true
            model:
              provider: gemini
              name: gemini-3.8-flash
              options:
                max_tokens: 2048
                input_cost: 1.65
                output_cost: 8.25
                gemini:
                  api_endpoint: aiplatform.eu.rep.googleapis.com
                  project_id: my-gcp-project
                  location_id: eu
            logging:
              log_statistics: true
              log_payloads: false
```

Try window C by hand first (the notebook's "Test 4", window C cells: two or three requests) and record run C only if the transformer works on at least one route; otherwise the by-hand result is the finding.

## Test 5: `auth.json`, through `run-auth.sh`

Which layer stops which credential problem, as on LiteLLM and Bifrost: Cloud Run IAM checks the Google ID token (`X-Serverless-Authorization`; refusals are HTML), then Kong's `key-auth` checks the key (`Authorization: Bearer <key>`; the credential is the literal string, ADR 0014) and `acl` the consumer's group (refusals are JSON). No config window: like `run-cost.sh`, `run-auth.sh` makes throwaway consumers through `/admin-api`, tagged `agw-throwaway` so decK ignores them, with a one-hour key `ttl`, and deletes them on exit:

| Consumer | Key state | Expected (from the source) |
| --- | --- | --- |
| `valid` | the run's own key (never the harness's) | 200 |
| `claude-only` | a `request-termination` plugin scoped to it and the `gemini` service: Kong OSS has no per-key model list | Gemini 403 with the plugin's message, before any model call; Claude 200 |
| `no-group` | valid, but in no group the chat services allow | 403 `You cannot consume this service` |
| `expired` | `ttl` 15 s, used once while valid, then left to lapse | 401 `Unauthorized` |
| `deleted` | used once, then its credential deleted | 401 `Unauthorized` |
| `rotated` | rotation as Kong OSS does it: a second key added, then the first deleted | old value 401, new value 200 |

Plus the layer cases (no credentials: Cloud Run 403; a key without an ID token: Cloud Run 401; an ID token without a key: 401 `No API key found in request`), a made-up unknown key (401 `Unauthorized`, which must not echo it) and the agent's own key sent by the harness (200: a key is a bearer secret). The expired, deleted and rotated-away keys are each used once on `/admin-api` before they lapse (403 there: authenticated, but not an admin; no model call), so Kong has them in its cache and the run shows a lapsed key leaves the cache, not just the database. Four Claude calls in all; the rest are refused before any model call. About a minute.

```bash
harness/scenarios/kong/run-auth.sh "revision <rev>, committed config"
```

Read-only checks to go with it (no model call): the gateway's service account and its keys (`gcloud iam service-accounts keys list --iam-account agw-gw-kong@my-gcp-project.iam.gserviceaccount.com --managed-by user`), which env vars on `agw-kong` are secret references (`gcloud run services describe agw-kong --project my-gcp-project --region europe-west1 --format=json`, printing names only), and who can read each `agw-kong-*` secret. Never print a secret's value, and never display `/key-auths` output: Kong stores and returns keys in clear.

### The echo window: what Kong forwards upstream

Which caller headers reach the model can't be seen from outside. This window points copies of the two chat routes at a loopback sink inside Kong, so the sink gets what Kong sends upstream through the same plugins and proxy settings (only `Host` and the path differ from a real Vertex call), and answers with header **names** only (plus the kind of `Authorization` and the segment lengths of `X-Serverless-Authorization`), in Gemini's response shape so both routes can read it. No model is called. Add the first route at the end of the `gemini` service's `routes:` list, the second at the end of the `claude` service's `routes:` list, and the sink as a service before `consumers:`; then `make sync-kong`, send one request to each route (`/v1/agw-echo/chat/completions` and `.../models/agw-echo:rawPredict`) with a throwaway consumer's key, and close the window as for test 4. The recorded run used a one-off script (not committed) that made the consumer through `/admin-api`, sent both requests with the ID token, the key and an extra `X-Agw-Probe` header, and deleted the consumer; any client that does the same will do. The recorded run is `results/raw/kong/*-echo-upstream-headers/`.

```yaml
      # TEST ONLY (test 5 echo window): remove. Gemini, translated, sent to the loopback sink.
      - name: gemini-echo
        paths: [/v1/agw-echo/chat/completions]
        methods: [POST]
        strip_path: false
        plugins:
          - name: ai-proxy
            config:
              route_type: llm/v1/chat
              auth:
                gcp_use_service_account: true
              model:
                provider: gemini
                name: gemini-3.8-flash
                options:
                  max_tokens: 256
                  upstream_url: http://127.0.0.1:8080/agw-echo-sink/gemini
              logging:
                log_statistics: false
                log_payloads: false

      # TEST ONLY (test 5 echo window): remove. Claude, preserve, sent to the loopback sink.
      - name: claude-echo
        paths: [/v1/projects/my-gcp-project/locations/eu/publishers/anthropic/models/agw-echo:rawPredict]
        methods: [POST]
        strip_path: false
        plugins:
          - name: ai-proxy
            config:
              route_type: preserve
              auth:
                gcp_use_service_account: true
              model:
                provider: gemini
                name: agw-echo
                options:
                  upstream_url: http://127.0.0.1:8080/
              logging:
                log_statistics: false
                log_payloads: false

  # TEST ONLY (test 5 echo window): remove. The loopback sink: matches only requests Kong
  # itself sends to 127.0.0.1, and answers before any auth plugin (pre-function runs first)
  # with what reached it: header names, the kind of Authorization and the segment lengths of
  # X-Serverless-Authorization, never a value. Gemini's response shape, so both routes read it.
  - name: echo-sink
    url: http://localhost:32000
    routes:
      - name: echo-sink
        hosts: ["127.0.0.1"]
        paths: [/]
        plugins:
          - name: pre-function
            config:
              access:
                - |
                  local h = kong.request.get_headers()
                  local names = {}
                  for k in pairs(h) do names[#names + 1] = k end
                  table.sort(names)
                  local auth = h["authorization"]
                  local kind = "none"
                  if type(auth) == "string" then
                    if auth:match("^Bearer ya29%.") then
                      kind = "Bearer + a Google access token"
                    else
                      kind = (auth:match("^(%S+)") or "?") .. " + something else"
                    end
                  end
                  local xsa = h["x-serverless-authorization"]
                  local segs = "absent"
                  if type(xsa) == "string" then
                    local t = {}
                    for s in xsa:gsub("^%s*[Bb]earer%s+", ""):gmatch("[^.]+") do t[#t + 1] = tostring(#s) end
                    segs = table.concat(t, ".")
                  end
                  local text = "path " .. kong.request.get_path() .. " | headers: " .. table.concat(names, ", ")
                    .. " | authorization: " .. kind .. " | x-serverless-authorization segment lengths: " .. segs
                  return kong.response.exit(200, {
                    candidates = { { content = { role = "model", parts = { { text = text } } }, finishReason = "STOP" } },
                    usageMetadata = { promptTokenCount = 1, candidatesTokenCount = 1, totalTokenCount = 2 },
                  })
```

## Test 6: `audit.json`, through `run-audit.sh`

Whether the logs can reconstruct one agent run. Kong keeps no request store: its record is `file-log`'s JSON line per request on stdout, in Cloud Logging, next to Cloud Run's own request log (Kong's nginx access logs go to stdout too, as plain lines). A row has the request id Kong returns to the caller (`X-Kong-Request-Id`), the consumer, route, service, status, latencies, `ai-proxy`'s statistics (Gemini only: the Claude routes have `log_statistics: false`), and **every request header** (the caller's key is already removed by `hide_credentials`; Kong's serializer redacts `Authorization`, which on model rows holds Kong's own Google token; `kong.yaml` writes `X-Serverless-Authorization` as `REDACTED` on every row), so a cooperating caller can tag requests with headers of its own, and the row keeps Cloud Run's `X-Cloud-Trace-Context`, which joins it to Cloud Run's request-log entry by trace id, not by time.

`run-audit.sh` sends `audit.json` with the harness's own key (test 6 audits the real callers' trail, AGENTS.md): five requests tagged `x-agw-session` / `x-agw-case` (Claude, Gemini, a Claude stream, a Gemini request Kong refuses with 400, a Claude path with no route, 404) and one untagged; then one request through `agw-agent` as it is (it tags nothing; the script checks the agent points at Kong first); then makes and deletes one throwaway consumer through `/admin-api` (Kong OSS has no admin audit log: what does the request log show instead?). `audit_trail.py` then reads the window's Kong rows and Cloud Run logs (gateway and agent) and writes `trail.json` and `trail.md` into the run directory: header names, and the values of only the user agent, the caller's `x-agw-*` tags and trace ids; content only as flags; and a scan of every row for a token or key. The 404 (no route) is logged too, but before routing and authentication, so its row has no route, service or consumer: only the caller's tag and user agent say whose it was. Six model calls at most (four gateway, one or two by the agent). About two minutes, half of it waiting for Cloud Logging.

```bash
harness/scenarios/kong/run-audit.sh "run A: committed config"
```

**Run A:** the committed config (`log_payloads: false` everywhere): no content in the log.

**Window B, content logged:** set `logging.log_payloads: true` on the `gemini` service's `ai-proxy` and, on both Claude routes' `ai-proxy`, `log_statistics: true` and `log_payloads: true` (`serialize-analytics.lua` writes payloads only when statistics are on). Each line gets a `# TEST ONLY (test 6 window B)` comment. `make sync-kong`, run `run-audit.sh "run B: log_payloads window"`, then close the window as for test 4. Kong then writes the request body it sends upstream and the response into each row, so prompts and answers sit in Cloud Logging for the log bucket's retention (`_Default`, 30 days). Check the streamed Claude row in run B: on a `preserve` stream Kong may not collect the response body (`parse-sse-chunk.lua`). The run's prompts are synthetic (the marker and a capital city), so nothing needs deleting afterwards; no credential is in a body.

## Test 7: `probe-ceiling.sh`

The OSS ceiling is mostly a write-up of tests 1-6 (`results/summary.md`, Kong "Test 7"). The probe asks the running gateway, read-only, how it answers for the enterprise features they needed (plus `ai-semantic-cache`): `GET /plugins/enabled`; `POST /schemas/plugins/validate` for each enterprise plugin (validation only, nothing stored), with `rate-limiting` as an OSS control; `POST /schemas/vaults/validate` for the GCP vault, with the `env` vault as a control; and `GET` on the enterprise Admin API routes (audit log, RBAC, workspaces, licences). No model call. It writes `probe.json` into a new `results/raw/kong/<time>-oss-ceiling-probe/` directory.

```bash
harness/scenarios/kong/probe-ceiling.sh
```
