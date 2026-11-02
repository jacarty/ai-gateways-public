"""Test 6 (audit fidelity) on Bifrost: collect the trail a run left and try to join it.

Usage: python3 audit_trail.py <run_dir>   (run-audit.sh calls it; standard library only)

Needs AGW_GATEWAY_URL (the service URL, no /v1) and AGW_ADMIN_HEADERS (a headers file
with an ID token and the admin login, as run-audit.sh writes it). Reads the run's
outcomes.jsonl (and agent-run.json, if the run also went through the agent), then fetches
for the run's time window:

- Bifrost's logs store (GET /api/logs, then /api/logs/{id} for each row), joined to each
  request by the x-request-id Bifrost returned (it is the row's id), else by the caller's
  own tag (the x-bf-lh-agw-case header, stored in the row's metadata), else by session
  (x-bf-session-id);
- Cloud Run request and container logs for the gateway and the agent (gcloud logging);
  the agent's own gateway call is found by its key name and time.

Writes trail.json (the evidence, redacted) and trail.md (what joined and what didn't)
into the run directory, which are committed. Shared helpers (redaction, address kinds,
Cloud Run's logs) are in agw_harness.trail. For content only flags are kept (prompt
marker, ID token, key value present); header names, never values, are kept.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agw_harness.trail import (  # noqa: E402
    as_dict,
    iso,
    logging_read,
    parse_time,
    redact,
    summarise_logs,
)

MARKER = "AGW-T6-MARKER"
SESSION = "agw-t6-session"
TAG = "agw-case"  # x-bf-lh-agw-case, as the row's metadata may key it
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.")


def _headers(path: str) -> dict[str, str]:
    out = {}
    for line in Path(path).read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _get(url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def log_rows(url: str, headers_file: str, t0: float, t1: float) -> list[dict]:
    """Every log row in the window, each with its full record."""
    headers = _headers(headers_file)
    q = urllib.parse.urlencode(
        {"start_time": iso(t0), "end_time": iso(t1), "limit": 200, "order": "asc"}
    )
    rows = _get(f"{url}/api/logs?{q}", headers).get("logs") or []
    if len(rows) == 200:
        print("WARNING: 200 log rows, the page limit; later ones are missing")
    full = []
    for row in rows:
        detail = _get(f"{url}/api/logs/{row['id']}", headers)
        full.append(detail.get("log", detail))
    return full


def tag_of(row: dict) -> str | None:
    """The caller's own case tag, wherever Bifrost stored the x-bf-lh-* header."""
    for k, v in as_dict(row.get("metadata")).items():
        if k.lower().removeprefix("x-bf-lh-") == TAG:
            return v if isinstance(v, str) else None
    return None


def summarise_row(row: dict) -> dict:
    """A log row reduced to what an auditor needs; content to flags only."""
    raw = json.dumps(row)
    usage = row.get("token_usage") or {}
    md = as_dict(row.get("metadata"))
    return {
        "id": row.get("id"),
        "time": row.get("timestamp"),
        "virtual_key": row.get("virtual_key_name"),
        "provider": row.get("provider"),
        "model": row.get("model"),
        "status": row.get("status"),
        "session_id": row.get("session_id"),
        "tag": tag_of(row),
        "metadata_keys": sorted(md),
        "user_agent": row.get("user_agent"),
        "parent_request_id": row.get("parent_request_id"),
        "fallback_index": row.get("fallback_index"),
        "selected_key": row.get("selected_key_name"),
        "tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
        "cost": row.get("cost"),
        "latency_ms": row.get("latency"),
        "overhead_ms": row.get("overhead_latency"),
        "stream": row.get("stream"),
        "content": {
            "prompt_marker": MARKER in raw,
            "input_stored": bool(row.get("input_history")),
            "output_stored": bool(row.get("output_message")),
            "id_token": bool(JWT.search(raw)),
            "virtual_key_value": "sk-bf-" in raw,
            "serverless_auth_header": "x-serverless-authorization" in raw.lower(),
        },
    }


