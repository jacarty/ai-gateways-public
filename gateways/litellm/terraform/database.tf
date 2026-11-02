# Postgres for LiteLLM's virtual keys, budgets and spend logs (tests 3 and 6).
# One small zonal instance, no replica, no backups: it is destroyed with the phase.
#
# Cloud Run reaches it through its built-in Cloud SQL connection (a Unix socket
# under /cloudsql, authorised by roles/cloudsql.client), so the instance needs no
# VPC and no authorised networks: its public IP accepts only connector traffic.

# Cloud SQL keeps a deleted instance's name reserved for about a week, so a
# suffix lets the stack be destroyed and re-applied within a phase.
resource "random_id" "db_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "litellm" {
  name                = "agw-litellm-${random_id.db_suffix.hex}"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = false

  settings {
    # Postgres 16 defaults to Enterprise Plus, which has no shared-core tiers.
    edition                     = "ENTERPRISE"
    tier                        = var.db_tier
    availability_type           = "ZONAL"
    disk_size                   = 10
    disk_autoresize             = false
    deletion_protection_enabled = false

    backup_configuration {
      enabled = false
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    # Cloud SQL takes user_labels, not the provider's default_labels.
    user_labels = {
      project = "ai-gateways"
      stack   = "gateway-litellm"
    }
  }

  lifecycle {
    # `make stop-litellm` / `make start-litellm` set this with gcloud; an apply
    # must not switch a stopped database back on.
    ignore_changes = [settings[0].activation_policy]
  }
}

# ABANDON on the database and user: destroying the instance removes both, and
# deleting them first fails (the user owns LiteLLM's tables; a stopped instance
# can't be reached at all).
resource "google_sql_database" "litellm" {
  name            = "litellm"
  instance        = google_sql_database_instance.litellm.name
  deletion_policy = "ABANDON"
}

# Password auth: LiteLLM's token-based DB auth covers AWS RDS and Azure only,
# not Cloud SQL IAM login (a test 5 finding). URL-safe, as it goes into DATABASE_URL.
# Users created through the Cloud SQL API join cloudsqlsuperuser, so LiteLLM is an
# admin of its own (dedicated, throwaway) instance.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "litellm" {
  name            = "litellm"
  instance        = google_sql_database_instance.litellm.name
  password        = random_password.db.result
  deletion_policy = "ABANDON"
}

# Only this instance: the project may hold other work's databases.
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = data.google_service_account.gateway.member

  condition {
    title = "agw-litellm-instance-only"
    expression = join(" && ", [
      "resource.type == \"sqladmin.googleapis.com/Instance\"",
      "resource.name == \"projects/${var.project_id}/instances/${google_sql_database_instance.litellm.name}\"",
    ])
  }
}
