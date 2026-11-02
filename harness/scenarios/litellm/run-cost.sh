#!/usr/bin/env bash
# Test 3 (cost control): run one cost-<name>.json scenario file with a throwaway LiteLLM
# key made for this run and deleted when it ends, even on failure. The key is only ever
# in this shell's variables and the harness's environment; the master key and ID token go
# to curl through a private headers file that is removed on exit.
#
# Usage, from anywhere:  harness/scenarios/litellm/run-cost.sh <name> ["note for meta.json"]
#   <name>: rpm | tpm | budget | race | unpriced | throttle
# The gateway's live revision is added to the note automatically.
set -euo pipefail

PROJECT=my-gcp-project
REGION=europe-west1
name=${1:-}
note=${2:-}

# The key's limits; every key also gets both real models and a $0.05 backstop budget.
case "${name}" in
  rpm) spec='{"rpm_limit": 3}' ;;
  tpm) spec='{"tpm_limit": 1000}' ;;
  budget) spec='{"max_budget": 0.0002}' ;;
  race) spec='{"max_budget": 0.0005}' ;;
  unpriced) spec='{"max_budget": 0.00001, "models": ["gemini-3.8-flash", "claude-haiku-5-5", "test-claude-unpriced"]}' ;;
  throttle) spec='{"rpm_limit": 4, "max_budget": 0.00001, "throttle_on_budget_exceeded": true}' ;;
  *)
    echo "usage: $0 <rpm|tpm|budget|race|unpriced|throttle> [note]" >&2
    exit 2
    ;;
esac

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
scenario="scenarios/litellm/cost-${name}.json"
[ -f "${harness_dir}/${scenario}" ] || { echo "no ${scenario} in ${harness_dir}" >&2; exit 2; }

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
# gcloud rather than Terraform state, so a fresh clone works without terraform init.
url=$(gcloud run services describe agw-litellm --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-litellm --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
master_key=$(gcloud secrets versions access latest --secret agw-litellm-master-key --project "${PROJECT}")

# Unique per run, so two runs of the same name never delete each other's key.
alias_name="agw-t3-run-${name}-$(date -u +%Y%m%dT%H%M%S)-$$"

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
cleanup() {
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' "${url}/key/delete" -H @"${admin_headers}" \
    -H "Content-Type: application/json" -d "{\"key_aliases\": [\"${alias_name}\"]}" || true)
  case "${code}" in
    200) echo "deleted ${alias_name}" ;;
    404) ;; # never minted (LiteLLM answers 404 "No keys found")
    "" | 000) echo "WARNING: could not reach the gateway to delete ${alias_name}; delete it in the admin UI" >&2 ;;
    *) echo "WARNING: could not delete ${alias_name} (HTTP ${code}); delete it in the admin UI (budget capped at \$0.05)" >&2 ;;
  esac
  rm -rf "${tmp}"
}
trap cleanup EXIT

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "${id_token}" "${master_key}" \
    >"${admin_headers}"
)
unset master_key

# The window-only runs need their model on the gateway: refuse clearly rather than mint a
# key for a model that isn't there.
if [ "${name}" = unpriced ] &&
  ! curl -fsS "${url}/v1/models" -H @"${admin_headers}" | grep '"test-claude-unpriced"' >/dev/null; then
  echo "test-claude-unpriced isn't on the gateway: open the test 3 window first (README.md)" >&2
  exit 2
fi

body=$(python3 -c '
import json, sys
spec = json.loads(sys.argv[2])
print(json.dumps({"key_alias": sys.argv[1], "models": ["gemini-3.8-flash", "claude-haiku-5-5"],
                  "max_budget": 0.05, **spec}))' "${alias_name}" "${spec}")
key=$(curl -fsS "${url}/key/generate" -H @"${admin_headers}" -H "Content-Type: application/json" -d "${body}" |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])')
echo "created ${alias_name} on ${revision}: ${spec}"

cd "${harness_dir}"
# Local runs only, so the ID token is always your gcloud identity: "auto" would pick the
# metadata server on a GCE VM and mint tokens as the VM's service account (403).
AGW_ID_TOKEN_SOURCE=gcloud AGW_GATEWAY_URL="${url}" AGW_GATEWAY_API_KEY="${key}" PYTHONPATH=src \
  uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway key ${alias_name} ${spec}${note:+; ${note}}"