def join(outcomes, rows, gateway_logs, agent=None):
    """Each request's row: by the returned request id, else by tag, else by session and
    model (one row each, strongest key first across all requests), else none; the agent's
    row by key and time; each row's Cloud Run request entry by time only (Bifrost's rows
    carry no trace id)."""
    used: set = set()

    def take(row):
        used.add(row["id"])
        return row

    # Strongest key first across all requests, so a weak match can't take a row a later
    # request would have joined exactly.
    joined: dict[int, tuple[dict, str]] = {}
    for i, o in enumerate(outcomes):
        rid = (o.get("headers") or {}).get("x-request-id")
        row = next((r for r in rows if rid and r["id"] == rid and r["id"] not in used), None)
        if row:
            joined[i] = (take(row), "request id")
    for i, o in enumerate(outcomes):
        if i not in joined:
            row = next((r for r in rows if r["tag"] == o["case"] and r["id"] not in used), None)
            if row:
                joined[i] = (take(row), "tag")
    for i, o in enumerate(outcomes):
        if i not in joined and o.get("tagged"):
            row = next(
                (
                    r
                    for r in rows
                    if r["session_id"] == SESSION
                    and r.get("model") == o.get("model")
                    and r["id"] not in used
                ),
                None,
            )
            if row:  # any same-model row of the session: a weak join, labelled as such
                joined[i] = (take(row), "session and model (ambiguous)")
    out = [
        {
            "case": o["case"],
            "status": o["status"],
            "row": joined[i][0]["id"] if i in joined else None,
            "joined_by": joined[i][1] if i in joined else None,
        }
        for i, o in enumerate(outcomes)
    ]

    agent_row = None
    if agent:
        t0, t1 = agent["started_at"], agent["ended_at"] + 5
        for r in rows:
            ts = parse_time(r["time"])
            if r["virtual_key"] == "agw-agent" and ts and t0 <= ts <= t1 and r["id"] not in used:
                agent_row = take(r)["id"]
                break

    def nearest_request(row):
        ts = parse_time(row["time"]) if row else None
        if ts is None:
            return None
        entries = [
            e for e in gateway_logs["request_log_entries"] if "/chat/completions" in e["path"]
        ]
        best = min(entries, key=lambda e: abs((parse_time(e["time"]) or 0) - ts), default=None)
        if best and abs((parse_time(best["time"]) or 0) - ts) <= 30:
            return best["trace"]
        return None

    by_id = {r["id"]: r for r in rows}
    for j in out:
        j["cloud_run_trace_by_time"] = nearest_request(by_id.get(j["row"]))
    return {
        "requests": out,
        "agent_row": agent_row,
        "agent_row_trace_by_time": nearest_request(by_id.get(agent_row)),
        "unjoined_rows": [r["id"] for r in rows if r["id"] not in used],
    }


