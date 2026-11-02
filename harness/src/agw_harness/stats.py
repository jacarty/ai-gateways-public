"""Summary statistics over a run's measured results."""

import math
from collections.abc import Sequence

from agw_harness.runner import Result


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize(results: Sequence[Result], wall_s: float) -> dict:
    ok = [r for r in results if r.ok]
    latency = [r.latency_s for r in ok]
    ttft = [r.ttft_s for r in ok if r.ttft_s is not None]
    # Failed requests that were actually sent (auth failures never were: latency 0).
    # A gateway that fails slow requests fast would look faster on `latency_s` alone.
    latency_all = [r.latency_s for r in results if r.latency_s > 0]
    out_tokens = [r.output_tokens for r in ok if r.output_tokens is not None]
    # Only responses that report thinking. Native Gemini/agent parsing maps an omitted field to 0
    # (Gemini omits zeros); an OpenAI-format gateway that drops it stays "unknown", not 0.
    thinking = [r.thinking_tokens for r in ok if r.thinking_tokens is not None]
    return {
        "requests": len(results),
        "ok": len(ok),
        "error_rate": round(1 - len(ok) / len(results), 4) if results else None,
        "wall_s": round(wall_s, 3),
        "throughput_rps": round(len(ok) / wall_s, 3) if wall_s > 0 else None,
        "latency_s": {
            "p50": percentile(latency, 50),
            "p95": percentile(latency, 95),
            "p99": percentile(latency, 99),
            "mean": _mean(latency),
        },
        "latency_all_s": {
            "p50": percentile(latency_all, 50),
            "p95": percentile(latency_all, 95),
            "p99": percentile(latency_all, 99),
        },
        "ttft_s": {"p50": percentile(ttft, 50), "p95": percentile(ttft, 95), "mean": _mean(ttft)}
        if ttft
        else None,
        "output_tokens_mean": _mean(out_tokens),
        "thinking_tokens_mean": _mean(thinking),
        "thinking_reported": len(thinking),
        "thinking_used": sum(1 for t in thinking if t > 0),
        "errors": sorted({r.error for r in results if r.error})[:5],
    }
