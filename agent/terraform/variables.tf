variable "project_id" {
  description = "GCP project that hosts the lab (my-gcp-project)."
  type        = string
}

variable "region" {
  description = "Region the Cloud Run service runs in."
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "Agent image to deploy, by digest: <foundation image_repository>/agent@sha256:... (tags are mutable)."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest (…/agent@sha256:<64 hex>), not a tag."
  }
}

variable "invoker_members" {
  description = "Principals allowed to call the private service, e.g. [\"user:me@example.com\"]."
  type        = list(string)
  default     = []

  validation {
    # The runtime SA can call the models: a public invoker would be open model spend.
    condition     = !anytrue([for m in var.invoker_members : contains(["allUsers", "allAuthenticatedUsers"], m)])
    error_message = "invoker_members must not include allUsers or allAuthenticatedUsers."
  }
}

variable "target" {
  description = "\"direct\" calls the models on the Agent Platform; \"gateway\" calls gateway_url."
  type        = string
  default     = "direct"

  validation {
    condition     = contains(["direct", "gateway"], var.target)
    error_message = "target must be \"direct\" or \"gateway\"."
  }
}

variable "gateway_url" {
  description = "OpenAI-compatible base URL of the gateway under test (target = \"gateway\")."
  type        = string
  default     = ""
}

variable "gateway_api_key_secret" {
  description = "Secret Manager secret holding the gateway key the agent sends (target = \"gateway\"), e.g. a LiteLLM virtual key. It must already have a version (Cloud Run rejects the revision otherwise) and the gateway stack grants agw-agent read access. Empty: no key."
  type        = string
  default     = ""

  validation {
    # Same naming rule as gateway secrets, so the agent can only be pointed at lab secrets.
    condition     = var.gateway_api_key_secret == "" || startswith(var.gateway_api_key_secret, "agw-")
    error_message = "gateway_api_key_secret must be empty or an agw-* secret."
  }
}

variable "gateway_claude_api" {
  description = "How Claude reaches the gateway: \"openai\" (its OpenAI API, LiteLLM and Bifrost) or \"anthropic\" (Claude's own Vertex rawPredict request under gateway_url, for Kong, which can't translate to Claude; ADR 0014)."
  type        = string
  default     = "openai"

  validation {
    condition     = contains(["openai", "anthropic"], var.gateway_claude_api)
    error_message = "gateway_claude_api must be \"openai\" or \"anthropic\"."
  }
}

variable "model_location" {
  description = "Where the models are called. \"eu\" is the EU multi-region endpoint; neither model has a europe-west1 endpoint."
  type        = string
  default     = "eu"
}

variable "max_output_tokens" {
  description = "Cap on generated tokens per call, to keep cost and latency variance low."
  type        = number
  default     = 256
}
