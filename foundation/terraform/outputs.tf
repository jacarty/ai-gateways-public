output "state_bucket" {
  description = "GCS bucket for every stack's remote state. Use as `bucket` in backend.hcl."
  value       = google_storage_bucket.tfstate.name
}

output "agent_service_account" {
  description = "Email of the agent's service account."
  value       = google_service_account.agent.email
}

output "gateway_service_accounts" {
  description = "Email of each gateway's service account, keyed by gateway."
  value       = { for k, sa in google_service_account.gateway : k => sa.email }
}

output "secret_prefix" {
  description = "Gateway secrets must be named <this><gateway>- (e.g. agw-kong-) to be readable by that gateway's service account."
  value       = local.secret_prefix
}

output "budget_id" {
  description = "Billing budget resource name."
  value       = google_billing_budget.this.name
}

output "image_repository" {
  description = "Artifact Registry path for images, e.g. <this>/agent:<tag>."
  value       = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "ghcr_repository" {
  description = "Artifact Registry path that proxies ghcr.io, e.g. <this>/berriai/litellm@sha256:<digest>."
  value       = "${google_artifact_registry_repository.ghcr.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ghcr.repository_id}"
}

output "dockerhub_repository" {
  description = "Artifact Registry path that proxies Docker Hub, e.g. <this>/kong/kong@sha256:<digest>."
  value       = "${google_artifact_registry_repository.dockerhub.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dockerhub.repository_id}"
}

output "build_service_account" {
  description = "Service account Cloud Build runs as (pass to gcloud builds submit --service-account)."
  value       = google_service_account.build.id
}

output "build_source_bucket" {
  description = "Bucket for gcloud builds submit --gcs-source-staging-dir."
  value       = google_storage_bucket.build_source.name
}

output "harness_service_account" {
  description = "Email of the harness service account (add to the agent's and gateways' invoker_members)."
  value       = google_service_account.harness.email
}

output "results_bucket" {
  description = "Bucket the harness job writes raw results to."
  value       = google_storage_bucket.results.name
}

output "network" {
  description = "Private network for gateway databases (Cloud SQL private_network, Cloud Run Direct VPC egress)."
  value       = google_compute_network.this.id
}

output "run_subnetwork" {
  description = "Subnet Cloud Run gateways use for Direct VPC egress (egress = PRIVATE_RANGES_ONLY)."
  value       = google_compute_subnetwork.run.id
}
