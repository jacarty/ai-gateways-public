# 0007. Pair every gateway run with a same-job direct baseline

- Status: Accepted
- Date: 2026-10-14

## Context

Two baseline runs about 1.5 hours apart (`results/summary.md`) showed Claude moving by tens of milliseconds but Gemini's p95 moving by up to 11 s in either direction. Direct Gemini had 8-31 s outliers with no thinking, and in the second run the agent cells, run about 20 minutes after the direct ones, were faster than direct. Cells run one after another, so they absorb that upstream drift.

## Decision

A gateway's numbers are compared only against a direct baseline measured in the same job. Compare Gemini on p50 and TTFT p50 rather than the tail; Claude is the stable signal for overhead. The earlier baseline stays as a reference and as evidence of variance, not as the comparison point.

## Consequences

- The harness needs a way to run direct and gateway cells together, ideally interleaved request by request.
- Gateway runs cost more requests and time.
- Gemini tail percentiles carry a caveat in any write-up.

## Implementation (2026-10-17)

The harness `compare` command implements this. Instead of interleaving request by request, the targets take turns in blocks within each cell, with the order reversed every block (ABBA) and the starting target flipped per cell; each block is re-warmed, and Cloud Run targets are pre-warmed per model before measuring. The summary pairs each target against the first. See `harness/README.md`.
