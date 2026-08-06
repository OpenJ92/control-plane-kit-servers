#!/bin/sh
set -eu

SERVERS_REPO="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
COORDINATES_FILE="$SERVERS_REPO/coordinates/server-products.json"
CONTROLLER_IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:published-1259}"

if [ "${CPK_GATEWAY_PUBLISHED_LIVE_ACCEPTANCE:-}" != "1" ]; then
  echo "set CPK_GATEWAY_PUBLISHED_LIVE_ACCEPTANCE=1 to run published gateway acceptance" >&2
  exit 1
fi
if [ ! -r "$COORDINATES_FILE" ]; then
  echo "server product coordinates are unavailable" >&2
  exit 1
fi

# The source image is orchestration only. Every process under test is selected
# below from the checked coordinate manifest and local product builds stay off.
docker build -f "$SERVERS_REPO/Dockerfile.test" -t "$CONTROLLER_IMAGE" "$SERVERS_REPO"
docker run --rm \
  "$CONTROLLER_IMAGE" \
  python scripts/apply_coordinates.py --check

coordinate_image() {
  docker run --rm \
    "$CONTROLLER_IMAGE" \
    python scripts/product_image_coordinate.py "$1"
}

product_source_commit() {
  docker run --rm \
    "$CONTROLLER_IMAGE" \
    python scripts/product_image_coordinate.py --source-commit "$1"
}

require_digest() {
  name="$1"
  image="$2"
  case "$image" in
    *@sha256:*) ;;
    *)
      echo "$name must use an immutable sha256 digest" >&2
      exit 1
      ;;
  esac
}

CPK_IMAGE="$(coordinate_image cpk-server)"
SECRETS_IMAGE="$(coordinate_image secrets-server)"
GATEWAY_IMAGE="$(coordinate_image cpk-local-gateway)"
CLOUDFLARED_IMAGE="$(coordinate_image cloudflared-connector)"
POSTGRES_IMAGE="$(coordinate_image postgres-server)"
HELLO_IMAGE="$(coordinate_image hello-server)"
GATEWAY_SOURCE_COMMIT="$(product_source_commit cpk-local-gateway)"

require_digest cpk-server "$CPK_IMAGE"
require_digest secrets-server "$SECRETS_IMAGE"
require_digest cpk-local-gateway "$GATEWAY_IMAGE"
require_digest cloudflared-connector "$CLOUDFLARED_IMAGE"
require_digest postgres-server "$POSTGRES_IMAGE"
require_digest hello-server "$HELLO_IMAGE"

if [ "${CPK_GATEWAY_PUBLISHED_LIVE_PLAN_ONLY:-}" = "1" ]; then
  printf '%s\n' \
    "cpk-server=$CPK_IMAGE" \
    "secrets-server=$SECRETS_IMAGE" \
    "cpk-local-gateway=$GATEWAY_IMAGE" \
    "cloudflared-connector=$CLOUDFLARED_IMAGE" \
    "postgres-server=$POSTGRES_IMAGE" \
    "hello-server=$HELLO_IMAGE" \
    "cpk-local-gateway-source=$GATEWAY_SOURCE_COMMIT"
  exit 0
fi

for image in \
  "$CPK_IMAGE" \
  "$SECRETS_IMAGE" \
  "$GATEWAY_IMAGE" \
  "$CLOUDFLARED_IMAGE" \
  "$POSTGRES_IMAGE" \
  "$HELLO_IMAGE"
do
  docker pull "$image" >/dev/null
done

export CPK_SERVERS_TEST_IMAGE="$CONTROLLER_IMAGE"
export CPK_SECRETS_TEST_IMAGE="$SECRETS_IMAGE"
export CPK_LIVE_POSTGRES_IMAGE="$POSTGRES_IMAGE"
export CPK_CLOUDFLARE_CUSTODY_SERVER_IMAGE="$CPK_IMAGE"
export CPK_CLOUDFLARE_CUSTODY_BUILD_IMAGES=0
export CPK_CLOUDFLARE_CUSTODY_SCENARIO=gateway-key-rotation-overlay
export CPK_SOURCE_LIVE_GATEWAY_IMAGE="$GATEWAY_IMAGE"
export CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT="$GATEWAY_SOURCE_COMMIT"

sh "$SERVERS_REPO/scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh"
sh "$SERVERS_REPO/scripts/docker_residue_audit.sh"

echo "cpk-server published gateway private/public acceptance passed"
