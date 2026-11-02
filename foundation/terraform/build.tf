# Image builds: Cloud Build runs the repo's Dockerfiles as a dedicated service
# account (not the Compute Engine default) and pushes to one shared repository.

resource "google_artifact_registry_repository" "images" {
  repository_id = "agw-images"
  location      = var.region
  format        = "DOCKER"
  description   = "ai-gateways agent and gateway images"

  # Keep the 10 newest versions of each image; delete anything else older than 30 days.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s"
    }
  }

  depends_on = [time_sleep.api_propagation]
}

# Upstream gateway images (LiteLLM, ...) are published on ghcr.io, which Cloud Run
# cannot pull from. This remote repository proxies it: deploy
# <region>-docker.pkg.dev/<project>/agw-ghcr/<owner>/<image>@sha256:<digest>.
resource "google_artifact_registry_repository" "ghcr" {
  repository_id = "agw-ghcr"
  location      = var.region
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "ai-gateways pull-through cache of ghcr.io"

  remote_repository_config {
    description = "ghcr.io"
    docker_repository {
      custom_repository {
        uri = "https://ghcr.io"
      }
    }
  }

  depends_on = [time_sleep.api_propagation]
}

# Kong's OSS image (kong/kong) is published on Docker Hub, which this proxies the
# same way: <region>-docker.pkg.dev/<project>/agw-dockerhub/kong/kong@sha256:<digest>.
resource "google_artifact_registry_repository" "dockerhub" {
  repository_id = "agw-dockerhub"
  location      = var.region
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "ai-gateways pull-through cache of Docker Hub"

  remote_repository_config {
    description = "Docker Hub"
    docker_repository {
      public_repository = "DOCKER_HUB"
    }
  }

  depends_on = [time_sleep.api_propagation]
}

resource "google_service_account" "build" {
  account_id   = "agw-build"
  display_name = "ai-gateways Cloud Build"

  depends_on = [time_sleep.api_propagation]
}

resource "google_artifact_registry_repository_iam_member" "build_writer" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.build.member
}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = google_service_account.build.member
}

# Source tarballs uploaded by `gcloud builds submit --gcs-source-staging-dir`.
# A dedicated bucket keeps the build SA's read access off every other bucket
# in the (possibly shared) project.
resource "google_storage_bucket" "build_source" {
  name     = "${var.project_id}-ai-gateways-build-src"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.this]
}

resource "google_storage_bucket_iam_member" "build_source_reader" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.build.member
}
