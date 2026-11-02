import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scenarios" / "bifrost" / "audit_trail.py"
spec = importlib.util.spec_from_file_location("bifrost_audit_trail", SCRIPT)
audit_trail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_trail)

FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"  # gitleaks:allow
FAKE_VKEY = "sk-bf-0123456789abcdef"  # gitleaks:allow

T0 = "2026-10-24T10:00:00Z"
T0_EPOCH = audit_trail.parse_time(T0)


# --- tag_of ---------------------------------------------------------------


def test_tag_of_reads_prefixed_key_from_dict_metadata():
    assert audit_trail.tag_of({"metadata": {"x-bf-lh-agw-case": "case-a"}}) == "case-a"


def test_tag_of_reads_unprefixed_key_and_ignores_case():
    assert audit_trail.tag_of({"metadata": {"agw-case": "case-b"}}) == "case-b"
    assert audit_trail.tag_of({"metadata": {"X-BF-LH-AGW-Case": "case-c"}}) == "case-c"


def test_tag_of_reads_metadata_stored_as_json_string():
    md = json.dumps({"x-bf-lh-agw-case": "case-d"})
    assert audit_trail.tag_of({"metadata": md}) == "case-d"


def test_tag_of_returns_none_when_missing_or_unusable():
    assert audit_trail.tag_of({}) is None
    assert audit_trail.tag_of({"metadata": {"other": "x"}}) is None
    assert audit_trail.tag_of({"metadata": "not json"}) is None
    assert audit_trail.tag_of({"metadata": ["x-bf-lh-agw-case"]}) is None
    assert audit_trail.tag_of({"metadata": {"x-bf-lh-agw-case": 5}}) is None


# --- summarise_row --------------------------------------------------------


def log_row(**fields):
    base = {
        "id": "req-1",
        "timestamp": T0,
        "virtual_key_name": "agw-harness",
        "provider": "vertex",
        "model": "gemini-3.8-flash",
        "status": "success",
        "session_id": "agw-t6-session",
        "metadata": {"x-bf-lh-agw-case": "case-a"},
        "token_usage": {"total_tokens": 42},
        "cost": 0.001,
    }
    return {**base, **fields}


def test_summarise_row_keeps_identity_fields_and_tag():
    s = audit_trail.summarise_row(log_row(latency=120, overhead_latency=3))
    assert s["id"] == "req-1" and s["virtual_key"] == "agw-harness"
    assert s["session_id"] == "agw-t6-session" and s["tag"] == "case-a"
    assert s["tokens"] == 42 and s["latency_ms"] == 120 and s["overhead_ms"] == 3
    assert s["metadata_keys"] == ["x-bf-lh-agw-case"]


def test_summarise_row_flags_content_without_copying_it():
    stored = log_row(
        input_history=[{"role": "user", "content": "AGW-T6-MARKER: hi"}],
        output_message={"content": "hello"},
        headers={"x-serverless-authorization": f"Bearer {FAKE_JWT}", "key": FAKE_VKEY},
    )
    s = audit_trail.summarise_row(stored)
    assert s["content"] == {
        "prompt_marker": True,
        "input_stored": True,
        "output_stored": True,
        "id_token": True,
        "virtual_key_value": True,
        "serverless_auth_header": True,
    }
    dumped = json.dumps(s)
    for value in (FAKE_JWT, FAKE_VKEY, "AGW-T6-MARKER", "hello"):
        assert value not in dumped, "the summary must keep flags, not values"


def test_summarise_row_with_nothing_stored_has_all_flags_false():
    s = audit_trail.summarise_row(log_row(input_history=[], output_message=None))
    assert not any(s["content"].values())


def test_summarise_row_tolerates_missing_usage_and_metadata():
    s = audit_trail.summarise_row({"id": "x"})
    assert s["tokens"] is None and s["tag"] is None and s["metadata_keys"] == []
    s = audit_trail.summarise_row({"id": "x", "token_usage": "odd"})
    assert s["tokens"] is None


# --- join -----------------------------------------------------------------


def srow(rid, tag=None, session=None, key="agw-harness", time=T0):
    return {"id": rid, "tag": tag, "session_id": session, "virtual_key": key, "time": time}


def outcome(case, rid=None, tagged=False, status=200):
    o = {"case": case, "status": status, "tagged": tagged}
    if rid:
        o["headers"] = {"x-request-id": rid}
    return o


