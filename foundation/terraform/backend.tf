# Remote state in the bucket this stack creates. Bootstrapping a new project:
#   1. comment this block out and apply once with local state
#   2. uncomment it, then: terraform init -migrate-state -backend-config=backend.hcl
#   3. run `terraform plan` (expect no changes) BEFORE deleting local state files
# See ../README.md.

terraform {
  backend "gcs" {
    prefix = "foundation"
  }
}
