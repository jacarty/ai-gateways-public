# 0017. Kong's audit trail is collected from Cloud Logging and joined by trace

- Status: Accepted
- Date: 2026-11-01

## Context

ADR 0012 built test 6's collector around LiteLLM's spend log, a table in the gateway's own database, and said a later gateway would reuse the method and the redactions but not the code. Kong keeps no request store. Its record is the `file-log` line it writes to stdout for every request, which Cloud Run ships to Cloud Logging next to its own request log. Kong's `file-log` also keeps every request header by default, including the caller's Google ID token (`X-Serverless-Authorization`, claims readable, signature replaced by Cloud Run), and Cloud Logging keeps the rows for 30 days.

## Decision

- **Collect from Cloud Logging only.** `harness/scenarios/kong/audit_trail.py` reads Kong's rows and Cloud Run's request logs for the run's time window with `gcloud logging read`. There is no Admin API or database read, so the collector sees what an operator with only log access sees.
- **Join by id, then by trace.** A row joins its request by the `X-Kong-Request-Id` Kong returned (the row's `request.id`), else by the caller's own `x-agw-case` tag. A row joins Cloud Run's request-log entry by the trace id in the `X-Cloud-Trace-Context` header Cloud Run added, which the row keeps. The agent's call joins by consumer and time only, because its `traceparent` is a new trace.
- **Keep the ID token out by config, not by the collector.** `kong.yaml` overwrites `X-Serverless-Authorization` with `REDACTED` in `file-log`, so no token is ever written to Cloud Logging. Kong's serializer already redacts `Authorization`. The collector still runs the shared redaction before committing anything (`trail.py`, ADR 0012), and commits content as flags.
- **Run two configs, as in ADR 0010:** A (committed) and B (`log_payloads` on, a decK window), so the finding covers the default and what a switch changes. Admin changes are probed with a throwaway consumer made and deleted through `/admin-api` (ADR 0015).

## Consequences

- The join to Cloud Run is exact, as LiteLLM's was and Bifrost's (by time) was not. The cost is a dependency on a Cloud Logging sink that works and a 30-day window: rows are read soon after the run and the evidence is committed redacted.
- Redacting by config means a changed or reverted `kong.yaml` would start logging ID tokens again; `make diff-kong` after every window is the check.
- With `log_payloads` on, prompts and answers sit in Cloud Logging for its retention, outside anything Kong can delete. The window is closed straight after run B.
- The trail shows what an honest caller leaves; a hostile one isn't tested (as in ADR 0012).

## Alternatives considered

- **Copy LiteLLM's collector and read a Kong database table:** Kong OSS has no request table, only configuration in Postgres.
- **Commit raw log exports:** richest, but puts ID tokens (if redaction failed) and callers' tags in git.
- **Add a custom log field with the ID token's email claim (`custom_fields_by_lua`):** would put a Google identity on every row without storing a token, but changes the gateway under test beyond the committed config. Noted in the results as an untried OSS route.
