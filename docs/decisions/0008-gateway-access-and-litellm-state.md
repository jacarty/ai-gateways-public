# 0008. Gateway access and LiteLLM state

- Status: Accepted
- Date: 2026-10-17

## Context

Phase 1 deploys LiteLLM on Cloud Run. Four choices were not settled in the plan: how callers and humans reach a gateway, where LiteLLM keeps virtual keys and budgets, whether to adopt LiteLLM's official Terraform module, and how to get an upstream image onto Cloud Run (which cannot pull from ghcr.io). An open question on the agent sending no ID token to a gateway also needed an answer.

## Decision

- **Gateways stay IAM-authenticated.** No `allUsers`: gateway service accounts call the models, so an open URL would be a spend risk. Callers send the ID token in `X-Serverless-Authorization` and the gateway key in `Authorization`. The harness already does this; the agent does it through `agent/src/agw_agent/auth.py`, with its key from an `agw-*` secret (`gateway_api_key_secret`).
- **Postgres on Cloud SQL from the start**, for virtual keys, budgets and spend logs (tests 3 and 6). One small zonal instance (`db-f1-micro`, no replica, no backups), reached through Cloud Run's built-in Cloud SQL connection. It uses password auth, because LiteLLM has no Cloud SQL IAM database auth (a test 5 finding). The password and `DATABASE_URL` are `agw-litellm-*` secrets.
- **Our own minimal Terraform stack, not the official `BerriAI/litellm/google` module.** The module puts `allUsers` behind a global load balancer, adds a read replica on `db-custom-2-7680`, runs min-instances 1, adds Memorystore HA and splits services. That is production shape, costs far more for a lab, and would hide the setup this project exists to learn.
- **Upstream images come through `agw-ghcr`**, an Artifact Registry remote repository proxying ghcr.io, and are deployed by digest (releases at least two weeks old). This is an exception to ADR 0004's build-it-ourselves flow, not a replacement: our own images still use `scripts/build-image.sh`. (Phase 3 adds `agw-dockerhub` for Kong's Docker Hub image, under the same rule.)
- **No IAP and no custom domain.** Humans reach the gateway with `gcloud run services proxy` (`make ui-<gw>`), which adds their ID token. IAP will be explored in a separate demo lab.

## Consequences

- Every caller needs `roles/run.invoker` and must mint ID tokens; the agent mints one from its service account, caches it, refreshes it before expiry and sends it on every call.
- The gateway cannot start while its database is stopped. `make stop-<gw>` / `make start-<gw>` toggle it and Terraform ignores the activation policy.
- Cold starts run migrations (up to about two minutes), so runs need a pre-warm.
- Password and keys sit in Secret Manager and in the stack's Terraform state (private state bucket).
- With one instance and no Redis, LiteLLM rate limits are per instance, so `max_instances` stays 1.
- The stack matches no production deployment; findings describe the OSS gateway, not the module's topology.

## Alternatives considered

- **`allUsers` behind its own key:** simplest for the agent, but anyone with the URL could reach a service that spends on the models.
- **Stateless LiteLLM (no database):** no virtual keys or budgets, so tests 3 and 6 could not run.
- **Official Terraform module:** rejected above as heavy, costly and opaque.
- **Build LiteLLM into our own image:** adds a build for no change to the software; the pull-through gives a digest-pinned upstream image.
- **IAP or a custom domain for the UI:** needs a load balancer and domain for a single-user lab.
