#!/usr/bin/env bash
# Test 5 (identity and secrets): run auth.json with the keys it needs. Makes throwaway Kong
# consumers through the Admin API (/admin-api), one per key state: valid (the run's own
# key), Claude-only, expired, in no group, deleted and rotated. Everything it makes is
# tagged agw-throwaway, not agw, so decK neither manages nor reports it (ADR 0015); every
# key has a Kong ttl, so a key this script fails to delete still expires (its consumer, and
# the Claude-only consumer's plugin on the gemini service, stay until deleted). The expired,
# deleted and rotated keys are used once on /admin-api while they are valid (403 there:
# authenticated, not an admin; no model call), so Kong has them cached and the run tests
# that a lapsed key leaves the cache too. Key values are only ever in this shell's
# variables and the harness's environment; the admin key and ID token go to curl through a
# private headers file removed on exit, and a test key reaches curl on stdin. Kong's
# log rows for the run's requests are saved next to the results as kong-log.json.
#
# Usage, from anywhere:  harness/scenarios/kong/run-auth.sh ["note for meta.json"]
# Never sync a config window during a run.
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
TAG=agw-throwaway
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/kong/auth.json"

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
# gcloud rather than Terraform state, so a fresh clone works without terraform init.
url=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
admin_key=$(gcloud secrets versions access latest --secret agw-kong-admin-key --project "${PROJECT}")
agent_key=$(gcloud secrets versions access latest --secret agw-kong-agent-key --project "${PROJECT}")
[ -n "${url}" ] && [ -n "${admin_key}" ] && [ -n "${agent_key}" ] && [ -n "${id_token}" ] ||
  { echo "agw-kong, its admin or agent key, or an ID token not found" >&2; exit 1; }
admin="${url}/admin-api"

# Unique per run, so two runs never delete each other's consumers; clean-up deletes by
# these names, so it works even if a create response can't be parsed.
prefix="agw-t5-$(date -u +%Y%m%dT%H%M%S)-$$"

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
consumers=()
cleanup() {
  local c code
  for c in "${consumers[@]}"; do
    # Deleting a consumer deletes its keys, ACL groups and plugins with it.
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE "${admin}/consumers/${c}" \
      -H @"${admin_headers}" || true)
    case "${code}" in
      204) echo "deleted ${c}" ;;
      404) echo "no ${c} to delete" ;;
      *) echo "WARNING: could not delete ${c} (HTTP ${code}); delete it through /admin-api or Kong Manager (its keys expire in an hour; the consumer and any plugin scoped to it stay)" >&2 ;;
    esac
  done
  rm -rf "${tmp}"
}
trap cleanup EXIT

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\nContent-Type: application/json\n' \
    "${id_token}" "${admin_key}" >"${admin_headers}"
)
unset admin_key

# POST a JSON body (on stdin, never in argv) to the Admin API; prints the response.
admin_post() {
  curl -fsS --max-time 30 -X POST "${admin}$1" -H @"${admin_headers}" -d @-
}

# new_key: a fresh random key value.
new_key() { python3 -I -c 'import secrets; print(secrets.token_urlsafe(32))'; }

# make_consumer <state> <group or ""> : creates ${prefix}-<state>, in the group if given;
# prints the consumer's id.
make_consumer() {
  local c="${prefix}-$1"
  consumers+=("${c}")
  printf '{"username": "%s", "tags": ["%s"]}' "${c}" "${TAG}" | admin_post /consumers |
    python3 -I -c 'import json, sys; print(json.load(sys.stdin)["id"])'
  if [ -n "$2" ]; then
    printf '{"group": "%s", "tags": ["%s"]}' "$2" "${TAG}" | admin_post "/consumers/${c}/acls" >/dev/null
  fi
}

# add_key <state> <value> <ttl s>: stores the literal "Bearer <value>", as the committed
# consumers' keys are (ADR 0014); prints the credential's id. The response echoes the key,
# so only the id is kept.
add_key() {
  printf '{"key": "Bearer %s", "ttl": %s, "tags": ["%s"]}' "$2" "$3" "${TAG}" |
    admin_post "/consumers/${prefix}-$1/key-auth" | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["id"])'
}

# use_once <value>: one authenticated request on /admin-api with this key (and the ID
# token), so Kong caches the credential; expects 403 (a caller, not an admin).
use_once() {
  local code
  # Headers on stdin (curl -H @-), so the key is never in a file or argv.
  code=$(printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "${id_token}" "$1" |
    curl -sS --max-time 30 -o /dev/null -w '%{http_code}' "${admin}/" -H @- || true)
  [ "${code}" = 403 ] || { echo "a test key got HTTP ${code} on /admin-api, not 403; stopping" >&2; exit 1; }
}

valid=$(new_key)
make_consumer valid callers >/dev/null
add_key valid "${valid}" 3600 >/dev/null

# Claude-only: Kong OSS has no per-key model list. A consumer is limited to some models by
# ACL groups per service (config) or, as here, a plugin scoped to the consumer and the
# gemini service that refuses before any model call.
claude_only=$(new_key)
# Through a file, not $(...): a subshell would lose make_consumer's entry in consumers,
# and clean-up would miss this consumer. An id is not a secret.
make_consumer claude-only callers >"${tmp}/claude-only.id"
claude_only_id=$(cat "${tmp}/claude-only.id")
add_key claude-only "${claude_only}" 3600 >/dev/null
printf '{"name": "request-termination", "consumer": {"id": "%s"}, "config": {"status_code": 403, "message": "agw test 5: this consumer is not allowed to use Gemini"}, "tags": ["%s"]}' \
  "${claude_only_id}" "${TAG}" | admin_post "/services/gemini/plugins" >/dev/null

