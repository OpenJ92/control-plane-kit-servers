#!/bin/sh
set -eu

DIGEST="sha256:9edd29c8b62f6413c7acb4009bfa655c065a31a0eac8728ec9d4350122e0a60d"
IMAGE="ghcr.io/openj92/control-plane-kit-servers/http-active-router@$DIGEST"

docker pull "$IMAGE" >/dev/null
HTTP_ACTIVE_ROUTER_IMAGE="$IMAGE" HTTP_ACTIVE_ROUTER_BUILD_IMAGE=0 \
  scripts/http_active_router_image_smoke.sh
