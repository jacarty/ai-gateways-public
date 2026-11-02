resource "google_monitoring_notification_channel" "budget_email" {
  display_name = "ai-gateways budget alerts"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [time_sleep.api_propagation]
}

# Alerts only: a budget does not stop spend. Destroy each gateway at phase end.
# Scoped to the whole project: model calls carry no labels, so a label filter
# would miss the main cost. Anything else in the project counts against it too.
resource "google_billing_budget" "this" {
  billing_account = var.billing_account_id
  display_name    = "${var.project_id} (ai-gateways)"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]

    # Alert on gross cost: promotional or trial credits must not hide spend.
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.budget_email.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [time_sleep.api_propagation]
}
