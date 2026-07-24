#!/bin/sh
set -eu

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:12e9eb53d1b61d662d10f007dccec91e9858e5a6bc015b96a703add341421899}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
