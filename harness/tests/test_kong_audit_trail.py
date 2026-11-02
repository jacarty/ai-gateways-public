import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scenarios" / "kong" / "audit_trail.py"
spec = importlib.util.spec_from_file_location("kong_audit_trail", SCRIPT)
audit_trail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_trail)

FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"  # gitleaks:allow

T0_MS = 1793550000000  # 2026-11-01, Kong's started_at is in milliseconds
T0 = T0_MS / 1000
TRACE = "0123456789abcdef0123456789abcdef"


# --- _trace -----------------------------------------------------------------


def test_trace_reads_cloud_trace_context_and_traceparent():
    assert audit_trail._trace(f"{TRACE}/123;o=1") == TRACE
    assert audit_trail._trace(f"00-{TRACE}-00f067aa0ba902b7-01") == TRACE
    assert audit_trail._trace(None) is None
    assert audit_trail._trace("") is None


# --- summarise_row ------------------------------------------------------------


def kong_entry(**payload):
    headers = {
        "authorization": "REDACTED",
        "x-serverless-authorization": "REDACTED",
        "user-agent": "python-httpx/0.28.1",
        "x-agw-session": "agw-t6-session",
        "x-agw-case": "case-a",
        "x-cloud-trace-context": f"{TRACE}/1;o=1",
    }
    base = {
        "request": {
            "id": "req-1",
            "method": "POST",
            "uri": "/v1/chat/completions?x=1",
            "headers": headers,
        },
        "response": {"status": 200},
        "consumer": {"username": "harness", "tags": None},
        "route": {"name": "gemini-chat"},
        "service": {"name": "gemini"},
        "started_at": T0_MS,
        "latencies": {"request": 1500, "kong": 3},
        "upstream_status": "200",
        "client_ip": "169.254.169.126",
        "ai": {
            "proxy": {
                "meta": {"response_model": "gemini-3.8-flash"},
                "usage": {"total_tokens": 42, "cost": 0.001},
            }
        },
    }
    for k, v in payload.items():
        base[k] = v
    return {"jsonPayload": base, "timestamp": "2026-11-01T00:00:00Z"}


def test_summarise_row_keeps_identity_fields_tag_and_trace():
    r = audit_trail.summarise_row(kong_entry())
    assert r["id"] == "req-1"
    assert r["consumer"] == "harness"
    assert r["route"] == "gemini-chat"
    assert r["path"] == "/v1/chat/completions"  # query string dropped
    assert (r["status"], r["tokens"], r["model"]) == (200, 42, "gemini-3.8-flash")
    assert (r["session"], r["tag"]) == ("agw-t6-session", "case-a")
    assert r["cloud_run_trace"] == TRACE
    assert r["client_ip"] == "link-local (Cloud Run front end)"
    assert r["time"].startswith("2026-")


def test_summarise_row_keeps_header_names_not_values():
    r = audit_trail.summarise_row(kong_entry())
    assert "user-agent" in r["header_names"]
    assert "python-httpx" not in json.dumps(r["header_names"])


def test_summarise_row_reports_redacted_credentials():
    c = audit_trail.summarise_row(kong_entry())["credentials"]
    assert c == {
        "authorization": "REDACTED",
        "x_serverless_authorization": "REDACTED",
        "jwt_anywhere": False,
        "google_token_anywhere": False,
    }


def test_summarise_row_flags_a_credential_kong_did_not_redact():
    entry = kong_entry()
    entry["jsonPayload"]["request"]["headers"]["x-serverless-authorization"] = f"Bearer {FAKE_JWT}"
    entry["jsonPayload"]["request"]["headers"].pop("authorization")
    c = audit_trail.summarise_row(entry)["credentials"]
    assert c["x_serverless_authorization"] == "NOT REDACTED"
    assert c["authorization"] == "absent"
    assert c["jwt_anywhere"] is True


def test_summarise_row_content_flags():
    plain = audit_trail.summarise_row(kong_entry())["content"]
    assert plain == {"prompt_marker": False, "payload_logged": False}
    ai = {"proxy": {"payload": {"request": "AGW-T6-MARKER: hi"}, "usage": {}}}
    logged = audit_trail.summarise_row(kong_entry(ai=ai))["content"]
    assert logged == {"prompt_marker": True, "payload_logged": True}


