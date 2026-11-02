# 0016. A private network for gateway databases; Kong reaches Postgres by private IP

- Status: Accepted
- Date: 2026-10-25

## Context

Kong's first hand-build on Postgres (ADR 0015) connected through Cloud Run's built-in Cloud SQL socket (`KONG_PG_HOST=unix:/cloudsql/…/.s.PGSQL.5432`). The CLI steps worked: 67 migrations and the admin bootstrap import ran. Kong itself then failed in nginx's `init` phase with `failed to retrieve PostgreSQL server_version_num: host or service not provided`. In `init` and `init_worker`, OpenResty's sockets don't exist, so Kong's Postgres connector falls back to LuaSocket (`kong/db/strategies/postgres/connector.lua:193`), which can't open `unix:` paths. Kong needs TCP.

Google documents two ways for Cloud Run to reach Cloud SQL Postgres: the built-in Unix socket on a public IP, and **TCP to a private IP over Direct VPC egress** or a Serverless VPC Access connector. The Cloud SQL Auth Proxy sidecar is documented for GKE only. Kong documents only `pg_host` / `pg_port` over TCP.

The lab is to run all three gateways side by side after this project, and nothing should accept inbound traffic from the internet.

## Decision

- **`foundation/` owns one private network, `agw-vpc`,** shared by every gateway stack:
  - a regional subnet for Cloud Run's Direct VPC egress (`agw-run-europe-west1`, 10.10.0.0/24, Private Google Access on);
  - a private services access range (`agw-private-services`, 10.20.0.0/20) and its peering, from which Cloud SQL private IPs come.
- **No inbound from the internet, and no internet egress from the network.**
  - The network has no default route.
  - Ingress is denied, explicitly and logged, except from Google's IAP TCP-forwarding range on port 22, for any future admin VM (none exists).
  - Cloud SQL instances on it have **no public IP** (`ipv4_enabled = false`).
- **Kong's instance is private-IP only.** Kong connects over TCP with password auth through Direct VPC egress (`egress = PRIVATE_RANGES_ONLY`), so only database traffic enters the VPC; its model calls leave Cloud Run as before. With no socket or proxy, the gateway's `roles/cloudsql.client` grant is not needed and is dropped.
- **LiteLLM and Bifrost are unchanged** (public-IP instances reached through the built-in socket, which they can use). Moving them onto `agw-vpc` is optional, for when all three run together.
- **The Cloud Run URLs stay as they are:** IAM-authenticated (`roles/run.invoker` plus an ID token), as in ADR 0008. Putting IAP in front of them is deferred.

## Consequences

- One network, one peering and two firewall rules in `foundation/`, at no running cost (Direct VPC egress and private services access are free).
- "No inbound from the internet" covers the network and the databases. The Cloud Run URLs themselves stay public and IAM-gated (`roles/run.invoker` plus an ID token); a leaked Kong admin key together with the invoker role gives control of Kong's config through `/admin-api`. IAP in front of the URLs is the deferred step.
- Every database on `agw-vpc` is reachable on 5432 from any Cloud Run service with egress into the subnet. Today those are only the gateways; each database still has its own user and password.
- The private services peering can only be removed after every instance using it is gone, which only matters if `foundation/` is destroyed.
- Cloud SQL still requires encrypted connections (`ENCRYPTED_ONLY`), so Kong sets `pg_ssl`, and `pg_ssl_verify` is on against the instance's own CA (the `agw-kong-db-ca` secret). Kong's Postgres client checks the chain, not the hostname, so the private IP verifies (confirmed by the first `agw-kong` start, 2026-10-25).

## Alternatives considered

- **Cloud SQL Auth Proxy sidecar** (a second container listening on `127.0.0.1:5432`): less infrastructure, but documented only for GKE, one more image (outside `agw-ghcr` / `agw-dockerhub`) and process per gateway, and Kong must wait for it to start.
- **Public IP with authorised networks:** Cloud Run has no fixed egress IP without more networking, and it would open the database to the internet.
- **A Serverless VPC Access connector:** documented too, but it runs billed connector instances, where Direct VPC egress has no extra cost.
