"""Command line: one run (`load`), the Phase 0 baseline grid (`baseline`), a paired
direct-versus-gateway comparison (`compare`), a summary table for a run (`report`), or
scripted gateway cases checked against expectations (`scenarios`, tests 2-6).

  python -m agw_harness.cli load --target direct --model gemini --n 200 -c 5 --stream
  python -m agw_harness.cli baseline
  python -m agw_harness.cli compare --targets direct,gateway
  python -m agw_harness.cli report results/raw/litellm/<run_id>
  python -m agw_harness.cli scenarios scenarios/litellm/failover.json

Each measured run writes <results_dir>/<run_id>/<target>-<model>-<stream|nostream>-c<N>.jsonl
(one line per measured request) and a matching .summary.json; `baseline` and `compare` also
write summary.md. `scenarios` writes meta.json, outcomes.jsonl and summary.md.
"""

import argparse
import asyncio
import dataclasses
import json
import math
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agw_harness import runner, scenarios, stats
from agw_harness.auth import Headers
from agw_harness.protocols import protocol_for
from agw_harness.settings import MODELS, TARGETS, Settings, load, require


def run_name(target: str, model: str, stream: bool, concurrency: int) -> str:
    return f"{target}-{model}-{'stream' if stream else 'nostream'}-c{concurrency}"


async def one_run(
    settings: Settings,
    out_dir: Path,
    *,
    target: str,
    model: str,
    stream: bool,
    concurrency: int,
    n: int,
    warmup: int,
    headers: Headers | None = None,
) -> dict:
    require(settings, target)
    proto = protocol_for(target, model, settings)
    headers = headers or Headers(target, settings)
    results, wall = await runner.run(
        proto, headers.get, n=n, concurrency=concurrency, stream=stream, warmup=warmup
    )
    return write_run(
        settings,
        out_dir,
        results,
        wall,
        target=target,
        model=model,
        stream=stream,
        concurrency=concurrency,
        warmup=warmup,
    )


