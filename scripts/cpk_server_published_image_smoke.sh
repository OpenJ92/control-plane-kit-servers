#!/bin/sh
set -eu

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:def866baeeda659d61a821a29a07a8ceb780bcb440ab7fe0c63a8fa8989e7c7a}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
