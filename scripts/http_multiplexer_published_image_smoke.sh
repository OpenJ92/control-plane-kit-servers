#!/bin/sh
set -eu

DIGEST="sha256:2b6466d87c7642691c4ce2ee52022450d7b7cf1055f1f25a1449adbb5c8131ec"
IMAGE="ghcr.io/openj92/control-plane-kit-servers/http-multiplexer@$DIGEST"

docker pull "$IMAGE" >/dev/null
HTTP_MULTIPLEXER_IMAGE="$IMAGE" HTTP_MULTIPLEXER_BUILD_IMAGE=0 \
  scripts/http_multiplexer_image_smoke.sh
