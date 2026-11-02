# 0009. Set model prices explicitly in gateway configs

- Status: Accepted
- Date: 2026-10-18

## Context

Test 3 (cost control) depends on the gateway pricing each request: a dollar budget is enforced against the gateway's own spend figure. LiteLLM computes that from a built-in price map. Checked against the Cloud Billing SKU catalogue and the Agent Platform pricing page, v1.103.2's map has every Gemini 3.8 Flash tier at half the real price, and has no entry for Haiku 5.5 at all. LiteLLM treats a model with no price as having a cost (budgets still apply; only an explicit price of 0 skips them), but its spend figure for such a model can't be right.

## Decision

Gateway configs set `input_cost_per_token` and `output_cost_per_token` on each model (`gateways/litellm/config/config.yaml`). Prices come from the Cloud Billing catalogue (read with `cloudbilling.googleapis.com`, enabled in `foundation/`) and the Agent Platform pricing page, for the EU multi-region endpoint, with the date checked in a comment. A price set in the config replaces the map entry, including any regional uplift the map applies. The notebook's price check compares LiteLLM's cost for a request with its tokens times the configured price; the configured prices themselves are checked by hand against the catalogue and pricing page.

## Consequences

- Budgets and spend logs are only as right as these numbers. They need a re-check when a model, a price or the gateway version changes.
- The wrong map is a finding for the write-up: a gateway's cost control trusts a price table the operator does not control by default.
- Other gateways get the same treatment in their phases, if they price requests.
- Short-prompt prices only; tiered prices for long prompts are not modelled (the test prompts are short).

## Alternatives considered

- **Trust the built-in map:** spend would read at half price for Gemini and have no basis for Haiku, and test 3's budget results would be wrong without any sign of it.
- **Patch or pin a newer gateway version:** the map is a moving target and the upstream fix is outside this project; explicit prices are visible in the config and testable.
