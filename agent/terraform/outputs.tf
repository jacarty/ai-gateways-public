output "url" {
  description = "Agent base URL. Call with an ID token: /apps/{gemini|claude}/users/{user}/sessions/{session}, then /run."
  value       = google_cloud_run_v2_service.agent.uri
}