def test_summarise_row_tolerates_missing_parts():
    entry = {"jsonPayload": {"request": {"id": "r"}}, "timestamp": "2026-11-01T00:00:00Z"}
    r = audit_trail.summarise_row(entry)
    assert r["id"] == "r" and r["consumer"] is None and r["tokens"] is None
    assert r["time"] == "2026-11-01T00:00:00Z"


# --- split --------------------------------------------------------------------


def test_split_separates_kong_rows_from_cloud_run_entries():
    request_log = {"httpRequest": {"status": 200}, "trace": "projects/p/traces/x"}
    line = {"textPayload": "nginx access line"}
    rows, rest = audit_trail.split([kong_entry(), request_log, line])
    assert len(rows) == 1 and rest == [request_log, line]


# --- join ---------------------------------------------------------------------


def row(rid, **fields):
    r = audit_trail.summarise_row(kong_entry())
    r.update(id=rid, **fields)
    return r


def outcome(case, rid=None, status=200):
    return {"case": case, "status": status, "headers": {"x-kong-request-id": rid} if rid else {}}


def logs(*entries):
    return {"request_log_entries": list(entries)}


def test_join_by_request_id_then_tag():
    rows = [row("a", tag="case-x"), row("b", tag="case-b")]
    j = audit_trail.join(
        [outcome("case-a", "a"), outcome("case-b")], rows, logs(), None, None, None
    )
    assert [(r["row"], r["joined_by"]) for r in j["requests"]] == [
        ("a", "request id"),
        ("b", "tag"),
    ]


def test_join_never_uses_a_row_twice():
    rows = [row("a", tag="case-b")]
    j = audit_trail.join(
        [outcome("case-a", "a"), outcome("case-b")], rows, logs(), None, None, None
    )
    assert j["requests"][1]["row"] is None


def test_join_cloud_run_entry_by_trace_not_time():
    entry = {"trace": TRACE, "status": 200, "path": "/v1/chat/completions"}
    other = {"trace": "other", "status": 500, "path": "/v1/chat/completions"}
    j = audit_trail.join(
        [outcome("case-a", "req-1")], [row("req-1")], logs(other, entry), None, None, None
    )
    assert j["requests"][0]["cloud_run_entry_by_trace"] is True
    assert j["requests"][0]["cloud_run_status"] == 200


def test_join_agent_rows_by_consumer_and_time_and_trace():
    t = audit_trail.iso(T0)
    agent_row = row("ag", consumer="agent", time=t, traceparent_trace=TRACE, tag=None)
    agent = {"started_at": T0 - 1, "ended_at": T0 + 1}
    agent_logs = logs({"trace": TRACE, "path": "/run", "status": 200, "time": t})
    j = audit_trail.join([], [agent_row], logs(), agent_logs, agent, None)
    assert j["agent"]["rows"] == ["ag"]
    assert j["agent"]["joined_by_trace"] is True
    assert j["unjoined_rows"] == []


def test_join_agent_without_a_shared_trace_is_reported():
    t = audit_trail.iso(T0)
    agent_row = row("ag", consumer="agent", time=t, traceparent_trace=None, tag=None)
    agent = {"started_at": T0 - 1, "ended_at": T0 + 1}
    agent_logs = logs({"trace": TRACE, "path": "/run", "status": 200, "time": t})
    j = audit_trail.join([], [agent_row], logs(), agent_logs, agent, None)
    assert j["agent"]["joined_by_trace"] is False
    assert j["agent"]["row_traceparent_traces"] == ["-"]


def test_join_agent_ignores_rows_outside_its_window():
    late = row("ag", consumer="agent", time=audit_trail.iso(T0 + 60), tag=None)
    j = audit_trail.join([], [late], logs(), logs(), {"started_at": T0, "ended_at": T0}, None)
    assert j["agent"]["rows"] == []
    assert j["unjoined_rows"][0]["id"] == "ag"


