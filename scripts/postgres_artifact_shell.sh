#!/bin/sh
# Product-local owning routes. Published qualification is separately authorized.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:?mode required}"
shift
case "$MODE" in --postgres-release-tests|--postgres-published-image) ;; *) exit 2 ;; esac
if [ "$MODE" = --postgres-published-image ]; then
  [ "${CPK_POSTGRES_ARTIFACT_MODE:-}" = published-digest ]
  : "${CPK_POSTGRES_IMAGE:?exact pre-pulled repository digest required}"
  : "${CPK_POSTGRES_SOURCE_REVISION:?expected source required}"
  : "${CPK_POSTGRES_RECIPE_SHA256:?expected recipe hash required}"
fi
CONTROLLER='' RECEIPTS=''
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || exit 2
  case "$1" in
    --controller-image-id) [ -z "$CONTROLLER" ]; CONTROLLER="$2" ;;
    --receipt-dir) [ -z "$RECEIPTS" ]; RECEIPTS="$2" ;;
    *) exit 2 ;;
  esac
  shift 2
done
case "$CONTROLLER" in sha256:*) ;; *) exit 2 ;; esac
[ "${#CONTROLLER}" = 71 ]
case "${CONTROLLER#sha256:}" in *[!0-9a-f]*) exit 2 ;; esac
case "$RECEIPTS" in /*) ;; *) exit 2 ;; esac
[ ! -e "$RECEIPTS" ] && [ ! -L "$RECEIPTS" ]
PARENT="$(dirname -- "$RECEIPTS")"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ]
[ "$(CDPATH= cd -- "$PARENT" && pwd -P)" = "$PARENT" ]
[ "$(docker image inspect "$CONTROLLER" --format '{{.Id}}')" = "$CONTROLLER" ]
umask 077
mkdir -m 700 "$RECEIPTS"
git rev-parse HEAD > "$RECEIPTS/source.commit"
git diff --binary HEAD > "$RECEIPTS/source.diff"
case "$MODE" in
 --postgres-release-tests)
  set +e
  docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --tmpfs /tmp:exec \
    --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/source/products/postgres_server/src \
    "$CONTROLLER" python -m unittest discover -s products/postgres_server/tests -p 'test_postgres*.py' -v \
    > "$RECEIPTS/tests.log" 2>&1
  RESULT=$?
  set -e
  printf '%s\n' "$RESULT" > "$RECEIPTS/tests.exit"
  cat "$RECEIPTS/tests.log"
  exit "$RESULT"
  ;;
 --postgres-published-image)
  mkdir -m 700 "$RECEIPTS/fixtures"
  RUN_RECORD="$(mktemp -d "$RECEIPTS/run.XXXXXXXXXX")"
  RUN="cpk-postgres-published-$(basename "$RUN_RECORD")"
  printf '%s\n' "$RUN" > "$RECEIPTS/run.id"
  set +e
  docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
    --mount "type=bind,source=$RECEIPTS/fixtures,target=/witness" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONPATH=/source/products/postgres_server/src:/source/products/postgres_server/tests \
    -e "CPK_POSTGRES_TEST_RUN=$RUN" -e "CPK_POSTGRES_HOST_RECORDS=$RECEIPTS/fixtures" \
    -e CPK_POSTGRES_ARTIFACT_MODE -e CPK_POSTGRES_IMAGE \
    -e CPK_POSTGRES_SOURCE_REVISION -e CPK_POSTGRES_RECIPE_SHA256 \
    "$CONTROLLER" python /source/products/postgres_server/tests/live_postgres_image.py \
    > "$RECEIPTS/qualification.log" 2>&1
  RESULT=$?
  set -e
  rmdir "$RECEIPTS/fixtures" || RESULT=1
  printf '%s\n' "$RESULT" > "$RECEIPTS/qualification.exit"
  cat "$RECEIPTS/qualification.log"
  exit "$RESULT"
  ;;
 *) echo 'PostgreSQL artifact route is unavailable' >&2; exit 2 ;;
esac
