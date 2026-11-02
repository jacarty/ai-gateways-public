#!/bin/sh
# Kong's container command on Cloud Run (ADR 0015): migrate the database, import
# the Admin API route and admin consumer, then run the image's own entrypoint.
# One instance, so no other node migrates at the same time. The image's /bin/sh
# is dash: no pipefail, so output is captured before it is redacted.
set -eu

[ -n "${AGW_KONG_ADMIN_KEY:-}" ] || { echo "AGW_KONG_ADMIN_KEY is empty" >&2; exit 1; }

# Replaces the admin key with REDACTED, as a literal string (no regex), reading it
# from the environment so it never appears in a command line.
redact() {
  awk 'function rep(s, k,   out, i) {
         if (k == "") return s
         out = ""
         while ((i = index(s, k)) > 0) { out = out substr(s, 1, i - 1) "REDACTED"; s = substr(s, i + length(k)) }
         return out s
       }
       { print rep($0, ENVIRON["AGW_KONG_ADMIN_KEY"]) }'
}

# `kong migrations list` reports the schema state as its exit code:
# 0 up to date, 3 needs bootstrap, 4 pending (run finish), 5 new (run up).
# Its stdout lists migrations; its stderr (connection or TLS errors) is kept.
rc=0
kong migrations list >/dev/null || rc=$?
case "$rc" in
  0) ;;
  3) kong migrations bootstrap ;;
  4) kong migrations finish ;;
  5) kong migrations up && kong migrations finish ;;
  *) echo "kong migrations list failed (exit $rc)" >&2; exit 1 ;;
esac

# The bootstrap file holds only the Admin API route and the admin consumer, with
# fixed IDs, so importing it on every start is an upsert. config/kong.yaml declares
# the same entities, so a decK sync keeps them. The key is filled in by awk from the
# environment (not sed, whose arguments would hold it), in the container's in-memory
# /tmp, removed after the import or if it fails.
boot=/tmp/bootstrap.yaml
trap 'rm -f "$boot"' EXIT
(
  umask 077
  awk '{ while ((i = index($0, "__AGW_KONG_ADMIN_KEY__")) > 0)
           $0 = substr($0, 1, i - 1) ENVIRON["AGW_KONG_ADMIN_KEY"] substr($0, i + 22)
         print }' /var/run/kong-bootstrap/bootstrap.yaml >"$boot"
)
# A failed import can echo entity values, the key among them: redact before logging.
if ! out=$(kong config db_import "$boot" 2>&1); then
  printf '%s\n' "$out" | redact >&2
  exit 1
fi
printf '%s\n' "$out" | redact
rm -f "$boot"
trap - EXIT

exec /entrypoint.sh kong docker-start
