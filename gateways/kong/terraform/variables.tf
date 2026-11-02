variable "project_id" {
  description = "GCP project that hosts the lab (my-gcp-project)."
  type        = string
}

variable "region" {
  description = "Region the gateway and its database run in."
  type        = string
  default     = "europe-west1"
}

variable "db_tier" {
  description = "Cloud SQL machine type. Shared-core is enough for Kong's entities (services, routes, plugins, consumers, keys) in a lab."
  type        = string
  default     = "db-f1-micro"
}

variable "image" {
  description = "Kong OSS image by digest, pulled through foundation's agw-dockerhub repo: <dockerhub_repository>/kong/kong@sha256:..."
  type        = string

  validation {
    condition     = can(regex("-docker\\.pkg\\.dev/[^/]+/agw-dockerhub/kong/kong@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be the OSS kong/kong image through agw-dockerhub, pinned by digest (<region>-docker.pkg.dev/<project>/agw-dockerhub/kong/kong@sha256:<64 hex>), not a tag or kong/kong-gateway (enterprise)."
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
  description = "Cloud Run instance cap. Fixed at 1: Kong's rate-limit counters (policy local) are per instance."
  type        = number
  default     = 1

  validation {
    condition     = var.max_instances == 1
    error_message = "max_instances must be 1: a second instance would count rate limits separately (test 3)."
  }
}
