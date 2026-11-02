# One identity per caller, so Cloud Logging can tell the agent and each
# gateway apart (test 6, audit fidelity). The harness runs as the operator's
# own credentials.

locals {
  # Roles every runtime identity needs: call models, write logs.
  runtime_roles = [
    "roles/aiplatform.user",
    "roles/logging.logWriter",
  ]

  gateway_bindings = {
    for pair in setproduct(var.gateways, local.runtime_roles) :
    "${pair[0]}/${pair[1]}" => { gateway = pair[0], role = pair[1] }
  }

  # Base prefix of gateway secrets; each gateway reads only its own,
  # <secret_prefix><gateway>-* (see gateway_secrets).
  secret_prefix = "agw-"
}

resource "google_service_account" "agent" {
  account_id   = "agw-agent"
  display_name = "ai-gateways ADK agent"

  depends_on = [time_sleep.api_propagation]
}

resource "google_project_iam_member" "agent" {
  for_each = toset(local.runtime_roles)

  project = var.project_id
  role    = each.value
  member  = google_service_account.agent.member
}

resource "google_service_account" "gateway" {
  for_each = var.gateways

  account_id   = "agw-gw-${each.value}"
  display_name = "ai-gateways ${each.value} gateway"

  depends_on = [time_sleep.api_propagation]
}

resource "google_project_iam_member" "gateway" {
  for_each = local.gateway_bindings

  project = var.project_id
  role    = each.value.role
  member  = google_service_account.gateway[each.value.gateway].member
}

# The project may hold other work's secrets, and each gateway's stack holds its
# own keys, so a gateway can only read secrets named <secret_prefix><gateway>-.
resource "google_project_iam_member" "gateway_secrets" {
  for_each = var.gateways

  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = google_service_account.gateway[each.value].member

  condition {
    title      = "agw-${each.value}-secrets-only"
    expression = "resource.name.startsWith(\"projects/${data.google_project.this.number}/secrets/${local.secret_prefix}${each.value}-\")"
  }
}
