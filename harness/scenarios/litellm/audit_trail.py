"""Test 6 (audit fidelity): collect the trail a run left and try to join it.

Usage: python3 audit_trail.py <run_dir>   (run-audit.sh calls it; standard library only)

Needs AGW_GATEWAY_URL and AGW_ADMIN_HEADERS (a headers file with an ID token and the
LiteLLM master key, as run-audit.sh writes it). Reads the run's outcomes.jsonl (and
agent-run.json, if the run also went through the agent), then fetches for the run's
time window:

- LiteLLM's spend-log rows (/spend/logs), joined to each request by its LiteLLM call id
  (the x-litellm-call-id response header the scenario records), or else by the caller's
  own tag (spend_logs_metadata.agw_case: refusals may carry no call id); each row is
  also marked if its session id equals a gateway request-log trace (LiteLLM's default
  session when the caller sends none);
- Cloud Run request and container logs for the gateway and the agent (gcloud logging);
  the agent's own gateway call is found by key alias and time.

Writes trail.json (the evidence, redacted) and trail.md (what joined and what didn't)
into the run directory, which are committed. Tokens, keys, key hashes, Google API keys
and personal email addresses are redacted; IP addresses are reduced to their kind; for
content only flags are kept (prompt marker, ID token, bearer value present). User
agents, traces, caller metadata and endpoints are kept as values.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

# The shared helpers live in the harness package; put it on the path so a plain python3
# (as run-audit.sh calls it) finds them.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agw_harness.trail import (  # noqa: E402
    as_dict,
    ip_kind,
    iso,
    logging_read,
    parse_time,
    redact,
    summarise_logs,
)

MARKER = "AGW-T6-MARKER"
SESSION = "agw-t6-session"


def spend_rows(url: str, headers_file: str, t0: float, t1: float) -> list[dict]:
    """Every spend-log row whose start time falls in [t0, t1]."""
    day0 = datetime.fromtimestamp(t0, UTC).date()
    day1 = datetime.fromtimestamp(t1, UTC).date() + timedelta(days=1)
    headers = {}
    for line in Path(headers_file).read_text().splitlines():
        name, _, val = line.partition(":")
        if val:
            headers[name.strip()] = val.strip()
    req = urllib.request.Request(
        f"{url}/spend/logs?start_date={day0}&end_date={day1}&summarize=false", headers=headers
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    rows = data if isinstance(data, list) else data.get("data", [])
    out = []
    for row in rows:
        start = parse_time(row.get("startTime"))
        if start is not None and t0 <= start <= t1:
            out.append(row)
    return out


def stored_header_names(psr) -> list[str] | None:
    """Names of request headers kept in a stored request: LiteLLM nests them under
    metadata.headers (and again under metadata.requester_metadata.headers)."""
    if not isinstance(psr, dict):
        return None
    md = as_dict(psr.get("metadata"))
    places = (
        psr.get("headers"),
        md.get("headers"),
        as_dict(md.get("requester_metadata")).get("headers"),
    )
    names = set()
    for headers in places:
        names |= set(as_dict(headers))
    return sorted(names)


def summarise_row(row: dict) -> dict:
    md = as_dict(row.get("metadata"))
    raw = json.dumps(row)
    psr = row.get("proxy_server_request") or md.get("proxy_server_request")
    psr = as_dict(psr) if not isinstance(psr, dict) else psr
    error = as_dict(md.get("error_information"))
    return {
        "start": row.get("startTime"),
        "call_id": md.get("litellm_call_id") or row.get("request_id"),
        "key_alias": md.get("user_api_key_alias"),
        "model_group": row.get("model_group"),
        "original_model_group": md.get("original_model_group"),
        "call_type": row.get("call_type"),
        "internal_call_origin": md.get("internal_call_origin"),
        "status": row.get("status"),
        "error": {k: error.get(k) for k in ("error_code", "error_class")} if error else None,
        "api_base": row.get("api_base"),
        "session_id": row.get("session_id"),
        "spend_logs_metadata": md.get("spend_logs_metadata"),
        "spend": row.get("spend"),
        "total_tokens": row.get("total_tokens"),
        "request_duration_ms": row.get("request_duration_ms"),
        "user": row.get("user") or None,
        "end_user": row.get("end_user") or None,
        "requester_ip": ip_kind(row.get("requester_ip_address") or md.get("requester_ip_address")),
        "user_agent": md.get("user_agent"),
        "applied_guardrails": md.get("applied_guardrails"),
        "content_stored": {
            "messages": bool(row.get("messages")),
            "response": bool(row.get("response")),
            "proxy_server_request": bool(psr),
        },
        "proxy_server_request_keys": sorted(psr) if isinstance(psr, dict) else None,
        "stored_header_names": stored_header_names(psr),
        "contains": {
            "prompt_marker": MARKER in raw,
            "id_token_jwt": "eyJ" in raw,
            "bearer_value": "bearer " in raw.lower(),
            "x_serverless_authorization": "x-serverless-authorization" in raw.lower(),
        },
    }


def main(run_dir: str) -> None:
    run = Path(run_dir)
    url, headers_file = os.environ["AGW_GATEWAY_URL"], os.environ["AGW_ADMIN_HEADERS"]
    outcomes = [json.loads(line) for line in (run / "outcomes.jsonl").read_text().splitlines()]
    agent_file = run / "agent-run.json"
    agent = json.loads(agent_file.read_text()) if agent_file.exists() else None
    starts = [o["started_at"] for o in outcomes] + ([agent["started_at"]] if agent else [])
    ends = [o["started_at"] + o["latency_s"] for o in outcomes] + (
        [agent["ended_at"]] if agent else []
    )
    t0, t1 = min(starts) - 15, max(ends) + 15

    # LiteLLM writes spend logs in batches (~10 s): retry until every sent request is there.
    wanted = {o["headers"].get("x-litellm-call-id") for o in outcomes} - {None}
    for attempt in range(8):
        rows = [summarise_row(r) for r in spend_rows(url, headers_file, t0, t1)]
        missing = wanted - {r["call_id"] for r in rows}
        if not missing or attempt == 7:
            if missing:
                print(f"WARNING: no spend-log row yet for call ids {sorted(missing)}")
            break
        time.sleep(15)

    # Cloud Logging ingestion lags too: retry until the gateway has a request log per request.
    needles = {
        "prompt_marker": MARKER,
        "session_id": SESSION,
        "id_token_jwt": "eyJ",
        "bearer": "bearer ",
    }
    for attempt in range(8):
        gateway_logs = summarise_logs(logging_read("agw-litellm", t0, t1), needles)
        expected = len(outcomes) + (1 if agent else 0)  # the agent's own gateway call too
        if len(gateway_logs["request_log_entries"]) >= expected or attempt == 7:
            break
        time.sleep(20)
    agent_logs = None
    for _ in range(4 if agent else 0):
        agent_logs = summarise_logs(logging_read("agw-agent", t0, t1), needles)
        if any("/run" in (e["path"] or "") for e in agent_logs["request_log_entries"]):
            break
        time.sleep(20)

    requests, other_rows, agent_view = join(outcomes, rows, gateway_logs, agent, agent_logs)

    trail = redact(
        {
            "run_id": run.name,
            "window": [iso(t0), iso(t1)],
            "requests": requests,
            "session": {"id": SESSION, "rows": [r for r in rows if r["session_id"] == SESSION]},
            "other_spend_rows_in_window": other_rows,
            "agent": agent_view,
            "gateway_logs": gateway_logs,
        }
    )
    (run / "trail.json").write_text(json.dumps(trail, indent=1) + "\n")
    (run / "trail.md").write_text(render(trail))
    print(f"wrote {run / 'trail.json'} and trail.md")


def join(outcomes, rows, gateway_logs, agent=None, agent_logs=None):
    """Join each request to its spend-log row, and the agent's run to what it caused.
    Returns (requests, rows nobody claimed, the agent view or None). A row joins at most
    one request."""
    # LiteLLM uses the incoming trace as the session id when the caller sends none, so
    # a row whose session is a gateway request-log trace joins that request log.
    traces = {e["trace"] for e in gateway_logs["request_log_entries"]} - {None}
    for r in rows:
        r["session_is_a_request_log_trace"] = r["session_id"] in traces

    by_call = {r["call_id"]: r for r in rows if r["call_id"]}
    by_case: dict[str, list] = {}
    for r in rows:  # refusals may carry no call id header: the caller's own tag instead
        if case := (r["spend_logs_metadata"] or {}).get("agw_case"):
            by_case.setdefault(case, []).append(r)
    claimed: set[int] = set()

    def take(row):
        if row is None or id(row) in claimed:
            return None
        claimed.add(id(row))
        return row

    requests = []
    for o in outcomes:
        call_id = o["headers"].get("x-litellm-call-id")
        row, joined_by = take(by_call.get(call_id) if call_id else None), "call id"
        if row is None:
            row = next((r for r in by_case.get(o["case"], []) if id(r) not in claimed), None)
            row, joined_by = take(row), "caller metadata"
        requests.append(
            {
                "case": o["case"],
                "http": o["status"],
                "call_id_header": call_id,
                "joined_by": joined_by if row else None,
                "spend_row": row,
            }
        )
    other_rows = [r for r in rows if id(r) not in claimed]

    if not agent:
        return requests, other_rows, None

    def during(ts):
        return agent["started_at"] - 1 <= (parse_time(ts) or 0) <= agent["ended_at"] + 1

    agent_view = {
        "run": agent,
        "agent_request_logs": [
            e for e in agent_logs["request_log_entries"] if "/run" in (e["path"] or "")
        ],
        "gateway_request_logs_during_the_run": [
            e for e in gateway_logs["request_log_entries"] if during(e["time"])
        ],
        "spend_rows_during_the_run": [
            r for r in other_rows if r["key_alias"] == "agw-agent" and during(r["start"])
        ],
        "agent_logs": {k: v for k, v in agent_logs.items() if k != "request_log_entries"},
    }
    return requests, other_rows, agent_view


def render(t: dict) -> str:
    def yn(v):
        return "yes" if v else "no"

    md = [f"# Audit trail: {t['run_id']}", "", f"Window {t['window'][0]} to {t['window'][1]}.", ""]
    md += [
        "## Each request and its spend-log row",
        "",
        "| Case | HTTP | Row joined by | Key alias | Model group | Status | Session "
        "| Session = request-log trace | Caller metadata | User agent | IP kind | Content stored "
        "| Header names stored | Marker | ID token | Bearer |",
        "|" + " --- |" * 16,
    ]
    for r in t["requests"]:
        s = r["spend_row"] or {}
        c, cs = s.get("contains", {}), s.get("content_stored", {})
        stored = ", ".join(k for k, v in cs.items() if v) or "none"
        session = (
            "tagged" if s.get("session_id") == t["session"]["id"] else ("random" if s else "—")
        )
        header_names = ", ".join(s.get("stored_header_names") or []) or "—"
        md.append(
            f"| {r['case']} | {r['http']} | {r.get('joined_by') or 'not found'} | "
            f"{s.get('key_alias') or '—'} | "
            f"{s.get('model_group') or '—'} | {s.get('status') or '—'} | "
            f"{session} | {yn(s.get('session_is_a_request_log_trace'))} | "
            f"{yn(s.get('spend_logs_metadata'))} | {s.get('user_agent') or '—'} | "
            f"{s.get('requester_ip') or '—'} | {stored} | "
            f"{header_names} | {yn(c.get('prompt_marker'))} | "
            f"{yn(c.get('id_token_jwt'))} | {yn(c.get('bearer_value'))} |"
        )
    md += ["", f"Session `{t['session']['id']}`: {len(t['session']['rows'])} spend-log rows.", ""]
    md += ["## Other spend-log rows in the window", ""]
    if t["other_spend_rows_in_window"]:
        md += [
            "| Key alias | Model group | Call type | Internal origin | Status |",
            "|" + " --- |" * 5,
        ]
        for s in t["other_spend_rows_in_window"]:
            md.append(
                f"| {s['key_alias'] or '—'} | {s['model_group'] or '—'} | {s['call_type']} | "
                f"{s['internal_call_origin'] or '—'} | {s['status']} |"
            )
    else:
        md.append("None.")
    a = t.get("agent")
    if a:
        md += ["", "## The agent run", ""]
        md.append(
            f"Agent request: HTTP {a['run'].get('status')}, session `{a['run'].get('session_id')}`."
        )
        md.append(
            f"- Agent request-log entries for /run: {len(a['agent_request_logs'])} "
            f"(traces {[e['trace'] for e in a['agent_request_logs']]})"
        )
        gw = a["gateway_request_logs_during_the_run"]
        md.append(
            f"- Gateway request-log entries during the run: {len(gw)} "
            f"(traces {[e['trace'] for e in gw]}, "
            f"user agents {sorted({e['user_agent'] for e in gw})})"
        )
        sr = a["spend_rows_during_the_run"]
        md.append(
            f"- Spend-log rows for key `agw-agent` during the run: {len(sr)} "
            f"(sessions {[r['session_id'] for r in sr]}; equal to a gateway request-log trace: "
            f"{[r.get('session_is_a_request_log_trace') for r in sr]})"
        )
        md.append(
            f"- Agent container logs: {a['agent_logs']['container_log_lines']} lines; "
            f"containing {a['agent_logs']['entries_containing']}; "
            f"naming a caller identity: {a['agent_logs']['entries_naming_a_caller_identity']}"
        )
    g = t["gateway_logs"]
    md += ["", "## Gateway Cloud Run logs", ""]
    md.append(
        f"{len(g['request_log_entries'])} request-log entries, "
        f"{g['container_log_lines']} container lines; "
        f"containing {g['entries_containing']}; naming a caller identity: "
        f"{g['entries_naming_a_caller_identity']}."
    )
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    main(sys.argv[1])