NO_LOGS = {"request_log_entries": []}


def entry(trace, offset, path="/v1/chat/completions"):
    return {"trace": trace, "path": path, "time": audit_trail.iso(T0_EPOCH + offset)}


def test_join_prefers_request_id_over_tag():
    rows = [srow("r1", tag="other"), srow("r2", tag="case-a")]
    j = audit_trail.join([outcome("case-a", rid="r1")], rows, NO_LOGS)
    assert j["requests"][0]["row"] == "r1"
    assert j["requests"][0]["joined_by"] == "request id"
    assert j["unjoined_rows"] == ["r2"]


def test_join_falls_back_to_tag_when_request_id_unknown():
    rows = [srow("r1", tag="case-a")]
    j = audit_trail.join([outcome("case-a", rid="nope")], rows, NO_LOGS)
    assert j["requests"][0]["joined_by"] == "tag" and j["requests"][0]["row"] == "r1"


def test_join_by_session_only_for_tagged_cases():
    rows = [srow("r1", session=audit_trail.SESSION)]
    j = audit_trail.join(
        [outcome("tagged", tagged=True), outcome("plain", tagged=False)], rows, NO_LOGS
    )
    by_case = {r["case"]: r for r in j["requests"]}
    joined = by_case["tagged"]
    assert joined["joined_by"] == "session and model (ambiguous)" and joined["row"] == "r1"
    assert by_case["plain"]["row"] is None and by_case["plain"]["joined_by"] is None


def test_join_never_uses_a_row_twice():
    rows = [srow("r1", tag="dup")]
    j = audit_trail.join([outcome("dup"), outcome("dup")], rows, NO_LOGS)
    assert [r["row"] for r in j["requests"]] == ["r1", None]


def test_join_session_does_not_reuse_row_taken_by_request_id():
    rows = [srow("r1", session=audit_trail.SESSION)]
    j = audit_trail.join(
        [outcome("a", rid="r1", tagged=True), outcome("b", tagged=True)], rows, NO_LOGS
    )
    assert [r["row"] for r in j["requests"]] == ["r1", None]


def test_join_agent_row_by_key_name_and_time_window():
    agent = {"started_at": T0_EPOCH, "ended_at": T0_EPOCH + 10}
    rows = [
        srow("wrong-key", key="agw-harness", time=audit_trail.iso(T0_EPOCH + 1)),
        srow("too-early", key="agw-agent", time=audit_trail.iso(T0_EPOCH - 1)),
        srow("too-late", key="agw-agent", time=audit_trail.iso(T0_EPOCH + 16)),
        srow("good", key="agw-agent", time=audit_trail.iso(T0_EPOCH + 14)),  # within end + 5
    ]
    j = audit_trail.join([], rows, NO_LOGS, agent)
    assert j["agent_row"] == "good"
    assert "good" not in j["unjoined_rows"] and "wrong-key" in j["unjoined_rows"]


def test_join_agent_row_is_none_without_agent_or_match():
    rows = [srow("r1", key="agw-agent")]
    assert audit_trail.join([], rows, NO_LOGS)["agent_row"] is None
    agent = {"started_at": T0_EPOCH + 100, "ended_at": T0_EPOCH + 110}
    assert audit_trail.join([], rows, NO_LOGS, agent)["agent_row"] is None


def test_join_agent_does_not_take_a_row_already_joined_to_a_request():
    agent = {"started_at": T0_EPOCH - 1, "ended_at": T0_EPOCH + 1}
    rows = [srow("r1", key="agw-agent")]
    j = audit_trail.join([outcome("a", rid="r1")], rows, NO_LOGS, agent)
    assert j["agent_row"] is None


def test_join_nearest_cloud_run_request_within_30s():
    logs = {
        "request_log_entries": [
            entry("far", 25),
            entry("near", 4),
            entry("wrong-path", 0, path="/api/logs"),
        ]
    }
    j = audit_trail.join([outcome("a", rid="r1")], [srow("r1")], logs)
    assert j["requests"][0]["cloud_run_trace_by_time"] == "near"


def test_join_cloud_run_trace_is_none_beyond_30s_or_without_row():
    logs = {"request_log_entries": [entry("late", 31)]}
    j = audit_trail.join([outcome("a", rid="r1"), outcome("b")], [srow("r1")], logs)
    assert [r["cloud_run_trace_by_time"] for r in j["requests"]] == [None, None]


