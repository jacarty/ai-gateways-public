import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scenarios" / "litellm" / "audit_trail.py"
spec = importlib.util.spec_from_file_location("audit_trail", SCRIPT)
audit_trail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_trail)

FAKE_HASH = "c2f4a1a9463218c56f37c525b58a239861a01d640490b7031b4d8fdda2b91d25"  # gitleaks:allow
FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"  # gitleaks:allow


def test_redact_removes_secrets_and_personal_emails_but_keeps_service_accounts():
    text = (
        f"hash {FAKE_HASH} key sk-AbCdEfGh1234567890xyz token {FAKE_JWT} "
        "user someone@example.com sa agw-agent@my-gcp-project.iam.gserviceaccount.com"
    )
    out = audit_trail.redact({"a": [text]})["a"][0]
    for secret in (FAKE_HASH, "sk-AbCdEfGh1234567890xyz", FAKE_JWT, "someone@example.com"):
        assert secret not in out
    assert "agw-agent@my-gcp-project.iam.gserviceaccount.com" in out


def row(**fields):
    base = {
        "request_id": "chatcmpl-1",
        "startTime": "2026-10-21T10:00:00.000Z",
        "model_group": "claude-haiku-5-5",
        "status": "success",
        "session_id": "agw-t6-session",
        "metadata": json.dumps(
            {
                "litellm_call_id": "call-1",
                "user_api_key_alias": "agw-harness",
                "spend_logs_metadata": {"agw_test": "6"},
            }
        ),
    }
    return {**base, **fields}


def test_summarise_row_flags_content_without_copying_it():
    stored = row(
        messages=[{"role": "user", "content": "AGW-T6-MARKER: hi"}],
        proxy_server_request={"headers": {"x-serverless-authorization": f"Bearer {FAKE_JWT}"}},
    )
    s = audit_trail.summarise_row(stored)
    assert s["call_id"] == "call-1" and s["key_alias"] == "agw-harness"
    assert s["content_stored"] == {
        "messages": True,
        "response": False,
        "proxy_server_request": True,
    }
    assert s["stored_header_names"] == ["x-serverless-authorization"]
    assert s["contains"] == {
        "prompt_marker": True,
        "id_token_jwt": True,
        "bearer_value": True,
        "x_serverless_authorization": True,
    }
    assert FAKE_JWT not in json.dumps(s), "the summary must keep flags, not values"


def test_summarise_row_with_nothing_stored():
    s = audit_trail.summarise_row(row(messages={}, response={}, proxy_server_request={}))
    assert s["content_stored"] == {
        "messages": False,
        "response": False,
        "proxy_server_request": False,
    }
    assert not any(s["contains"].values())


def test_parse_time_handles_zulu_and_naive_times():
    assert audit_trail.parse_time("2026-10-21T10:00:00Z") == audit_trail.parse_time(
        "2026-10-21T10:00:00"
    )
    assert audit_trail.parse_time("not a time") is None and audit_trail.parse_time(None) is None


def test_render_reports_each_request_and_the_session():
    s = audit_trail.summarise_row(row())
    trail = {
        "run_id": "r",
        "window": ["a", "b"],
        "requests": [
            {"case": "session-claude", "http": 200, "joined_by": "call id", "spend_row": s}
        ],
        "session": {"id": "agw-t6-session", "rows": [s]},
        "other_spend_rows_in_window": [],
        "agent": None,
        "gateway_logs": {
            "request_log_entries": [],
            "container_log_lines": 0,
            "entries_containing": {},
            "entries_naming_a_caller_identity": 0,
        },
    }
    md = audit_trail.render(trail)
    assert (
        "| session-claude | 200 | call id | agw-harness | claude-haiku-5-5 | success | tagged |"
        in md
    )
    assert "Session `agw-t6-session`: 1 spend-log rows." in md


