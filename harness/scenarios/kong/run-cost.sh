#!/usr/bin/env bash
# Test 3 (cost control): run one cost-<name>.json scenario file with a throwaway Kong
# consumer made for this run through the Admin API (/admin-api) and deleted when it ends,
# even on failure. The consumer, its ACL group, its key and its rate-limiting plugin are
# tagged agw-throwaway, not agw, so decK neither manages nor reports them (ADR 0015); the
# key also has a Kong ttl, so a key this script fails to delete still expires. The key's
# value is only ever in this shell's variables and the harness's environment; the admin key
# and ID token go to curl through a private headers file that is removed on exit. After the
# run, Kong's log rows for its requests are saved next to the results as kong-log.json.
#
# Usage, from anywhere:  harness/scenarios/kong/run-cost.sh <name> ["note for meta.json"]
#   <name>: rpm | race | model-limit | caps
# Kong's rate-limiting windows are clock minutes, so the run starts just after a minute
# turns. Never sync a config window during a run.
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
TAG=agw-throwaway
name=${1:-}
note=${2:-}

# The consumer's limits: a rate-limiting plugin on the consumer (all its routes), on the
# consumer and the Gemini route only, or none. Kong's default policy, "local", counts in
# the instance's memory.
case "${name}" in
  rpm | race) scope=consumer limit='{"minute": 3, "policy": "local"}' ;;
  model-limit) scope=gemini-chat limit='{"minute": 1, "policy": "local"}' ;;
  caps) scope=none limit='' ;;
  *)
    echo "usage: $0 <rpm|race|model-limit|caps> [note]" >&2
    exit 2
    ;;
esac

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/kong/cost-${name}.json"
[ -f "${harness_dir}/${scenario}" ] || { echo "no ${scenario} in ${harness_dir}" >&2; exit 2; }

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
# gcloud rather than Terraform state, so a fresh clone works without terraform init.
url=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
admin_key=$(gcloud secrets versions access latest --secret agw-kong-admin-key --project "${PROJECT}")
[ -n "${url}" ] && [ -n "${admin_key}" ] && [ -n "${id_token}" ] ||
  { echo "agw-kong, its admin key or an ID token not found" >&2; exit 1; }
admin="${url}/admin-api"

# Unique per run, so two runs never delete each other's consumer; clean-up deletes by this
# name, so it works even if a create response can't be parsed.
consumer="agw-t3-${name}-$(date -u +%Y%m%dT%H%M%S)-$$"

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
created=""
cleanup() {
  local code
  if [ -n "${created}" ]; then
    # Deleting the consumer deletes its key, ACL group and plugins with it.
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE "${admin}/consumers/${consumer}" \
      -H @"${admin_headers}" || true)
    case "${code}" in
      204) echo "deleted ${consumer}" ;;
      404) echo "no ${consumer} to delete" ;;
      *) echo "WARNING: could not delete ${consumer} (HTTP ${code}); delete it through /admin-api or Kong Manager (its key expires in an hour)" >&2 ;;
    esac
  fi
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

created=1
consumer_id=$(printf '{"username": "%s", "tags": ["%s"]}' "${consumer}" "${TAG}" |
  admin_post /consumers | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["id"])')
printf '{"group": "callers", "tags": ["%s"]}' "${TAG}" | admin_post "/consumers/${consumer}/acls" >/dev/null
key=$(python3 -I -c 'import secrets; print(secrets.token_urlsafe(32))')
# Stored as the literal "Bearer <key>", as the committed consumers' keys are (ADR 0014).
# The response echoes the key, so it is discarded.
printf '{"key": "Bearer %s", "ttl": 3600, "tags": ["%s"]}' "${key}" "${TAG}" |
  admin_post "/consumers/${consumer}/key-auth" >/dev/null
case "${scope}" in
  consumer)
    printf '{"name": "rate-limiting", "config": %s, "tags": ["%s"]}' "${limit}" "${TAG}" |
      admin_post "/consumers/${consumer}/plugins" >/dev/null
    ;;
  gemini-chat)
    printf '{"name": "rate-limiting", "consumer": {"id": "%s"}, "config": %s, "tags": ["%s"]}' \
      "${consumer_id}" "${limit}" "${TAG}" | admin_post "/routes/gemini-chat/plugins" >/dev/null
    ;;
esac
echo "created ${consumer} on ${revision}: rate-limiting ${limit:-none} on ${scope}"

# Kong rebuilds its plugin list on its next poll (about 5 s), then the run waits for the
# next minute to start, so a run's requests share one rate-limiting window.
sleep 6
sleep $((61 - 10#$(date -u +%S)))

cd "${harness_dir}"
# Local runs only, so the ID token is always your gcloud identity: "auto" would pick the
# metadata server on a GCE VM and mint tokens as the VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_CLAUDE_API=anthropic AGW_GATEWAY_API_KEY="${key}" AGW_RESULTS_DIR="${repo_dir}/results/raw/kong" \
  PYTHONPATH=src uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway consumer ${consumer}, rate-limiting ${limit:-none} on ${scope}${note:+; ${note}}" \
  2>&1 | tee /dev/stderr)
unset key

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
