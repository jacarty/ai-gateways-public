output "job" {
  description = "Job name, for gcloud run jobs execute."
  value       = google_cloud_run_v2_job.harness.name
}

output "results_bucket" {
  description = "Where runs land: gs://<this>/<run_id>/."
  value       = local.results_bucket
}
