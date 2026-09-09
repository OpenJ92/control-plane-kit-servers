#!/bin/sh
set -eu

IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# Explicit local #163 release only; ordinary/hosted runs do not enter this mode.
# These inputs must be authorized as one concrete source/effect envelope before
# invocation. Supplying variables is not itself permission for external effects.
CHILD_RELEASE="${CPK_CHILD_ACCEPTANCE_RELEASE:-}"
if [ -n "$CHILD_RELEASE" ]; then
  : "${CPK_CHILD_ACCEPTANCE_DIGEST:?exact approved release digest required}"
  : "${CPK_CHILD_ACCEPTANCE_RUN:?exact approved parent installation required}"
  : "${CPK_CHILD_CLOUDFLARE_TOKEN_FILE:?approved private raw token input required}"
  : "${CPK_PARENT_TUNNEL_TOKEN_FILE:?approved retained ingress token input required}"
  [ -f "$CHILD_RELEASE" ] && [ -f "$CPK_CHILD_CLOUDFLARE_TOKEN_FILE" ] && [ -f "$CPK_PARENT_TUNNEL_TOKEN_FILE" ]
  CHILD_SOURCE_HEAD="$(git -C "$ROOT" rev-parse HEAD)"
  [ -z "$(git -C "$ROOT" status --porcelain)" ] || { echo 'child acceptance requires reviewed clean source' >&2; exit 1; }
fi

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
# Real external-root launcher: canonical products, isolated test workspace, no
# provider/DNS exposure or retained acceptance installation.
(
  RECORDS="$(mktemp -d)"
  RUN="root-$(date +%s)-$$"
  if [ -n "$CHILD_RELEASE" ]; then
    RUN="$CPK_CHILD_ACCEPTANCE_RUN"
    mkdir -m 700 "$RECORDS/inputs"
    cp "$CHILD_RELEASE" "$RECORDS/release.json"
    cp "$CPK_CHILD_CLOUDFLARE_TOKEN_FILE" "$RECORDS/inputs/cloudflare-token"
    cp "$CPK_PARENT_TUNNEL_TOKEN_FILE" "$RECORDS/inputs/parent-tunnel-token"
    chmod 400 "$RECORDS/release.json" "$RECORDS/inputs/cloudflare-token" "$RECORDS/inputs/parent-tunnel-token"
  fi
  DRIVER_TAG="control-plane-kit-bootstrap-test:$RUN"
  DRIVER=""
  child_fixture() {
    phase="$1"
    case "$phase" in
      seed) set -- --network "container:$PARENT_CONTAINER_ID" ;;
      preflight|observe|finish) set -- --network "container:$PARENT_CONTAINER_ID" \
        --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock ;;
      *) set -- --network none ;;
    esac
    docker run --rm "$@" \
      --label "org.openj92.cpk.test-run=$RUN" \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e "CPK_CHILD_SOURCE_HEAD=$CHILD_SOURCE_HEAD" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_child_fixture.py "$phase" "$RUN" "$CPK_CHILD_ACCEPTANCE_DIGEST"
  }
  child_api() {
    docker run --rm --network "container:$PARENT_CONTAINER_ID" \
      --label "org.openj92.cpk.test-run=$RUN" \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_child_api.py "$1"
  }
  cleanup_root_bootstrap() {
    [ -n "$DRIVER" ] || return 0
    if [ -n "$CHILD_RELEASE" ]; then
      # Failed/uncertain child work preserves its root custody and process state.
      # Never substitute root teardown for successful public child convergence.
      child_fixture require-complete || return 1
    fi
    docker run --rm --network none \
      --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_root_bootstrap.py cleanup "$RUN" || return 1
    [ "$(docker image inspect --format '{{.Id}}' "$DRIVER_TAG")" = "$DRIVER" ] || return 1
    [ "$(docker image inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$DRIVER")" = "$RUN" ] || return 1
    docker image rm "$DRIVER_TAG" >/dev/null
  }
  trap 'result=$?; trap - 0; cleanup_root_bootstrap || { echo "root bootstrap cleanup HOLD; records=$RECORDS" >&2; result=1; }; exit "$result"' 0
  [ -z "$(docker image ls -q --filter "reference=$DRIVER_TAG")" ]
  docker build -f products/cpk_server/Dockerfile.bootstrap --build-arg "CPK_IMAGE=$CPK_IMAGE" \
    --label "org.openj92.cpk.test-run=$RUN" --iidfile "$RECORDS/driver" -t "$DRIVER_TAG" .
  DRIVER="$(cat "$RECORDS/driver")"
  if [ -n "$CHILD_RELEASE" ]; then
    # Plan input remains private and owned by the invoking host user, as required
    # by the existing bootstrap launcher. Later profiles use controller ownership.
    docker run --rm --network none --user "$(id -u):$(id -g)" \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e "CPK_CHILD_SOURCE_HEAD=$CHILD_SOURCE_HEAD" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_child_fixture.py prepare "$RUN" "$CPK_CHILD_ACCEPTANCE_DIGEST"
  else
    docker run --rm --network none --user "$(id -u):$(id -g)" \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_root_bootstrap.py prepare "$RUN"
  fi
  sh bootstrap.sh plan "$DRIVER" "$RECORDS/input.json" > "$RECORDS/plan.json"
  DIGEST="$(docker run --rm --network none \
    --mount "type=bind,source=$ROOT,target=/source,readonly" \
    --mount "type=bind,source=$RECORDS,target=/witness,readonly" \
    -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
    python /source/products/cpk_server/tests/live_root_bootstrap.py digest "$RUN")"
  sh bootstrap.sh apply "$DRIVER" "$RECORDS/plan.json" "$DIGEST" "$RECORDS/material/index.json" "$RECORDS/state" > "$RECORDS/result.json"
  docker run --rm --network none \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --mount "type=bind,source=$ROOT,target=/source,readonly" \
    --mount "type=bind,source=$RECORDS,target=/witness" \
    -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
    python /source/products/cpk_server/tests/live_root_bootstrap.py check "$RUN"
  if sh bootstrap.sh apply "$DRIVER" "$RECORDS/plan.json" "$DIGEST" "$RECORDS/material/index.json" "$RECORDS/state" > "$RECORDS/reapply.json"; then
    echo 'root bootstrap unexpectedly redispatched completed acquisition' >&2
    exit 1
  fi
  docker run --rm --network none \
    --mount "type=bind,source=$ROOT,target=/source,readonly" \
    --mount "type=bind,source=$RECORDS,target=/witness,readonly" \
    -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
    python /source/products/cpk_server/tests/live_root_bootstrap.py unchanged "$RUN"
  if [ -n "$CHILD_RELEASE" ]; then
    PARENT_CONTAINER_ID="$(child_fixture parent-id)"
    child_fixture preflight
    child_fixture seed
    child_api deploy
    child_fixture observe
    docker run --rm --network none \
      --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$RECORDS,target=/witness" \
      -e PYTHONPATH=/source:/app/products/cpk_server/src "$DRIVER" \
      python /source/products/cpk_server/tests/live_root_bootstrap.py restart-for-child "$RUN"
    child_api reconnect
    child_api teardown
    child_fixture finish
  fi
)
sh scripts/docker_residue_audit.sh
