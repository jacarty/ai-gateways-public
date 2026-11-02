output "database_instance" {
  description = "Cloud SQL instance name (make stop-kong / start-kong stop and start it)."
  value       = google_sql_database_instance.kong.name
}

output "admin_key_secret" {
  description = "Secret for the admin consumer's key (decK and the test scripts)."
  value       = google_secret_manager_secret.this["agw-kong-admin-key"].secret_id
}

output "manager_password_secret" {
  description = "Secret holding the Kong Manager password (user \"admin\")."
  value       = google_secret_manager_secret.this["agw-kong-manager-password"].secret_id
}

output "agent_key_secret" {
  description = "Secret for the agent's Kong key: set it as the agent's gateway_api_key_secret."
  value       = google_secret_manager_secret.this["agw-kong-agent-key"].secret_id
}

output "harness_key_secret" {
  description = "Secret for the harness's Kong key: set it as the harness job's gateway_api_key_secret."
  value       = google_secret_manager_secret.this["agw-kong-harness-key"].secret_id
}

output "url" {
  description = "Gateway base URL (the service URL)."
  value       = google_cloud_run_v2_service.kong.uri
}

output "gateway_url" {
  description = "Base URL for callers (<url>/v1): Gemini at <this>/chat/completions, Claude at <this>/projects/.../claude-haiku-5-5:rawPredict. Set the agent's gateway_url and AGW_GATEWAY_URL to this."
  value       = "${google_cloud_run_v2_service.kong.uri}/v1"
}

output "database_private_ip" {
  description = "Cloud SQL private IP on agw-vpc (KONG_PG_HOST)."
  value       = google_sql_database_instance.kong.private_ip_address
}
