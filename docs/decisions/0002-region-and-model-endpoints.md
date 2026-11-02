# 0002. Deploy in europe-west1; call both models on the EU multi-region endpoint

- Status: Accepted
- Date: 2026-10-14

## Context

The first plan used London (`europe-west2`). Day-1 checks (`docs/day1-checks.md`) found that Claude Haiku 5.5 has only US multi-region, EU multi-region and global endpoints, with no single-region endpoints, and that Haiku 4.5 (which has `europe-west1`) retires from 2026-10-15. Gemini Flash in `europe-west2` was unreliable (residency table versus reports of 404s). `gemini-3.8-flash` turned out to have no `europe-west1` endpoint either, only global and `us`/`eu` multi-region.

## Decision

All deployed resources (Cloud Run, Artifact Registry, buckets) live in Belgium, `europe-west1`. Both models are called on the EU multi-region endpoint: `GOOGLE_CLOUD_LOCATION=eu`, host `aiplatform.eu.rep.googleapis.com`. Models are `gemini-3.8-flash` and `claude-haiku-5-5`. Haiku 4.5 is not used.

## Consequences

- One model endpoint for every path, which helps comparability.
- Model calls leave the region for the EU multi-region, so the model hop is the same for baseline and gateways but not co-located.
- Claude quota on the EU multi-region endpoint was confirmed working for `my-gcp-project` (the agent's first `claude` call answered).