def test_join_agent_row_gets_its_own_nearest_trace():
    agent = {"started_at": T0_EPOCH, "ended_at": T0_EPOCH + 1}
    logs = {"request_log_entries": [entry("agent-trace", 2)]}
    j = audit_trail.join([], [srow("a1", key="agw-agent")], logs, agent)
    assert j["agent_row_trace_by_time"] == "agent-trace"


def test_join_lists_unjoined_rows():
    rows = [srow("r1", tag="case-a"), srow("stray")]
    j = audit_trail.join([outcome("case-a")], rows, NO_LOGS)
    assert j["unjoined_rows"] == ["stray"]


# --- render ---------------------------------------------------------------


def trail(agent_run=None, agent_row=None):
    rows = [
        {
            "id": "r1",
            "virtual_key": "agw-harness",
            "session_id": "agw-t6-session",
            "tag": "case-a",
            "user_agent": "python-httpx",
            "content": {"input_stored": True, "id_token": False},
        }
    ]
    requests = [
        {
            "case": "case-a",
            "status": 200,
            "row": "r1",
            "joined_by": "request id",
            "cloud_run_trace_by_time": "trace-1",
        },
        {
            "case": "case-b",
            "status": 500,
            "row": None,
            "joined_by": None,
            "cloud_run_trace_by_time": None,
        },
    ]
    return {
        "window": {"start": "s", "end": "e"},
        "rows": rows,
        "gateway_cloud_run": {"request_log_entries": [1, 2], "entries_naming_a_caller_identity": 0},
        "agent_run": agent_run,
        "join": {
            "requests": requests,
            "agent_row": agent_row,
            "agent_row_trace_by_time": None,
            "unjoined_rows": [],
        },
        "response_headers": {"case-a": {"x-request-id": "r1"}, "case-b": None},
    }


def test_render_has_one_table_row_per_request():
    lines = audit_trail.render(trail()).splitlines()
    table = [ln for ln in lines if ln.startswith("| case-")]
    assert len(table) == 2
    assert "| case-a | 200 | found | request id | agw-harness |" in table[0]
    assert "| yes | no |" in table[0]
    assert "| case-b | 500 | none | - | - | - | - | - | no | no |" == table[1]


def test_render_omits_agent_paragraph_without_agent_run():
    assert "Agent run" not in audit_trail.render(trail())


def test_render_includes_agent_paragraph_when_agent_run_set():
    t = trail(agent_run={"session_id": "sess-9", "status": 200}, agent_row="r1")
    out = audit_trail.render(t)
    assert "**Agent run** (session `sess-9`, HTTP 200): gateway row found" in out
    assert "user agent `python-httpx`" in out


def test_render_reports_agent_row_not_found():
    t = trail(agent_run={"session_id": "sess-9", "status": 200}, agent_row=None)
    assert "gateway row not found" in audit_trail.render(t)


def test_render_records_only_non_empty_response_headers():
    out = audit_trail.render(trail())
    assert '"case-a"' in out and '"case-b"' not in out


def test_join_tries_every_request_id_before_any_weaker_key():
    # The tagged request without an id must not take the session row that a later
    # request's own id points at.
    rows = [srow("r1", session=audit_trail.SESSION), srow("r2", session=audit_trail.SESSION)]
    j = audit_trail.join(
        [outcome("first", tagged=True), outcome("second", rid="r1", tagged=True)], rows, NO_LOGS
    )
    by_case = {r["case"]: r for r in j["requests"]}
    assert by_case["second"]["row"] == "r1" and by_case["second"]["joined_by"] == "request id"
    assert by_case["first"]["row"] == "r2"


def test_join_by_session_needs_the_same_model():
    rows = [{**srow("r1", session=audit_trail.SESSION), "model": "gemini-3.8-flash"}]
    o = {**outcome("tagged", tagged=True), "model": "claude-haiku-5-5"}
    assert audit_trail.join([o], rows, NO_LOGS)["requests"][0]["row"] is None


def test_metadata_as_a_json_string_counts_for_tags_and_keys():
    row = {"metadata": '{"x-bf-lh-agw-case": "a", "x-bf-lh-agw-test": "6"}'}
    assert audit_trail.tag_of(row) == "a"
    assert audit_trail.summarise_row(row)["metadata_keys"] == [
        "x-bf-lh-agw-case",
        "x-bf-lh-agw-test",
    ]
