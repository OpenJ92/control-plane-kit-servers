#!/bin/sh
# Reached only through the owning test.sh / producer entrypoints.
set -eu
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
shift
CONTROLLER='' CONTROLLER_RECEIPT='' RECEIPTS='' CANDIDATE='' SOURCE=''
invalid() { echo 'Invalid managed release input' >&2; exit 2; }
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || invalid
  case "$1" in
    --controller-image-id) [ -z "$CONTROLLER" ] || invalid; CONTROLLER="$2" ;;
    --controller-receipt) [ -z "$CONTROLLER_RECEIPT" ] || invalid; CONTROLLER_RECEIPT="$2" ;;
    --receipt-dir) [ -z "$RECEIPTS" ] || invalid; RECEIPTS="$2" ;;
    --image-id) [ -z "$CANDIDATE" ] || invalid; CANDIDATE="$2" ;;
    --source) [ -z "$SOURCE" ] || invalid; SOURCE="$2" ;;
    *) invalid ;;
  esac
  shift 2
done
if [ "$MODE" = --managed-connector-candidate ]; then
  case "$CANDIDATE" in sha256:*) ;; *) invalid ;; esac
  [ "${#CANDIDATE}" = 71 ] || invalid
  case "${CANDIDATE#sha256:}" in *[!0-9a-f]*) invalid ;; esac
  [ "${#SOURCE}" = 40 ] || invalid
  case "$SOURCE" in *[!0-9a-f]*) invalid ;; esac
else
  [ -z "$CANDIDATE$SOURCE" ] || invalid
