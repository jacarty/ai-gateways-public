# State lives in the bucket foundation/ created: terraform init -backend-config=../../foundation/terraform/backend.hcl
terraform {
  backend "gcs" {
    prefix = "harness"
  }
}
