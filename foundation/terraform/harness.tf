# The load harness: runs as a Cloud Run job next to the agent and gateways, and
# writes raw results to a bucket mounted into the job. Results are then copied
# into results/raw/ and committed.

resource "google_service_account" "harness" {
  account_id   = "agw-harness"
  display_name = "ai-gateways load harness"

  depends_on = [time_sleep.api_propagation]
}

# Direct baseline calls the models itself; logs for the job's own output.
resource "google_project_iam_member" "harness" {
  for_each = toset(local.runtime_roles)

  project = var.project_id
  role    = each.value
  member  = google_service_account.harness.member
}

# No force_destroy: runs are evidence. Copies live in git (results/raw/), but a
# foundation destroy stops here until the bucket is emptied by hand.
resource "google_storage_bucket" "results" {
  name     = "${var.project_id}-ai-gateways-results"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  depends_on = [time_sleep.api_propagation]
}

# Read and write: the job mounts the bucket with gcsfuse, which lists and creates objects.
resource "google_storage_bucket_iam_member" "harness_results" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectUser"
  member = google_service_account.harness.member
}
