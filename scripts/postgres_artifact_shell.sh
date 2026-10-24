#!/bin/sh
# Product-local owning routes. Published qualification is separately authorized.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:?mode required}"
shift
case "$MODE" in --postgres-release-tests|--postgres-published-image|--postgres-source-image) ;; *) exit 2 ;; esac
if [ "$MODE" = --postgres-published-image ]; then
  [ "${CPK_POSTGRES_ARTIFACT_MODE:-}" = published-digest ]
  : "${CPK_POSTGRES_IMAGE:?exact pre-pulled repository digest required}"
  : "${CPK_POSTGRES_SOURCE_REVISION:?expected source required}"
  : "${CPK_POSTGRES_RECIPE_SHA256:?expected recipe hash required}"
fi
if [ "$MODE" = --postgres-source-image ]; then
  [ -z "${CPK_POSTGRES_ARTIFACT_MODE+x}${CPK_POSTGRES_IMAGE+x}${CPK_POSTGRES_SOURCE_REVISION+x}${CPK_POSTGRES_RECIPE_SHA256+x}" ]
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
 --postgres-published-image|--postgres-source-image)
  mkdir -m 700 "$RECEIPTS/fixtures"
  RUN_RECORD="$(mktemp -d "$RECEIPTS/run.XXXXXXXXXX")"
  RUN="cpk-postgres-witness-$(basename "$RUN_RECORD")"
  printf '%s\n' "$RUN" > "$RECEIPTS/run.id"
  # Separate ownership keys/names preserve the witness's pre-existing-resource
  # refusal. The project label still includes both owners in the final audit.
  OWNER="$(basename "$RUN_RECORD")"
  NETWORK_NAME="cpk-pg-controller-$OWNER"
  CONTROLLER_NAME="cpk-pg-controller-$OWNER"
  OWNER_LABEL="org.openj92.cpk.controller-run=$OWNER"
  PROJECT_LABEL='org.openj92.project=control-plane-kit-servers'
  NETWORK_ATTEMPTED=0 CONTROLLER_ATTEMPTED=0
  : > "$RECEIPTS/qualification.log"
  valid_id() {
    [ "${#1}" = 64 ] || return 1
    case "$1" in *[!0-9a-f]*) return 1 ;; esac
  }
  controller_absent() {
    remaining="$(docker ps -aq --no-trunc --filter "id=$CONTROLLER_ID")" || return 1
    [ -z "$remaining" ]
  }
  verify_network() {
    observed="$(docker network inspect "$NETWORK_ID" --format '{{.Id}}|{{.Name}}|{{.Internal}}|{{index .Labels "org.openj92.cpk.controller-run"}}|{{len .Containers}}')" || return 1
    [ "$observed" = "$NETWORK_ID|$NETWORK_NAME|true|$OWNER|0" ]
  }
  cleanup_owned() {
    if [ "$CONTROLLER_ATTEMPTED" = 1 ]; then
      [ -s "$RECEIPTS/controller.id" ] || return 1
      CONTROLLER_ID="$(cat "$RECEIPTS/controller.id")" || return 1
      valid_id "$CONTROLLER_ID" || return 1
      remaining="$(docker ps -aq --no-trunc --filter "id=$CONTROLLER_ID")" || return 1
      if [ -n "$remaining" ]; then
        [ "$remaining" = "$CONTROLLER_ID" ] || return 1
        observed="$(docker container inspect "$CONTROLLER_ID" --format '{{.Id}}|{{.Name}}|{{index .Config.Labels "org.openj92.cpk.controller-run"}}|{{.Image}}')" || return 1
        [ "$observed" = "$CONTROLLER_ID|/$CONTROLLER_NAME|$OWNER|$CONTROLLER" ] || return 1
        docker container rm -f "$CONTROLLER_ID" || return 1
      fi
      controller_absent || return 1
    fi
    if [ "$NETWORK_ATTEMPTED" = 1 ]; then
      [ -s "$RECEIPTS/network.id" ] || return 1
      NETWORK_ID="$(cat "$RECEIPTS/network.id")" || return 1
      valid_id "$NETWORK_ID" || return 1
      verify_network || return 1
      docker network rm "$NETWORK_ID" || return 1
      remaining="$(docker network ls -q --no-trunc --filter "id=$NETWORK_ID")" || return 1
      [ -z "$remaining" ] || return 1
    fi
  }
  finish() {
    result=$?
    trap - 0 INT TERM
    cleanup_ok=0
    cleanup_owned > "$RECEIPTS/cleanup.log" 2>&1 && cleanup_ok=1
    # These exact private fixtures were previously cleaned by test.sh in source
    # mode. Published witness also cleans them; missing files are harmless.
    if [ "$cleanup_ok" = 1 ]; then
      rm -f "$RECEIPTS/fixtures/control.json" "$RECEIPTS/fixtures/password" "$RECEIPTS/fixtures/10-witness.sql" || result=1
      if [ -d "$RECEIPTS/fixtures/wrong-owner-data" ]; then
        rmdir "$RECEIPTS/fixtures/wrong-owner-data" || result=1
      fi
      rmdir "$RECEIPTS/fixtures" || result=1
    else
      result=1
    fi
    printf '%s\n' "$result" > "$RECEIPTS/qualification.exit"
    cat "$RECEIPTS/qualification.log"
    [ "$result" = 0 ] || echo 'PostgreSQL owning invocation failed; private receipts retained' >&2
    exit "$result"
  }
  trap finish 0
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # Refuse adoption even before create; unknown outcomes are retained, never
  # resolved by name-based deletion or a second creation attempt.
  for filter in "label=$OWNER_LABEL" "name=$NETWORK_NAME"; do
    found="$(docker network ls -q --filter "$filter")"
    [ -z "$found" ]
    found="$(docker ps -aq --filter "$filter")"
    [ -z "$found" ]
  done
  NETWORK_ATTEMPTED=1
  docker network create --internal --label "$OWNER_LABEL" --label "$PROJECT_LABEL" "$NETWORK_NAME" > "$RECEIPTS/network.id"
  NETWORK_ID="$(cat "$RECEIPTS/network.id")"
  valid_id "$NETWORK_ID"
  verify_network
  if [ "$MODE" = --postgres-source-image ]; then
    CPK_POSTGRES_ARTIFACT_MODE=source-built
  fi
  export CPK_POSTGRES_ARTIFACT_MODE
  CONTROLLER_ATTEMPTED=1
  docker create --pull never --network "$NETWORK_ID" --read-only --tmpfs /tmp:exec \
    --name "$CONTROLLER_NAME" --cidfile "$RECEIPTS/controller.id" \
    --label "$OWNER_LABEL" --label "$PROJECT_LABEL" \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
    --mount "type=bind,source=$RECEIPTS/fixtures,target=/witness" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONPATH=/source/products/postgres_server/src:/source/products/postgres_server/tests \
    -e "CPK_POSTGRES_TEST_RUN=$RUN" -e "CPK_POSTGRES_HOST_RECORDS=$RECEIPTS/fixtures" \
    -e "CPK_POSTGRES_ARTIFACT_MODE=$CPK_POSTGRES_ARTIFACT_MODE" -e CPK_POSTGRES_IMAGE \
    -e CPK_POSTGRES_SOURCE_REVISION -e CPK_POSTGRES_RECIPE_SHA256 \
    "$CONTROLLER" python /source/products/postgres_server/tests/live_postgres_image.py \
    > "$RECEIPTS/controller-create.log" 2>&1
  CONTROLLER_ID="$(cat "$RECEIPTS/controller.id")"
  valid_id "$CONTROLLER_ID"
  docker start --attach "$CONTROLLER_ID" > "$RECEIPTS/qualification.log" 2>&1
  exit 0
  ;;
 *) echo 'PostgreSQL artifact route is unavailable' >&2; exit 2 ;;
esac
