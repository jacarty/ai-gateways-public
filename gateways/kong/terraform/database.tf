# Postgres for Kong's entities (services, routes, plugins, consumers, keys), so
# the Admin API can create and delete them at runtime: decK syncs config/kong.yaml
# through it, and tests 3, 5 and 6 mint throwaway keys through it (ADR 0015).
# Kong keeps no request logs or counters here. One small zonal instance, no
# replica, no backups.
#
# Private IP only, on foundation's agw-vpc (ADR 0016): Kong's init phase can't use
# Cloud Run's /cloudsql Unix socket, so Kong connects over TCP through Direct VPC
# egress. No public IP, so nothing on the internet can reach it. Password auth
# over TCP needs no roles/cloudsql.client (that authorises the socket and proxy).

data "google_service_account" "gateway" {
  account_id = "agw-gw-kong"
}

# Created by foundation/ (network.tf), with its private services access peering.
data "google_compute_network" "agw" {
  name = "agw-vpc"
}

# Cloud SQL keeps a deleted instance's name reserved for about a week, so a
# suffix lets the stack be destroyed and re-applied within a phase.
resource "random_id" "db_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "kong" {
  name                = "agw-kong-${random_id.db_suffix.hex}"
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
      ipv4_enabled    = false
      private_network = data.google_compute_network.agw.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    # Cloud SQL takes user_labels, not the provider's default_labels.
    user_labels = {
      project = "ai-gateways"
      stack   = "gateway-kong"
    }
  }

  lifecycle {
    # `make stop-kong` / `make start-kong` set this with gcloud; an apply must
    # not switch a stopped database back on.
    ignore_changes = [settings[0].activation_policy]
  }
}

# ABANDON on the database and user: destroying the instance removes both, and
# deleting them first fails (the user owns Kong's tables; a stopped instance
# can't be reached at all).
resource "google_sql_database" "kong" {
  name            = "kong"
  instance        = google_sql_database_instance.kong.name
  deletion_policy = "ABANDON"
}

# Password auth, as for LiteLLM and Bifrost. Users created through the Cloud SQL
# API join cloudsqlsuperuser, so Kong owns its own (dedicated) instance and its
# startup migrations can create the schema.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "kong" {
  name            = "kong"
  instance        = google_sql_database_instance.kong.name
  password        = random_password.db.result
  deletion_policy = "ABANDON"
}
