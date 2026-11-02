variable "project_id" {
  description = "GCP project that hosts the lab (my-gcp-project)."
  type        = string
}

variable "region" {
  description = "Region the job runs in, next to the agent and gateways."
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "Harness image, by digest: <foundation image_repository>/harness@sha256:... (tags are mutable)."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest (…/harness@sha256:<64 hex>), not a tag."
  }
}

variable "gateway_url" {
  description = "OpenAI-compatible base URL of the gateway under test, for gateway-target runs."
  type        = string
  default     = ""
}

variable "gateway_claude_api" {
  description = "How Claude reaches the gateway target: \"openai\" (its /chat/completions, LiteLLM and Bifrost) or \"anthropic\" (the direct rawPredict request under gateway_url, for Kong; ADR 0014)."
  type        = string
  default     = "openai"

  validation {
    condition     = contains(["openai", "anthropic"], var.gateway_claude_api)
    error_message = "gateway_claude_api must be \"openai\" or \"anthropic\"."
  }
}

variable "gateway_api_key_secret" {
  description = "Secret Manager secret with the gateway key for gateway-target runs, e.g. agw-litellm-harness-key (a LiteLLM virtual key, like the agent's). It must already have a version; the gateway stack grants agw-harness read access. Empty: no key."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_api_key_secret == "" || startswith(var.gateway_api_key_secret, "agw-")
    error_message = "gateway_api_key_secret must be empty or an agw-* secret."
  }
}

variable "timeout_s" {
  description = "Job execution timeout in seconds. A default compare (direct + gateway) took about 20 minutes against LiteLLM; the agent target, more requests or a slow upstream day add to that, and a timeout kills the job with no retry."
  type        = number
  default     = 7200

  validation {
    condition     = var.timeout_s >= 600 && var.timeout_s <= 86400
    error_message = "timeout_s must be between 600 and 86400 (Cloud Run's job maximum is 24 h)."
  }
}

variable "model_location" {
  description = "Where direct-target runs call the models. \"eu\" is the EU multi-region endpoint."
  type        = string
  default     = "eu"
}

variable "max_tokens" {
  description = "Token cap per request, the same for every target."
  type        = number
  default     = 256
}
