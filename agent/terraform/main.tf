data "google_service_account" "agent" {
  account_id = "agw-agent"
}

# IAM-authenticated, not network-private: the URL is public, but every caller
# needs roles/run.invoker and an ID token. Unauthenticated calls never start an instance.
resource "google_cloud_run_v2_service" "agent" {
  name                = "agw-agent"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = data.google_service_account.agent.email
    timeout                          = "60s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "AGW_TARGET"
        value = var.target
      }
      env {
        name  = "AGW_GATEWAY_URL"
        value = var.gateway_url
      }
      # The gateway's key goes in Authorization; the agent adds an ID token for
      # Cloud Run itself (agw_agent.auth). The gateway stack grants both: read access
      # to the key's secret and run.invoker for agw-agent.
      dynamic "env" {
        for_each = var.gateway_api_key_secret == "" ? [] : [var.gateway_api_key_secret]
        content {
          name = "AGW_GATEWAY_API_KEY"
          value_source {
            secret_key_ref {
              secret = env.value
              # Read when each instance starts: after a new key version, warm instances
              # keep the old key until they are replaced, so force a new revision
              # (or let the service scale to zero) before a measured run.
              version = "latest"
            }
          }
        }
      }
      env {
        name  = "AGW_GATEWAY_CLAUDE_API"
        value = var.gateway_claude_api
      }
      env {
        name  = "AGW_MAX_OUTPUT_TOKENS"
        value = tostring(var.max_output_tokens)
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.model_location
      }
      env {
        name  = "GOOGLE_GENAI_USE_ENTERPRISE"
        value = "true"
      }

      # Up to about 90 s to start: a cold instance failed the earlier 30 s (10 x 3 s) and
      # its callers got 503s (Phase 1, test 6 run A). The request that woke it is still
      # bound by the 60 s timeout above.
      startup_probe {
        http_get {
          path = "/list-apps"
        }
        initial_delay_seconds = 2
        timeout_seconds       = 5
        period_seconds        = 3
        failure_threshold     = 30
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  name     = google_cloud_run_v2_service.agent.name
  location = google_cloud_run_v2_service.agent.location
  role     = "roles/run.invoker"
  member   = each.value
}

# Read access to the gateway key's secret moved to the gateway stack, next to the
# secret, so the two are created and destroyed together. Forget this stack's copy
# of the binding without deleting it (the gateway stack now manages it).
removed {
  from = google_secret_manager_secret_iam_member.gateway_key

  lifecycle {
    destroy = false
  }
}