def write_run(
    settings: Settings,
    out_dir: Path,
    results: list[runner.Result],
    wall: float,
    *,
    target: str,
    model: str,
    stream: bool,
    concurrency: int,
    warmup: int,
    **extra,
) -> dict:
    """Write a run's per-request lines and summary, print one line, return the summary."""
    name = run_name(target, model, stream, concurrency)
    with (out_dir / f"{name}.jsonl").open("w") as f:
        for r in results:
            f.write(r.to_json() + "\n")
    summary = {
        "run": name,
        "target": target,
        "model": model,
        "model_name": settings.model_name(model),
        "stream": stream,
        "concurrency": concurrency,
        "warmup_discarded": warmup,
        **extra,
        **stats.summarize(results, wall),
    }
    (out_dir / f"{name}.summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lat = summary["latency_s"]
    print(
        f"{name}: ok {summary['ok']}/{summary['requests']}  "
        f"p50 {lat['p50']}s  p95 {lat['p95']}s  "
        f"ttft p50 {(summary['ttft_s'] or {}).get('p50')}s",
        flush=True,
    )
    return summary


def baseline_grid(n_direct: int, n_agent: int, targets: list[str]) -> list[dict]:
    n_for = {"direct": n_direct, "agent": n_agent}
    return [
        {"target": t, "model": m, "stream": s, "concurrency": c, "n": n_for[t]}
        for t in targets
        for m in MODELS
        for s in (False, True)
        for c in (1, 5)
    ]


# A run fails (non-zero exit) when more than this share of its requests fail.
MAX_ERROR_RATE = 0.05


def failed(summary: dict) -> bool:
    rate = summary.get("error_rate")
    return rate is None or rate > MAX_ERROR_RATE


def thinking_cell(s: dict) -> str:
    """Successful requests that used any thinking, e.g. "3/200".

    On the native paths (direct, and the agent calling the models) a missing count
    means zero: Gemini omits zero counts and Claude runs with thinking off. Through a
    gateway (the gateway target, or the agent with agent_backend "gateway") it means
    unknown, because an OpenAI-format gateway may drop the field: that shows as
    "unknown", or as "used/reported of ok" when only some responses reported it.
    """
    ok, used = s.get("ok", 0), s.get("thinking_used") or 0
    reported = s.get("thinking_reported", 0)
    via_gateway = s.get("target") == "gateway" or s.get("agent_backend") == "gateway"
    if not via_gateway or reported == ok:
        return f"{used}/{ok}"
    if not reported:
        return "unknown"
    return f"{used}/{reported} of {ok}"


def markdown_table(summaries: list[dict], throughput: str = "req/s") -> str:
    rows = [
        "| Run | OK | p50 s | p95 s | p99 s | p95 all s | TTFT p50 s | TTFT p95 s "
        f"| {throughput} | out tok | think tok | thinking > 0 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        lat, ttft = s["latency_s"], s["ttft_s"] or {}
        lat_all = s.get("latency_all_s") or {}
        rows.append(
            f"| {s['run']} | {s['ok']}/{s['requests']} | {lat['p50']} | {lat['p95']} | "
            f"{lat['p99']} | {lat_all.get('p95', '')} | {ttft.get('p50', '')} | "
            f"{ttft.get('p95', '')} | {s['throughput_rps']} | {s['output_tokens_mean']} | "
            f"{s['thinking_tokens_mean']} | {thinking_cell(s)} |"
        )
    return "\n".join(rows) + "\n"


def _delta(a: float | None, b: float | None) -> str:
    return f"{b - a:+.3f}" if a is not None and b is not None else ""


def _errors(s: dict) -> str:
    rate = s.get("error_rate")
    return f"{rate:.1%}" if rate is not None else ""


def paired_table(summaries: list[dict], baseline: str = "direct") -> str:
    """Each non-baseline run against the baseline run of the same cell, same job."""
    by_cell: dict[tuple, dict[str, dict]] = {}
    for s in summaries:
        cell = (s["model"], s["stream"], s["concurrency"])
        by_cell.setdefault(cell, {})[s["target"]] = s
    # Error rates beside the latencies: a target that fails slow requests fast would
    # otherwise look faster, since the percentiles cover successful requests only.
    rows = [
        f"| Cell | Target | {baseline} p50 s | p50 s | Δ p50 s | {baseline} p95 s | p95 s "
        f"| Δ p95 s | {baseline} TTFT p50 s | TTFT p50 s | Δ TTFT p50 s "
        f"| {baseline} errors | errors |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for (model, stream, conc), runs in by_cell.items():
        base = runs.get(baseline)
        if not base:
            continue
        cell = f"{model}-{'stream' if stream else 'nostream'}-c{conc}"
        b_lat, b_ttft = base["latency_s"], base["ttft_s"] or {}
        for target, s in runs.items():
            if target == baseline:
                continue
            lat, ttft = s["latency_s"], s["ttft_s"] or {}
            rows.append(
                f"| {cell} | {target} | {b_lat['p50']} | {lat['p50']} | "
                f"{_delta(b_lat['p50'], lat['p50'])} | {b_lat['p95']} | {lat['p95']} | "
                f"{_delta(b_lat['p95'], lat['p95'])} | {b_ttft.get('p50', '')} | "
                f"{ttft.get('p50', '')} | {_delta(b_ttft.get('p50'), ttft.get('p50'))} | "
                f"{_errors(base)} | {_errors(s)} |"
            )
    return "\n".join(rows) + "\n"


def new_out_dir(settings: Settings, label: str) -> tuple[str, Path]:
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{label}-{uuid.uuid4().hex[:6]}"
    out = Path(settings.results_dir) / run_id
    out.mkdir(parents=True, exist_ok=False)
    return run_id, out


def write_meta(out: Path, run_id: str, settings: Settings, extra: dict) -> None:
    meta = {
        "run_id": run_id,
        "image": settings.image,
        "model_location": settings.model_location,
        "gemini_model": settings.gemini_model,
        "claude_model": settings.claude_model,
        "max_tokens": settings.max_tokens,
        "thinking": {"gemini": "LOW", "claude": "off"},
        # Which identity called the Cloud Run targets (test 5, audit).
        "id_token_source": settings.id_token_source,
        # How Claude was sent to a gateway target (openai or anthropic; Kong).
        "gateway_claude_api": settings.gateway_claude_api,
        **extra,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


async def cmd_load(args: argparse.Namespace, settings: Settings) -> int:
    require(settings, args.target)  # before anything is written
    run_id, out = new_out_dir(settings, args.target)
    write_meta(out, run_id, settings, {"command": "load"})
    summary = await one_run(
        settings,
        out,
        target=args.target,
        model=args.model,
        stream=args.stream,
        concurrency=args.concurrency,
        n=args.n,
        warmup=args.warmup,
    )
    print(f"results: {out}")
    return 1 if failed(summary) else 0


async def cmd_baseline(args: argparse.Namespace, settings: Settings) -> int:
    targets = args.targets.split(",")
    for t in targets:
        require(settings, t)
    grid = baseline_grid(args.n_direct, args.n_agent, targets)
    run_id, out = new_out_dir(settings, "baseline")
    write_meta(out, run_id, settings, {"command": "baseline", "grid": grid})
    headers = {t: Headers(t, settings) for t in targets}
    summaries = []
    for cell in grid:
        try:
            summary = await one_run(
                settings, out, warmup=args.warmup, headers=headers[cell["target"]], **cell
            )
        except Exception as e:  # noqa: BLE001 - one broken cell must not lose the others
            name = run_name(cell["target"], cell["model"], cell["stream"], cell["concurrency"])
            print(f"{name}: FAILED {type(e).__name__}: {e}", flush=True)
            summary = {"run": name, **stats.summarize([], 0.0), "errors": [f"{e!r}"[:500]]}
        summaries.append(summary)
        # Rewritten after every cell, so an interrupted run still leaves a table.
        (out / "summary.md").write_text(f"# Baseline {run_id}\n\n" + markdown_table(summaries))
    print(f"results: {out}")
    return 1 if any(failed(s) for s in summaries) else 0


# Pre-warm: one request per model to each Cloud Run target before anything is
# measured. A cold gateway can take most of a minute to start (and LiteLLM's first
# Claude call on a new instance ~15 s), past the 60 s request timeout.
PREWARM_TIMEOUT_S = 180.0
PREWARM_ATTEMPTS = 3
PREWARM_RETRY_WAIT_S = 5.0


async def prewarm(settings: Settings, targets: list[str], headers: dict[str, Headers]) -> list:
    """Send one non-streaming request per model to each non-direct target; record each try.

    The first try's latency is a cold-start data point; failures are logged and warned
    about, never fatal (the cells' own warm-ups follow).
    """
    log = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(PREWARM_TIMEOUT_S)) as client:
        for target in targets:
            if target == "direct":
                continue
            for model in MODELS:
                proto = protocol_for(target, model, settings)
                for attempt in range(1, PREWARM_ATTEMPTS + 1):
                    try:
                        h = await headers[target].get()
                    except Exception as e:  # noqa: BLE001 - logged like a failed attempt
                        r = runner._auth_failure(0, e)
                    else:
                        r = await runner.send_one(client, proto, h, 0, False)
                    log.append(
                        {
                            "target": target,
                            "model": model,
                            "attempt": attempt,
                            "status": r.status,
                            "latency_s": r.latency_s,
                            "error": r.error,
                        }
                    )
                    print(f"prewarm {target}-{model}: {r.status} {r.latency_s}s", flush=True)
                    if r.ok:
                        break
                    if attempt < PREWARM_ATTEMPTS:
                        await asyncio.sleep(PREWARM_RETRY_WAIT_S)
                else:
                    print(f"WARN prewarm {target}-{model}: no successful response", flush=True)
    return log


def compare_grid(concurrencies: list[int]) -> list[dict]:
    return [
        {"model": m, "stream": s, "concurrency": c}
        for m in MODELS
        for s in (False, True)
        for c in concurrencies
    ]


def block_order(targets: list[str], block: int, flip: bool) -> list[str]:
    """ABBA: the order reverses every block (and per cell), so in every cell each
    target's requests sit at the same average time position."""
    forward = (block % 2 == 0) != flip
    return list(targets) if forward else list(reversed(targets))


async def compare_cell(
    settings: Settings,
    out: Path,
    cell: dict,
    targets: list[str],
    headers: dict[str, Headers],
    *,
    n: int,
    block: int,
    warmup: int,
    flip: bool,
    extra: dict[str, dict] | None = None,
) -> list[dict]:
    """Take turns between the targets in blocks of `block` requests until each has sent `n`.

    Same-time pairing (ADR 0007): upstream drift lands on every target alike. Each
    target keeps one client for the cell, but its idle connections expire while the
    other target runs (and so may the gateway's own upstream ones), so every block
    after the first starts with `concurrency` discarded requests to reopen them;
    the first block gets the full `warmup`.
    """
    model, stream, conc = cell["model"], cell["stream"], cell["concurrency"]
    protos = {t: protocol_for(t, model, settings) for t in targets}
    results: dict[str, list[runner.Result]] = {t: [] for t in targets}
    walls = dict.fromkeys(targets, 0.0)
    clients = {
        t: httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_connections=conc, max_keepalive_connections=conc),
        )
        for t in targets
    }
    blocks = math.ceil(n / block)
    orders = []
    try:
        for b in range(blocks):
            size = min(block, n - b * block)
            order = block_order(targets, b, flip)
            orders.append(order)
            for t in order:
                got, wall = await runner.run(
                    protos[t],
                    headers[t].get,
                    n=size,
                    concurrency=conc,
                    stream=stream,
                    warmup=warmup if b == 0 else (conc if warmup else 0),
                    client=clients[t],
                    offset=b * block,
                )
                results[t].extend(got)
                walls[t] += wall
    finally:
        for c in clients.values():
            await c.aclose()
    return [
        write_run(
            settings,
            out,
            results[t],
            walls[t],
            target=t,
            model=model,
            stream=stream,
            concurrency=conc,
            warmup=warmup,
            blocks=blocks,
            block_size=block,
            rewarm_per_block=conc if warmup else 0,
            block_orders=orders,
            **(extra or {}).get(t, {}),
        )
        for t in targets
    ]


def crashed_cell(cell: dict, targets: list[str], error: Exception) -> list[dict]:
    """Stand-in summaries for a cell that raised, so it shows (and fails the run)."""
    name_of = {t: run_name(t, cell["model"], cell["stream"], cell["concurrency"]) for t in targets}
    return [
        {
            "run": name_of[t],
            "target": t,
            **cell,
            **stats.summarize([], 0.0),
            "errors": [f"cell crashed: {type(error).__name__}: {error}"[:500]],
        }
        for t in targets
    ]


async def cmd_compare(args: argparse.Namespace, settings: Settings) -> int:
    targets = args.targets.split(",")
    if len(targets) < 2 or len(set(targets)) != len(targets):
        raise ValueError(f"--targets needs two or more distinct targets, got {args.targets!r}")
    for t in targets:
        require(settings, t)
    grid = compare_grid([int(c) for c in args.concurrency.split(",")])
    # Credentials before the run directory, so a credentials failure leaves nothing behind.
    headers = {t: Headers(t, settings) for t in targets}
    extra = {"agent": {"agent_backend": args.agent_backend}} if "agent" in targets else {}
    run_id, out = new_out_dir(settings, "compare")
    warm = await prewarm(settings, targets, headers)
    write_meta(
        out,
        run_id,
        settings,
        {
            "command": "compare",
            "targets": targets,
            "n_per_target": args.n,
            "block": args.block,
            "agent_backend": args.agent_backend if "agent" in targets else None,
            "grid": grid,
            "prewarm": warm,
        },
    )
    summaries: list[dict] = []
    crashed = False
    started = time.time()
    for i, cell in enumerate(grid):
        try:
            summaries += await compare_cell(
                settings,
                out,
                cell,
                targets,
                headers,
                n=args.n,
                block=args.block,
                warmup=args.warmup,
                flip=i % 2 == 1,
                extra=extra,
            )
        except Exception as e:  # noqa: BLE001 - one broken cell must not lose the others
            print(f"cell {cell}: FAILED {type(e).__name__}: {e}", flush=True)
            crashed = True
            summaries += crashed_cell(cell, targets, e)
        (out / "summary.md").write_text(compare_markdown(run_id, summaries, targets[0], warm))
    print(f"results: {out} ({time.time() - started:.0f}s)")
    return 1 if crashed or not summaries or any(failed(s) for s in summaries) else 0


def prewarm_table(log: list[dict]) -> str:
    rows = [
        "| Target | Model | Attempt | Status | Latency s | Error |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in log:
        error = (e.get("error") or "").replace("|", "/").replace("\n", " ")[:120]
        rows.append(
            f"| {e.get('target')} | {e.get('model')} | {e.get('attempt')} | {e.get('status')} | "
            f"{e.get('latency_s', '')} | {error} |"
        )
    return "\n".join(rows) + "\n"


def compare_markdown(
    run_id: str, summaries: list[dict], baseline: str = "direct", prewarm_log: list | None = None
) -> str:
    md = (
        f"# Compare {run_id}\n\n## Paired (same job, alternating blocks)\n\n"
        f"Each target against `{baseline}` in the same cell. p95 and p99 rest on a few "
        "samples per cell, so compare Gemini on p50 and TTFT p50 (ADR 0007); Claude is the "
        "steadier overhead signal.\n\n"
        + paired_table(summaries, baseline)
        + "\n## All runs\n\nreq/s is summed over blocks (each block drains to zero), so it "
        "compares between targets of one run, not with `load` or `baseline` runs.\n\n"
        + markdown_table(summaries, throughput="req/s (blocks)")
    )
    if prewarm_log:
        md += (
            "\n## Pre-warm\n\n"
            "The first attempt per target and model is a cold-start data point.\n\n"
        )
        md += prewarm_table(prewarm_log)
    return md


def git_commit() -> str | None:
    """The checked-out commit for local runs (the job's image has no git; AGW_IMAGE says it)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        # Tracked changes only: a run just copied into results/raw/ is untracked and
        # doesn't make the code that ran dirty (a config window in a tracked file does).
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


async def cmd_scenarios(args: argparse.Namespace, settings: Settings) -> int:
    """Send a scenario file's cases to the gateway and record what happened."""
    require(settings, "gateway")
    scenario = scenarios.load_file(args.file)
    headers = Headers("gateway", settings)
    run_id, out = new_out_dir(settings, f"scenarios-{scenario.name}")
    write_meta(
        out,
        run_id,
        settings,
        {
            "command": "scenarios",
            "gateway_url": settings.gateway_url,
            "git_commit": git_commit(),
            "note": args.note,
            "timeout_s": scenario.timeout_s,
            "scenario_file": str(args.file),
            "scenario": scenario.raw,
            # A shared case set (cases_from) lives in another file: keep what was sent.
            **(
                {"expanded_cases": [dataclasses.asdict(c) for c in scenario.cases]}
                if "cases_from" in scenario.raw
                else {}
            ),
        },
    )
    # Each outcome is written as it arrives, so an interrupted run keeps what it did.
    with (out / "outcomes.jsonl").open("w") as f:

        def sink(o: scenarios.Outcome) -> None:
            f.write(o.to_json() + "\n")
            f.flush()

        outcomes = await scenarios.run_file(settings, scenario, headers, sink)
    (out / "summary.md").write_text(scenarios.scenarios_markdown(run_id, scenario, outcomes))
    matched = sum(o.expected for o in outcomes)
    print(f"matched {matched}/{len(outcomes)} attempts; results: {out}")
    return 0


def run_order(summary: dict, meta: dict) -> tuple:
    """Sort key matching the order a run wrote its rows: the grid, then the targets."""
    cells = [
        (c["model"], c["stream"], c["concurrency"]) + ((c["target"],) if "target" in c else ())
        for c in meta.get("grid", [])
    ]
    targets = meta.get("targets", [])
    model, stream, conc, target = (
        summary.get("model"),
        summary.get("stream"),
        summary.get("concurrency"),
        summary.get("target"),
    )
    for key in ((model, stream, conc, target), (model, stream, conc)):
        if key in cells:
            t = targets.index(target) if target in targets else 0
            return (cells.index(key), t, summary.get("run", ""))
    return (len(cells), 0, summary.get("run", ""))


def recount_thinking(run_dir: Path, summary: dict) -> None:
    """Thinking counts from the per-request lines, so runs that predate them get them too."""
    lines = run_dir / f"{summary['run']}.jsonl"
    if not lines.exists():
        return
    rows = [json.loads(line) for line in lines.read_text().splitlines() if line.strip()]
    thinking = [
        r["thinking_tokens"] for r in rows if r.get("ok") and r.get("thinking_tokens") is not None
    ]
    summary["thinking_reported"] = len(thinking)
    summary["thinking_used"] = sum(1 for t in thinking if t > 0)


def cmd_report(args: argparse.Namespace) -> int:
    """Print the summary tables for a run directory (e.g. one copied into results/raw/)."""
    run_dir = Path(args.run_dir)
    summaries = [json.loads(p.read_text()) for p in sorted(run_dir.glob("*.summary.json"))]
    if not summaries:
        print(f"no *.summary.json in {run_dir}", file=sys.stderr)
        return 1
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    for s in summaries:
        recount_thinking(run_dir, s)
    summaries.sort(key=lambda s: run_order(s, meta))
    if meta.get("command") == "compare":
        targets = meta.get("targets") or ["direct"]
        md = compare_markdown(
            meta.get("run_id", run_dir.name), summaries, targets[0], meta.get("prewarm")
        )
        print(md, end="")
    else:
        print(markdown_table(summaries), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agw-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_load = sub.add_parser("load", help="one run against one target and model")
    p_load.add_argument("--target", choices=TARGETS, required=True)
    p_load.add_argument("--model", choices=MODELS, required=True)
    p_load.add_argument("--n", type=int, default=200)
    p_load.add_argument("-c", "--concurrency", type=int, default=1)
    p_load.add_argument("--stream", action="store_true")
    p_load.add_argument("--warmup", type=int, default=10)

    p_base = sub.add_parser("baseline", help="the Phase 0 baseline grid")
    p_base.add_argument("--targets", default="direct,agent")
    p_base.add_argument("--n-direct", type=int, default=200)
    p_base.add_argument("--n-agent", type=int, default=50)
    p_base.add_argument("--warmup", type=int, default=10)

    p_cmp = sub.add_parser("compare", help="targets side by side, alternating blocks, same job")
    p_cmp.add_argument("--targets", default="direct,gateway")
    p_cmp.add_argument("--n", type=int, default=100, help="measured requests per target per cell")
    p_cmp.add_argument("--block", type=int, default=25, help="requests per block")
    p_cmp.add_argument("--concurrency", default="1,5")
    p_cmp.add_argument("--warmup", type=int, default=10)
    p_cmp.add_argument(
        "--agent-backend",
        choices=("direct", "gateway"),
        default="direct",
        help="what the agent calls (its AGW_TARGET), recorded with agent-target runs",
    )

    p_scn = sub.add_parser(
        "scenarios", help="scripted gateway cases (failover, cost, screening, auth, audit)"
    )
    p_scn.add_argument("file", help="scenario JSON, e.g. scenarios/litellm/failover.json")
    p_scn.add_argument(
        "--note", default=None, help="recorded in meta.json, e.g. the gateway revision or switches"
    )

    p_rep = sub.add_parser("report", help="print the summary tables for a run directory")
    p_rep.add_argument("run_dir")

    args = parser.parse_args(argv)
    if args.command == "report":
        return cmd_report(args)
    settings = load()
    commands = {
        "load": cmd_load,
        "baseline": cmd_baseline,
        "compare": cmd_compare,
        "scenarios": cmd_scenarios,
    }
    return asyncio.run(commands[args.command](args, settings))


if __name__ == "__main__":
    sys.exit(main())
