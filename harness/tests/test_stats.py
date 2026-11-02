from agw_harness.runner import Result
from agw_harness.stats import percentile, summarize


def result(latency, ok=True, ttft=None, out=10, think=None, error=None):
    return Result(0, 0, 0.0, 200 if ok else 500, ok, latency, ttft, 5, out, think, 20, error)


def test_nearest_rank_percentile():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile(values, 100) == 100
    assert percentile([7], 99) == 7
    assert percentile([], 50) is None


def test_summary_counts_only_successful_latencies():
    results = [result(1.0), result(2.0), result(9.9, ok=False, error="boom")]
    s = summarize(results, wall_s=2.0)
    assert s["requests"] == 3 and s["ok"] == 2
    assert s["error_rate"] == round(1 / 3, 4)
    assert s["latency_s"]["p50"] == 1.0 and s["latency_s"]["p95"] == 2.0
    assert s["throughput_rps"] == 1.0
    assert s["ttft_s"] is None
    assert s["errors"] == ["boom"]


def test_summary_reports_ttft_and_thinking():
    s = summarize([result(1.0, ttft=0.2, think=3), result(1.0, ttft=0.4)], wall_s=1.0)
    assert s["ttft_s"]["p50"] == 0.2
    # Only responses that report thinking count; the other is "unknown", not 0.
    assert s["thinking_tokens_mean"] == 3 and s["thinking_reported"] == 1


def test_latency_all_includes_failed_requests_that_were_sent():
    timed_out = result(60.0, ok=False, error="ReadTimeout")
    never_sent = result(0.0, ok=False, error="auth: boom")
    s = summarize([result(1.0), result(1.0), timed_out, never_sent], wall_s=1.0)
    assert s["latency_s"]["p99"] == 1.0
    assert s["latency_all_s"]["p99"] == 60.0
    assert s["requests"] == 4 and s["ok"] == 2


def test_percentile_edges_and_unsorted_input():
    assert percentile([3, 1, 2], 50) == 2
    assert percentile([1, 2, 3, 4], 50) == 2  # nearest rank, not interpolated
    assert percentile([1, 2, 3, 4], 0) == 1
    assert percentile([5, 1], 100) == 5


def test_summary_single_result():
    s = summarize([result(0.5, ttft=0.1)], wall_s=0.5)
    assert s["latency_s"] == {"p50": 0.5, "p95": 0.5, "p99": 0.5, "mean": 0.5}
    assert s["ttft_s"]["p95"] == 0.1
    assert s["error_rate"] == 0.0 and s["throughput_rps"] == 2.0


def test_summary_all_failures_has_no_latency_stats():
    s = summarize([result(1.0, ok=False, error="a"), result(2.0, ok=False, error="b")], 1.0)
    assert s["ok"] == 0 and s["error_rate"] == 1.0 and s["throughput_rps"] == 0.0
    assert s["latency_s"] == {"p50": None, "p95": None, "p99": None, "mean": None}
    assert s["ttft_s"] is None
    assert s["output_tokens_mean"] is None and s["thinking_tokens_mean"] is None
    assert s["errors"] == ["a", "b"]


def test_summary_no_results():
    s = summarize([], wall_s=1.0)
    assert s["requests"] == 0 and s["error_rate"] is None and s["latency_s"]["p50"] is None


def test_summary_zero_wall_time_has_no_throughput():
    assert summarize([result(1.0)], wall_s=0)["throughput_rps"] is None


def test_summary_errors_are_deduplicated_sorted_and_capped():
    results = [result(1.0, ok=False, error=f"e{i % 7}") for i in range(20)]
    assert summarize(results, 1.0)["errors"] == ["e0", "e1", "e2", "e3", "e4"]


def test_summary_excludes_failed_ttft_and_tokens():
    results = [result(1.0, ttft=0.2, out=10), result(9.0, ok=False, ttft=5.0, out=999)]
    s = summarize(results, 1.0)
    assert s["ttft_s"]["mean"] == 0.2 and s["output_tokens_mean"] == 10


def test_thinking_used_counts_requests_with_any_thinking():
    rs = [
        Result(i, 0, 0.0, 200, True, 1.0, None, 1, 1, t, 1, None)
        for i, t in enumerate([0, 5, None, 12])
    ]
    s = summarize(rs, 1.0)
    assert s["thinking_reported"] == 3 and s["thinking_used"] == 2
