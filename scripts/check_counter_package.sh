#!/bin/sh
# Read current provider truth; never mutate permissions, tags or packages.
set -eu
MODE="${1:?counter package check mode is required}"
case "$MODE" in read|before-push|published) ;; *) exit 1 ;; esac
ENDPOINT='users/OpenJ92/packages/container/control-plane-kit-servers%2Fcpk-server'
METADATA="$(gh api "$ENDPOINT")"
printf '%s\n' "$METADATA" | jq -e '
  .id == 13950177 and .name == "control-plane-kit-servers/cpk-server" and
  .package_type == "container" and .visibility == "private" and
  .repository.full_name == "OpenJ92/control-plane-kit-servers"' >/dev/null
[ "$MODE" != read ] || exit 0
TAG="${2:?counter tag is required}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
sh "$ROOT/scripts/counter_witness_destination.sh" openj92 control-plane-kit-servers "$TAG" >/dev/null
# Capture the complete paginated response before parsing: an API/page failure
# must not be hidden by the exit status of a downstream JSON filter.
VERSIONS="$(gh api --paginate --slurp "$ENDPOINT/versions?per_page=100")"
printf '%s\n' "$VERSIONS" | jq -e '
  type == "array" and all(.[]; type == "array") and
  all(.[][]; (.id | type) == "number" and (.name | type) == "string" and
    (.metadata.container.tags | type) == "array" and
    all(.metadata.container.tags[]; type == "string"))' >/dev/null
if [ "$MODE" = before-push ]; then
  printf '%s\n' "$VERSIONS" | jq -e --arg tag "$TAG" '
    all(.[][]; all(.metadata.container.tags[]; . != $tag))' >/dev/null
else
  REFERENCE="${3:?published counter reference is required}"
  printf '%s\n' "$REFERENCE" | sh "$ROOT/scripts/select_repository_digest.sh" \
    ghcr.io/openj92/control-plane-kit-servers/cpk-server >/dev/null
  DIGEST="${REFERENCE#*@}"
  printf '%s\n' "$VERSIONS" | jq -e --arg tag "$TAG" --arg digest "$DIGEST" '
    [.[][] | select(.name == $digest and any(.metadata.container.tags[]; . == $tag))] |
    if length == 1 then .[0] | {package_id: 13950177, version_id: .id,
      digest: .name, tags: .metadata.container.tags, visibility: "private"}
    else error("counter publication version correlation failed") end'
fi