def test_redact_regressions_from_review():
    out = audit_trail.redact(
        "alice@gmail.com,sa@p.iam.gserviceaccount.com ALICE@GMAIL.COM AIza" + "B" * 35
    )
    assert "alice@gmail.com" not in out and "ALICE@GMAIL.COM" not in out
    assert "sa@p.iam.gserviceaccount.com" in out and "AIza" not in out


def test_ip_kind_never_keeps_the_address():
    assert audit_trail.ip_kind("169.254.169.126") == "link-local (Cloud Run front end)"
    assert audit_trail.ip_kind("10.1.2.3") == audit_trail.ip_kind("172.20.0.1") == "private"
    assert audit_trail.ip_kind("203.0.113.7") == "public (redacted)"
    assert audit_trail.ip_kind(None) is None


def summary(call_id, case=None, alias="agw-harness", session="s", start="2026-10-21T10:00:01Z"):
    return {
        "call_id": call_id,
        "spend_logs_metadata": {"agw_case": case} if case else None,
        "key_alias": alias,
        "session_id": session,
        "start": start,
    }


def outcome(case, call_id=None, status=200):
    headers = {"x-litellm-call-id": call_id} if call_id else {}
    return {"case": case, "status": status, "headers": headers}


LOGS = {"request_log_entries": [{"trace": "t-agent", "time": "2026-10-21T10:00:05Z", "path": "/x"}]}


def test_join_by_call_id_then_caller_metadata_and_never_twice():
    rows = [
        summary("c1", "a"),
        summary(None, "refused"),
        summary("c9", "dup"),
        summary("c8", "dup"),
    ]
    outcomes = [
        outcome("a", "c1"),
        outcome("refused", None, 403),  # no call id header
        outcome("dup"),
        outcome("dup"),
        outcome("lost", "c-missing"),
    ]
    requests, other, _ = audit_trail.join(outcomes, rows, {"request_log_entries": []})
    joined = [
        (r["case"], r["joined_by"], r["spend_row"] and r["spend_row"]["call_id"]) for r in requests
    ]
    assert joined == [
        ("a", "call id", "c1"),
        ("refused", "caller metadata", None),
        ("dup", "caller metadata", "c9"),
        ("dup", "caller metadata", "c8"),
        ("lost", None, None),
    ]
    assert other == []


def test_join_finds_the_agent_row_by_key_and_window_and_flags_the_trace():
    rows = [summary("c1", "a"), summary("c2", alias="agw-agent", session="t-agent")]
    agent = {
        "started_at": audit_trail.parse_time("2026-10-21T10:00:00Z"),
        "ended_at": audit_trail.parse_time("2026-10-21T10:00:10Z"),
    }
    agent_logs = {
        "request_log_entries": [{"path": "/run", "trace": "t-run", "time": None}],
        "container_log_lines": 3,
    }
    requests, other, view = audit_trail.join([outcome("a", "c1")], rows, LOGS, agent, agent_logs)
    assert [r["call_id"] for r in other] == ["c2"]
    assert [r["call_id"] for r in view["spend_rows_during_the_run"]] == ["c2"]
    assert view["spend_rows_during_the_run"][0]["session_is_a_request_log_trace"] is True
    assert requests[0]["spend_row"]["session_is_a_request_log_trace"] is False
    assert len(view["agent_request_logs"]) == 1 and "request_log_entries" not in view["agent_logs"]


def test_stored_header_names_finds_litellms_nested_headers():
    psr = {
        "metadata": {
            "headers": {"x-serverless-authorization": "Bearer x", "user-agent": "u"},
            "requester_metadata": {"headers": {"x-litellm-session-id": "s"}},
        }
    }
    assert audit_trail.stored_header_names(psr) == [
        "user-agent",
        "x-litellm-session-id",
        "x-serverless-authorization",
    ]
    assert (
        audit_trail.stored_header_names({}) == [] and audit_trail.stored_header_names(None) is None
    )