fi
case "$RECEIPTS" in /*) ;; *) invalid ;; esac
[ ! -e "$RECEIPTS" ] && [ ! -L "$RECEIPTS" ] || invalid
PARENT="$(dirname -- "$RECEIPTS")"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ] || invalid
[ "$(CDPATH= cd -- "$PARENT" && pwd -P)" = "$PARENT" ] || invalid
# Archive acquisition never reads ignored working files. Only mounted modes
# reject executable inputs absent from their tracked source evidence.
if [ "$MODE" != --managed-connector-controller ]; then
  IGNORED="$(git ls-files --others --ignored --exclude-standard -- products scripts src tests)"
  if printf '%s\n' "$IGNORED" | grep -Eq '\.(py|pyc|pyo|pyd|so|sh)$'; then invalid; fi
fi
umask 077
if [ "$MODE" = --managed-connector-controller ]; then
  [ -z "$CONTROLLER$CONTROLLER_RECEIPT" ] || invalid
  [ -z "$(git status --porcelain)" ] || invalid
  SOURCE="$(git rev-parse HEAD)"
  TREE="$(git rev-parse HEAD^{tree})"
  [ -z "$(git ls-tree -r "$SOURCE" | awk '$1 == "160000" {print $3}')" ] || invalid
  for INPUT in Dockerfile.test pyproject.toml README.md AGENTS.md GIT-FLOW.md test.sh bootstrap.sh .github coordination coordinates catalogue products docs scripts src tests; do
    git cat-file -e "$SOURCE:$INPUT" || invalid
  done
  RECIPE="$(hash_file Dockerfile.test | cut -d ' ' -f 1)"
  mkdir -m 700 "$RECEIPTS"
  git archive --format=tar "$SOURCE" > "$RECEIPTS/source.tar"
  git ls-tree -r --name-only "$SOURCE" > "$RECEIPTS/source.paths"
  LC_ALL=C sort "$RECEIPTS/source.paths" > "$RECEIPTS/source.files"
  tar -tf "$RECEIPTS/source.tar" > "$RECEIPTS/archive.paths"
  sed '/\/$/d' "$RECEIPTS/archive.paths" | LC_ALL=C sort > "$RECEIPTS/archive.files"
  cmp "$RECEIPTS/source.files" "$RECEIPTS/archive.files" || invalid
  hash_file "$RECEIPTS/source.tar" > "$RECEIPTS/source.tar.sha256"
  set +e
  docker build -f Dockerfile.test --label "org.opencontainers.image.revision=$SOURCE" \
    --iidfile "$RECEIPTS/image.id" - < "$RECEIPTS/source.tar" > "$RECEIPTS/build.log" 2>&1
  RESULT=$?
  set -e
  printf '%s\n' "$RESULT" > "$RECEIPTS/build.exit"
  [ "$RESULT" = 0 ] || exit "$RESULT"
  [ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$SOURCE" ] || exit 1
  ID="$(cat "$RECEIPTS/image.id")"
  [ "$(docker image inspect "$ID" --format '{{.Id}}')" = "$ID" ] || exit 1
  LOG_HASH="$(hash_file "$RECEIPTS/build.log" | cut -d ' ' -f 1)"
  jq -n --arg source "$SOURCE" --arg tree "$TREE" --arg recipe "$RECIPE" --arg image "$ID" --arg log "$LOG_HASH" \
    '{schema:"cpk.cloudflared-controller-acquisition.v1",source_commit:$source,source_tree:$tree,dockerfile_sha256:$recipe,image_id:$image,build_exit:0,build_log_sha256:$log}' > "$RECEIPTS/controller.json"
  echo "Controller receipt: $RECEIPTS/controller.json"
  exit 0
fi
case "$MODE" in --managed-connector-release-tests|--managed-connector-candidate) ;; *) invalid ;; esac
[ -z "$(git ls-files --others --exclude-standard)" ] || invalid
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
if [ "$MODE" = --managed-connector-candidate ]; then
  [ -z "$(git status --porcelain)" ] || invalid
  [ "$(git rev-parse HEAD)" = "$SOURCE" ] || invalid
  TREE="$(git rev-parse HEAD^{tree})"
  [ "$(jq -r .source_commit "$CONTROLLER_RECEIPT")" = "$SOURCE" ] || invalid
  [ "$(jq -r .source_tree "$CONTROLLER_RECEIPT")" = "$TREE" ] || invalid
  [ "$(docker image inspect "$CANDIDATE" --format '{{.Id}}')" = "$CANDIDATE" ] || exit 1
  mkdir -m 700 "$RECEIPTS/fixtures"
  RUN_RECORD="$(mktemp "$RECEIPTS/run.XXXXXXXXXXXX")"
  RUN="cpk-managed-release-$(basename "$RUN_RECORD")"
  printf '%s\n' "$RUN" > "$RUN_RECORD"
  [ -z "$(docker container ls -aq --filter "label=org.openj92.cpk.test-run=$RUN")" ] || exit 1
  set +e
  docker run --pull never --rm --network none \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --mount "type=bind,source=$ROOT,target=/source,readonly" \
    --mount "type=bind,source=$RECEIPTS,target=/evidence" \
    --mount "type=bind,source=$RECEIPTS/fixtures,target=/witness" \
    --workdir /source -e PYTHONDONTWRITEBYTECODE=1 -e DOCKER_HOST=unix:///var/run/docker.sock \
    -e "CPK_MANAGED_IMAGE=$CANDIDATE" -e "CPK_MANAGED_SOURCE=$SOURCE" \
    -e "CPK_RELEASE_CONTROLLER=$CONTROLLER" -e "CPK_RELEASE_TREE=$TREE" \
    -e "CPK_MANAGED_TEST_RUN=$RUN" -e "CPK_MANAGED_HOST_RECORDS=$RECEIPTS/fixtures" \
    -e "CPK_MANAGED_HOST_TESTS=$ROOT/products/cloudflared_connector/tests" \
    "$CONTROLLER" python products/cloudflared_connector/release.py qualify \
    > "$RECEIPTS/controller.log" 2>&1
  RESULT=$?
  set -e
  printf '%s\n' "$RESULT" > "$RECEIPTS/controller.exit"
  # A killed controller leaves retained evidence; never claim cleanup on its behalf.
  [ "$RESULT" = 0 ] || exit "$RESULT"
  [ "$(docker image inspect "$CANDIDATE" --format '{{.Id}}')" = "$CANDIDATE" ] || exit 1
  [ -z "$(docker container ls -aq --filter "label=org.openj92.cpk.test-run=$RUN")" ] || exit 1
  exit 0
fi
git rev-parse HEAD > "$RECEIPTS/source.commit"
git diff --binary HEAD > "$RECEIPTS/source.diff"
hash_file "$RECEIPTS/source.diff" > "$RECEIPTS/source.diff.sha256"
set +e
docker run --pull never --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:exec \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  --workdir /source -e PYTHONDONTWRITEBYTECODE=1 \
  "$CONTROLLER" sh -c 'python -m unittest discover -s products/cloudflared_connector/tests -p test_managed_release.py -v && python -m unittest discover -s products/cloudflared_connector/tests -p test_managed_witness_diagnostics.py -v' \
  > "$RECEIPTS/tests.log" 2>&1
RESULT=$?
set -e
printf '%s\n' "$RESULT" > "$RECEIPTS/tests.exit"
cat "$RECEIPTS/tests.log"
exit "$RESULT"
