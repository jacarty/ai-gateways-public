locals {
  services = [
    "aiplatform.googleapis.com",           # Gemini and Claude on the Agent Platform; Agent Runtime
    "run.googleapis.com",                  # gateways (and possibly the agent)
    "artifactregistry.googleapis.com",     # agent and gateway images
    "cloudbuild.googleapis.com",           # builds images from the repo's Dockerfiles
    "secretmanager.googleapis.com",        # gateway config secrets; keys for test 5
    "sqladmin.googleapis.com",             # Cloud SQL for gateways that need a database (LiteLLM)
    "logging.googleapis.com",              # audit fidelity (test 6)
    "monitoring.googleapis.com",           # budget alert notification channel
    "billingbudgets.googleapis.com",       # the budget itself
    "cloudbilling.googleapis.com",         # SKU price catalog: checks gateway model prices (test 3)
    "iam.googleapis.com",                  # service accounts
    "iamcredentials.googleapis.com",       # token minting for workload identity (test 5)
    "cloudresourcemanager.googleapis.com", # project IAM bindings
    "storage.googleapis.com",              # Terraform state bucket
    "serviceusage.googleapis.com",         # quota project for user_project_override
    "compute.googleapis.com",              # the private network gateways reach their databases on
    "servicenetworking.googleapis.com",    # private services access: Cloud SQL private IPs
  ]
}

resource "google_project_service" "this" {
  for_each = toset(local.services)

  service = each.value

  # Keep APIs on if this stack is destroyed; disabling them can break
  # resources managed by other stacks.
  disable_on_destroy = false
}

# Newly enabled APIs take a minute to propagate; without this the budget and
# notification channel can fail with a 403 on a project's first apply.
resource "time_sleep" "api_propagation" {
  create_duration = "60s"

  triggers = {
    services = join(",", sort(local.services))
  }

  depends_on = [google_project_service.this]
}
