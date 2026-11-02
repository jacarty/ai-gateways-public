"""Test 6 (audit fidelity) on Kong: collect the trail a run left and try to join it.

Usage: python3 audit_trail.py <run_dir>   (run-audit.sh calls it; standard library only)

Kong keeps no request store: its record is the file-log line per request on stdout, in
Cloud Logging, next to Cloud Run's own request log. So everything comes from gcloud
logging for the run's time window (from outcomes.jsonl, agent-run.json and
admin-probe.json in the run directory):

- Kong's rows, joined to each request by the X-Kong-Request-Id Kong returned (it is the
  row's request.id), else by the caller's own tag (its x-agw-case header, which the row
  keeps with every other request header);
- each row to its Cloud Run request-log entry by trace: the row keeps the
  X-Cloud-Trace-Context header Cloud Run added, whose trace id is the entry's;
- the agent's own call to Kong by consumer ("agent") and time, and to the agent's
  /run by the trace in the call's traceparent, if the agent propagated it;
- the admin probe's /admin-api rows (Kong OSS has no admin audit log).

Writes trail.json (the evidence, redacted) and trail.md (what joined and what didn't)
into the run directory, which are committed. Header names are kept, and the values of only
user-agent, the caller's x-agw-* tags and the trace ids; content is kept only as flags.
A request refused before routing (404, no route) is logged too, with no route, service or
consumer: only its tag and user agent say whose it was.
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agw_harness.trail import (  # noqa: E402
    ip_kind,
    iso,
    logging_read,
    parse_time,
    redact,
    summarise_logs,
)

MARKER = "AGW-T6-MARKER"
SESSION = "agw-t6-session"
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.")
TOKEN = re.compile(r"\bya29\.")


def _trace(value: str | None) -> str | None:
    """The trace id in an X-Cloud-Trace-Context ("<trace>/<span>;o=1") or a W3C
    traceparent ("00-<trace>-<span>-<flags>") header."""
    if not value:
        return None
    if value.startswith("00-") and value.count("-") == 3:
        return value.split("-")[1]
    return value.split("/", 1)[0] or None


def summarise_row(entry: dict) -> dict:
    """A Kong file-log row reduced to what an auditor needs; content to flags only."""
    p = entry["jsonPayload"]
    raw = json.dumps(p)
    req, resp = p.get("request") or {}, p.get("response") or {}
    headers = {k.lower(): v for k, v in (req.get("headers") or {}).items()}
    ai = p.get("ai") or {}
    proxy = ai.get("proxy") or {}
    usage, meta = proxy.get("usage") or {}, proxy.get("meta") or {}
    consumer = p.get("consumer") or {}
    return {
        "id": req.get("id"),
        "time": iso(p["started_at"] / 1000) if p.get("started_at") else entry.get("timestamp"),
        "consumer": consumer.get("username"),
        "consumer_tags": consumer.get("tags"),
        "route": (p.get("route") or {}).get("name"),
        "service": (p.get("service") or {}).get("name"),
        "method": req.get("method"),
        "path": req.get("uri", "").split("?", 1)[0],
        "status": resp.get("status"),
        "upstream_status": p.get("upstream_status"),
        "latency_ms": (p.get("latencies") or {}).get("request"),
        "kong_ms": (p.get("latencies") or {}).get("kong"),
        "model": meta.get("response_model") or meta.get("request_model"),
        "tokens": usage.get("total_tokens"),
        "cost": usage.get("cost"),
        "user_agent": headers.get("user-agent"),
        "client_ip": ip_kind(p.get("client_ip")),
        "session": headers.get("x-agw-session"),
        "tag": headers.get("x-agw-case"),
        "cloud_run_trace": _trace(headers.get("x-cloud-trace-context")),
        "traceparent_trace": _trace(headers.get("traceparent")),
        "header_names": sorted(headers),
        # On model rows the caller's key is already gone (key-auth hide_credentials) and
        # the Authorization Kong's serializer redacts is Kong's own Google token (ai-proxy);
        # on a 404 no-route row it is the caller's key. kong.yaml's custom field always
        # writes x-serverless-authorization as REDACTED, sent or not. So the two flags say
        # what the row shows; the *_anywhere scans are the real check.
        "credentials": {
            "authorization": "REDACTED"
            if headers.get("authorization") == "REDACTED"
            else ("absent" if "authorization" not in headers else "NOT REDACTED"),
            "x_serverless_authorization": "REDACTED"
            if headers.get("x-serverless-authorization") == "REDACTED"
            else ("absent" if "x-serverless-authorization" not in headers else "NOT REDACTED"),
            "jwt_anywhere": bool(JWT.search(raw)),
            "google_token_anywhere": bool(TOKEN.search(raw)),
        },
        "content": {
            "prompt_marker": MARKER in raw,
            "payload_logged": any(
                "payload" in (v or {}) for v in ai.values() if isinstance(v, dict)
            ),
        },
    }


def no_queries(logs: dict | None) -> dict | None:
    """summarise_logs keeps each request's query string, and a Kong key sent there (43
    URL-safe characters) is no pattern redact() knows: drop every query string."""
    for e in (logs or {}).get("request_log_entries", []):
        e["path"] = (e.get("path") or "").split("?", 1)[0]
    return logs


def split(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Kong's file-log rows and the rest (Cloud Run's request log, container lines)."""
    rows = [e for e in entries if ((e.get("jsonPayload") or {}).get("request") or {}).get("id")]
    rest = [e for e in entries if e not in rows]
    return rows, rest


