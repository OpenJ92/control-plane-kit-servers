#!/bin/sh
# Reached only through the owning test.sh / producer entrypoints.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
shift
CONTROLLER='' CONTROLLER_RECEIPT='' RECEIPTS=''
invalid() { echo 'Invalid managed release input' >&2; exit 2; }
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || invalid
  case "$1" in
    --controller-image-id) [ -z "$CONTROLLER" ] || invalid; CONTROLLER="$2" ;;
    --controller-receipt) [ -z "$CONTROLLER_RECEIPT" ] || invalid; CONTROLLER_RECEIPT="$2" ;;
    --receipt-dir) [ -z "$RECEIPTS" ] || invalid; RECEIPTS="$2" ;;
    *) invalid ;;
  esac
  shift 2
done
case "$RECEIPTS" in /*) ;; *) invalid ;; esac
[ ! -e "$RECEIPTS" ] && [ ! -L "$RECEIPTS" ] || invalid
PARENT="$(dirname -- "$RECEIPTS")"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ] || invalid
umask 077
if [ "$MODE" = --managed-connector-controller ]; then
  [ -z "$CONTROLLER$CONTROLLER_RECEIPT" ] || invalid
  [ -z "$(git status --porcelain)" ] || invalid
  SOURCE="$(git rev-parse HEAD)"
  TREE="$(git rev-parse HEAD^{tree})"
  RECIPE="$(shasum -a 256 Dockerfile.test | cut -d ' ' -f 1)"
  mkdir -m 700 "$RECEIPTS"
  set +e
  docker build -f Dockerfile.test --label "org.opencontainers.image.revision=$SOURCE" \
    --iidfile "$RECEIPTS/image.id" . > "$RECEIPTS/build.log" 2>&1
  RESULT=$?
  set -e
  printf '%s\n' "$RESULT" > "$RECEIPTS/build.exit"
  [ "$RESULT" = 0 ] || exit "$RESULT"
  ID="$(cat "$RECEIPTS/image.id")"
  [ "$(docker image inspect "$ID" --format '{{.Id}}')" = "$ID" ] || exit 1
  LOG_HASH="$(shasum -a 256 "$RECEIPTS/build.log" | cut -d ' ' -f 1)"
  jq -n --arg source "$SOURCE" --arg tree "$TREE" --arg recipe "$RECIPE" --arg image "$ID" --arg log "$LOG_HASH" \
    '{schema:"cpk.cloudflared-controller-acquisition.v1",source_commit:$source,source_tree:$tree,dockerfile_sha256:$recipe,image_id:$image,build_exit:0,build_log_sha256:$log}' > "$RECEIPTS/controller.json"
  echo "Controller receipt: $RECEIPTS/controller.json"
  exit 0
fi
[ "$MODE" = --managed-connector-release-tests ] || invalid
case "$CONTROLLER" in sha256:*) ;; *) invalid ;; esac
[ "${#CONTROLLER}" = 71 ] || invalid
case "${CONTROLLER#sha256:}" in *[!0-9a-f]*) invalid ;; esac
case "$CONTROLLER_RECEIPT" in /*) ;; *) invalid ;; esac
[ -f "$CONTROLLER_RECEIPT" ] && [ ! -L "$CONTROLLER_RECEIPT" ] || invalid
[ "$(wc -c < "$CONTROLLER_RECEIPT")" -le 65536 ] || invalid
jq -e --arg id "$CONTROLLER" 'type == "object" and .schema == "cpk.cloudflared-controller-acquisition.v1" and .image_id == $id and .build_exit == 0 and (.source_commit | test("^[0-9a-f]{40}$")) and (.source_tree | test("^[0-9a-f]{40}$")) and (.dockerfile_sha256 | test("^[0-9a-f]{64}$")) and (.build_log_sha256 | test("^[0-9a-f]{64}$"))' "$CONTROLLER_RECEIPT" >/dev/null || invalid
[ "$(docker image inspect "$CONTROLLER" --format '{{.Id}}')" = "$CONTROLLER" ] || exit 1
[ "$(docker image inspect "$CONTROLLER" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$(jq -r .source_commit "$CONTROLLER_RECEIPT")" ] || exit 1
mkdir -m 700 "$RECEIPTS"
cp "$CONTROLLER_RECEIPT" "$RECEIPTS/controller.json"
git rev-parse HEAD > "$RECEIPTS/source.commit"
git diff --binary HEAD > "$RECEIPTS/source.diff"
shasum -a 256 "$RECEIPTS/source.diff" > "$RECEIPTS/source.diff.sha256"
set +e
docker run --pull never --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  --workdir /source -e PYTHONDONTWRITEBYTECODE=1 \
  "$CONTROLLER" sh -c 'python -m unittest discover -s products/cloudflared_connector/tests -p test_managed_release.py -v && python -m unittest discover -s products/cloudflared_connector/tests -p test_managed_witness_diagnostics.py -v' \
  > "$RECEIPTS/tests.log" 2>&1
RESULT=$?
set -e
printf '%s\n' "$RESULT" > "$RECEIPTS/tests.exit"
cat "$RECEIPTS/tests.log"
exit "$RESULT"