# A valid key whose consumer is in no group the chat services allow.
no_group=$(new_key)
make_consumer no-group "" >/dev/null
add_key no-group "${no_group}" 3600 >/dev/null

expiring=$(new_key)
make_consumer expired callers >/dev/null
expires_at=$(($(date +%s) + 15))
add_key expired "${expiring}" 15 >/dev/null
use_once "${expiring}"

deleted=$(new_key)
make_consumer deleted callers >/dev/null
deleted_cred=$(add_key deleted "${deleted}" 3600)
use_once "${deleted}"
curl -fsS --max-time 30 -o /dev/null -X DELETE "${admin}/consumers/${prefix}-deleted/key-auth/${deleted_cred}" \
  -H @"${admin_headers}"

# Rotation in Kong OSS: add a second key to the consumer, then delete the first.
rotated_old=$(new_key)
make_consumer rotated callers >/dev/null
rotated_old_cred=$(add_key rotated "${rotated_old}" 3600)
use_once "${rotated_old}"
rotated_new=$(new_key)
add_key rotated "${rotated_new}" 3600 >/dev/null
curl -fsS --max-time 30 -o /dev/null -X DELETE "${admin}/consumers/${prefix}-rotated/key-auth/${rotated_old_cred}" \
  -H @"${admin_headers}"

echo "made ${#consumers[@]} consumers ${prefix}-* on ${revision}"
# Kong rebuilds its plugin list on its next poll (about 5 s), and the expiring key's 15 s
# ttl must have run out: wait for whichever is later.
wait_s=$((expires_at + 2 - $(date +%s)))
[ "${wait_s}" -ge 6 ] || wait_s=6
sleep "${wait_s}"

cd "${harness_dir}"
# Local runs only, so the ID token is always your gcloud identity: "auto" would pick the
# metadata server on a GCE VM and mint tokens as the VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_CLAUDE_API=anthropic AGW_GATEWAY_API_KEY="${valid}" AGW_RESULTS_DIR="${repo_dir}/results/raw/kong" \
  AGW_T5_CLAUDE_ONLY_KEY="${claude_only}" AGW_T5_EXPIRED_KEY="${expiring}" AGW_T5_NO_GROUP_KEY="${no_group}" \
  AGW_T5_DELETED_KEY="${deleted}" AGW_T5_ROTATED_OLD_KEY="${rotated_old}" AGW_T5_ROTATED_NEW_KEY="${rotated_new}" \
  AGW_T5_AGENT_KEY="${agent_key}" AGW_T5_UNKNOWN_KEY="agw-unknown-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')" \
  PYTHONPATH=src uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway consumers ${prefix}-*${note:+; ${note}}" \
  2>&1 | tee /dev/stderr)
unset valid claude_only expiring no_group deleted rotated_old rotated_new agent_key

# Kong's log rows for the run's requests (by x-kong-request-id), projected to the fields
# below: no request headers. Rows reach Cloud Logging a few seconds late, so retry.
run_dir=$(printf '%s\n' "${out}" | sed -n 's/.*results: //p' | tail -1)
case "${run_dir}" in /*) ;; ?*) run_dir="${harness_dir}/${run_dir}" ;; esac
if [ -n "${run_dir}" ] && [ -f "${run_dir}/outcomes.jsonl" ]; then
  python3 -I - "${run_dir}" "${PROJECT}" "${tmp}/kong-log.json" <<'EOF' && mv "${tmp}/kong-log.json" "${run_dir}/kong-log.json" && echo "saved ${run_dir}/kong-log.json"
import json, subprocess, sys, time
run_dir, project, out = sys.argv[1:]
outcomes = [json.loads(line) for line in open(f"{run_dir}/outcomes.jsonl")]
ids = {o["headers"].get("x-kong-request-id") for o in outcomes} - {None}
start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(min(o["started_at"] for o in outcomes) - 10))
flt = ('resource.type="cloud_run_revision" AND resource.labels.service_name="agw-kong" '
       f'AND timestamp>="{start}" AND jsonPayload.request.id:*')
fields = ("timestamp,jsonPayload.request.id,jsonPayload.request.method,jsonPayload.route.name,"
          "jsonPayload.service.name,jsonPayload.consumer.username,jsonPayload.response.status,"
          "jsonPayload.upstream_status,jsonPayload.latencies,jsonPayload.tries,jsonPayload.ai")
for attempt in range(7):
    rows = json.loads(subprocess.run(
        ["gcloud", "logging", "read", flt, "--project", project, f"--format=json({fields})"],
        capture_output=True, text=True, check=True, timeout=60).stdout or "[]")
    rows = [r for r in rows if r["jsonPayload"]["request"]["id"] in ids]
    if len(rows) >= len(ids) or attempt == 6:
        break
    time.sleep(10)
rows.sort(key=lambda r: r["timestamp"])
print(f"{len(rows)} of {len(ids)} requests in Kong's log", file=sys.stderr)
with open(out, "w") as f:
    json.dump(rows, f, indent=1)
    f.write("\n")
EOF
fi
