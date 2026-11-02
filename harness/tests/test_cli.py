import json
import re

import pytest

from agw_harness import cli
from agw_harness.settings import load, require


def test_baseline_grid_matches_the_plan():
    grid = cli.baseline_grid(200, 50, ["direct", "agent"])
    assert len(grid) == 16  # 2 targets x 2 models x stream/no x c1/c5
    assert sum(c["n"] for c in grid) == 8 * 200 + 8 * 50
    assert {c["concurrency"] for c in grid} == {1, 5}


def test_run_name():
    assert cli.run_name("direct", "gemini", True, 5) == "direct-gemini-stream-c5"


@pytest.mark.parametrize(
    ("target", "env", "message"),
    [
        ("direct", {}, "AGW_PROJECT"),
        ("agent", {"AGW_PROJECT": "p"}, "AGW_AGENT_URL"),
        ("gateway", {"AGW_PROJECT": "p"}, "AGW_GATEWAY_URL"),
        (
            "gateway",
            {"AGW_GATEWAY_URL": "https://gw.example/v1", "AGW_GATEWAY_CLAUDE_API": "anthropic"},
            "AGW_PROJECT",
        ),
        ("proxy", {}, "target"),
    ],
)
def test_require_rejects_incomplete_targets(target, env, message):
    with pytest.raises(ValueError, match=message):
        require(load(env), target)


def test_gateway_claude_api_defaults_to_openai_and_is_validated():
    assert load({}).gateway_claude_api == "openai"
    with pytest.raises(ValueError, match="AGW_GATEWAY_CLAUDE_API"):
        load({"AGW_GATEWAY_CLAUDE_API": "native"})


def test_invalid_max_tokens_rejected():
    with pytest.raises(ValueError, match="AGW_MAX_TOKENS"):
        load({"AGW_MAX_TOKENS": "0"})


