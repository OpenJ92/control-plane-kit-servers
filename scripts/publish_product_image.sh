#!/bin/sh
set -eu

PRODUCT_ID="${1:-}"
TAG="${2:-extract-f}"
OWNER="${GHCR_OWNER:-openj92}"
PACKAGE="${GHCR_PACKAGE:-control-plane-kit-servers}"

if [ "$PRODUCT_ID" != "cpk-server" ]; then
  echo "unsupported product id: $PRODUCT_ID" >&2
  exit 2
fi

DOCKERFILE="products/cpk_server/Dockerfile"
IMAGE="ghcr.io/$OWNER/$PACKAGE/cpk-server:$TAG"

docker build -f "$DOCKERFILE" -t "$IMAGE" .
docker push "$IMAGE"

docker image inspect "$IMAGE" --format "{{index .RepoDigests 0}}"