def test_join_admin_rows_in_the_probe_window():
    t = audit_trail.iso(T0)
    probe = {"consumer": "agw-t6-admin-probe-x", "started_at": T0, "ended_at": T0 + 1}
    post = row("p1", route="admin-api", time=t, method="POST", path="/admin-api/consumers")
    delete = row(
        "p2",
        route="admin-api",
        time=t,
        method="DELETE",
        path="/admin-api/consumers/agw-t6-admin-probe-x",
    )
    j = audit_trail.join([], [post, delete], logs(), None, None, probe)
    assert [a["method"] for a in j["admin_rows"]] == ["POST", "DELETE"]
    assert [a["names_the_probe"] for a in j["admin_rows"]] == [False, True]
    assert j["unjoined_rows"] == []


# --- render -------------------------------------------------------------------


def trail(**extra):
    r = row("req-1")
    t = {
        "window": {"start": "s", "end": "e"},
        "rows": [r],
        "gateway_cloud_run": {"request_log_entries": [], "entries_naming_a_caller_identity": 0},
        "agent_run": None,
        "admin_probe": None,
        "join": audit_trail.join(
            [outcome("case-a", "req-1"), outcome("case-b", status=404)],
            [r],
            logs(),
            None,
            None,
            None,
        ),
        "response_headers": {"case-a": {"x-kong-request-id": "req-1"}, "case-b": {}},
    }
    t.update(extra)
    return t


def test_render_has_one_row_per_request_and_marks_missing_rows():
    md = audit_trail.render(trail())
    assert "| case-a | 200 | found | request id | harness |" in md
    assert "| case-b | 404 | none | - |" in md
    assert '"case-b"' not in md  # empty response headers left out


def test_render_says_credentials_redacted():
    md = audit_trail.render(trail())
    line = next(x for x in md.splitlines() if x.startswith("| case-a"))
    assert line.rstrip(" |").endswith("yes")


def test_render_omits_agent_and_admin_paragraphs_without_them():
    md = audit_trail.render(trail())
    assert "Agent run" not in md and "Admin probe" not in md


# --- review fixes -------------------------------------------------------------


def test_no_queries_drops_query_strings_from_cloud_run_paths():
    out = audit_trail.no_queries(logs({"path": "/v1/x?authorization=Bearer%20abc", "trace": "t"}))
    assert out["request_log_entries"][0]["path"] == "/v1/x"
    assert audit_trail.no_queries(None) is None


def test_join_agent_trace_only_from_runs_in_its_window():
    t = audit_trail.iso(T0)
    agent_row = row("ag", consumer="agent", time=t, traceparent_trace=TRACE, tag=None)
    agent = {"started_at": T0 - 1, "ended_at": T0 + 1}
    elsewhere = {"trace": TRACE, "path": "/run", "status": 200, "time": audit_trail.iso(T0 + 300)}
    j = audit_trail.join([], [agent_row], logs(), logs(elsewhere), agent, None)
    assert j["agent"]["joined_by_trace"] is False
    assert j["agent"]["ambiguous"] is False


def test_render_reports_incomplete_collection():
    md = audit_trail.render(trail(collection_missing={"request_ids": ["x"], "agent_row": False}))
    assert "incomplete" in md
    assert "Collection: complete." in audit_trail.render(trail(collection_missing={}))


def test_summarise_row_for_a_404_before_routing():
    entry = kong_entry(route=None, service=None, consumer=None, ai=None)
    entry["jsonPayload"]["response"] = {"status": 404}
    r = audit_trail.summarise_row(entry)
    assert (r["route"], r["service"], r["consumer"], r["status"]) == (None, None, None, 404)
    assert r["tag"] == "case-a"  # only the caller's own tag says whose it was
    assert r["tokens"] is None and r["content"]["payload_logged"] is False


def test_redact_scrubs_a_token_in_a_kept_value():
    entry = kong_entry()
    entry["jsonPayload"]["request"]["headers"]["user-agent"] = f"x {FAKE_JWT}"
    r = audit_trail.redact(audit_trail.summarise_row(entry))
    assert FAKE_JWT not in json.dumps(r)
