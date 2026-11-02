"""Audit-trail helpers shared by the per-gateway test 6 collectors.

The collectors (harness/scenarios/<gw>/audit_trail.py) read a run's outcomes, fetch
what the gateway and Cloud Run logged for the same window, join the two, and write a
redacted trail into the run directory (ADR 0012). The gateway-specific parts (the
gateway's own log API, its join keys) stay in each collector; this module holds what
every gateway needs: redaction, address kinds, time handling, and Cloud Run's logs.
Standard library only, so a collector can run with a plain python3.
"""

import ipaddress
import json
import re
import subprocess
from datetime import UTC, datetime

PROJECT = "my-gcp-project"

REDACTIONS = (
    (re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])"), "<sha256>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "sk-<key>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"), "<jwt>"),
    (re.compile(r"\bya29\.[A-Za-z0-9_.-]+"), "<token>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), "<api key>"),
    # Personal addresses (service-account addresses are evidence and stay).
    (
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@(?![A-Za-z0-9.-]*\.iam\.gserviceaccount\.com\b)"
            r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
        "<email>",
    ),
)


def redact(value):
    """Keys, key hashes, tokens, Google API keys and personal emails out of any value."""
    if isinstance(value, str):
        for pattern, replacement in REDACTIONS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value


# Private address space proper (RFC 1918 and IPv6 unique local), not ipaddress's broader
# is_private, which also counts documentation and other reserved ranges.
_PRIVATE_NETS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def ip_kind(ip: str | None) -> str | None:
    """What kind of address recorded the request, never the address (it may be personal)."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "unparseable (redacted)"
    addr = getattr(addr, "ipv4_mapped", None) or addr  # ::ffff:10.0.0.1 is 10.0.0.1
    if addr.is_link_local:
        return "link-local (Cloud Run front end)"
    if addr.is_loopback or any(addr in net for net in _PRIVATE_NETS if net.version == addr.version):
        return "private"
    return "public (redacted)"


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_time(text: str | None) -> float | None:
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).timestamp()


def as_dict(value):
    """A dict from a dict or a JSON object string; {} for anything else."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return {}


def logging_read(service: str, t0: float, t1: float) -> list[dict]:
    """A Cloud Run service's request and container log entries for a time window."""
    flt = (
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}" '
        f'AND timestamp>="{iso(t0)}" AND timestamp<="{iso(t1)}"'
    )
    out = subprocess.run(
        ["gcloud", "logging", "read", flt, "--project", PROJECT, "--format=json", "--limit=1000"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    entries = json.loads(out or "[]")
    if len(entries) == 1000:
        print(f"WARNING: {service}: 1000 log entries, the limit; older ones are missing")
    return entries


def summarise_logs(entries: list[dict], needles: dict[str, str]) -> dict:
    """Cloud Run log entries reduced to request records and counts: which entries name a
    caller identity, and how many contain each needle (e.g. the prompt marker)."""
    requests, lines = [], 0
    hits = dict.fromkeys(needles, 0)
    identity = 0
    for e in entries:
        raw = json.dumps(e)
        for name, needle in needles.items():
            hits[name] += needle.lower() in raw.lower()
        if "authenticationInfo" in raw or "principalEmail" in raw:
            identity += 1
        hr = e.get("httpRequest")
        if hr:
            requests.append(
                {
                    "time": e.get("timestamp"),
                    "method": hr.get("requestMethod"),
                    "path": re.sub(r"^https?://[^/]+", "", hr.get("requestUrl", "")),
                    "status": hr.get("status"),
                    "latency": hr.get("latency"),
                    "user_agent": hr.get("userAgent"),
                    "remote_ip": ip_kind(hr.get("remoteIp")),
                    "trace": (e.get("trace") or "").rsplit("/", 1)[-1] or None,
                }
            )
        else:
            lines += 1
    return {
        "request_log_entries": requests,
        "container_log_lines": lines,
        "entries_naming_a_caller_identity": identity,
        "entries_containing": hits,
    }
