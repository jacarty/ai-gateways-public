# 0010. Behaviour tests use config windows, throwaway keys and local runs

- Status: Accepted
- Date: 2026-10-18

## Context

Tests 2 (failover) and 3 (cost control) need things the measured config must not have: fallbacks would let Claude answer a failed Gemini request in a `compare` run and count it as a Gemini success; mock flags let any key holder force failures; a test-only model or throttle setting changes behaviour for every key. Test 3 also needs keys with tiny limits, and the harness job mounts one fixed key secret.

## Decision

- **Measured runs stay on the committed config** and run as the `agw-harness` job. Behaviour tests are not measurements.
- **Behaviour tests use a config window:** the extra config is added to `config.yaml` for the test only, deployed, and removed again afterwards (`git diff` shows only the additions; a check confirms the gateway is back to normal). Each scenario README gives the exact lines and the close-down steps.
- **Test 3 uses throwaway keys.** `harness/scenarios/<gw>/run-cost.sh` mints a key with the run's limits, runs the scenario file locally with it and deletes it on exit; the notebook does the same in memory. The harness and agent keys are never used.
- **Scenario runs are local** (`AGW_ID_TOKEN_SOURCE=gcloud`), recorded with a `--note` naming the live revision and settings, and the raw output is committed to `results/raw/<gateway>/`.

## Consequences

- A window left open changes behaviour for every key, so closing it is a step in each README, not an afterthought.
- Scenario runs depend on the operator's gcloud identity and a running gateway; the job path exists but needs an image rebuilt after the scenario files change.
- Every test starts from a fresh key, so no spend or rate-limit window carries over.
- Window-dependent cases are noted as such in the OSS-ceiling write-up.

## Alternatives considered

- **Leave fallbacks and mocks on in the committed config:** simpler, but contaminates every measured run.
- **A second gateway deployment for behaviour tests:** cleaner isolation, but doubles the stack (Cloud SQL included) and the spend for config that lasts minutes.
- **Reuse the harness key with a lowered budget:** changes the key measured runs depend on and leaves spend behind.
