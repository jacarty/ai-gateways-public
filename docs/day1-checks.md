# Day-1 checks

Research done Oct 12, 2026, before any build work. Sources are linked inline. Vendor and third-party claims about OSS editions are hypotheses until confirmed hands-on, and the OSS-ceiling column in `results/summary.md` records what was actually found.

## Outcome

- **Region:** `europe-west1` (Belgium) for all deployed resources.
- **Claude:** Claude Haiku 5.5 via the EU multi-region endpoint.
- **Scope:** three OSS gateways. Gemini Agent Gateway and Model Armor are moved to a separate project (reasons below).

## Region and models

| Check | Finding | Source |
| --- | --- | --- |
| Claude Haiku 4.5 regions | `us-east5`, `europe-west1`, global only; no `europe-west2`. Retirement "not sooner than Oct 15, 2026". | [Haiku 4.5](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/haiku-4-5) |
| Claude Haiku 5.5 regions | GA Oct 7, 2026. US multi-region, EU multi-region and global endpoints only; no single-region endpoints. Multi-region quota listed as 1,500 QPM, 15M input TPM, 1.5M output TPM. | [Haiku 5.5](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/haiku-5-5), [Claude on Google Cloud](https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai) |
| Gemini Flash in `europe-west2` | Unreliable: residency table says yes, forum reports of 404s and support saying not rolled out. Moot after moving to `europe-west1`. | [Data residency](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency), [forum](https://discuss.google.dev/t/404-issue-with-vertex-ai-gemini-2-5-flash-and-europe-west2/193847) |
| Gemini 3.8 Flash regions | `gemini-3.8-flash`, GA Sep 2, 2026. Global, and `us`/`eu` multi-region only: no `europe-west1`. Both models therefore use `GOOGLE_CLOUD_LOCATION=eu` (host `aiplatform.eu.rep.googleapis.com`); google-genai and the Anthropic Vertex SDK both map `eu` to that host. | [Gemini 3.8 Flash](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash) |
| Product names | Vertex AI is now Gemini Enterprise Agent Platform; Vertex AI Agent Engine is now Agent Runtime. Terraform resources keep `google_vertex_ai_*` names. | [Name changes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes) |

## OSS edition contents (first pass)

| Gateway | Free / OSS | Paid only |
| --- | --- | --- |
| LiteLLM | Proxy, virtual keys, budgets and rate limits, routing and fallback, logging callbacks | Audit logs, most built-in guardrails (Lakera, LlamaGuard, secret masking, etc.), secret managers, SSO/JWT, per-team logging |
| Bifrost (Apache 2.0) | Routing, fallbacks, virtual keys, budgets, caching, OpenTelemetry, custom plugins | Guardrails, adaptive load balancing, clustering, secret manager, audit logs, SSO/RBAC |
| Kong OSS | AI Proxy (with streaming), AI Prompt Guard / Template / Decorator | AI Proxy Advanced (load balancing, failover), AI Rate Limiting Advanced (token limits), PII Sanitizer, Semantic Prompt Guard, GCP Model Armor plugin |

Sources: [LiteLLM Enterprise](https://docs.litellm.ai/docs/enterprise), [Bifrost pricing](https://www.getmaxim.ai/bifrost/pricing.md), [innFactory on Bifrost](https://innfactory.ai/en/services/ai-gateway/vs/bifrost/), [Kong AI plugins](https://developer.konghq.com/plugins/?category=ai), [Kong AI Proxy](https://developer.konghq.com/plugins/ai-proxy/), [innFactory on Kong](https://innfactory.ai/en/services/ai-gateway/vs/kong-ai-gateway/).

**Expected OSS-ceiling hot spots:** test 4 (screening) for all three; tests 2 and 3 for Kong.

## Still open (needs the project console)

- [x] Claude Haiku 5.5 enabled in Model Garden (Oct 13, 2026).
- [x] Claude Haiku 5.5 quota on the EU multi-region endpoint: the deployed agent's first `claude` call answered (Oct 13, 2026).
- [x] Gemini Flash call: `gemini-3.8-flash` answered on the `eu` multi-region endpoint from `my-gcp-project` (Oct 13, 2026). It has no `europe-west1` endpoint; see below.
- [x] Kong OSS AI Proxy can reach Claude on the Agent Platform: **not by translation** (checked in the 3.9.3 source, 2026-10-24). The `gemini` provider's Vertex path is fixed to `publishers/google`, and the `anthropic` provider has no GCP identity and the wrong body shape for Vertex; Vertex's OpenAI-compatible endpoint doesn't serve Claude in `eu` (probe: 400 "not servable in region eu"). Claude goes through Kong as a native `rawPredict` pass-through (`route_type: preserve`), with Kong's GCP token; see `gateways/kong/NOTES.md`.
- [x] Confirm the LiteLLM / Bifrost / Kong OSS splits above against each project's own source and licence files (in each gateway's Understand step). LiteLLM done (Phase 1, test 7 in `results/summary.md`): right about audit logs and SSO/JWT; wrong about guardrails, whose built-in kinds are OSS (only per-key selection and the legacy moderation callbacks are gated). Bifrost checked against the source at `transports/v2.2.6` (Phase 2 Understand, `gateways/bifrost/NOTES.md`): right; the enterprise edition is a separate closed build, and the OSS source also leaves out circuit breaker, alerting, projects, SCIM and log exporters, while manual virtual-key rotation and per-model budgets are OSS. Confirmed live in Phase 2's tests (test 7 in `results/summary.md`): a configured guardrail is silently ignored, and enterprise API routes answer with the UI page. Kong checked against the 3.9.3 and 3.9.4 source (Phase 3 Understand, `gateways/kong/NOTES.md`) and live (Phase 3 test 7): right on every item; the source adds `rate-limiting-advanced` (sliding windows), `ai-semantic-cache`, `openid-connect`, `jwt-signer`, `key-auth-enc`, the GCP vault, the admin audit log, RBAC and workspaces to the enterprise side, Kafka log export to the enterprise side, and `ai-request-transformer`'s LLM rewrite and the bundled log exporters to the OSS side. Its plugin gates are loud: an enterprise plugin fails validation by name; an enterprise route is a plain 404.
