#!/bin/sh
set -eu

DIGEST="sha256:0000000000000000000000000000000000000000000000000000000000000000"
IMAGE="ghcr.io/openj92/control-plane-kit-servers/http-multiplexer@$DIGEST"

docker pull "$IMAGE" >/dev/null
HTTP_MULTIPLEXER_IMAGE="$IMAGE" HTTP_MULTIPLEXER_BUILD_IMAGE=0 \
  scripts/http_multiplexer_image_smoke.sh
