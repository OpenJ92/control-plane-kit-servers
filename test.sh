#!/bin/sh
set -eu

IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

cd "$ROOT"

docker run --rm \
  -v "$ROOT:/source:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /source && PYTHONPATH=/source/src python scripts/apply_coordinates.py --check'

docker run --rm \
  -v "$ROOT:/source:ro" \
  -v "$ROOT/test_support:/test-support:ro" \
  -e CPK_PACKAGE_ROOT=/source \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /test-support && python -m unittest discover -s tests -v'

docker run --rm \
  -v "$ROOT:/source:ro" \
  -v "$ROOT/test_support:/test-support:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  python /test-support/package_integrity.py \
    --package-root /source \
    --source-root src \
    --source-root products \
    --test-root tests \
    --test-root products \
    --gate-file test.sh

docker build -f Dockerfile.test -t "$IMAGE" .
docker run --rm "$IMAGE"
docker run --rm "$IMAGE" \
  sh -c 'cd /tmp && python -c "import control_plane_kit_servers; print(\"control-plane-kit-servers import ok\")"'

# Source-built Secrets and CPK file witnesses. Only this bounded controller receives
# local daemon authority; the ordinary package suite above remains socket-free.
(
  RECORDS="$(mktemp -d)"
  RUN="cpk-numeric-$(basename "$RECORDS")"
  TAG="control-plane-kit-secrets-numeric:$RUN"
  CPK_TAG="control-plane-kit-cpk-numeric:$RUN"
  cleanup_numeric_bootstrap() {
    failed=0
    if [ -s "$RECORDS/controller" ]; then
      identity="$(cat "$RECORDS/controller")" || return 1
      observed="$(docker container ls -aq --no-trunc --filter "id=$identity")" || return 1
      if [ -n "$observed" ]; then
        [ "$observed" = "$identity" ] || return 1
        owner="$(docker inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$identity")" || return 1
        [ "$owner" = "$RUN" ] || return 1
        docker rm -f "$identity" >/dev/null || failed=1
        observed="$(docker container ls -aq --no-trunc --filter "id=$identity")" || return 1
        [ -z "$observed" ] || failed=1
      fi
    fi
    if [ -s "$RECORDS/network" ]; then
      identity="$(cat "$RECORDS/network")" || return 1
      observed="$(docker network ls -q --no-trunc --filter "id=$identity")" || return 1
      if [ -n "$observed" ]; then
        [ "$observed" = "$identity" ] || return 1
        owner="$(docker network inspect --format '{{index .Labels "org.openj92.cpk.test-run"}}' "$identity")" || return 1
        [ "$owner" = "$RUN" ] || return 1
        docker network rm "$identity" >/dev/null || failed=1
        observed="$(docker network ls -q --no-trunc --filter "id=$identity")" || return 1
        [ -z "$observed" ] || failed=1
      fi
    fi
    for record in image cpk-image; do
      if [ -s "$RECORDS/$record" ]; then
        case "$record" in image) image_tag="$TAG" ;; cpk-image) image_tag="$CPK_TAG" ;; esac
        identity="$(cat "$RECORDS/$record")" || return 1
        observed="$(docker image inspect --format '{{.Id}}' "$image_tag")" || return 1
        owner="$(docker image inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$identity")" || return 1
        [ "$observed" = "$identity" ] && [ "$owner" = "$RUN" ] || return 1
        docker image rm "$image_tag" >/dev/null || failed=1
        observed="$(docker image ls -q --no-trunc --filter "reference=$image_tag")" || return 1
        [ -z "$observed" ] || failed=1
      fi
    done
    [ "$failed" = 0 ] || return 1
    rm -f "$RECORDS/controller" "$RECORDS/network" "$RECORDS/image" "$RECORDS/cpk-image"
    rmdir "$RECORDS"
  }
  trap 'result=$?; trap - 0; cleanup_numeric_bootstrap || { echo "numeric bootstrap cleanup incomplete; records=$RECORDS" >&2; result=1; }; exit "$result"' 0
  if [ -n "${DOCKER_TLS_VERIFY:-}" ] || [ -n "${DOCKER_CERT_PATH:-}" ]; then
    echo 'numeric bootstrap witness requires a local Unix Docker context' >&2
    exit 1
  fi
  ENDPOINT="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
  case "$ENDPOINT" in
    unix:///*) ;;
    *) echo 'numeric bootstrap witness rejects remote or ambiguous Docker context' >&2; exit 1 ;;
  esac
  ENGINE_ID="$(docker info --format '{{.ID}}')"
  [ -n "$ENGINE_ID" ]
  EXISTING="$(docker container ls -aq --no-trunc --filter "name=^/$RUN$")"
  [ -z "$EXISTING" ] || { echo 'numeric bootstrap controller already exists' >&2; exit 1; }
  EXISTING="$(docker network ls -q --filter "name=^$RUN$")"
  [ -z "$EXISTING" ] || { echo 'numeric bootstrap network already exists' >&2; exit 1; }
  EXISTING="$(docker image ls -q --no-trunc --filter "reference=$TAG")"
  [ -z "$EXISTING" ] || { echo 'numeric bootstrap image tag already exists' >&2; exit 1; }
  EXISTING="$(docker image ls -q --no-trunc --filter "reference=$CPK_TAG")"
  [ -z "$EXISTING" ] || { echo 'numeric CPK image tag already exists' >&2; exit 1; }
  docker build -f products/secrets_server/Dockerfile \
    --label "org.openj92.cpk.test-run=$RUN" \
    --iidfile "$RECORDS/image" -t "$TAG" .
  PRODUCT_IMAGE_ID="$(cat "$RECORDS/image")"
  docker build -f products/cpk_server/Dockerfile \
    --label "org.openj92.cpk.test-run=$RUN" \
    --iidfile "$RECORDS/cpk-image" -t "$CPK_TAG" .
  CPK_PRODUCT_IMAGE_ID="$(cat "$RECORDS/cpk-image")"
  HELPER_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
  docker network create --internal \
    --label "org.openj92.cpk.test-run=$RUN" \
    --label org.openj92.project=control-plane-kit-servers "$RUN" > "$RECORDS/network"
  NETWORK_ID="$(cat "$RECORDS/network")"
  docker run --name "$RUN" --cidfile "$RECORDS/controller" \
    --label "org.openj92.cpk.test-run=$RUN" \
    --label org.openj92.project=control-plane-kit-servers \
    --network "$NETWORK_ID" \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    -e DOCKER_HOST=unix:///var/run/docker.sock \
    -e PYTHONPATH=/app \
    -e "CPK_SECRET_TEST_RUN=$RUN" \
    -e "CPK_SECRET_PRODUCT_IMAGE=$PRODUCT_IMAGE_ID" \
    -e "CPK_NUMERIC_PRODUCT_IMAGE=$CPK_PRODUCT_IMAGE_ID" \
    -e "CPK_SECRET_HELPER_IMAGE=$HELPER_IMAGE_ID" \
    -e "CPK_SECRET_ENGINE_ID=$ENGINE_ID" \
    -e "CPK_SECRET_NETWORK=$NETWORK_ID" \
    "$HELPER_IMAGE_ID" python products/secrets_server/tests/live_numeric_bootstrap.py
)

SECRETS_IMAGE="$(docker run --rm "$IMAGE" python scripts/product_image_coordinate.py secrets-server)"
CPK_SECRETS_BUILD_IMAGE=0 \
CPK_SECRETS_BUILD_CONTROLLER=0 \
CPK_SERVERS_TEST_IMAGE="$IMAGE" \
CPK_SECRETS_IMAGE="$SECRETS_IMAGE" \
  sh scripts/secrets_server_image_smoke.sh
CPK_SERVER_BUILD_IMAGE=1 sh scripts/cpk_server_image_smoke.sh
CPK_IMAGE="$(docker run --rm "$IMAGE" python scripts/product_image_coordinate.py cpk-server)"
CPK_SERVER_IMAGE="$CPK_IMAGE" sh scripts/cpk_server_published_image_smoke.sh
sh scripts/docker_residue_audit.sh
