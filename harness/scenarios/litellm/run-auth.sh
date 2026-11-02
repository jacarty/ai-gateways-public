#!/usr/bin/env bash
# Test 5 (identity and secrets): run auth.json with the keys it needs. Mints throwaway
# LiteLLM keys in four states (Claude-only, expired, blocked, deleted), reads the agent's
# key, and passes them to the harness as AGW_T5_* environment variables only; the keys it
# made are deleted on exit, even on failure. As in run-cost.sh, the master key and ID
# token reach curl through a private headers file removed on exit.
#
# Usage, from anywhere:  harness/scenarios/litellm/run-auth.sh ["note for meta.json"]
# The gateway's live revision is added to the note automatically.
set -euo pipefail

PROJECT=my-gcp-project
REGION=europe-west1
note=${1:-}

harness_dir=$(cd "$(dirname "$0")/../.." && pwd)
scenario="scenarios/litellm/auth.json"

# Read everything into variables first: a failing command substitution inside printf's
# arguments would not stop the script (set -e ignores it there).
# gcloud rather than Terraform state, so a fresh clone works without terraform init.
url=$(gcloud run services describe agw-litellm --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-litellm --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
master_key=$(gcloud secrets versions access latest --secret agw-litellm-master-key --project "${PROJECT}")
agent_key=$(gcloud secrets versions access latest --secret agw-litellm-agent-key --project "${PROJECT}")
harness_key=$(gcloud secrets versions access latest --secret agw-litellm-harness-key --project "${PROJECT}")

# Unique per run, so overlapping runs never delete each other's keys. Named up front,
# so clean-up knows them even if minting fails half-way.
suffix="$(date -u +%Y%m%dT%H%M%S)-$$"
aliases=()
for name in claude-only expired blocked deleted; do aliases+=("agw-t5-run-${name}-${suffix}"); done

tmp=$(mktemp -d)
admin_headers="${tmp}/admin.headers"
cleanup() {
  # One alias at a time: a key that was never minted (404) mustn't stop the others.
  local a code
  for a in "${aliases[@]}"; do
    [ -n "${a}" ] || continue
    code=$(curl -sS -o /dev/null -w '%{http_code}' "${url}/key/delete" -H @"${admin_headers}" \
      -H "Content-Type: application/json" -d "{\"key_aliases\": [\"${a}\"]}" || true)
    case "${code}" in
      200) echo "deleted ${a}" ;;
      404) ;; # never minted (LiteLLM answers 404 "No keys found")
      "" | 000) echo "WARNING: could not reach the gateway to delete ${a}; delete it in the admin UI" >&2 ;;
      *) echo "WARNING: could not delete ${a} (HTTP ${code}); delete it in the admin UI (budget capped at \$0.01)" >&2 ;;
    esac
  done
  rm -rf "${tmp}"
}
trap cleanup EXIT

(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "${id_token}" "${master_key}" \
    >"${admin_headers}"
)
unset master_key

admin() { # admin <path> <json body>: the response body on stdout
  curl -fsS "${url}$1" -H @"${admin_headers}" -H "Content-Type: application/json" -d "$2"
}

key_admin() { # key_admin <path> <JSON field> <key>: like admin, with the key kept off argv
  KEY="$3" python3 -c 'import json, os, sys; print(json.dumps({sys.argv[1]: os.environ["KEY"]}))' "$2" |
    curl -fsS -o /dev/null "${url}$1" -H @"${admin_headers}" -H "Content-Type: application/json" --data-binary @-
}

mint() { # mint <name> <extra JSON fields, without braces>: prints the new key
  local alias_name="agw-t5-run-$1-${suffix}" body
  body="{\"key_alias\": \"${alias_name}\", \"max_budget\": 0.01, $2}"
  admin /key/generate "${body}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])'
}

claude_only_key=$(mint claude-only '"models": ["claude-haiku-5-5"]')
expired_key=$(mint expired '"models": ["claude-haiku-5-5"], "duration": "1s"')
blocked_key=$(mint blocked '"models": ["claude-haiku-5-5"]')
deleted_key=$(mint deleted '"models": ["claude-haiku-5-5"]')
key_admin /key/block key "${blocked_key}"
KEY="${deleted_key}" python3 -c 'import json, os; print(json.dumps({"keys": [os.environ["KEY"]]}))' |
  curl -fsS -o /dev/null "${url}/key/delete" -H @"${admin_headers}" -H "Content-Type: application/json" --data-binary @-
aliases=("${aliases[@]/agw-t5-run-deleted-${suffix}/}") # already gone
sleep 3 # let the 1 s key expire
echo "minted Claude-only, expired, blocked and deleted keys (agw-t5-run-*-${suffix}) on ${revision}"

cd "${harness_dir}"
# Local runs only, so the ID token is always your gcloud identity: "auto" would pick the
# metadata server on a GCE VM and mint tokens as the VM's service account (403).
AGW_ID_TOKEN_SOURCE=gcloud AGW_GATEWAY_URL="${url}" \
  AGW_GATEWAY_API_KEY="${harness_key}" \
  AGW_T5_AGENT_KEY="${agent_key}" \
  AGW_T5_CLAUDE_ONLY_KEY="${claude_only_key}" \
  AGW_T5_EXPIRED_KEY="${expired_key}" \
  AGW_T5_BLOCKED_KEY="${blocked_key}" \
  AGW_T5_DELETED_KEY="${deleted_key}" \
  PYTHONPATH=src uv run python -m agw_harness.cli scenarios "${scenario}" \
  --note "revision ${revision}; throwaway keys agw-t5-run-*-${suffix}${note:+; ${note}}"
