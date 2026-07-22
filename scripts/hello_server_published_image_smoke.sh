#!/bin/sh
set -eu

IMAGE="ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:0000000000000000000000000000000000000000000000000000000000000000"

docker pull "$IMAGE"

HELLO_SERVER_IMAGE="$IMAGE" \
HELLO_SERVER_BUILD_IMAGE=0 \
  scripts/hello_server_image_smoke.sh
