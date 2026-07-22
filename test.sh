#!/bin/sh
set -eu

IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"

docker build -f Dockerfile.test -t "$IMAGE" .
docker run --rm "$IMAGE"
sh scripts/cpk_server_image_smoke.sh
sh scripts/docker_residue_audit.sh
