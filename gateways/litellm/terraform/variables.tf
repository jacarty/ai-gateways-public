variable "project_id" {
  description = "GCP project that hosts the lab (my-gcp-project)."
  type        = string
}

variable "region" {
  description = "Region the gateway and its database run in."
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "LiteLLM image by digest, pulled through foundation's agw-ghcr repo: <ghcr_repository>/berriai/litellm@sha256:..."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest (…/berriai/litellm@sha256:<64 hex>), not a tag."
  }
}

variable "invoker_members" {
  description = "Principals allowed to call the gateway, e.g. the agent and harness service accounts."
  type        = list(string)
  default     = []

  validation {
    # The gateway's SA can call the models: a public invoker would be open model spend.
    condition     = !anytrue([for m in var.invoker_members : contains(["allUsers", "allAuthenticatedUsers"], m)])
    error_message = "invoker_members must not include allUsers or allAuthenticatedUsers."
  }
}

variable "max_instances" {
  description = "Cloud Run instance cap. Keep 1: without Redis, LiteLLM's rate limits are counted per instance (and db-f1-micro allows about 25 connections)."
  type        = number
  default     = 1

  validation {
    condition     = var.max_instances >= 1 && var.max_instances <= 2
    error_message = "max_instances must be 1 or 2."
  }
}

variable "model_location" {
  description = "Where the models are called. \"eu\" is the EU multi-region endpoint, the same as the baseline."
  type        = string
  default     = "eu"
}

variable "db_tier" {
  description = "Cloud SQL machine type. Shared-core is enough for keys, budgets and spend logs in a lab."
  type        = string
  default     = "db-f1-micro"
}
