#!/bin/sh
set -eu

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:dacf70bb1dac886d24a7abdf101cf9a95bfd5ed54cef036a59fce810c7b76d9e}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
