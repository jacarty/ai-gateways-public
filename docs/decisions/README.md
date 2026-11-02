# Architecture decision records

Significant decisions taken during implementation that are not already settled in the plan. Format: Context / Decision / Consequences. Add new ones as `NNNN-short-title.md` and list them here.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-scope-three-oss-gateways.md) | Scope: three OSS gateways, agent-to-model traffic only | Accepted |
| [0002](0002-region-and-model-endpoints.md) | Deploy in europe-west1; both models on the EU multi-region endpoint | Accepted |
| [0003](0003-agent-on-cloud-run.md) | Host the ADK agent on Cloud Run | Accepted |
| [0004](0004-images-via-cloud-build-by-digest.md) | Build with Cloud Build, deploy by digest, refuse dirty trees | Accepted |
| [0005](0005-thinking-fixed-test-condition.md) | Fix the thinking condition: Gemini LOW, Claude off | Accepted |
| [0006](0006-harness-design.md) | Harness design: native APIs for direct, one client, Cloud Run job | Accepted |
| [0007](0007-paired-baselines.md) | Pair every gateway run with a same-job direct baseline | Accepted |
| [0008](0008-gateway-access-and-litellm-state.md) | Gateway access and LiteLLM state: IAM-authenticated, Cloud SQL, own stack, agw-ghcr | Accepted |
| [0009](0009-explicit-model-prices.md) | Set model prices explicitly in gateway configs | Accepted |
| [0010](0010-behaviour-tests-config-windows.md) | Behaviour tests use config windows, throwaway keys and local runs | Accepted |
| [0011](0011-shared-screening-case-set.md) | One gateway-neutral screening case set, classified by outcome | Accepted |
| [0012](0012-audit-trail-collector.md) | Test 6 reconstructs a run with a trail collector that commits only redacted flags | Accepted |
| [0013](0013-bifrost-state-and-keys.md) | Bifrost: Postgres for both stores, config.json as source of truth, Terraform-generated virtual keys | Accepted |
| [0014](0014-kong-claude-path-and-keys.md) | Kong: Claude as a native pass-through, Bearer keys, throwaway keys by redeploy | Accepted; keys-by-redeploy superseded by 0015 |
| [0015](0015-kong-postgres-and-deck.md) | Kong: Postgres, decK as source of truth, throwaway keys through the Admin API | Accepted |
| [0016](0016-private-network-for-gateway-databases.md) | A private network for gateway databases; Kong reaches Postgres by private IP | Accepted |
| [0017](0017-kong-audit-collector-cloud-logging.md) | Kong's test 6 trail is collected from Cloud Logging only and joined by request id and trace | Accepted |
