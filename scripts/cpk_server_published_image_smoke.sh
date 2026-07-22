#!/bin/sh
set -eu

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:d796b9df23098d87b03d89da5d125102b46482c0562b84179b8cde0d15fc0fb1}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
