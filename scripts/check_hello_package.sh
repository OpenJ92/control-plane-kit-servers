#!/bin/sh
# Provider reads only. Preserve gh failures, including a failure on a later page.
set -eu
MODE="${1:?check mode required}"
SOURCE="${2:?source commit required}"
case "$MODE" in before-push|published) ;; *) exit 1 ;; esac
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"
ENDPOINT='users/OpenJ92/packages/container/control-plane-kit-servers%2Fhello-server'
EVIDENCE="$(mktemp -d)"
trap 'rm -rf -- "$EVIDENCE"' EXIT
trap 'exit 1' HUP INT TERM
gh api "$ENDPOINT" > "$EVIDENCE/package.json"
gh api --paginate --slurp "$ENDPOINT/versions?per_page=100" > "$EVIDENCE/versions.json"
if [ "$MODE" = published ]; then
  set -- /evidence "$SOURCE" "$MODE" "${3:?published reference required}"
else
  set -- /evidence "$SOURCE" "$MODE"
fi
docker run --rm --network none \
  -v "$ROOT/scripts:/scripts:ro" -v "$EVIDENCE:/evidence:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 "$POLICY_IMAGE" \
  python /scripts/hello_publication_metadata.py "$@"
