#!/bin/sh
set -eu

DIGEST="sha256:0000000000000000000000000000000000000000000000000000000000000000"
IMAGE="ghcr.io/openj92/control-plane-kit-servers/http-active-router@$DIGEST"

docker pull "$IMAGE" >/dev/null
HTTP_ACTIVE_ROUTER_IMAGE="$IMAGE" HTTP_ACTIVE_ROUTER_BUILD_IMAGE=0 \
  scripts/http_active_router_image_smoke.sh
