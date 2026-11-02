data "google_service_account" "gateway" {
  account_id = "agw-gw-bifrost"
}

# The Bifrost gateway, as one container (API, admin UI and both stores' clients).
# IAM-authenticated like the agent: callers need roles/run.invoker and an ID token,
# plus a Bifrost virtual key (sk-bf-...) in Authorization (the ID token then goes
# in X-Serverless-Authorization).
resource "google_cloud_run_v2_service" "bifrost" {
  name                = "agw-bifrost"
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
        secret = google_secret_manager_secret.this["agw-bifrost-config"].secret_id
        items {
          # Pinned, not "latest": a config change makes a new revision on apply.
          version = google_secret_manager_secret_version.this["agw-bifrost-config"].version
          path    = "config.json"
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.bifrost.connection_name]
      }
    }

    containers {
      image = var.image
      # Bifrost reads config.json from APP_DIR (/app/data), which must be writable;
      # secret volumes are read-only, so mount it elsewhere and copy it in (the
      # pattern from Bifrost's own Cloud Run guide), then run the image's entrypoint.
      command = ["sh"]
      args    = ["-c", "cp /var/run/bifrost-config/config.json /app/data/config.json && exec /app/docker-entrypoint.sh"]

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # Same compute as LiteLLM's, so test 1 compares the gateways, not their
        # sizing. CPU stays on between requests: Bifrost writes request logs in
        # 5 s batches and syncs prices in the background. Still scales to zero.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      volume_mounts {
        name       = "config"
        mount_path = "/var/run/bifrost-config"
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "AGW_PROJECT"
        value = var.project_id
      }
      env {
        name  = "BIFROST_ADMIN_USERNAME"
        value = "admin"
      }
      # Cloud Run's Cloud SQL connection: a Unix socket directory, which pgx takes
      # as host (no TCP port; ssl_mode disable, the connector encrypts the link).
      env {
        name  = "AGW_DB_HOST"
        value = "/cloudsql/${google_sql_database_instance.bifrost.connection_name}"
      }
      env {
        name  = "AGW_DB_USER"
        value = google_sql_user.bifrost.name
      }
      env {
        name  = "AGW_DB_NAME"
        value = google_sql_database.bifrost.name
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.value
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.key].secret_id
              version = google_secret_manager_secret_version.this[env.key].version
            }
          }
        }
      }

      # A cold start runs migrations and downloads the model catalog from
      # getbifrost.ai (about 22 s in the hand-build) before serving, so allow
      # up to about two minutes.
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 24
      }
    }
  }

  depends_on = [time_sleep.cloudsql_client_propagation]
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  name     = google_cloud_run_v2_service.bifrost.name
  location = google_cloud_run_v2_service.bifrost.location
  role     = "roles/run.invoker"
  member   = each.value
}
