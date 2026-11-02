#!/usr/bin/env bash
# Test 6 (audit fidelity): run audit.json, send one request through the agent (unchanged:
# it tags nothing), make and delete one throwaway consumer through /admin-api (an admin
# change for the trail to show), then collect the trail every request left into
# trail.json / trail.md in the run directory (audit_trail.py). Everything Kong records is
# its file-log line per request in Cloud Logging, so the collector reads only gcloud logs.
#
# Unlike tests 3 and 5, this uses the real harness key, not a throwaway one: the test is
# whether the trail the real callers (harness and agent) leave can be joined (AGENTS.md).
# key-auth's hide_credentials removes the caller's key before the log; Kong's serializer
# redacts Authorization (on model rows, Kong's own Google token) and kong.yaml redacts
# X-Serverless-Authorization, so no key or token value should reach a row; the collector
# scans every row for one.
# The admin key and ID token reach curl through a private headers file removed on exit.
#
# Usage, from anywhere:  harness/scenarios/kong/run-audit.sh ["note for meta.json"]
# Never sync a config window during a run.
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
TAG=agw-throwaway
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/kong/audit.json"

# Everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
url=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
agent_url=$(gcloud run services describe agw-agent --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
id_token=$(gcloud auth print-identity-token)
admin_key=$(gcloud secrets versions access latest --secret agw-kong-admin-key --project "${PROJECT}")
harness_key=$(gcloud secrets versions access latest --secret agw-kong-harness-key --project "${PROJECT}")
[ -n "${url}" ] && [ -n "${agent_url}" ] && [ -n "${admin_key}" ] && [ -n "${harness_key}" ] && [ -n "${id_token}" ] ||
  { echo "agw-kong, agw-agent, a key or an ID token not found" >&2; exit 1; }

# The agent must really point at this gateway, or its call would leave no gateway trail and
# read as a finding. Checked before anything is sent.
agent_spec=$(gcloud run services describe agw-agent --project "${PROJECT}" --region "${REGION}" --format=json)
if ! printf %s "${agent_spec}" | python3 -I -c '
import json, sys
env = {e["name"]: e.get("value") for c in json.load(sys.stdin)["spec"]["template"]["spec"]["containers"]
       for e in c.get("env", [])}
sys.exit(env.get("AGW_TARGET") != "gateway" or not (env.get("AGW_GATEWAY_URL") or "").startswith(sys.argv[1])
         or env.get("AGW_GATEWAY_CLAUDE_API") != "anthropic")
' "${url}"; then
  echo "agw-agent doesn't point at ${url} (AGW_TARGET=gateway, AGW_GATEWAY_CLAUDE_API=anthropic): fix agent/terraform first" >&2
  exit 2
fi
unset agent_spec

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
agent_headers="${tmp}/agent.headers"
probe=""
cleanup() {
  local code
  if [ -n "${probe}" ]; then # only if the probe's delete didn't run
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE "${url}/admin-api/consumers/${probe}" \
      -H @"${admin_headers}" || true)
    case "${code}" in
      204 | 404) ;;
      *) echo "WARNING: could not delete ${probe} (HTTP ${code}); delete it through /admin-api or Kong Manager" >&2 ;;
    esac
  fi
  rm -rf "${tmp}"
}
trap cleanup EXIT
(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\nContent-Type: application/json\n' \
    "${id_token}" "${admin_key}" >"${admin_headers}"
  printf 'Authorization: Bearer %s\n' "${id_token}" >"${agent_headers}"
)
unset admin_key

cd "${harness_dir}"
# Local runs only: "auto" would mint ID tokens as a GCE VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_CLAUDE_API=anthropic AGW_GATEWAY_API_KEY="${harness_key}" \
  AGW_RESULTS_DIR="${repo_dir}/results/raw/kong" PYTHONPATH=src \
  uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}${note:+; ${note}}" 2>&1 | tee /dev/stderr)
unset harness_key
run_dir=$(printf '%s\n' "${out}" | sed -n 's/.*results: //p' | tail -1)
case "${run_dir}" in /*) ;; ?*) run_dir="${harness_dir}/${run_dir}" ;; esac
[ -n "${run_dir}" ] && [ -d "${run_dir}" ] || { echo "could not find the run directory in the harness output" >&2; exit 1; }

# One request through the agent, as it is: ADK's /run, a session of our own naming. The
# agent calls Kong with its own key and tags nothing.
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
answer = None  # flags only: no response text goes into the committed run
if status == "200":
    try:
        events = json.loads(open(out).read() or "[]")
        texts = [p.get("text", "") for e in events for p in (e.get("content") or {}).get("parts", [])]
        answer = " ".join(t for t in texts if t)
    except (OSError, ValueError):
        answer = None
record = {"status": int(status or 0), "started_at": float(started), "ended_at": float(ended),
          "session_id": session, "app": "claude", "answered": bool(answer), "answer_chars": len(answer or "")}
with open(path, "w") as f:
    f.write(json.dumps(record, indent=1) + "\n")
print(f"agent: HTTP {status}, session {session}")
EOF

# An admin change for the trail: a throwaway consumer (no key, no group) made and deleted
# through /admin-api, as an operator would. Kong OSS has no admin audit log; the question
# is what its request log shows instead.
probe="agw-t6-admin-probe-$(date -u +%Y%m%dT%H%M%S)-$$"
p_started=$(date +%s.%N)
printf '{"username": "%s", "tags": ["%s"]}' "${probe}" "${TAG}" |
  curl -fsS --max-time 30 -o /dev/null -X POST "${url}/admin-api/consumers" -H @"${admin_headers}" -d @-
curl -fsS --max-time 30 -o /dev/null -X DELETE "${url}/admin-api/consumers/${probe}" -H @"${admin_headers}"
p_ended=$(date +%s.%N)
python3 -I -c 'import json, sys, pathlib; pathlib.Path(sys.argv[4]).write_text(json.dumps({"consumer": sys.argv[1], "started_at": float(sys.argv[2]),
  "ended_at": float(sys.argv[3]), "steps": ["POST /admin-api/consumers", "DELETE /admin-api/consumers/<name>"]},
  indent=1) + "\n")' \
  "${probe}" "${p_started}" "${p_ended}" "${run_dir}/admin-probe.json"
echo "admin probe: made and deleted ${probe}"
probe=""

echo "waiting for Cloud Logging to catch up ..."
sleep 30
python3 -I "${harness_dir}/scenarios/kong/audit_trail.py" "${run_dir}"