def join(outcomes, rows, gateway_logs, agent_logs, agent, probe):
    used: set = set()
    joined: dict[int, tuple[dict, str]] = {}
    for i, o in enumerate(outcomes):
        rid = (o.get("headers") or {}).get("x-kong-request-id")
        row = next((r for r in rows if rid and r["id"] == rid and r["id"] not in used), None)
        if row:
            used.add(row["id"])
            joined[i] = (row, "request id")
    for i, o in enumerate(outcomes):
        if i not in joined:
            row = next((r for r in rows if r["tag"] == o["case"] and r["id"] not in used), None)
            if row:
                used.add(row["id"])
                joined[i] = (row, "tag")

    traces = {e["trace"]: e for e in gateway_logs["request_log_entries"] if e.get("trace")}
    requests = []
    for i, o in enumerate(outcomes):
        row = joined.get(i, (None, None))[0]
        entry = traces.get(row["cloud_run_trace"]) if row else None
        requests.append(
            {
                "case": o["case"],
                "status": o["status"],
                "row": row["id"] if row else None,
                "joined_by": joined[i][1] if i in joined else None,
                "cloud_run_entry_by_trace": bool(entry),
                "cloud_run_status": entry["status"] if entry else None,
            }
        )

    agent_join = None
    if agent:
        t0, t1 = agent["started_at"] - 2, agent["ended_at"] + 5  # Kong's clock vs ours
        mine = [
            r
            for r in rows
            if r["consumer"] == "agent"
            and r["id"] not in used
            and t0 <= (parse_time(r["time"]) or 0) <= t1
        ]
        # Only the agent's own /run: the request-log entry is written when it ends.
        runs = [
            e
            for e in (agent_logs or {}).get("request_log_entries", [])
            if e["path"] == "/run" and t0 - 5 <= (parse_time(e["time"]) or 0) <= t1 + 5
        ]
        run_traces = {e["trace"] for e in runs if e.get("trace")}
        agent_join = {
            "rows": [r["id"] for r in mine],
            "user_agents": sorted({r["user_agent"] or "-" for r in mine}),
            "agent_run_traces": sorted(run_traces),
            "row_traceparent_traces": sorted({r["traceparent_trace"] or "-" for r in mine}),
            "joined_by_trace": any(r["traceparent_trace"] in run_traces for r in mine),
            "ambiguous": len(runs) > 1,
        }
        used.update(r["id"] for r in mine)

    admin = []
    if probe:
        t0, t1 = probe["started_at"] - 2, probe["ended_at"] + 5
        for r in rows:
            if r["route"] == "admin-api" and t0 <= (parse_time(r["time"]) or 0) <= t1:
                used.add(r["id"])
                admin.append(
                    {
                        k: r[k]
                        for k in (
                            "id",
                            "time",
                            "consumer",
                            "method",
                            "path",
                            "status",
                            "user_agent",
                        )
                    }
                    | {"names_the_probe": probe["consumer"] in r["path"]}
                )
    return {
        "requests": requests,
        "agent": agent_join,
        "admin_rows": admin,
        "unjoined_rows": [
            {k: r[k] for k in ("id", "route", "consumer", "method", "path", "status")}
            for r in rows
            if r["id"] not in used
        ],
    }


