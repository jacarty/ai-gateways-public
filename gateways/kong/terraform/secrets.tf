# Secrets for Kong and its callers. Names start with agw-kong-, the only secrets
# this gateway's service account can read (foundation's conditional binding).
#
# Values are generated here, so they also sit in this stack's Terraform state
# (the private state bucket). Read one with:
#   gcloud secrets versions access latest --secret agw-kong-admin-key --project my-gcp-project
#
# Key secrets hold the bare key, which callers send as `Authorization: Bearer <key>`
# (the OpenAI and Anthropic clients add "Bearer "). Kong's key-auth compares the
# whole header, so each credential in config/kong.yaml is the literal "Bearer <key>"
# (ADR 0014).

locals {
  secrets = {
    "agw-kong-db-password" = random_password.db.result
    # The admin consumer: the startup wrapper imports it with the Admin API route,
    # and decK and the test scripts use it.
    "agw-kong-admin-key"   = random_password.key["admin"].result
    "agw-kong-agent-key"   = random_password.key["agent"].result
    "agw-kong-harness-key" = random_password.key["harness"].result
    # Kong Manager login (user "admin", basic-auth), like LiteLLM's and Bifrost's UIs.
    "agw-kong-manager-password" = random_password.manager.result
    # Not secret, but a secret volume is the simplest way to mount a file on Cloud
    # Run: the startup wrapper and the admin bootstrap it imports (ADR 0015).
    "agw-kong-start"     = file("${path.module}/../config/start.sh")
    "agw-kong-bootstrap" = file("${path.module}/../config/bootstrap.yaml")
    # The instance's own CA (per-instance, Google-managed), so Kong verifies Postgres.
    "agw-kong-db-ca" = google_sql_database_instance.kong.server_ca_cert[0].cert
  }

  callers = {
    agent   = "agw-agent"
    harness = "agw-harness"
  }
}

resource "random_password" "manager" {
  length  = 32
  special = false
}

resource "random_password" "key" {
  for_each = toset(["admin", "agent", "harness"])

  length  = 40
  special = false
}

resource "google_secret_manager_secret" "this" {
  # Listed by name: keys(local.secrets) would inherit the values' sensitivity,
  # which for_each rejects.
  for_each = toset([
    "agw-kong-db-password",
    "agw-kong-admin-key",
    "agw-kong-agent-key",
    "agw-kong-harness-key",
    "agw-kong-manager-password",
    "agw-kong-start",
    "agw-kong-bootstrap",
    "agw-kong-db-ca",
  ])

  secret_id = each.value

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "this" {
  for_each = google_secret_manager_secret.this

  secret      = each.value.id
  secret_data = local.secrets[each.key]

  # The running revision is pinned to the current version: create its
  # replacement first, so cold starts never meet a deleted version.
  lifecycle {
    create_before_destroy = true
  }
}

data "google_service_account" "caller" {
  for_each = local.callers

  account_id = each.value
}

# Each caller reads only its own key (the agent's gateway_api_key_secret, the
# harness job's gateway_api_key_secret).
resource "google_secret_manager_secret_iam_member" "caller_key_reader" {
  for_each = local.callers

  secret_id = google_secret_manager_secret.this["agw-kong-${each.key}-key"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = data.google_service_account.caller[each.key].member
}
