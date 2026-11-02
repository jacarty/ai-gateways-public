provider "google" {
  project = var.project_id
  region  = var.region

  # The Billing Budgets API needs a quota project when called with user
  # credentials (gcloud ADC); without this, budget creation fails with a 403.
  user_project_override = true
  billing_project       = var.project_id

  default_labels = {
    project = "ai-gateways"
    stack   = "foundation"
  }
}