def test_one_run_writes_jsonl_and_summary(settings, tmp_path, monkeypatch):
    async def fake_run(proto, headers, **kwargs):
        from agw_harness.runner import Result

        return [Result(0, 0, 0.0, 200, True, 1.0, None, 5, 3, None, 9, None)], 1.0

    class FakeHeaders:
        async def get(self):
            return {}

    monkeypatch.setattr(cli.runner, "run", fake_run)
    import asyncio

    summary = asyncio.run(
        cli.one_run(
            settings,
            tmp_path,
            target="direct",
            model="claude",
            stream=False,
            concurrency=1,
            n=1,
            warmup=0,
            headers=FakeHeaders(),
        )
    )
    assert summary["model_name"] == "claude-haiku-5-5" and summary["ok"] == 1
    lines = (tmp_path / "direct-claude-nostream-c1.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["latency_s"] == 1.0
    assert (
        json.loads((tmp_path / "direct-claude-nostream-c1.summary.json").read_text())["run"]
        == summary["run"]
    )
    assert "direct-claude-nostream-c1" in cli.markdown_table([summary])


def fake_run_factory(ok=True):
    from agw_harness.runner import Result

    async def fake_run(proto, headers, **kwargs):
        r = Result(
            0,
            0,
            0.0,
            200 if ok else 500,
            ok,
            1.0,
            0.1 if ok else None,
            5,
            3,
            None,
            9,
            None if ok else "boom",
        )
        return [r], 1.0

    return fake_run


class FakeHeaders:
    created = []

    def __init__(self, target, settings):
        self.target = target
        FakeHeaders.created.append(target)

    async def get(self):
        return {}


@pytest.fixture
def fake_runner(monkeypatch, tmp_path):
    FakeHeaders.created = []
    monkeypatch.setattr(cli, "Headers", FakeHeaders)
    monkeypatch.setattr(cli.runner, "run", fake_run_factory())
    monkeypatch.setenv("AGW_PROJECT", "my-gcp-project")
    monkeypatch.setenv("AGW_AGENT_URL", "https://agent.example")
    monkeypatch.setenv("AGW_RESULTS_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("AGW_IMAGE", "img:1")
    return tmp_path / "out"


def only_run_dir(root):
    (d,) = list(root.iterdir())
    return d


def test_markdown_table_blank_ttft_for_non_stream_and_all_failures():
    from agw_harness.stats import summarize

    ok = {"run": "a", **summarize([], 1.0)}
    table = cli.markdown_table([ok])
    assert table.splitlines()[2].startswith("| a | 0/0 | None | None | None | None |")
    assert len(table.splitlines()) == 3 and table.endswith("\n")


def test_cmd_baseline_writes_summary_md_and_meta(fake_runner, capsys):
    rc = cli.main(["baseline", "--n-direct", "1", "--n-agent", "1", "--warmup", "0"])
    assert rc == 0
    out = only_run_dir(fake_runner)
    assert re.search(r"-baseline-[0-9a-f]{6}$", out.name)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["command"] == "baseline" and meta["run_id"] == out.name
    assert meta["image"] == "img:1" and meta["model_location"] == "eu"
    assert meta["thinking"] == {"gemini": "LOW", "claude": "off"}
    assert len(meta["grid"]) == 16
    md = (out / "summary.md").read_text()
    assert md.startswith(f"# Baseline {out.name}\n")
    assert md.count("| direct-") == 8 and md.count("| agent-") == 8
    assert len(list(out.glob("*.jsonl"))) == 16
    assert len(list(out.glob("*.summary.json"))) == 16
    assert "results:" in capsys.readouterr().out


def test_cmd_baseline_builds_one_headers_per_target(fake_runner):
    cli.main(["baseline", "--n-direct", "1", "--n-agent", "1", "--warmup", "0"])
    assert FakeHeaders.created == ["direct", "agent"]  # shared across the grid cells


def test_cmd_baseline_single_target(fake_runner):
    assert cli.main(["baseline", "--targets", "direct", "--warmup", "0"]) == 0
    out = only_run_dir(fake_runner)
    assert len(json.loads((out / "meta.json").read_text())["grid"]) == 8
    assert "| agent-" not in (out / "summary.md").read_text()


def test_cmd_baseline_fails_fast_on_missing_target_config(fake_runner, monkeypatch):
    monkeypatch.delenv("AGW_AGENT_URL")
    with pytest.raises(ValueError, match="AGW_AGENT_URL"):
        cli.main(["baseline"])
    assert not fake_runner.exists()  # nothing written before validation


def test_cmd_baseline_returns_1_when_any_run_fails(fake_runner, monkeypatch):
    monkeypatch.setattr(cli.runner, "run", fake_run_factory(ok=False))
    assert cli.main(["baseline", "--targets", "direct", "--warmup", "0"]) == 1
    # failed runs are still written so the failure is inspectable
    assert (only_run_dir(fake_runner) / "summary.md").exists()


def test_cmd_load_writes_meta_and_returns_0(fake_runner):
    rc = cli.main(
        ["load", "--target", "agent", "--model", "claude", "--n", "1", "--warmup", "0", "--stream"]
    )
    assert rc == 0
    out = only_run_dir(fake_runner)
    assert re.search(r"-agent-[0-9a-f]{6}$", out.name)
    assert json.loads((out / "meta.json").read_text())["command"] == "load"
    assert (out / "agent-claude-stream-c1.jsonl").exists()
    assert not (out / "summary.md").exists()  # only baseline writes it


def test_cmd_load_returns_1_when_no_request_succeeds(fake_runner, monkeypatch):
    monkeypatch.setattr(cli.runner, "run", fake_run_factory(ok=False))
    assert cli.main(["load", "--target", "direct", "--model", "gemini", "--warmup", "0"]) == 1


def test_main_rejects_unknown_target(fake_runner):
    with pytest.raises(SystemExit):
        cli.main(["load", "--target", "proxy", "--model", "gemini"])


def test_new_out_dir_is_timestamped_and_labelled(tmp_path):
    s = load({"AGW_RESULTS_DIR": str(tmp_path)})
    run_id, out = cli.new_out_dir(s, "x")
    assert out.is_dir() and out.name == run_id and re.search(r"Z-x-[0-9a-f]{6}$", run_id)
    assert out.parent == tmp_path


def test_failed_uses_the_error_rate_threshold():
    assert not cli.failed({"error_rate": 0.0})
    assert not cli.failed({"error_rate": cli.MAX_ERROR_RATE})
    assert cli.failed({"error_rate": cli.MAX_ERROR_RATE + 0.01})
    assert cli.failed({"error_rate": None})


def test_cmd_load_checks_config_before_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGW_RESULTS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="AGW_AGENT_URL"):
        cli.main(["load", "--target", "agent", "--model", "gemini"])
    assert list(tmp_path.iterdir()) == []


def test_cmd_baseline_survives_a_crashing_cell(fake_runner, monkeypatch):
    real = cli.runner.run
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("cell blew up")
        return await real(*args, **kwargs)

    monkeypatch.setattr(cli.runner, "run", flaky)
    rc = cli.main(["baseline", "--n-direct", "1", "--n-agent", "1", "--warmup", "0"])
    assert rc == 1
    md = (only_run_dir(fake_runner) / "summary.md").read_text()
    assert md.count("| direct-") + md.count("| agent-") == 16
    assert "| direct-gemini-nostream-c5 | 0/0 |" in md


# --- compare -----------------------------------------------------------------


def recording_run(calls):
    """A fake runner.run that records which protocol ran each block, and how."""
    from agw_harness.runner import Result

    async def fake_run(proto, headers, **kwargs):
        calls.append({"proto": type(proto).__name__, **kwargs})
        size, offset = kwargs["n"], kwargs.get("offset", 0)
        return [
            Result(offset + i, 0, 0.0, 200, True, 1.0, 0.1, 5, 3, None, 9, None)
            for i in range(size)
        ], 1.0

    return fake_run


def gateway_env(monkeypatch):
    monkeypatch.setenv("AGW_GATEWAY_URL", "https://gw.example")


def test_compare_grid_is_models_by_stream_by_concurrency():
    grid = cli.compare_grid([1, 5])
    assert len(grid) == 8
    assert {(c["model"], c["stream"], c["concurrency"]) for c in grid} == {
        (m, s, c) for m in ("gemini", "claude") for s in (False, True) for c in (1, 5)
    }


@pytest.mark.parametrize("flip", [False, True])
def test_compare_cell_abba_blocks_and_rewarms_each_block(fake_runner, monkeypatch, flip):
    import asyncio

    gateway_env(monkeypatch)
    calls = []
    monkeypatch.setattr(cli.runner, "run", recording_run(calls))
    settings = load()
    headers = {t: cli.Headers(t, settings) for t in ("direct", "gateway")}
    out = fake_runner
    out.mkdir()
    cell = {"model": "claude", "stream": False, "concurrency": 2}

    summaries = asyncio.run(
        cli.compare_cell(
            settings, out, cell, ["direct", "gateway"], headers, n=60, block=25, warmup=3, flip=flip
        )
    )

    a, b = ("OpenAIChat", "AnthropicNative") if flip else ("AnthropicNative", "OpenAIChat")
    # ABBA: the order reverses every block, so neither target is systematically earlier.
    assert [c["proto"] for c in calls] == [a, b, b, a, a, b]
    assert [c["n"] for c in calls] == [25, 25, 25, 25, 10, 10]
    assert [c["offset"] for c in calls] == [0, 0, 25, 25, 50, 50]
    # Full warm-up before the first block; then `concurrency` requests to reopen
    # connections that idled while the other target ran.
    assert [c["warmup"] for c in calls] == [3, 3, 2, 2, 2, 2]
    # One client per target, reused for all its blocks.
    by_proto = {}
    for c in calls:
        by_proto.setdefault(c["proto"], set()).add(id(c["client"]))
    assert all(len(ids) == 1 for ids in by_proto.values())
    assert [s["target"] for s in summaries] == ["direct", "gateway"]
    assert all(s["requests"] == 60 and s["blocks"] == 3 for s in summaries)
    assert summaries[0]["rewarm_per_block"] == 2 and len(summaries[0]["block_orders"]) == 3
    lines = (out / "gateway-claude-nostream-c2.jsonl").read_text().splitlines()
    assert [json.loads(line)["index"] for line in lines] == list(range(60))


def test_prewarm_hits_each_model_on_cloud_run_targets_and_retries(fake_runner, monkeypatch):
    import asyncio

    from agw_harness.runner import Result

    gateway_env(monkeypatch)
    statuses = iter([503, 200, 200])
    sent = []

    async def fake_send(client, proto, headers, index, stream):
        sent.append(type(proto).__name__)
        status = next(statuses)
        return Result(0, 0, 0.0, status, status == 200, 2.0, None, 1, 1, None, 3, None)

    monkeypatch.setattr(cli.runner, "send_one", fake_send)
    monkeypatch.setattr(cli, "PREWARM_RETRY_WAIT_S", 0)
    settings = load()
    headers = {t: cli.Headers(t, settings) for t in ("direct", "gateway")}
    log = asyncio.run(cli.prewarm(settings, ["direct", "gateway"], headers))
    assert sent == ["OpenAIChat"] * 3  # never direct; gemini retried once, then claude
    assert [(e["model"], e["attempt"], e["status"]) for e in log] == [
        ("gemini", 1, 503),
        ("gemini", 2, 200),
        ("claude", 1, 200),
    ]


def test_cmd_compare_writes_paired_summary_and_prewarm_meta(fake_runner, monkeypatch):
    gateway_env(monkeypatch)
    monkeypatch.setattr(cli.runner, "run", recording_run([]))

    async def no_prewarm(settings, targets, headers):
        return [{"target": "gateway", "model": "gemini", "attempt": 1, "status": 200}]

    monkeypatch.setattr(cli, "prewarm", no_prewarm)
    rc = cli.main(["compare", "--n", "4", "--block", "2", "--concurrency", "1", "--warmup", "0"])
    assert rc == 0
    run_dir = only_run_dir(fake_runner)
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["command"] == "compare" and meta["targets"] == ["direct", "gateway"]
    assert meta["prewarm"][0]["status"] == 200 and len(meta["grid"]) == 4
    md = (run_dir / "summary.md").read_text()
    assert "## Paired" in md and "| gemini-nostream-c1 | gateway |" in md
    assert len(list(run_dir.glob("*.summary.json"))) == 8


@pytest.mark.parametrize("targets", ["gateway", "direct,direct"])
def test_cmd_compare_needs_two_distinct_targets(fake_runner, monkeypatch, targets):
    gateway_env(monkeypatch)
    with pytest.raises(ValueError, match="two or more distinct"):
        cli.main(["compare", "--targets", targets])


def test_paired_table_reports_deltas_against_direct():
    def s(target, p50, p95, ttft):
        return {
            "target": target,
            "model": "gemini",
            "stream": True,
            "concurrency": 1,
            "latency_s": {"p50": p50, "p95": p95},
            "ttft_s": {"p50": ttft},
        }

    table = cli.paired_table([s("direct", 1.0, 2.0, 0.5), s("gateway", 1.25, 2.5, 0.6)])
    row = table.splitlines()[2]
    assert row.startswith("| gemini-stream-c1 | gateway | 1.0 | 1.25 | +0.250 |")
    assert "+0.500" in row and "+0.100" in row


@pytest.mark.parametrize(
    ("summary", "cell"),
    [
        # Native paths: missing means zero (Gemini omits zeros; Claude has thinking off).
        ({"target": "direct", "ok": 200, "thinking_reported": 0}, "0/200"),
        ({"target": "agent", "ok": 50, "thinking_reported": 3, "thinking_used": 3}, "3/50"),
        # Gateway: missing means unknown.
        ({"target": "gateway", "ok": 50, "thinking_reported": 0}, "unknown"),
        ({"target": "gateway", "ok": 50, "thinking_reported": 50, "thinking_used": 0}, "0/50"),
        (
            {"target": "gateway", "ok": 50, "thinking_reported": 10, "thinking_used": 2},
            "2/10 of 50",
        ),
    ],
)
def test_thinking_cell_keeps_missing_apart_from_zero_on_gateways(summary, cell):
    assert cli.thinking_cell(summary) == cell


def test_report_prints_tables_for_a_copied_run(tmp_path, capsys):
    from agw_harness.stats import summarize

    for target in ("direct", "gateway"):
        s = {
            "run": f"{target}-gemini-nostream-c1",
            "target": target,
            "model": "gemini",
            "stream": False,
            "concurrency": 1,
            **summarize([], 1.0),
        }
        (tmp_path / f"{s['run']}.summary.json").write_text(json.dumps(s))
    (tmp_path / "meta.json").write_text(json.dumps({"command": "compare", "run_id": "r1"}))
    assert cli.main(["report", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Compare r1") and "gateway-gemini-nostream-c1" in out


def test_report_without_summaries_fails(tmp_path):
    assert cli.main(["report", str(tmp_path)]) == 1


def test_block_order_is_abba_and_flips_per_cell():
    t, r = ["direct", "gateway"], ["gateway", "direct"]
    # Blocks run AB, BA, AB, BA: direct-gateway-gateway-direct-direct-gateway-...
    assert [cli.block_order(t, b, False) for b in range(4)] == [t, r, t, r]
    assert [cli.block_order(t, b, True) for b in range(2)] == [r, t]


def test_prewarm_logs_credential_failures_and_warns_when_nothing_succeeds(
    fake_runner, monkeypatch, capsys
):
    import asyncio

    gateway_env(monkeypatch)
    monkeypatch.setattr(cli, "PREWARM_RETRY_WAIT_S", 0)

    class BrokenHeaders:
        async def get(self):
            raise RuntimeError("gcloud not logged in")

    async def must_not_send(*args, **kwargs):
        raise AssertionError("sent without credentials")

    monkeypatch.setattr(cli.runner, "send_one", must_not_send)
    log = asyncio.run(cli.prewarm(load(), ["direct", "gateway"], {"gateway": BrokenHeaders()}))
    assert len(log) == 2 * cli.PREWARM_ATTEMPTS
    assert all(e["status"] == 0 and e["error"].startswith("auth:") for e in log)
    assert capsys.readouterr().out.count("WARN prewarm") == 2


def test_cmd_compare_crashing_cell_is_shown_and_fails_the_run(fake_runner, monkeypatch):
    gateway_env(monkeypatch)
    calls, raised = [], []
    good = recording_run(calls)

    async def flaky(proto, headers, **kwargs):
        # Once: the first gateway block of the second cell.
        if type(proto).__name__ == "OpenAIChat" and len(calls) >= 2 and not raised:
            raised.append(True)
            raise OSError("gcsfuse went away")
        return await good(proto, headers, **kwargs)

    monkeypatch.setattr(cli.runner, "run", flaky)

    async def no_prewarm(settings, targets, headers):
        return []

    monkeypatch.setattr(cli, "prewarm", no_prewarm)
    rc = cli.main(["compare", "--n", "2", "--block", "2", "--concurrency", "1", "--warmup", "0"])
    # The second cell (gemini stream, gateway first after the flip) raises.
    assert rc == 1
    md = (only_run_dir(fake_runner) / "summary.md").read_text()
    assert "| gateway-gemini-stream-c1 | 0/0 |" in md
    assert "| direct-gemini-stream-c1 | 0/0 |" in md
    assert "| gateway-claude-nostream-c1 | 2/2 |" in md  # later cells still ran


def test_paired_table_uses_the_given_baseline_and_shows_error_rates():
    def s(target, p50, err):
        return {
            "target": target,
            "model": "claude",
            "stream": False,
            "concurrency": 1,
            "latency_s": {"p50": p50, "p95": p50},
            "ttft_s": None,
            "error_rate": err,
        }

    table = cli.paired_table([s("gateway", 1.0, 0.0), s("agent", 1.5, 0.04)], "gateway")
    row = table.splitlines()[2]
    assert row.startswith("| claude-nostream-c1 | agent | 1.0 | 1.5 | +0.500 |")
    assert row.endswith("| 0.0% | 4.0% |")


def test_thinking_cell_treats_agent_behind_a_gateway_as_unknown():
    s = {"target": "agent", "ok": 50, "thinking_reported": 0, "agent_backend": "gateway"}
    assert cli.thinking_cell(s) == "unknown"
    assert cli.thinking_cell({**s, "agent_backend": "direct"}) == "0/50"


def test_report_orders_a_baseline_run_by_its_grid_and_recounts_thinking(tmp_path, capsys):
    from agw_harness.runner import Result
    from agw_harness.stats import summarize

    grid = cli.baseline_grid(2, 2, ["direct", "agent"])[:2]  # direct-gemini nostream c1, c5
    for cell in reversed(grid):  # written out of order on purpose
        name = cli.run_name(cell["target"], cell["model"], cell["stream"], cell["concurrency"])
        rows = [
            Result(0, 0, 0.0, 200, True, 1.0, None, 1, 1, 7, 1, None),
            Result(1, 1, 0.0, 200, True, 1.0, None, 1, 1, None, 1, None),
            Result(2, 2, 0.0, 500, False, 1.0, None, None, None, 9, 0, "boom"),
        ]
        (tmp_path / f"{name}.jsonl").write_text("\n".join(r.to_json() for r in rows) + "\n")
        summary = {"run": name, **cell, **summarize(rows, 1.0)}
        del summary["thinking_reported"], summary["thinking_used"]  # as in older runs
        (tmp_path / f"{name}.summary.json").write_text(json.dumps(summary))
    (tmp_path / "meta.json").write_text(json.dumps({"command": "baseline", "grid": grid}))

    assert cli.main(["report", str(tmp_path)]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("| direct")]
    assert [ln.split("|")[1].strip() for ln in lines] == [
        "direct-gemini-nostream-c1",
        "direct-gemini-nostream-c5",
    ]
    # Recounted from the lines: one of the two OK rows thought; the failed row is ignored.
    assert all(ln.rstrip().endswith("| 1/2 |") for ln in lines)


@pytest.mark.parametrize(
    ("env", "expected"), [({}, "openai"), ({"AGW_GATEWAY_CLAUDE_API": "anthropic"}, "anthropic")]
)
def test_write_meta_records_gateway_claude_api(tmp_path, env, expected):
    cli.write_meta(tmp_path, "r1", load({"AGW_PROJECT": "p", **env}), {})
    assert json.loads((tmp_path / "meta.json").read_text())["gateway_claude_api"] == expected