def main(run_dir: str) -> None:
    run = Path(run_dir)
    outcomes = [json.loads(line) for line in (run / "outcomes.jsonl").read_text().splitlines()]
    agent = (
        json.loads((run / "agent-run.json").read_text())
        if (run / "agent-run.json").exists()
        else None
    )
    probe = (
        json.loads((run / "admin-probe.json").read_text())
        if (run / "admin-probe.json").exists()
        else None
    )
    # The run's own window, from what was recorded, so re-running the collector later
    # doesn't pull in other traffic.
    t0 = min(o["started_at"] for o in outcomes) - 5
    last = max(o["started_at"] + (o.get("latency_s") or 0) for o in outcomes)
    t1 = max(last, (agent or {}).get("ended_at", 0), (probe or {}).get("ended_at", 0)) + 60

    # Rows reach Cloud Logging a few seconds late: retry until every request id Kong
    # returned, an agent row in the agent's window and both probe operations show, or give
    # up after about a minute and record what was missing.
    wanted = {(o.get("headers") or {}).get("x-kong-request-id") for o in outcomes} - {None}
    for _ in range(7):
        entries = logging_read("agw-kong", t0, t1)
        row_entries, rest = split(entries)
        rows = [summarise_row(e) for e in row_entries]
        missing = {
            "request_ids": sorted(wanted - {r["id"] for r in rows}),
            "agent_row": bool(agent)
            and not any(
                r["consumer"] == "agent"
                and agent["started_at"] - 2 <= (parse_time(r["time"]) or 0) <= agent["ended_at"] + 5
                for r in rows
            ),
            "admin_rows": bool(probe)
            and {"POST", "DELETE"}
            - {
                r["method"]
                for r in rows
                if r["route"] == "admin-api"
                and probe["started_at"] - 2 <= (parse_time(r["time"]) or 0) <= probe["ended_at"] + 5
            }
            != set(),
        }
        if not any(missing.values()):
            break
        time.sleep(10)
    else:
        print(f"WARNING: after about a minute, still missing: {missing}")
    rows.sort(key=lambda r: r["time"] or "")
    needles = {"prompt_marker": MARKER, "session": SESSION}
    if probe:  # Kong's admin access log (stdout) is a second admin trail: does it name it?
        needles["admin_probe"] = probe["consumer"]
    gateway_logs = no_queries(summarise_logs(rest, needles))
    agent_logs = (
        no_queries(summarise_logs(logging_read("agw-agent", t0, t1), needles)) if agent else None
    )

    trail = {
        "window": {"start": iso(t0), "end": iso(t1)},
        "collection_missing": missing,
        "rows": rows,
        "gateway_cloud_run": gateway_logs,
        "agent_cloud_run": agent_logs,
        "agent_run": agent,
        "admin_probe": probe,
        "join": join(outcomes, rows, gateway_logs, agent_logs, agent, probe),
        "response_headers": {o["case"]: o.get("headers") for o in outcomes},
    }
    trail = redact(trail)
    (run / "trail.json").write_text(json.dumps(trail, indent=1) + "\n")
    (run / "trail.md").write_text(render(trail))
    print(f"wrote {run / 'trail.json'} and trail.md: {len(rows)} Kong rows")


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
        "Kong row",
        "Joined by",
        "Consumer",
        "Route",
        "Session",
        "Tag",
        "Tokens",
        "Cloud Run entry (by trace)",
        "Prompt logged",
        "Credentials redacted",
    )
    lines = [
        "# Test 6 trail (Kong)",
        "",
        f"Window {t['window']['start']} to {t['window']['end']}: {len(t['rows'])} Kong rows, "
        f"{len(cr['request_log_entries'])} gateway request-log entries, "
        f"{cr['entries_naming_a_caller_identity']} entries naming a Google identity.",
        "",
        "Collection: "
        + (
            "complete."
            if not any((t.get("collection_missing") or {}).values())
            else f"incomplete after about a minute: {json.dumps(t['collection_missing'])}."
        ),
        "",
        cells(*head),
        cells(*["---"] * len(head)),
    ]
    for j in t["join"]["requests"]:
        r = rows.get(j["row"]) or {}
        c, cred = r.get("content") or {}, r.get("credentials") or {}
        redacted = (
            "-"
            if not r
            else yn(
                cred.get("authorization") in ("REDACTED", "absent")
                and cred.get("x_serverless_authorization") in ("REDACTED", "absent")
                and not cred.get("jwt_anywhere")
                and not cred.get("google_token_anywhere")
            )
        )
        lines.append(
            cells(
                j["case"],
                j["status"],
                "found" if r else "none",
                j["joined_by"] or "-",
                r.get("consumer") or "-",
                r.get("route") or "-",
                r.get("session") or "-",
                r.get("tag") or "-",
                r.get("tokens") if r.get("tokens") is not None else "-",
                f"yes ({j['cloud_run_status']})" if j["cloud_run_entry_by_trace"] else "no",
                yn(c.get("prompt_marker")),
                redacted,
            )
        )
    a = t["join"].get("agent")
    if t.get("agent_run") and a is not None:
        run = t["agent_run"]
        lines += [
            "",
            f"**Agent run** (session `{run['session_id']}`, HTTP {run['status']}): "
            f"{len(a['rows'])} Kong row(s) by consumer `agent` and time, user agent "
            f"{', '.join(f'`{u}`' for u in a['user_agents']) or '-'}; joined to the agent's "
            f"`/run` by trace: {yn(a['joined_by_trace'])} (its row's traceparent trace "
            f"{', '.join(a['row_traceparent_traces']) or '-'}, the agent's /run trace "
            f"{', '.join(a['agent_run_traces']) or '-'}).",
        ]
    if t.get("admin_probe"):
        lines += [
            "",
            "**Admin probe** (a throwaway consumer made and deleted through `/admin-api`):",
            "",
        ]
        lines += [
            f"- {r['time']} {r['method']} {r['path']} → {r['status']}, consumer `{r['consumer']}`, "
            f"user agent `{r['user_agent']}`"
            + (" (names the probe)" if r["names_the_probe"] else "")
            for r in t["join"]["admin_rows"]
        ] or ["- no admin rows found"]
    lines += [
        "",
        f"Unjoined Kong rows: {len(t['join']['unjoined_rows'])}. Response headers recorded: "
        + json.dumps({k: v for k, v in t["response_headers"].items() if v}),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main(sys.argv[1])
