# ai-gateways

A lab for playing with AI gateways: build, run and break three open-source ones on GCP, one at a time, in front of the same small agent, to learn how each is set up and how it behaves.

It's a learning project, not a benchmark. Each gateway goes through the same seven tests so there's something concrete to poke at, and the notes and numbers record what happened in this one project, region and set of short runs.

> **Status:** Phases 0 (Setup), 1 (LiteLLM), 2 (Bifrost) and 3 (Kong OSS) are complete: all three gateways have run the seven-test matrix, and every gateway stack is destroyed. Results are in [results/summary.md](results/summary.md), starting with a [side-by-side table](results/summary.md#across-the-three-gateways) and its OSS ceiling; [takeaways](docs/takeaways.md) sums up what each gateway turned out to be good at. Phase 4, the write-up, adds those two, an [architecture layout](docs/architecture.md) and a [setup guide](docs/setup-guide.md). Plan: [docs/plan-v0.1.md](docs/plan-v0.1.md).

**Deploy it yourself:** [docs/setup-guide.md](docs/setup-guide.md) takes a fresh clone to a running lab in your own GCP project.

## The gateways

| # | Gateway | Hosting |
|---|---------|---------|
| 1 | [LiteLLM](https://github.com/BerriAI/litellm) (OSS) | Cloud Run |
| 2 | [Bifrost](https://github.com/maximhq/bifrost) (OSS) | Cloud Run |
| 3 | [Kong](https://github.com/Kong/kong) OSS | Cloud Run |

Each one sits between a small ADK agent and Gemini Enterprise Agent Platform (formerly Vertex AI), serving Gemini 3.8 Flash and Claude Haiku 5.5 on the EU multi-region endpoint. A direct-to-model path is the baseline. Everything is deployed in `europe-west1`. Only agent-to-model traffic is in scope, and only the free OSS editions are used.

## The tests

Every gateway runs the same seven tests:

1. **Overhead:** added latency (p50/p95), streaming time to first token (TTFT), throughput
2. **Routing and failover:** Gemini to Claude and back, on a forced error or 429
3. **Cost control:** token budgets and rate limits, and whether they are hard or advisory
4. **Inline screening:** whether prompt-injection and PII cases are blocked, logged or invisible
5. **Identity and secrets:** keys vs workload identity
6. **Audit fidelity:** whether the logs can reconstruct a single agent run
7. **OSS ceiling:** what needed a paid tier

## Layout

- [foundation/](foundation/README.md): persistent Terraform stack (APIs, budget, service accounts, state)
- [agent/](agent/README.md): the one ADK agent on Cloud Run
- [harness/](harness/README.md): the load harness, run as a Cloud Run job
- [results/](results/summary.md): committed raw runs and the results table
- `scripts/build-image.sh`: the only way images are built (Cloud Build, by digest); the root `Makefile` wraps each gateway's deploy, start/stop, UI proxy and destroy
- `gateways/`: one folder per gateway (`litellm/`, `bifrost/`, `kong/`), each with a "how it works" note, a README, a test notebook and its Terraform stack

## What came out of it

- A "how it works" note per gateway
- A [results table](results/summary.md#across-the-three-gateways) with an OSS-ceiling table, with raw output committed
- [Takeaways](docs/takeaways.md): what each gateway turned out to be good at
- An [architecture layout](docs/architecture.md): what runs where, identities, network and Terraform stacks

## Repo docs

- [docs/plan-v0.1.md](docs/plan-v0.1.md): scope, architecture, milestones, risks
- [docs/setup-guide.md](docs/setup-guide.md): deploy the lab in your own GCP project, step by step
- [docs/architecture.md](docs/architecture.md): components, request paths, identities and roles, network, Terraform stacks
- [docs/day1-checks.md](docs/day1-checks.md): pre-build research on regions, models and OSS editions
- [docs/takeaways.md](docs/takeaways.md): what each gateway turned out to be good at, from the results
- [docs/decisions/](docs/decisions/README.md): architecture decision records
- [AGENTS.md](AGENTS.md): context for coding agents working in this repo

## Licence

[MIT](LICENSE)
