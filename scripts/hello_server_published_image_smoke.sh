#!/bin/sh
set -eu

IMAGE="ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:0b5d62c2706bdfc5b53b67c7e0a72e36b8af7d13f8b2abf26eaa6e6eb7dda5f0"

docker pull "$IMAGE"

HELLO_SERVER_IMAGE="$IMAGE" \
HELLO_SERVER_BUILD_IMAGE=0 \
  scripts/hello_server_image_smoke.sh
