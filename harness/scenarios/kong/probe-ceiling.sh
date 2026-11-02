#!/usr/bin/env bash
# Test 7 (OSS ceiling): ask Kong, read-only, how it answers for the enterprise features the
# matrix needed. No model call and no entity created: GET /plugins/enabled; POST
# /schemas/plugins/validate and /schemas/vaults/validate (validation only, nothing is
# stored) for each enterprise plugin and the GCP vault, with an OSS plugin as a control;
# GET on the enterprise Admin API routes (audit log, RBAC, workspaces, licences). Writes
# probe.json (status and message per probe) into a new run directory under
# results/raw/kong/. The admin key and ID token reach curl through a private headers file
# removed on exit.
#
# Usage, from anywhere:  harness/scenarios/kong/probe-ceiling.sh
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1

repo_dir=$(cd "$(dirname "$0")/../../.." && pwd)
url=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')
revision=$(gcloud run services describe agw-kong --project "${PROJECT}" --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)')
id_token=$(gcloud auth print-identity-token)
admin_key=$(gcloud secrets versions access latest --secret agw-kong-admin-key --project "${PROJECT}")
[ -n "${url}" ] && [ -n "${admin_key}" ] && [ -n "${id_token}" ] ||
  { echo "agw-kong, its admin key or an ID token not found" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT
(
  umask 077
  printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\nContent-Type: application/json\n' \
    "${id_token}" "${admin_key}" >"${tmp}/admin.headers"
)
unset admin_key id_token

run_dir="${repo_dir}/results/raw/kong/$(date -u +%Y%m%dT%H%M%SZ)-oss-ceiling-probe"
mkdir -p "${run_dir}"

# probe <label> <method> <path> [json body]: one line of JSON with the status and body.
probe() {
  local code
  : >"${tmp}/body" # a failed request must not pair its status with the last probe's body
  if [ $# -ge 4 ]; then
    code=$(printf %s "$4" | curl -sS --max-time 30 -o "${tmp}/body" -w '%{http_code}' -X "$2" \
      "${url}/admin-api$3" -H @"${tmp}/admin.headers" -d @- || true)
  else
    code=$(curl -sS --max-time 30 -o "${tmp}/body" -w '%{http_code}' -X "$2" \
      "${url}/admin-api$3" -H @"${tmp}/admin.headers" || true)
  fi
  python3 -I -c '
import json, sys
label, method, path, code, body_file = sys.argv[1:]
raw = open(body_file).read()
try:
    body = json.loads(raw)
except ValueError:
    body = raw[:300]
print(json.dumps({"probe": label, "request": f"{method} {path}", "status": int(code or 0), "body": body}))
' "$1" "$2" "$3" "${code}" "${tmp}/body" >>"${tmp}/probes.jsonl"
}

probe "enabled plugins" GET /plugins/enabled
# Control: an OSS plugin validates.
probe "control: rate-limiting (OSS)" POST /schemas/plugins/validate '{"name": "rate-limiting", "config": {"minute": 1}}'
for p in ai-proxy-advanced ai-rate-limiting-advanced ai-sanitizer ai-semantic-prompt-guard ai-semantic-cache \
  ai-gcp-model-armor rate-limiting-advanced openid-connect key-auth-enc jwt-signer; do
  probe "enterprise plugin: ${p}" POST /schemas/plugins/validate "{\"name\": \"${p}\", \"config\": {}}"
done
probe "control: env vault (OSS)" POST /schemas/vaults/validate '{"name": "env", "prefix": "agw-env"}'
probe "enterprise vault: gcp" POST /schemas/vaults/validate '{"name": "gcp", "prefix": "agw-gcp", "config": {"project_id": "my-gcp-project"}}'
for path in /audit/requests /audit/objects /rbac/users /rbac/roles /workspaces /licenses; do
  probe "enterprise route: ${path}" GET "${path}"
done

python3 -I - "${tmp}/probes.jsonl" "${run_dir}/probe.json" "${revision}" <<'EOF'
import json, sys
src, out, revision = sys.argv[1:]
probes = [json.loads(line) for line in open(src)]
with open(out, "w") as f:
    f.write(json.dumps({"revision": revision, "probes": probes}, indent=1) + "\n")
for p in probes:
    body = p["body"]
    msg = body.get("message") if isinstance(body, dict) else str(body)[:80]
    if p["probe"] == "enabled plugins" and isinstance(body, dict):
        msg = f"{len(body.get('enabled_plugins', []))} plugins"
    print(f"{p['status']}  {p['probe']}: {str(msg)[:110]}")
EOF
echo "results: ${run_dir}"
# The controls must validate, or every answer above may be a 401 or an outage, not Kong's.
python3 -I -c '
import json, sys
probes = json.load(open(sys.argv[1]))["probes"]
bad = [p["probe"] for p in probes if p["probe"].startswith("control") and p["status"] != 200]
sys.exit(f"controls failed: {bad}; the answers above are not evidence" if bad else 0)
' "${run_dir}/probe.json"
