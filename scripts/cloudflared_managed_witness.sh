#!/bin/sh
# Owned test.sh stage; no standalone release or alternate test harness.
set -eu

RECORDS="$(mktemp -d)"
RUN="cpk-managed-$(basename "$RECORDS")"
TAG="control-plane-kit-cloudflared-managed:$RUN"
IMAGE_ID=""

cleanup() {
  failed=0
  # This unique ownership label was absent before any resource was created.
  identities="$(docker container ls -aq --no-trunc --filter "label=org.openj92.cpk.test-run=$RUN")" || return 1
  for identity in $identities; do
    owner="$(docker inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$identity")" || return 1
    [ "$owner" = "$RUN" ] || return 1
    docker rm -f "$identity" >/dev/null || failed=1
    observed="$(docker container ls -aq --no-trunc --filter "id=$identity")" || return 1
    [ -z "$observed" ] || failed=1
  done
  if [ -n "$IMAGE_ID" ]; then
    observed="$(docker image inspect --format '{{.Id}}' "$TAG")" || return 1
    [ "$observed" = "$IMAGE_ID" ] || return 1
    owner="$(docker image inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$IMAGE_ID")" || return 1
    [ "$owner" = "$RUN" ] || return 1
    docker image rm "$TAG" >/dev/null || failed=1
    observed="$(docker image ls -q --filter "reference=$TAG")" || return 1
    [ -z "$observed" ] || failed=1
  fi
  if [ "$failed" = 0 ]; then
    if [ -d "$RECORDS/results" ]; then
      rm -f "$RECORDS/results"/cpk-witness-*.json
      rmdir "$RECORDS/results" || return 1
    fi
    rm -f "$RECORDS/containers.json" "$RECORDS/image"
    rmdir "$RECORDS"
  fi
  return "$failed"
}

[ -z "$(docker container ls -aq --filter "label=org.openj92.cpk.test-run=$RUN")" ]
[ -z "$(docker image ls -q --filter "reference=$TAG")" ]
trap 'result=$?; trap - EXIT INT TERM; cleanup || result=1; exit "$result"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker build -f products/cloudflared_connector/Dockerfile.managed \
  --label "org.openj92.cpk.test-run=$RUN" --iidfile "$RECORDS/image" -t "$TAG" .
IMAGE_ID="$(cat "$RECORDS/image")"
docker run --rm --name "$RUN-controller" --network none \
  --label "org.openj92.cpk.test-run=$RUN" \
  --label org.openj92.project=control-plane-kit-servers \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount "type=bind,source=$PWD,target=/source,readonly" \
  --mount "type=bind,source=$RECORDS,target=/witness" \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -e PYTHONPATH=/source/products/cloudflared_connector/tests \
  -e "CPK_MANAGED_TEST_RUN=$RUN" \
  -e "CPK_MANAGED_IMAGE=$IMAGE_ID" \
  -e "CPK_MANAGED_HOST_RECORDS=$RECORDS" \
  -e "CPK_MANAGED_HOST_TESTS=$PWD/products/cloudflared_connector/tests" \
  "${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}" \
  python /source/products/cloudflared_connector/tests/packaged_managed_witness.py controller

cleanup
trap - EXIT INT TERM
echo 'managed cloudflared package stage passed with owned container/image/fixture cleanup; live qualification pending'
