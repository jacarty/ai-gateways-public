output "url" {
  description = "Gateway base URL. OpenAI API at <url>/chat/completions; set AGW_GATEWAY_URL to this."
  value       = google_cloud_run_v2_service.litellm.uri
}

output "database_instance" {
  description = "Cloud SQL instance name (make stop-litellm / start-litellm stop and start it)."
  value       = google_sql_database_instance.litellm.name
}

output "master_key_secret" {
  description = "Secret holding the LiteLLM master key (admin UI password for user \"admin\")."
  value       = google_secret_manager_secret.this["agw-litellm-master-key"].secret_id
}

output "agent_key_secret" {
  description = "Secret for the agent's virtual key: set it as the agent's gateway_api_key_secret."
  value       = google_secret_manager_secret.caller_key["agent"].secret_id
}

output "harness_key_secret" {
  description = "Secret for the harness's virtual key: set it as the harness job's gateway_api_key_secret."
  value       = google_secret_manager_secret.caller_key["harness"].secret_id
}
