#!/usr/bin/env bash
# Test 6 (audit fidelity): run audit.json, send one request through the agent (unchanged:
# it tags nothing), then collect the trail every request left into trail.json / trail.md
# in the run directory (audit_trail.py). The harness key is the run's key; the admin login
# (to read Bifrost's logs store) and the ID token reach curl and the collector through a
# private headers file removed on exit.
#
# Unlike tests 3 and 5, this uses the real harness key, not a throwaway one: the test is
# whether the trail the real callers (harness and agent) leave can be joined. If a
# logging_headers window was open (README.md, run B), rows now hold that key's value:
# rotate the harness and agent keys afterwards, or rely on the phase-end destroy.
#
# Usage, from anywhere:  harness/scenarios/bifrost/run-audit.sh ["note for meta.json"]
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/bifrost/audit.json"

# Everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
url=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
agent_url=$(gcloud run services describe agw-agent --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
id_token=$(gcloud auth print-identity-token)
admin_password=$(gcloud secrets versions access latest --secret agw-bifrost-admin-password --project "${PROJECT}")
harness_key=$(gcloud secrets versions access latest --secret agw-bifrost-harness-key --project "${PROJECT}")

# The agent must really point at this gateway, or its call would leave no gateway trail and
# read as a finding. Checked before anything is sent.
agent_spec=$(gcloud run services describe agw-agent --project "${PROJECT}" --region "${REGION}" --format=json)
if ! printf %s "${agent_spec}" | python3 -I -c '
import json, sys
env = {e["name"]: e.get("value") for c in json.load(sys.stdin)["spec"]["template"]["spec"]["containers"]
       for e in c.get("env", [])}
sys.exit(env.get("AGW_TARGET") != "gateway" or not (env.get("AGW_GATEWAY_URL") or "").startswith(sys.argv[1]))
' "${url}"; then
  echo "agw-agent doesn't point at ${url} (AGW_TARGET=gateway): fix agent/terraform first" >&2
  exit 2
fi
unset agent_spec

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT
admin_headers="${tmp}/admin.headers"
agent_headers="${tmp}/agent.headers"
(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Basic %s\n' \
    "${id_token}" "$(printf 'admin:%s' "${admin_password}" | base64 -w0)" >"${admin_headers}"
  printf 'Authorization: Bearer %s\n' "${id_token}" >"${agent_headers}"
)
unset admin_password

cd "${harness_dir}"
# Local runs only: "auto" would mint ID tokens as a GCE VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_API_KEY="${harness_key}" AGW_RESULTS_DIR="${repo_dir}/results/raw/bifrost" PYTHONPATH=src \
  uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}${note:+; ${note}}" 2>&1 | tee /dev/stderr)
unset harness_key
run_dir=$(printf '%s\n' "${out}" | sed -n 's/.*results: //p' | tail -1)
[ -n "${run_dir}" ] && [ -d "${run_dir}" ] || { echo "could not find the run directory in the harness output" >&2; exit 1; }

# One request through the agent, as it is: ADK's /run, a session of our own naming. The
# agent calls the gateway with its own key and tags nothing.
session="agw-t6-agent-$(date -u +%Y%m%dT%H%M%S)"
body=$(python3 -I -c 'import json, sys; print(json.dumps({"app_name": "claude", "user_id": "agw-t6",
  "session_id": sys.argv[1], "new_message": {"role": "user", "parts": [{"text":
  "AGW-T6-MARKER (agent): What is the capital of Belgium?"}]}}))' "${session}")
: >"${tmp}/agent.out" # exists even if curl can't connect
started=$(date +%s.%N)
status=$(curl -sS -o "${tmp}/agent.out" -w '%{http_code}' --max-time 180 "${agent_url}/run" \
  -H @"${agent_headers}" -H "Content-Type: application/json" -d "${body}" || true)
ended=$(date +%s.%N)
python3 -I - "${run_dir}/agent-run.json" "${status}" "${started}" "${ended}" "${session}" "${tmp}/agent.out" <<'EOF'
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

echo "waiting for the logs store and Cloud Logging to catch up ..."
sleep 30
AGW_GATEWAY_URL="${url}" AGW_ADMIN_HEADERS="${admin_headers}" \
  python3 -I "${harness_dir}/scenarios/bifrost/audit_trail.py" "${run_dir}"
