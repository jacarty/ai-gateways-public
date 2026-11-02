# 0004. Build images with Cloud Build, deploy by digest, refuse dirty trees

- Status: Accepted
- Date: 2026-10-14

## Context

The workstation has no Docker. Image tags are mutable, and `gcloud builds submit` uploads the working tree rather than a commit, so a tag could name code that is not in git.

## Decision

`scripts/build-image.sh <component>` is the only way images are built. It refuses to run when `<component>/` has uncommitted or untracked changes, runs Cloud Build as the dedicated `agw-build` service account (source staged in its own bucket), tags the image with the short commit, and prints the digest-pinned `image = "...@sha256:..."` line. Terraform stacks take that digest, and the agent's variable rejects a tag. Dockerfile bases and the Cloud Build builder are pinned by digest. Images go to the `agw-images` Artifact Registry repository, which keeps the 10 newest versions per image.

## Consequences

- A deployed image maps to exactly one commit.
- Commit before you build; a build needs `foundation/terraform` initialised, since the script reads its outputs.
- Digest-pinned bases get no OS patches until bumped.
- Tags stay mutable; digests make that safe.
