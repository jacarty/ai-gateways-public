#!/usr/bin/env bash
# decK against the running agw-kong, through its /admin-api route (ADR 0015).
#   gateways/kong/deck.sh diff    # live config vs config/kong.yaml; exit 2 if they differ
#   gateways/kong/deck.sh sync    # make the live config match config/kong.yaml
#
# Credentials (your ID token, the admin key, the caller keys, the Kong Manager password) are read with gcloud
# into variables. decK gets its headers from a config file that is a pipe (fd 3,
# behind a .yaml symlink so decK picks the YAML parser), because DECK_HEADERS splits
# on spaces and decK echoes the broken value (it once printed the admin key). Nothing
# is written to disk or the command line, and decK's output is redacted.
set -euo pipefail
shopt -s inherit_errexit

PROJECT=my-gcp-project
REGION=europe-west1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$HERE/config/kong.yaml"

cmd="${1:-}"
case "$cmd" in
  diff | sync) ;;
  *) echo "usage: $0 diff|sync" >&2; exit 64 ;;
esac

secret() { gcloud secrets versions access latest --secret "$1" --project "$PROJECT"; }

url="$(gcloud run services describe agw-kong --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
[ -n "$url" ] || { echo "agw-kong not found: make deploy-kong first" >&2; exit 1; }
id_token="$(gcloud auth print-identity-token)"
DECK_ADMIN_KEY="$(secret agw-kong-admin-key)"
DECK_AGENT_KEY="$(secret agw-kong-agent-key)"
DECK_HARNESS_KEY="$(secret agw-kong-harness-key)"
DECK_MANAGER_PASSWORD="$(secret agw-kong-manager-password)"
# Kong keeps only a hash of a basic-auth password, so decK ignores the password when it
# compares: a rotated password would never reach Kong. The credential's id is derived
# from the password instead (a SHA-256, UUID-shaped; the password is 32 random
# characters, so it can't be recovered), so a new password is a new credential, which
# decK creates while deleting the old one.
DECK_MANAGER_CRED_ID="$(printf '%s' "$DECK_MANAGER_PASSWORD" | sha256sum | cut -c1-32 |
  sed -E 's/^(.{8})(.{4})(.{4})(.{4})/\1-\2-\3-\4-/')"
export DECK_ADMIN_KEY DECK_AGENT_KEY DECK_HARNESS_KEY DECK_MANAGER_PASSWORD DECK_MANAGER_CRED_ID

for k in DECK_ADMIN_KEY DECK_AGENT_KEY DECK_HARNESS_KEY DECK_MANAGER_PASSWORD; do
  [ -n "${!k}" ] || { echo "$k is empty: check the agw-kong-* secrets" >&2; exit 1; }
done

# Replaces the keys and the Manager password (literal strings, read from the environment, so they never
# appear in a command line), any JWT, and any "Bearer <value>" (every Kong
# credential has that form, so a diff after a rotation, which shows the old,
# still-live value, is masked too) with REDACTED.
redact() {
  awk 'function rep(s, k,   out, i) {
         if (k == "") return s
         out = ""
         while ((i = index(s, k)) > 0) { out = out substr(s, 1, i - 1) "REDACTED"; s = substr(s, i + length(k)) }
         return out s
       }
       { $0 = rep(rep(rep(rep($0, ENVIRON["DECK_ADMIN_KEY"]), ENVIRON["DECK_AGENT_KEY"]), ENVIRON["DECK_HARNESS_KEY"]), ENVIRON["DECK_MANAGER_PASSWORD"])
         gsub(/eyJ[A-Za-z0-9._-]+/, "REDACTED-JWT"); gsub(/Bearer [A-Za-z0-9._~+\/=-]+/, "Bearer REDACTED"); print }'
}

link_dir="$(mktemp -d)"
trap 'rm -rf "$link_dir"' EXIT
exec 3< <(printf 'kong-addr: %s/admin-api\nheaders:\n  - "X-Serverless-Authorization:Bearer %s"\n  - "Authorization:Bearer %s"\n' \
  "$url" "$id_token" "$DECK_ADMIN_KEY")
ln -s /dev/fd/3 "$link_dir/deck.yaml"

# Kong scales to zero: a cold start (migrations check, bootstrap import) takes about
# 10 s, decK's default client timeout.
# A rotated Manager password: decK creates the new credential before deleting the old
# one, and the username "admin" must be unique, so the create fails and decK drops the
# deletion. Remove the stale credential first (Kong Manager's login is briefly absent).
admin_api() {
  curl -sS --fail --max-time 60 -H @<(printf 'X-Serverless-Authorization: Bearer %s\nAuthorization: Bearer %s\n' \
    "$id_token" "$DECK_ADMIN_KEY") "$@"
}
if [ "$cmd" = sync ]; then
  stale="$(admin_api "$url/admin-api/consumers/manager/basic-auth" 2>/dev/null |
    python3 -I -c 'import json, os, sys
for c in json.load(sys.stdin).get("data", []):
    if c["id"] != os.environ["DECK_MANAGER_CRED_ID"]:
        print(c["id"])' || true)"
  for cred in $stale; do
    echo "removing the old Kong Manager credential (password rotated)"
    admin_api -X DELETE "$url/admin-api/consumers/manager/basic-auth/$cred" >/dev/null
  done
fi

if [ "$cmd" = diff ]; then
  # --non-zero-exit-code: exit 2 when the live config differs, so callers can tell.
  deck gateway diff "$CONFIG" --config "$link_dir/deck.yaml" --timeout 60 --non-zero-exit-code 2>&1 | redact
else
  deck gateway sync "$CONFIG" --config "$link_dir/deck.yaml" --timeout 60 2>&1 | redact
fi
