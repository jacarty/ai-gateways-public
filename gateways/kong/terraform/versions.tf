# Pinned exactly, to releases at least two weeks old (the repo's rule for upstream code):
# google 8.6.0 (2026-10-06), random 3.9.1, time 0.14.2 (2026-09-11), Terraform 1.16.x (the pre-commit hooks need 1.16).
# .terraform.lock.hcl records the same versions with their hashes; bump both together.
terraform {
  required_version = "~> 1.16.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "= 3.9.1"
    }
    time = {
      source  = "hashicorp/time"
      version = "= 0.14.2"
    }
  }
}
