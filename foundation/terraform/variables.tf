variable "project_id" {
  description = "GCP project that hosts the lab (my-gcp-project). May be shared with other work, so this stack only adds to it."
  type        = string
}

variable "region" {
  description = "Region for all deployed resources. The models themselves are called on the EU multi-region endpoint (location \"eu\")."
  type        = string
  default     = "europe-west1"
}

variable "billing_account_id" {
  description = "Billing account the budget is attached to, e.g. 012345-6789AB-CDEF01."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget in whole units of budget_currency. Covers ALL spend in the project, not just this lab."
  type        = number
  default     = 50
}

variable "budget_currency" {
  description = "ISO 4217 code. Must match the billing account's currency (the my-gcp-project billing account is USD), or the budget fails with a 400."
  type        = string
  default     = "USD"
}

variable "alert_email" {
  description = "Address that receives budget alerts, in addition to the billing account's admins."
  type        = string
}

variable "gateways" {
  description = "Gateways that get their own service account."
  type        = set(string)
  default     = ["litellm", "bifrost", "kong"]

  validation {
    # Service account ids are 6-30 chars and get the 7-char prefix "agw-gw-".
    # No hyphens: a gateway reads secrets named agw-<gw>-, so "kong" would
    # otherwise also read a "kong-x" gateway's secrets.
    condition     = alltrue([for g in var.gateways : can(regex("^[a-z][a-z0-9]{0,22}$", g))])
    error_message = "Gateway names must be lowercase letters and digits, start with a letter, and be at most 23 characters."
  }
}
