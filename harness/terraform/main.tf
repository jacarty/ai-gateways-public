data "google_service_account" "harness" {
  account_id = "agw-harness"
}

data "google_cloud_run_v2_service" "agent" {
  name     = "agw-agent"
  location = var.region
}

locals {
  # Created by foundation/ (output results_bucket).
  results_bucket = "${var.project_id}-ai-gateways-results"
}

# Runs to completion and stops: no idle cost. Execute with
#   gcloud run jobs execute agw-harness --region europe-west1 --wait [--args=...]
resource "google_cloud_run_v2_job" "harness" {
  name                = "agw-harness"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account       = data.google_service_account.harness.email
      timeout               = "${var.timeout_s}s"
      max_retries           = 0
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

      containers {
        image = var.image
        args  = ["baseline"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name  = "AGW_PROJECT"
          value = var.project_id
        }
        env {
          name  = "AGW_MODEL_LOCATION"
          value = var.model_location
        }
        env {
          name  = "AGW_MAX_TOKENS"
          value = tostring(var.max_tokens)
        }
        env {
          name  = "AGW_AGENT_URL"
          value = data.google_cloud_run_v2_service.agent.uri
        }
        env {
          name  = "AGW_GATEWAY_URL"
          value = var.gateway_url
        }
        env {
          name  = "AGW_GATEWAY_CLAUDE_API"
          value = var.gateway_claude_api
        }
        # Read when an execution starts, so a new key version applies to the next run.
        dynamic "env" {
          for_each = var.gateway_api_key_secret == "" ? [] : [var.gateway_api_key_secret]
          content {
            name = "AGW_GATEWAY_API_KEY"
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
        env {
          name  = "AGW_RESULTS_DIR"
          value = "/results"
        }
        env {
          name  = "AGW_IMAGE"
          value = var.image
        }

        volume_mounts {
          name       = "results"
          mount_path = "/results"
        }
      }

      volumes {
        name = "results"
        gcs {
          bucket    = local.results_bucket
          read_only = false
        }
      }
    }
  }
}
