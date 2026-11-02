output "url" {
  description = "Gateway base URL (the service URL). Bifrost's OpenAI API is under /v1: see gateway_url."
  value       = google_cloud_run_v2_service.bifrost.uri
}

output "gateway_url" {
  description = "OpenAI-compatible base URL (<url>/v1/chat/completions): set the agent's gateway_url and AGW_GATEWAY_URL to this."
  value       = "${google_cloud_run_v2_service.bifrost.uri}/v1"
}

output "database_instance" {
  description = "Cloud SQL instance name (make stop-bifrost / start-bifrost stop and start it)."
  value       = google_sql_database_instance.bifrost.name
}

output "admin_password_secret" {
  description = "Secret holding the admin UI password (user \"admin\")."
  value       = google_secret_manager_secret.this["agw-bifrost-admin-password"].secret_id
}

output "agent_key_secret" {
  description = "Secret for the agent's virtual key: set it as the agent's gateway_api_key_secret."
  value       = google_secret_manager_secret.this["agw-bifrost-agent-key"].secret_id
}

output "harness_key_secret" {
  description = "Secret for the harness's virtual key: set it as the harness job's gateway_api_key_secret."
  value       = google_secret_manager_secret.this["agw-bifrost-harness-key"].secret_id
}
