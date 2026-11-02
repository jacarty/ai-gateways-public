#!/usr/bin/env bash
# Test 6 (audit fidelity): run audit.json, send one request through the agent (unchanged:
# it tags nothing), then collect the trail every request left into trail.json / trail.md
# in the run directory (audit_trail.py). The harness key is the run's key; the master key
# (to read LiteLLM's spend logs) and the ID token reach curl and the collector through a
# private headers file removed on exit.
#
# Usage, from anywhere:  harness/scenarios/litellm/run-audit.sh ["note for meta.json"]
# The gateway's live revision is added to the note automatically.
set -euo pipefail

PROJECT=my-gcp-project
REGION=europe-west1
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
scenario="scenarios/litellm/audit.json"

# Everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
describe() { gcloud run services describe "$1" --project "${PROJECT}" --region "${REGION}" --format="value($2)"; }
url=$(describe agw-litellm status.url)
agent_url=$(describe agw-agent status.url)
revision=$(describe agw-litellm status.latestReadyRevisionName)
id_token=$(gcloud auth print-identity-token)
master_key=$(gcloud secrets versions access latest --secret agw-litellm-master-key --project "${PROJECT}")
harness_key=$(gcloud secrets versions access latest --secret agw-litellm-harness-key --project "${PROJECT}")

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT
admin_headers="${tmp}/admin.headers"
agent_headers="${tmp}/agent.headers"
(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "${id_token}" "${master_key}" \
    >"${admin_headers}"
  printf 'Authorization: Bearer %s\n' "${id_token}" >"${agent_headers}"
)
unset master_key

cd "${harness_dir}"
# Local runs only: "auto" would mint ID tokens as a GCE VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_GATEWAY_URL="${url}" AGW_GATEWAY_API_KEY="${harness_key}" \
  PYTHONPATH=src uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}${note:+; ${note}}" | tee /dev/stderr)
run_dir=$(printf '%s\n' "${out}" | sed -n 's/.*; results: \([^ ]*\).*/\1/p' | tail -1)
[ -n "${run_dir}" ] || { echo "could not find the run directory in the harness output" >&2; exit 1; }

# One request through the agent, as it is: ADK's /run, a session of our own naming. The
# agent calls the gateway with its own key and tags nothing. Check it really points at this
# gateway, or its call would leave no gateway trail and read as a finding.
agent_env=$(gcloud run services describe agw-agent --project "${PROJECT}" --region "${REGION}" \
  --format='value(spec.template.spec.containers[0].env)')
case "${agent_env}" in
  *"'value': 'gateway'"*"${url}"* | *"${url}"*"'value': 'gateway'"*) ;;
  *) echo "agw-agent doesn't point at ${url} (AGW_TARGET=gateway): fix agent/terraform first" >&2; exit 2 ;;
esac
session="agw-t6-agent-$(date -u +%Y%m%dT%H%M%S)"
body=$(python3 -c 'import json, sys; print(json.dumps({"app_name": "claude", "user_id": "agw-t6",
  "session_id": sys.argv[1], "new_message": {"role": "user", "parts": [{"text":
  "AGW-T6-MARKER (agent): What is the capital of Belgium?"}]}}))' "${session}")
: >"${tmp}/agent.out" # exists even if curl can't connect
started=$(date +%s.%N)
status=$(curl -sS -o "${tmp}/agent.out" -w '%{http_code}' --max-time 180 "${agent_url}/run" \
  -H @"${agent_headers}" -H "Content-Type: application/json" -d "${body}" || true)
ended=$(date +%s.%N)
python3 - "${run_dir}/agent-run.json" "${status}" "${started}" "${ended}" "${session}" "${tmp}/agent.out" <<'EOF'
import json, sys
path, status, started, ended, session, out = sys.argv[1:]
answer = ""  # kept only for a 200: an error body is not copied into the committed run
if status == "200":
    try:
        events = json.loads(open(out).read() or "[]")
        texts = [p.get("text", "") for e in events for p in (e.get("content") or {}).get("parts", [])]
        answer = " ".join(t for t in texts if t)
    except (OSError, ValueError):
        answer = "(unreadable response)"
json.dump({"status": int(status or 0), "started_at": float(started), "ended_at": float(ended),
           "session_id": session, "app": "claude", "answer": answer[:300]}, open(path, "w"), indent=1)
open(path, "a").write("\n")
print(f"agent: HTTP {status}, session {session}")
EOF

echo "waiting for spend logs and Cloud Logging to catch up ..."
sleep 30
AGW_GATEWAY_URL="${url}" AGW_ADMIN_HEADERS="${admin_headers}" \
  python3 "${harness_dir}/scenarios/litellm/audit_trail.py" "${run_dir}"
