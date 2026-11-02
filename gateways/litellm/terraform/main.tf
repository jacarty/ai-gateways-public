data "google_service_account" "gateway" {
  account_id = "agw-gw-litellm"
}

locals {
  secret_env = {
    LITELLM_MASTER_KEY = "agw-litellm-master-key"
    LITELLM_SALT_KEY   = "agw-litellm-salt-key"
    DATABASE_URL       = "agw-litellm-database-url"
  }
}

# The LiteLLM proxy, as one container (the "monolith": API, admin UI and DB
# migrations together). IAM-authenticated like the agent: callers need
# roles/run.invoker and an ID token, plus a LiteLLM key in Authorization (the ID
# token then goes in X-Serverless-Authorization).
resource "google_cloud_run_v2_service" "litellm" {
  name                = "agw-litellm"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = data.google_service_account.gateway.email
    # Longer than the callers' 60 s, so a slow model call is timed out by the
    # caller, the same as on the direct baseline, not by the gateway.
    timeout                          = "300s"
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    volumes {
      name = "config"
      secret {
        secret = google_secret_manager_secret.this["agw-litellm-config"].secret_id
        items {
          # Pinned, not "latest": a config change makes a new revision on apply.
          version = google_secret_manager_secret_version.this["agw-litellm-config"].version
          path    = "config.yaml"
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.litellm.connection_name]
      }
    }

    containers {
      image = var.image
      args  = ["--port", "4000", "--config", "/etc/litellm/config.yaml", "--telemetry", "False"]

      ports {
        container_port = 4000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # CPU stays on between requests: LiteLLM flushes spend to Postgres in the
        # background every 10-15 s, and throttling that would skew tests 3 and 6.
        # Still scales to zero (min 0); billed for instance time while up.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      volume_mounts {
        name       = "config"
        mount_path = "/etc/litellm"
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "AGW_MODEL_LOCATION"
        value = var.model_location
      }
      # Models added in the admin UI are kept in Postgres, beside the ones in config.yaml.
      env {
        name  = "STORE_MODEL_IN_DB"
        value = "True"
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = google_secret_manager_secret_version.this[env.value].version
            }
          }
        }
      }

      # Every cold start runs LiteLLM's Prisma migrations before serving, so
      # allow up to about two minutes.
      startup_probe {
        http_get {
          path = "/health/liveliness"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 24
      }
    }
  }

  depends_on = [google_project_iam_member.cloudsql_client]
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  name     = google_cloud_run_v2_service.litellm.name
  location = google_cloud_run_v2_service.litellm.location
  role     = "roles/run.invoker"
  member   = each.value
}
