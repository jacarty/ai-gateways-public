import subprocess
import sys
from pathlib import Path

import pytest

from agw_harness import trail


@pytest.mark.parametrize(
    ("ip", "kind"),
    [
        ("169.254.169.126", "link-local (Cloud Run front end)"),
        ("fe80::1", "link-local (Cloud Run front end)"),
        ("10.1.2.3", "private"),
        ("172.20.0.1", "private"),
        ("192.168.0.9", "private"),
        ("fd12:3456::1", "private"),  # IPv6 unique local, labelled public before
        ("127.0.0.1", "private"),
        ("203.0.113.7", "public (redacted)"),
        ("2001:db8::1", "public (redacted)"),
        ("::ffff:10.0.0.1", "private"),  # IPv4-mapped
        ("not-an-ip", "unparseable (redacted)"),
        (None, None),
    ],
)
def test_ip_kind_never_keeps_the_address(ip, kind):
    assert trail.ip_kind(ip) == kind


def test_redact_keeps_bifrost_keys_out():
    assert trail.redact({"v": "Bearer sk-bf-AbCdEfGh1234567890xyz"}) == {"v": "Bearer sk-<key>"}


def test_summarise_logs_reduces_entries_to_records_and_counts():
    entries = [
        {
            "timestamp": "2026-10-24T10:00:00Z",
            "trace": "projects/p/traces/abc",
            "httpRequest": {
                "requestMethod": "POST",
                "requestUrl": "https://gw.example/v1/chat/completions",
                "status": 200,
                "remoteIp": "203.0.113.7",
            },
        },
        {"textPayload": "AGW-T6-MARKER in a container line"},
    ]
    s = trail.summarise_logs(entries, {"marker": "agw-t6-marker"})
    assert s["request_log_entries"][0]["path"] == "/v1/chat/completions"
    assert s["request_log_entries"][0]["trace"] == "abc"
    assert s["request_log_entries"][0]["remote_ip"] == "public (redacted)"
    assert s["container_log_lines"] == 1 and s["entries_containing"] == {"marker": 1}


def test_trail_imports_under_a_plain_isolated_python():
    # run-audit.sh runs the collectors with `python3 -I`, outside uv: the module (and the
    # package's __init__) must need nothing but the standard library.
    src = Path(__file__).parents[1] / "src"
    code = f"import sys; sys.path.insert(0, {str(src)!r}); import agw_harness.trail"
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
