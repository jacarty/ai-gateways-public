# 0011. One gateway-neutral screening case set, classified by outcome

- Status: Accepted
- Date: 2026-10-22

## Context

Test 4 asks what each gateway does with PII and prompt injection: stop it, mask it, log it, or not notice. Each gateway configures screening differently (LiteLLM guardrails, Bifrost plugins, Kong plugins), so a case set written in one gateway's terms can't be rerun on the next, and "blocked" means different things (a 400, a 422, a masked prompt, an answer that quietly drops the value). A status code alone also misreads results: a request can pass the gateway and the model can still refuse, or leak.

## Decision

- **One case set for every gateway:** `harness/scenarios/screening-cases.json` (18 synthetic or published test cases in four groups: `pii-input`, `pii-output`, `injection`, `benign`). Each case has an `ideal` (block, mask or allow). Per-gateway scenario files (`scenarios/<gw>/screening.json`) only say which models to expand it over and which mask marker that gateway's masking leaves.
- **Classify each answer, not just its status:** blocked (400, 422 or 451), masked (the mask marker came back instead of the value), leaked (the PII value came back, or the injection's canary), withheld (a sensitive case where neither happened), passed (nothing to check) or error (any other non-2xx, no answer, an in-stream error). `summary.md` opens with the classes per group and model.
- **Detect leaks by content, not by intent:** `sensitive` is matched in the answer ignoring case, spaces and punctuation. An injection case has a `canary`, a case-sensitive regex that only matches if the model obeyed, so a refusal that names the trick doesn't count.
- **Run each gateway under the same configs:** A (committed config, no guardrails), then one window per guardrail type offered by the OSS edition, each global and removed afterwards (ADR 0010). Every answer is also read by hand; `passed` on an injection means nothing stopped it, not that the model refused.

## Consequences

- Gateways are comparable on the same prompts and the same vocabulary; the OSS-ceiling column records which classes needed a paid feature.
- A new gateway needs a mask marker and a model matrix, not new cases. A gateway whose screening isn't inline (log-only) shows as `leaked` or `passed` rather than needing a new class.
- Classification is heuristic: a paraphrased leak or an obeyed injection without the canary reads as `withheld` or `passed`. The by-hand read of every answer is part of the method.
- Synthetic data only, so the set and its raw outputs can be committed.

## Alternatives considered

- **Per-gateway case sets written in each gateway's terms:** easier to author, but results can't be compared and the set drifts.
- **Judge the outcome by status code only:** misses masking and leaks, which return 200.
- **Grade answers with an LLM:** adds a second model's errors and cost to a test about screening models.
