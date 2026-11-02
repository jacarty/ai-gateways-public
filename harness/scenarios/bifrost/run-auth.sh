#!/usr/bin/env bash
# Test 5 (identity and secrets): run auth.json with the keys it needs. Makes throwaway
# Bifrost virtual keys through the admin API in five states (Claude-only, expiring,
# inactive, deleted, rotated), reads the agent's key, and passes them to the harness as
# AGW_T5_* environment variables only; the keys it made are deleted on exit, even on
# failure. As in run-cost.sh, the admin password and ID token reach curl through a private
# headers file removed on exit.
#
# Usage, from anywhere:  harness/scenarios/bifrost/run-auth.sh ["note for meta.json"]
# Never deploy Bifrost while this runs: a restart removes keys made through the admin API.
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/bifrost/auth.json"

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
url=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
admin_password=$(gcloud secrets versions access latest --secret agw-bifrost-admin-password --project "${PROJECT}")
agent_key=$(gcloud secrets versions access latest --secret agw-bifrost-agent-key --project "${PROJECT}")
harness_key=$(gcloud secrets versions access latest --secret agw-bifrost-harness-key --project "${PROJECT}")

suffix="$(date -u +%Y%m%dT%H%M%S)-$$"
tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
key_ids=()
cleanup() {
  local id code
  for id in "${key_ids[@]}"; do
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE "${url}/api/governance/virtual-keys/${id}" \
      -H @"${admin_headers}" || true)
    case "${code}" in
      200 | 204 | 404) ;; # 404: already gone (the deleted-key case deletes its own)
      *) echo "WARNING: could not delete key ${id} (HTTP ${code}); delete it in the admin UI" >&2 ;;
    esac
  done
  rm -rf "${tmp}"
}
trap cleanup EXIT

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Basic %s\nContent-Type: application/json\n' \
    "${id_token}" "$(printf 'admin:%s' "${admin_password}" | base64 -w0)" >"${admin_headers}"
)
unset admin_password

# make_key <name> <allowed models JSON> <extra JSON>: prints "<id> <value>". The value never
# reaches the command line of anything but the harness's environment.
make_key() {
  local body created
  body=$(python3 -I -c '
import json, sys
print(json.dumps({"name": sys.argv[1], "description": "test 5 throwaway key (run-auth.sh), deleted on exit",
                  "provider_configs": [{"provider": "vertex", "allowed_models": json.loads(sys.argv[2]),
                                        "key_ids": ["*"], "weight": 1}],
                  "budgets": [{"max_limit": 0.05, "reset_duration": "1d"}], **json.loads(sys.argv[3])}))' \
    "agw-t5-$1-${suffix}" "$2" "$3")
  created=$(curl -fsS -X POST "${url}/api/governance/virtual-keys" -H @"${admin_headers}" -d "${body}")
  printf %s "${created}" | python3 -I -c '
import json, sys
vk = json.load(sys.stdin)["virtual_key"]
v = vk["value"]["value"] if isinstance(vk["value"], dict) else vk["value"]
print(vk["id"], v)'
}
value_of() { printf %s "${1#* }"; }
id_of() { printf %s "${1%% *}"; }

both='["gemini-3.8-flash", "claude-haiku-5-5"]'
claude_only=$(make_key claude-only '["claude-haiku-5-5"]' '{}')
key_ids+=("$(id_of "${claude_only}")")
expires=$(date -u -d '+5 seconds' +%Y-%m-%dT%H:%M:%SZ)
expiring=$(make_key expired "${both}" "{\"expires_at\": \"${expires}\"}")
key_ids+=("$(id_of "${expiring}")")
inactive=$(make_key inactive "${both}" '{"is_active": false}')
key_ids+=("$(id_of "${inactive}")")
deleted=$(make_key deleted "${both}" '{}')
key_ids+=("$(id_of "${deleted}")")
curl -fsS --max-time 30 -o /dev/null -X DELETE "${url}/api/governance/virtual-keys/$(id_of "${deleted}")" -H @"${admin_headers}"
rotated=$(make_key rotated "${both}" '{}')
key_ids+=("$(id_of "${rotated}")")
rotated_new=$(curl -fsS -X POST "${url}/api/governance/virtual-keys/$(id_of "${rotated}")/rotate" -H @"${admin_headers}" \
  | python3 -I -c '
import json, sys
vk = json.load(sys.stdin)["virtual_key"]
print(vk["value"]["value"] if isinstance(vk["value"], dict) else vk["value"])')
for v in "$(value_of "${claude_only}")" "$(value_of "${expiring}")" "$(value_of "${inactive}")" \
  "$(value_of "${deleted}")" "$(value_of "${rotated}")" "${rotated_new}"; do
  case "${v}" in sk-bf-*) ;; *) echo "a created key has no sk-bf- value; stopping" >&2; exit 1 ;; esac
done
[ "$(value_of "${rotated}")" != "${rotated_new}" ] || { echo "rotation returned the same value; stopping" >&2; exit 1; }
echo "made 5 keys on ${revision} (claude-only, expiring at ${expires}, inactive, deleted, rotated)"
sleep 6 # past the expiring key's expiry

cd "${harness_dir}"
# Local runs only: the ID token is always your gcloud identity. The run's own key is the
# harness's; each case swaps in the credential it tests.
PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_API_KEY="${harness_key}" AGW_RESULTS_DIR="${repo_dir}/results/raw/bifrost" PYTHONPATH=src \
  AGW_T5_CLAUDE_ONLY_KEY="$(value_of "${claude_only}")" AGW_T5_EXPIRED_KEY="$(value_of "${expiring}")" \
  AGW_T5_INACTIVE_KEY="$(value_of "${inactive}")" AGW_T5_DELETED_KEY="$(value_of "${deleted}")" \
  AGW_T5_ROTATED_OLD_KEY="$(value_of "${rotated}")" AGW_T5_ROTATED_NEW_KEY="${rotated_new}" \
  AGW_T5_AGENT_KEY="${agent_key}" AGW_T5_UNKNOWN_KEY="sk-bf-agw-unknown-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')" \
  uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway keys agw-t5-*-${suffix}${note:+; ${note}}"
