# foundation

The persistent stack: enabled APIs, the budget and alert, the Terraform state bucket, the image repository and build account, the results bucket, and service accounts for the agent, each gateway and the harness. It is applied once and kept for the life of the project. Every other stack stores its state in the bucket this one creates.

It deploys into **`my-gcp-project`**, a lab project kept separate from workstation projects. The project may hold other work, so the stack only adds to it: IAM bindings are additive, APIs stay enabled on destroy, and names are prefixed (`agw-`, `-ai-gateways-tfstate`).

## What it creates

| Resource | Purpose |
| --- | --- |
| Project APIs | Agent Platform, Cloud Run, Artifact Registry, Cloud Build, Secret Manager, Logging, Monitoring, Billing Budgets, IAM, IAM Credentials, Resource Manager, Service Usage, Storage, Cloud Billing (read the public SKU price catalogue, to check gateway model prices) |
| Billing budget + email channel | Alerts at 50%, 90%, 100% actual and 100% forecast, on gross cost (credits excluded). Alerts only: it does not cap spend, and billing data lags by hours. Covers **all** spend in the project, not just this lab |
| `<project>-ai-gateways-tfstate` bucket | Versioned, private remote state for every stack, one prefix each |
| `agw-agent` service account | The agent: `aiplatform.user`, `logging.logWriter` |
| `agw-images` Artifact Registry repo | Docker images for the agent and any custom gateway images; keeps the 10 newest per image |
| `agw-build` service account + `<project>-ai-gateways-build-src` bucket | Cloud Build runs as `agw-build` (Artifact Registry writer on `agw-images`, log writer), reading source only from its own staging bucket (deleted after 7 days) |
| `agw-harness` service account + `<project>-ai-gateways-results` bucket | The load harness job runs as `agw-harness` (the agent's roles, so the direct baseline can call the models), with `storage.objectUser` on the results bucket, which the job mounts. The bucket has no `force_destroy`: runs are evidence |
| `agw-gw-<gateway>` service accounts | One per gateway, so logs can tell them apart: the agent's roles plus `secretmanager.secretAccessor`, limited by an IAM condition to its own secrets, named `agw-<gateway>-*` |

## Prerequisites

- A GCP project linked to a billing account.
- `gcloud auth application-default login` as a user with Owner on the project, plus `roles/billing.costsManager` (or Billing Account Administrator) on the billing account for the budget.
- The billing account's currency, for `budget_currency`.
- Resource Manager and Service Usage enabled, since the stack reads the project before it enables anything. They are on by default in most projects; if not:

  ```bash
  gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project my-gcp-project
  ```

## First apply (local state)

The stack creates its own state bucket, so on a brand-new project the first apply uses local state: comment out the `backend "gcs"` block in `terraform/backend.tf` first. (In this repo it is already applied and the block is live.)

```bash
cd foundation/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in
terraform init
terraform apply
```

The apply waits 60s after enabling APIs so they can propagate. If it still fails with a transient 403 or "service account does not exist", run `terraform apply` again.

Check that the budget alert email arrived or that the budget shows in Billing → Budgets & alerts. No other stack deploys until it does.

## Migrate to remote state

```bash
cp backend.hcl.example backend.hcl   # bucket = $(terraform output -raw state_bucket)
# uncomment the backend block in backend.tf again
terraform init -migrate-state -force-copy -backend-config=backend.hcl
```

Init must print `Successfully configured the backend "gcs"` and ask nothing about a missing backend block. Then run `terraform plan` and confirm **No changes**. Only after that, delete the local `terraform.tfstate*` files. Run each command on its own, not pasted together.

Other stacks use the same `backend.hcl` with their own `prefix` in their backend block, e.g. `gateways/litellm`.

## Destroying

The state bucket has `prevent_destroy`, so `terraform destroy` on this stack fails by design. To tear the project down, remove the `lifecycle` block in `state.tf` first, after every other stack is destroyed.

## After the apply: day-1 checks

On a new project, check these before deploying anything that calls the models (see `docs/day1-checks.md`; both are done for `my-gcp-project`):

- Claude Haiku 5.5 quota on the EU multi-region endpoint: IAM & Admin → Quotas, filter "anthropic". Request an increase if it is 0.
- Claude Haiku 5.5 enabled in Model Garden. Partner models may need accepting the terms in the console, which can need `roles/consumerprocurement.entitlementManager`.
