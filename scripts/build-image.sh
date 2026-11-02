#!/bin/sh
#
# Build and push an image with Cloud Build, tagged with the current commit, then
# print the digest-pinned `image = ...` line for <component>/terraform/terraform.tfvars.
#
#   scripts/build-image.sh agent
#   scripts/build-image.sh harness
#
# <component>/ must hold a Dockerfile and cloudbuild.yaml (with an _IMAGE substitution).
# Refuses to build uncommitted changes, so a tag always names exactly what is in the
# image (gcloud uploads the working tree, not the commit).

set -eu

COMPONENT=${1:?usage: scripts/build-image.sh <component>}
PROJECT=${AGW_PROJECT:-my-gcp-project}
REGION=${AGW_REGION:-europe-west1}

cd "$(git rev-parse --show-toplevel)"

if [ ! -f "$COMPONENT/cloudbuild.yaml" ]; then
    echo "✗ $COMPONENT/cloudbuild.yaml not found" >&2
    exit 1
fi

if ! git diff --quiet HEAD -- "$COMPONENT" || [ -n "$(git ls-files --others --exclude-standard "$COMPONENT")" ]; then
    echo "✗ $COMPONENT/ has uncommitted changes (staged or not): commit them first." >&2
    git status --short "$COMPONENT" >&2
    exit 1
fi

REPO=$(terraform -chdir=foundation/terraform output -raw image_repository)
BUILD_SA=$(terraform -chdir=foundation/terraform output -raw build_service_account)
SRC_BUCKET=$(terraform -chdir=foundation/terraform output -raw build_source_bucket)
TAG=$(git rev-parse --short HEAD)
IMAGE="$REPO/$COMPONENT:$TAG"

echo "Building $IMAGE"
gcloud builds submit "$COMPONENT" \
    --project "$PROJECT" --region "$REGION" \
    --config "$COMPONENT/cloudbuild.yaml" \
    --substitutions "_IMAGE=$IMAGE" \
    --service-account "$BUILD_SA" \
    --gcs-source-staging-dir "gs://$SRC_BUCKET/source"

DIGEST=$(gcloud artifacts docker images describe "$IMAGE" --format='value(image_summary.digest)')
echo
echo "Put this in $COMPONENT/terraform/terraform.tfvars:"
echo "image = \"$REPO/$COMPONENT@$DIGEST\"  # tag $TAG"
