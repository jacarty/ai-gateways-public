# Secrets the gateway reads at start. Names start with agw-litellm-, the only
# secrets this gateway's service account can read (foundation's conditional
# binding).
#
# Values are generated here, so they also sit in this stack's Terraform state
# (the private state bucket). Read one with:
#   gcloud secrets versions access latest --secret agw-litellm-master-key --project my-gcp-project

locals {
  config_path = "${path.module}/../config/config.yaml"

  secrets = {
    # Admin key: UI login (user "admin") and minting virtual keys.
    "agw-litellm-master-key" = "sk-${random_password.master_key.result}"
    # Encrypts provider credentials LiteLLM stores in the database, so it must not
    # change while the database lives (no prevent_destroy: both go at phase end).
    "agw-litellm-salt-key" = random_password.salt_key.result
    "agw-litellm-database-url" = join("", [
      "postgresql://${google_sql_user.litellm.name}:${random_password.db.result}",
      "@localhost/${google_sql_database.litellm.name}",
      "?host=/cloudsql/${google_sql_database_instance.litellm.connection_name}",
    ])
    # Not secret, but a secret volume is the simplest way to mount a file on Cloud Run.
    "agw-litellm-config" = file(local.config_path)
  }
}

resource "random_password" "master_key" {
  length  = 40
  special = false
}

resource "random_password" "salt_key" {
  length  = 40
  special = false
}

resource "google_secret_manager_secret" "this" {
  # Listed by name: keys(local.secrets) would inherit the values' sensitivity,
  # which for_each rejects.
  for_each = toset([
    "agw-litellm-master-key",
    "agw-litellm-salt-key",
    "agw-litellm-database-url",
    "agw-litellm-config",
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

# One LiteLLM virtual key per caller, so spend, limits and logs are attributed to
# the agent and the harness separately and both paths do the same key lookup. Each
# key is created in LiteLLM (UI or /key/generate) and added as a version by hand
# (see ../README.md); Terraform owns only the secrets and who may read them, so the
# phase-end destroy removes all of it.
locals {
  callers = {
    agent   = "agw-agent"
    harness = "agw-harness"
  }
}

resource "google_secret_manager_secret" "caller_key" {
  for_each = local.callers

  secret_id = "agw-litellm-${each.key}-key"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

data "google_service_account" "caller" {
  for_each = local.callers

  account_id = each.value
}

resource "google_secret_manager_secret_iam_member" "caller_key_reader" {
  for_each = local.callers

  secret_id = google_secret_manager_secret.caller_key[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = data.google_service_account.caller[each.key].member
}

# The agent's key was a single resource before the harness got one.
moved {
  from = google_secret_manager_secret.agent_key
  to   = google_secret_manager_secret.caller_key["agent"]
}

moved {
  from = google_secret_manager_secret_iam_member.agent_key_reader
  to   = google_secret_manager_secret_iam_member.caller_key_reader["agent"]
}
