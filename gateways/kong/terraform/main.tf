# Created by foundation/ (network.tf): Cloud Run's Direct VPC egress subnet.
data "google_compute_subnetwork" "run" {
  name   = "agw-run-${var.region}"
  region = var.region
}

locals {
  # Secret name => the environment variable Kong or start.sh reads it from.
  secret_env = {
    # A secret name and the env var it fills, not a value; gitleaks' hashicorp-tf-password
    # rule matches any password = "...".
    "agw-kong-db-password" = "KONG_PG_PASSWORD" # gitleaks:allow
    "agw-kong-admin-key"   = "AGW_KONG_ADMIN_KEY"
  }

  # Secret name => mounted file: the startup wrapper, the admin bootstrap it
  # imports, and the database's CA certificate.
  secret_files = {
    "agw-kong-start"     = { dir = "/var/run/kong-start", file = "start.sh" }
    "agw-kong-bootstrap" = { dir = "/var/run/kong-bootstrap", file = "bootstrap.yaml" }
    "agw-kong-db-ca"     = { dir = "/var/run/kong-db-ca", file = "server-ca.pem" }
  }

  kong_env = {
    KONG_DATABASE      = "postgres"
    KONG_PG_HOST       = google_sql_database_instance.kong.private_ip_address
    KONG_PG_PORT       = "5432"
    KONG_PG_USER       = google_sql_user.kong.name
    KONG_PG_DATABASE   = google_sql_database.kong.name
    KONG_PG_SSL        = "on"
    KONG_PG_SSL_VERIFY = "on"
    # The system CAs (for Vertex) plus the instance's own CA (for Postgres). Kong's
    # Postgres client checks the chain only, not the name, so the private IP works.
    KONG_LUA_SSL_TRUSTED_CERTIFICATE = "system,/var/run/kong-db-ca/server-ca.pem"
    KONG_PROXY_LISTEN                = "0.0.0.0:8080"
    # One worker for the one vCPU: "auto" counts the sandbox's 2 CPUs, which doubles
    # Postgres connection pools on a db-f1-micro and isn't comparable sizing.
    KONG_NGINX_WORKER_PROCESSES = "1"
    # The Admin API is reachable only through Kong's own /admin-api route (ADR 0015).
    KONG_ADMIN_LISTEN = "127.0.0.1:8001"
    # Kong Manager OSS (the admin UI), also on loopback: Kong's /manager and
    # /manager-api routes serve it and its Admin API calls, behind basic-auth in
    # kong.yaml. KONG_ADMIN_GUI_API_URL is not what the browser uses: Manager can't
    # take a relative URL, so kong.yaml serves Manager's kconfig.js itself (keep its
    # values in step with these settings).
    KONG_ADMIN_GUI_LISTEN  = "127.0.0.1:8002"
    KONG_ADMIN_GUI_PATH    = "/manager"
    KONG_ADMIN_GUI_API_URL = "/manager-api"
    # For the startup probe only: Cloud Run sends outside traffic to 8080.
    KONG_STATUS_LISTEN     = "0.0.0.0:8100"
    KONG_PROXY_ACCESS_LOG  = "/dev/stdout"
    KONG_PROXY_ERROR_LOG   = "/dev/stderr"
    KONG_ADMIN_ACCESS_LOG  = "/dev/stdout"
    KONG_ADMIN_ERROR_LOG   = "/dev/stderr"
    KONG_ANONYMOUS_REPORTS = "off"
  }
}

# Kong OSS, as one container: the proxy, its Admin API on loopback, and the
# startup wrapper that migrates the database and imports the admin route
# (config/start.sh). IAM-authenticated like the other gateways: callers need
# roles/run.invoker and an ID token in X-Serverless-Authorization, plus a Kong
# key in Authorization.
resource "google_cloud_run_v2_service" "kong" {
  name                = "agw-kong"
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

    # Only private ranges (the database) go through the VPC; model calls leave
    # Cloud Run as before (ADR 0016).
    vpc_access {
      network_interfaces {
        network    = data.google_compute_network.agw.id
        subnetwork = data.google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    dynamic "volumes" {
      for_each = local.secret_files
      content {
        name = volumes.key
        secret {
          secret = google_secret_manager_secret.this[volumes.key].secret_id
          items {
            # Pinned, not "latest": a change makes a new revision on apply.
            version = google_secret_manager_secret_version.this[volumes.key].version
            path    = volumes.value.file
          }
        }
      }
    }

    containers {
      image   = var.image
      command = ["sh"]
      args    = ["/var/run/kong-start/start.sh"]

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # Same compute as LiteLLM's and Bifrost's, so test 1 compares the
        # gateways, not their sizing. CPU stays on between requests: Kong polls
        # the database for config changes every 5 s. Still scales to zero.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      dynamic "volume_mounts" {
        for_each = local.secret_files
        content {
          name       = volume_mounts.key
          mount_path = volume_mounts.value.dir
        }
      }

      dynamic "env" {
        for_each = local.kong_env
        content {
          name  = env.key
          value = env.value
        }
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

      # Migrations (first start only) and the bootstrap import run before Kong
      # listens; a warm database takes about 5 s (hand-build).
      startup_probe {
        http_get {
          path = "/status/ready"
          port = 8100
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 24
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  name     = google_cloud_run_v2_service.kong.name
  location = google_cloud_run_v2_service.kong.location
  role     = "roles/run.invoker"
  member   = each.value
}
