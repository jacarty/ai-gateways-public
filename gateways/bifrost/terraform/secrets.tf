# Secrets the gateway reads at start. Names start with agw-bifrost-, the only
# secrets this gateway's service account can read (foundation's conditional
# binding).
#
# Values are generated here, so they also sit in this stack's Terraform state
# (the private state bucket). Read one with:
#   gcloud secrets versions access latest --secret agw-bifrost-admin-password --project my-gcp-project

locals {
  config_path = "${path.module}/../config/config.json"

  # Secret name => the environment variable config.json reads it from (env.NAME).
  secret_env = {
    "agw-bifrost-admin-password" = "BIFROST_ADMIN_PASSWORD"
    # Only needed until an admin account exists; config.json creates one at start,
    # so this is a backstop that keeps /api closed if that ever fails.
    "agw-bifrost-setup-token" = "BIFROST_SETUP_TOKEN"
    # Encrypts the credentials Bifrost stores in Postgres; it can't change while
    # the database lives (no prevent_destroy: both go at phase end).
    "agw-bifrost-encryption-key" = "BIFROST_ENCRYPTION_KEY"
    "agw-bifrost-db-password"    = "AGW_DB_PASSWORD"
    # One virtual key per caller, so spend, limits and logs are attributed to the
    # agent and the harness separately. Bifrost reads each key's value from its
    # virtual_keys entry in config.json; values must start with sk-bf-, or Bifrost
    # silently generates a different one.
    "agw-bifrost-agent-key"   = "AGW_BIFROST_AGENT_KEY"
    "agw-bifrost-harness-key" = "AGW_BIFROST_HARNESS_KEY"
  }

  secrets = {
    "agw-bifrost-admin-password" = random_password.admin.result
    "agw-bifrost-setup-token"    = random_password.setup_token.result
    "agw-bifrost-encryption-key" = random_password.encryption_key.result
    "agw-bifrost-db-password"    = random_password.db.result
    "agw-bifrost-agent-key"      = "sk-bf-${random_password.caller_key["agent"].result}"
    "agw-bifrost-harness-key"    = "sk-bf-${random_password.caller_key["harness"].result}"
    # Not secret, but a secret volume is the simplest way to mount a file on Cloud Run.
    "agw-bifrost-config" = file(local.config_path)
  }

  callers = {
    agent   = "agw-agent"
    harness = "agw-harness"
  }
}

resource "random_password" "admin" {
  length  = 32
  special = false
}

resource "random_password" "setup_token" {
  length  = 40
  special = false
}

resource "random_password" "encryption_key" {
  length  = 40
  special = false
}

resource "random_password" "caller_key" {
  for_each = local.callers

  length  = 40
  special = false
}

resource "google_secret_manager_secret" "this" {
  # Listed by name: keys(local.secrets) would inherit the values' sensitivity,
  # which for_each rejects.
  for_each = toset([
    "agw-bifrost-admin-password",
    "agw-bifrost-setup-token",
    "agw-bifrost-encryption-key",
    "agw-bifrost-db-password",
    "agw-bifrost-agent-key",
    "agw-bifrost-harness-key",
    "agw-bifrost-config",
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

  secret_id = google_secret_manager_secret.this["agw-bifrost-${each.key}-key"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = data.google_service_account.caller[each.key].member
}
