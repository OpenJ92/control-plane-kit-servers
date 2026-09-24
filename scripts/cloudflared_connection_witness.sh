#!/bin/sh
# Called only by the owning test.sh. Exact source image, local synthetic data.
set -eu

RECORDS="$(mktemp -d)"
RUN="cpk-connector-$(basename "$RECORDS")"
TAG="control-plane-kit-cloudflared-witness:$RUN"

cleanup() {
  failed=0
  if [ -s "$RECORDS/container" ]; then
    identity="$(cat "$RECORDS/container")" || return 1
    observed="$(docker container ls -aq --no-trunc --filter "id=$identity")" || return 1
    if [ -n "$observed" ]; then
      [ "$observed" = "$identity" ] || return 1
      owner="$(docker inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$identity")" || return 1
      [ "$owner" = "$RUN" ] || return 1
      docker rm -f "$identity" >/dev/null || failed=1
    fi
    [ -z "$(docker container ls -aq --no-trunc --filter "id=$identity")" ] || failed=1
  fi
  observed="$(docker image ls -q --no-trunc --filter "reference=$TAG")" || return 1
  if [ -n "$observed" ]; then
    if [ -n "${IMAGE_ID:-}" ]; then
      [ "$observed" = "$IMAGE_ID" ] || return 1
    fi
    owner="$(docker image inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$observed")" || return 1
    [ "$owner" = "$RUN" ] || return 1
    [ "$(docker image inspect --format '{{.Id}}' "$TAG")" = "$observed" ] || return 1
    docker image rm "$TAG" >/dev/null || failed=1
    [ -z "$(docker image ls -q --filter "reference=$TAG")" ] || failed=1
  fi
  if [ "$failed" = 0 ]; then
    rm -f "$RECORDS/container" "$RECORDS/config.json"
    rmdir "$RECORDS"
  fi
  return "$failed"
}

[ -z "$(docker container ls -aq --filter "name=^/$RUN$")" ]
[ -z "$(docker image ls -q --filter "reference=$TAG")" ]
trap 'result=$?; trap - EXIT INT TERM; cleanup || result=1; exit "$result"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker build -f products/cloudflared_connector/Dockerfile \
  --label "org.openj92.cpk.test-run=$RUN" -t "$TAG" .
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$TAG")"
docker image inspect --format '{{json .Config}}' "$IMAGE_ID" > "$RECORDS/config.json"
chmod 644 "$RECORDS/config.json"
# Scheduled checks are disabled in this fixture container so only its controlled
# test client consumes the local one-response server. The image's real scheduled
# command/bounds are inspected separately. This is not live tunnel evidence.
docker run --rm --name "$RUN" --cidfile "$RECORDS/container" \
  --network none --no-healthcheck \
  --label org.openj92.project=control-plane-kit-servers \
  --label "org.openj92.cpk.test-run=$RUN" \
  --mount "type=bind,source=$PWD/products/cloudflared_connector/tests,target=/witness,readonly" \
  --mount "type=bind,source=$RECORDS/config.json,target=/witness-config.json,readonly" \
  --entrypoint python "$IMAGE_ID" /witness/packaged_connection_witness.py

cleanup
trap - EXIT INT TERM