def main(run_dir: str) -> None:
    run = Path(run_dir)
    outcomes = [json.loads(line) for line in (run / "outcomes.jsonl").read_text().splitlines()]
    scenario = json.loads((run / "meta.json").read_text()).get("scenario") or {}
    cases = {c["name"]: c for c in scenario.get("cases", [])}
    for o in outcomes:
        case = cases.get(o["case"], {})
        o["tagged"] = any(k.lower() == "x-bf-session-id" for k in case.get("headers") or {})
        o["model"] = case.get("model")
    agent_file = run / "agent-run.json"
    agent = json.loads(agent_file.read_text()) if agent_file.exists() else None

    # The run's own window, from what was recorded, so re-running the collector later
    # doesn't pull in other traffic.
    t0 = min(o["started_at"] for o in outcomes) - 5
    last = max(o["started_at"] + (o.get("latency_s") or 0) for o in outcomes)
    t1 = max(last, (agent or {}).get("ended_at", 0)) + 60
    url, headers_file = os.environ["AGW_GATEWAY_URL"], os.environ["AGW_ADMIN_HEADERS"]

    # The logs store writes in batches (5 s): retry until every request id Bifrost returned
    # (and the agent's row) shows, or give up after a minute and say so.
    wanted = {(o.get("headers") or {}).get("x-request-id") for o in outcomes} - {None}
    rows = []
    for _ in range(6):
        rows = [summarise_row(r) for r in log_rows(url, headers_file, t0, t1)]
        have = {r["id"] for r in rows}
        agent_seen = not agent or any(r["virtual_key"] == "agw-agent" for r in rows)
        if wanted <= have and agent_seen:
            break
        time.sleep(10)
    else:
        missing = len(wanted - have)
        print(
            f"WARNING: after a minute, {missing} request ids missing, agent row seen={agent_seen}"
        )
    needles = {"prompt_marker": MARKER, "session": SESSION}
    gateway_logs = summarise_logs(logging_read("agw-bifrost", t0, t1), needles)
    agent_logs = summarise_logs(logging_read("agw-agent", t0, t1), needles) if agent else None

    trail = {
        "window": {"start": iso(t0), "end": iso(t1)},
        "rows": rows,
        "gateway_cloud_run": gateway_logs,
        "agent_cloud_run": agent_logs,
        "agent_run": agent,
        "join": join(outcomes, rows, gateway_logs, agent),
        "response_headers": {o["case"]: o.get("headers") for o in outcomes},
    }
    trail = redact(trail)
    (run / "trail.json").write_text(json.dumps(trail, indent=1) + "\n")
    (run / "trail.md").write_text(render(trail))
    print(f"wrote {run / 'trail.json'} and trail.md: {len(rows)} log rows")


def render(t: dict) -> str:
    def yn(v):
        return "yes" if v else "no"

    def cells(*values):
        return "| " + " | ".join(str(v) for v in values) + " |"

    rows = {r["id"]: r for r in t["rows"]}
    cr = t["gateway_cloud_run"]
    head = (
        "Request",
        "Status",
        "Log row",
        "Joined by",
        "Key",
        "Session",
        "Tag",
        "Cloud Run trace (by time)",
        "Content stored",
        "ID token stored",
    )
    lines = [
        "# Test 6 trail (Bifrost)",
        "",
        f"Window {t['window']['start']} to {t['window']['end']}: {len(t['rows'])} log rows, "
        f"{len(cr['request_log_entries'])} gateway request-log entries, "
        f"{cr['entries_naming_a_caller_identity']} entries naming a Google identity.",
        "",
        cells(*head),
        cells(*["---"] * len(head)),
    ]
    for j in t["join"]["requests"]:
        r = rows.get(j["row"]) or {}
        c = r.get("content") or {}
        lines.append(
            cells(
                j["case"],
                j["status"],
                "found" if r else "none",
                j["joined_by"] or "-",
                r.get("virtual_key") or "-",
                r.get("session_id") or "-",
                r.get("tag") or "-",
                j["cloud_run_trace_by_time"] or "-",
                yn(c.get("input_stored")),
                yn(c.get("id_token")),
            )
        )
    if t.get("agent_run"):
        a, r = t["agent_run"], rows.get(t["join"]["agent_row"]) or {}
        found = "found" if r else "not found"
        who = f" (`{r.get('virtual_key')}`, user agent `{r.get('user_agent')}`)" if r else ""
        trace = t["join"]["agent_row_trace_by_time"] or "none"
        lines += [
            "",
            f"**Agent run** (session `{a['session_id']}`, HTTP {a['status']}): gateway row {found} "
            f"by key and time{who}; nearest gateway request-log trace {trace}. Nothing in the row "
            "names the agent's own session or trace.",
        ]
    recorded = {k: v for k, v in t["response_headers"].items() if v}
    lines += [
        "",
        f"Unjoined rows: {len(t['join']['unjoined_rows'])}. Response headers recorded: "
        + json.dumps(recorded),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main(sys.argv[1])
