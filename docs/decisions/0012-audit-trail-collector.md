# 0012. Test 6 reconstructs a run with a trail collector that commits only redacted flags

- Status: Accepted
- Date: 2026-10-22

## Context

Test 6 asks whether the logs can reconstruct one agent run: which request, which key, which model, what it cost, whether a refusal left a record. The evidence sits in several places (the gateway's spend log in its database, the gateway's and agent's Cloud Run request and container logs) and has no shared id by default. Some of it is sensitive: with `store_prompts_in_spend_logs` the spend log keeps prompts, answers and the caller's Google ID token, and logs carry keys, key hashes, IP addresses and personal email addresses. Raw output is normally committed (`results/raw/`), so a naive dump would commit credentials.

## Decision

- **Collect with a script, not by hand:** `harness/scenarios/<gw>/audit_trail.py` (standard library only, called by `run-audit.sh`) reads the run's `outcomes.jsonl`, then fetches for the run's time window the gateway's spend-log rows and the Cloud Run logs of the gateway and the agent, and tries to join them. The join keys are the gateway's call id (response header), else the caller's own tag (`spend_logs_metadata`, since refusals may carry no call id), else, for the agent's own call, key alias and time. Whether each request joined, and by what, is the finding; the script retries until every request appears (spend logs are written in batches, Cloud Logging ingests late) and says which never did.
- **Test with a cooperating caller and an uncooperating one:** harness requests carry a session id and tags; one request goes through the agent unchanged (it tags nothing). The gap between the two is the result.
- **Commit evidence redacted, content as flags:** `trail.json` and `trail.md` are written into the run directory with tokens, keys, key hashes, API keys and personal email addresses replaced, IP addresses reduced to their kind, and prompts, answers and tokens reduced to flags (marker present, ID token present). Service-account addresses, user agents, traces, endpoints and caller metadata stay as values. Run through the same redaction as the other raw output; the secrets scanner still runs at commit.
- **Run in configs, as in ADR 0010:** A (committed), D (`store_prompts_in_spend_logs`), C (the LLM judge), so the finding covers what an operator has by default and what a switch changes.

## Consequences

- The trail can be committed and re-read without holding anything secret; the cost is that the raw values aren't in git, so a changed redaction needs a rerun.
- Rows written while a content-storing window is open persist in the gateway's database until `make destroy-<gw>`; that, not the repo, is where the sensitive copy lives.
- The collector is per gateway: its fetch calls are LiteLLM's. A later gateway reuses the method and the redactions, not the code.
- The test reflects a cooperating caller; it can't show what a hostile caller leaves, only what logs record about an honest one.

## Alternatives considered

- **Read the logs by hand in the notebook:** kept as the by-hand route, but not repeatable or committable.
- **Commit raw log exports:** richest evidence, but would put ID tokens, keys and personal addresses in git.
- **Add tracing to the agent so everything joins:** would measure our instrumentation, not what the gateway gives an operator who changes nothing.
