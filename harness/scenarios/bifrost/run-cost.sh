#!/usr/bin/env bash
# Test 3 (cost control): run one cost-<name>.json scenario file with a throwaway Bifrost
# virtual key made for this run through the admin API and deleted when it ends, even on
# failure. The key's value is only ever in this shell's variables and the harness's
# environment; the admin password and ID token go to curl through a private headers file
# that is removed on exit. After the run, the key's own quota (budgets and usage, read with
# the key itself) is saved next to the results as quota.json.
#
# Usage, from anywhere:  harness/scenarios/bifrost/run-cost.sh <name> ["note for meta.json"]
#   <name>: rpm | tpm | budget | race | model-budget | reset | unpriced
# Never deploy Bifrost while this runs: a restart would drop the throwaway key (config.json
# is the source of truth for virtual keys).
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
name=${1:-}
note=${2:-}

# The key's limits. Every key gets both real models and a $0.05 daily backstop budget;
# budgets on one key need distinct reset durations, so the run's own budgets use 1h or 1m.
models='["gemini-3.8-flash", "claude-haiku-5-5"]'
case "${name}" in
  rpm) spec='{"rate_limit": {"request_max_limit": 3, "request_reset_duration": "1m"}}' ;;
  tpm) spec='{"rate_limit": {"token_max_limit": 1000, "token_reset_duration": "1m"}}' ;;
  budget) spec='{"budgets": [{"max_limit": 0.0002, "reset_duration": "1h"}]}' ;;
  race) spec='{"budgets": [{"max_limit": 0.0001, "reset_duration": "1h"}]}' ;;
  model-budget) spec='{"model_budgets": [{"model_name": "gemini-3.8-flash", "budgets": [{"max_limit": 0.0003, "reset_duration": "1h"}]}]}' ;;
  reset) spec='{"budgets": [{"max_limit": 0.0001, "reset_duration": "1m"}]}' ;;
  unpriced)
    spec='{"budgets": [{"max_limit": 0.0001, "reset_duration": "1h"}]}'
    models='["gemini-3.8-flash", "claude-haiku-5-5", "test-claude-unpriced"]'
    ;;
  *)
    echo "usage: $0 <rpm|tpm|budget|race|model-budget|reset|unpriced> [note]" >&2
    exit 2
    ;;
esac

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
repo_dir=$(cd "${harness_dir}/.." && pwd)
scenario="scenarios/bifrost/cost-${name}.json"
[ -f "${harness_dir}/${scenario}" ] || { echo "no ${scenario} in ${harness_dir}" >&2; exit 2; }

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
# gcloud rather than Terraform state, so a fresh clone works without terraform init.
url=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-bifrost --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
admin_password=$(gcloud secrets versions access latest --secret agw-bifrost-admin-password --project "${PROJECT}")

# Unique per run, so two runs of the same name never delete each other's key.
key_name="agw-t3-${name}-$(date -u +%Y%m%dT%H%M%S)-$$"

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
key_headers="${tmp}/key.headers"
key_id=""
cleanup() {
  local code
  if [ -n "${key_id}" ]; then
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE "${url}/api/governance/virtual-keys/${key_id}" \
      -H @"${admin_headers}" || true)
    case "${code}" in
      200 | 204) echo "deleted ${key_name}" ;;
      *) echo "WARNING: could not delete ${key_name} (${key_id}, HTTP ${code}); delete it in the admin UI (budget capped at \$0.05 a day)" >&2 ;;
    esac
  fi
  rm -rf "${tmp}"
}
trap cleanup EXIT

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Basic %s\nContent-Type: application/json\n' \
    "${id_token}" "$(printf 'admin:%s' "${admin_password}" | base64 -w0)" >"${admin_headers}"
)
unset admin_password

# The window-only run needs its model on the gateway: refuse clearly rather than mint a key
# for a model that isn't there.
if [ "${name}" = unpriced ] && ! grep -q 'test-claude-unpriced' "${repo_dir}/gateways/bifrost/config/config.json"; then
  echo "test-claude-unpriced isn't in config.json: open the test 3 window first (README.md)" >&2
  exit 2
fi

# Build the key: limits go on the key itself, except model budgets, which sit under the
# provider config they belong to.
body=$(python3 -I -c '
import json, sys
spec, models = json.loads(sys.argv[2]), json.loads(sys.argv[3])
pc = {"provider": "vertex", "allowed_models": models, "key_ids": ["*"], "weight": 1}
if "model_budgets" in spec:
    pc["model_budgets"] = spec.pop("model_budgets")
budgets = [{"max_limit": 0.05, "reset_duration": "1d"}] + spec.pop("budgets", [])
print(json.dumps({"name": sys.argv[1], "description": "test 3 throwaway key (run-cost.sh), deleted on exit",
                  "provider_configs": [pc], "budgets": budgets, **spec}))' "${key_name}" "${spec}" "${models}")
created=$(curl -fsS -X POST "${url}/api/governance/virtual-keys" -H @"${admin_headers}" -d "${body}")
# One parse for both, so the id (for cleanup) is set whenever the value is. If the parse
# itself fails the key is left behind with its $0.05 daily backstop; the next restart of
# Bifrost removes it (config.json declares virtual_keys).
parsed=$(printf %s "${created}" | python3 -I -c '
import json, sys
vk = json.load(sys.stdin)["virtual_key"]
v = vk["value"]
print(vk["id"], v["value"] if isinstance(v, dict) else v)')
unset created
key_id=${parsed%% *}
key=${parsed#* }
unset parsed
case "${key}" in sk-bf-*) ;; *) echo "the created key has no sk-bf- value; stopping" >&2; exit 1 ;; esac
echo "created ${key_name} (${key_id}) on ${revision}: ${spec}"

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "${id_token}" "${key}" >"${key_headers}"
)

cd "${harness_dir}"
# Local runs only, so the ID token is always your gcloud identity: "auto" would pick the
# metadata server on a GCE VM and mint tokens as the VM's service account (403).
out=$(PYTHONUNBUFFERED=1 AGW_ID_TOKEN_SOURCE=gcloud AGW_PROJECT="${PROJECT}" AGW_GATEWAY_URL="${url}/v1" \
  AGW_GATEWAY_API_KEY="${key}" AGW_RESULTS_DIR="${repo_dir}/results/raw/bifrost" PYTHONPATH=src \
  uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway key ${key_name} ${spec}${note:+; ${note}}" 2>&1 | tee /dev/stderr)
unset key

# The key's quota as its holder sees it, after the run. Charging is asynchronous, so wait
# a moment for the last request's usage to land.
run_dir=$(printf '%s\n' "${out}" | sed -n 's/.*results: //p' | tail -1)
case "${run_dir}" in /*) ;; ?*) run_dir="${harness_dir}/${run_dir}" ;; esac
sleep 3
if [ -n "${run_dir}" ] && [ -d "${run_dir}" ]; then
  # The quota response holds no key value, but scrub any sk-bf- string anyway: this file
  # is committed with the run. Written to tmp first, so a failed read leaves no partial file.
  curl -fsS --max-time 30 "${url}/api/governance/virtual-keys/quota" -H @"${key_headers}" | python3 -I -c '
import json, sys
def scrub(x):
    if isinstance(x, dict):
        return {k: scrub(v) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub(v) for v in x]
    return "[redacted]" if isinstance(x, str) and "sk-bf-" in x else x
json.dump(scrub(json.load(sys.stdin)), sys.stdout, indent=1); print()' >"${tmp}/quota.json" \
    && mv "${tmp}/quota.json" "${run_dir}/quota.json" && echo "saved ${run_dir}/quota.json"
fi
