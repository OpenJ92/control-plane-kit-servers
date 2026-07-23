#!/bin/sh
set -eu

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:c3d0304ec4676c4e3d3cd2173594834c807b6ed6b37de83d164bd14ec6298e93}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
