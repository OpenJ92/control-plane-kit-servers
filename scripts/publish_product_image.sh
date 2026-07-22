#!/bin/sh
set -eu

PRODUCT_ID="${1:-}"
TAG="${2:-extract-f}"
OWNER="${GHCR_OWNER:-openj92}"
PACKAGE="${GHCR_PACKAGE:-control-plane-kit-servers}"

case "$PRODUCT_ID" in
  cpk-server)
    DOCKERFILE="products/cpk_server/Dockerfile"
    IMAGE_NAME="cpk-server"
    ;;
  hello-server)
    DOCKERFILE="products/hello_server/Dockerfile"
    IMAGE_NAME="hello-server"
    ;;
  *)
    echo "unsupported product id: $PRODUCT_ID" >&2
    exit 2
    ;;
esac

IMAGE="ghcr.io/$OWNER/$PACKAGE/$IMAGE_NAME:$TAG"

docker build -f "$DOCKERFILE" -t "$IMAGE" .
docker push "$IMAGE"

docker image inspect "$IMAGE" --format "{{index .RepoDigests 0}}"
