#!/bin/sh
set -eu

PRODUCT_ID="${1:-}"
TAG="${2:-extract-f}"
OWNER="${GHCR_OWNER:-openj92}"
PACKAGE="${GHCR_PACKAGE:-control-plane-kit-servers}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"

cd "$ROOT"

case "$PRODUCT_ID" in
  cpk-server)
    DOCKERFILE="products/cpk_server/Dockerfile"
    IMAGE_NAME="cpk-server"
    ;;
  hello-server)
    DOCKERFILE="products/hello_server/Dockerfile"
    IMAGE_NAME="hello-server"
    ;;
  http-active-router)
    DOCKERFILE="products/http_active_router/Dockerfile"
    IMAGE_NAME="http-active-router"
    ;;
  http-multiplexer)
    DOCKERFILE="products/http_multiplexer/Dockerfile"
    IMAGE_NAME="http-multiplexer"
    ;;
  cpk-local-gateway)
    DOCKERFILE="products/cpk_local_gateway/Dockerfile"
    IMAGE_NAME="cpk-local-gateway"
    ;;
  cloudflared-connector)
    DOCKERFILE="products/cloudflared_connector/Dockerfile"
    IMAGE_NAME="cloudflared-connector"
    ;;
  secrets-server)
    DOCKERFILE="products/secrets_server/Dockerfile"
    IMAGE_NAME="secrets-server"
    ;;
  *)
    echo "unsupported product id: $PRODUCT_ID" >&2
    exit 2
    ;;
esac

IMAGE="ghcr.io/$OWNER/$PACKAGE/$IMAGE_NAME:$TAG"

docker run --rm \
  -v "$ROOT:/source:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /source && PYTHONPATH=/source/src python scripts/apply_coordinates.py --check'

docker build -f "$DOCKERFILE" -t "$IMAGE" .
docker push "$IMAGE"

docker image inspect "$IMAGE" --format "{{index .RepoDigests 0}}"
echo "Update coordinates/server-products.json with the verified published digest; regenerate coordinates in Docker and validate with ./test.sh." >&2
