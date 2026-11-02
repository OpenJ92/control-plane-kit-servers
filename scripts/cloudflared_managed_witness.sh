#!/bin/sh
# Owned test.sh stage; no standalone release or alternate test harness.
set -eu
RESULT_VOLUME_SCRIPT="$(dirname -- "$0")/cloudflared_result_volume.sh"

# Explicit selected-image mode borrows the image and retains its evidence.
OBSERVATION=''
CONTROLLER_MODE=controller
if [ "$#" -gt 0 ]; then
  case "$1" in
    --managed-connector-candidate)
      exec sh "$(dirname -- "$0")/cloudflared_release_shell.sh" "$@" ;;
    --contents-only)
      [ "$#" = 2 ] || exit 2
      OBSERVATION="$2"
      [ -f "$OBSERVATION/controller.json" ] && [ -f "$OBSERVATION/source.commit" ] || exit 2
      CONTROLLER_MODE=contents-controller ;;
    *) exit 2 ;;
  esac
fi

RECORDS="$(mktemp -d)"
RUN="cpk-managed-$(basename "$RECORDS")"
TAG="control-plane-kit-cloudflared-managed:$RUN"
IMAGE_ID=""
VOLUME_ATTEMPTED=0

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
  if [ "$VOLUME_ATTEMPTED" = 1 ]; then
    sh "$RESULT_VOLUME_SCRIPT" remove "$RUN" "$RECORDS" || failed=1
  fi
  if [ -n "$IMAGE_ID" ]; then
    observed="$(docker image inspect --format '{{.Id}}' "$TAG")" || return 1
    [ "$observed" = "$IMAGE_ID" ] || return 1
    owner="$(docker image inspect --format '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$IMAGE_ID")" || return 1
    [ "$owner" = "$RUN" ] || return 1
    docker image rm "$TAG" >/dev/null || failed=1
    observed="$(docker image ls -q --filter "reference=$TAG")" || return 1
    [ -z "$observed" ] || failed=1
  else
    # An interrupted build may leave a tag before its image ID was recorded.
    # Preserve that uncertain image; do not certify cleanup or delete by name.
    observed="$(docker image ls -q --filter "reference=$TAG")" || return 1
    [ -z "$observed" ] || return 1
  fi
  if [ "$failed" = 0 ]; then
    rm -f "$RECORDS/result-volume.json" "$RECORDS/result-volume.empty.json" \
      "$RECORDS/containers.json" "$RECORDS/image" || return 1
    rmdir "$RECORDS" || return 1
  fi
  return "$failed"
}

[ -z "$(docker container ls -aq --filter "label=org.openj92.cpk.test-run=$RUN")" ]
[ -z "$(docker image ls -q --filter "reference=$TAG")" ]
finish() {
  result=$?
  trap - EXIT INT TERM
  cleanup_outcome=verified
  if ! cleanup; then cleanup_outcome=incomplete; result=1; fi
  if [ -n "$OBSERVATION" ]; then
    outcome=failed
    if [ "$result" = 0 ]; then outcome=contents_observed; fi
    printf '{"stage":"managed_cloudflared_contents_observation","outcome":"%s","cleanup":"%s","exit_code":%s}\n' \
      "$outcome" "$cleanup_outcome" "$result" > "$OBSERVATION/result.json" || result=1
  elif [ "$result" = 0 ]; then
    echo 'managed cloudflared package stage passed with owned container/image/fixture cleanup; live qualification pending'
  fi
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker build -f products/cloudflared_connector/Dockerfile.managed \
  --label "org.openj92.cpk.test-run=$RUN" --iidfile "$RECORDS/image" -t "$TAG" .
IMAGE_ID="$(cat "$RECORDS/image")"
if [ -n "$OBSERVATION" ]; then
  printf '%s\n' "$RUN" > "$OBSERVATION/run"
  printf '%s\n' "$IMAGE_ID" > "$OBSERVATION/fixture-image.id"
fi
VOLUME_ATTEMPTED=1
sh "$RESULT_VOLUME_SCRIPT" acquire "$RUN" "$RECORDS"
if [ -n "$OBSERVATION" ]; then
  cp "$RECORDS/result-volume.json" "$OBSERVATION/result-volume.json"
fi
docker run --rm --name "$RUN-controller" --network none \
  --label "org.openj92.cpk.test-run=$RUN" \
  --label org.openj92.project=control-plane-kit-servers \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount "type=bind,source=$PWD,target=/source,readonly" \
  --mount "type=bind,source=$RECORDS,target=/witness" \
  --mount "type=volume,source=$RUN-results,target=/witness-results,volume-nocopy" \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -e PYTHONPATH=/source/products/cloudflared_connector/tests \
  -e "CPK_MANAGED_TEST_RUN=$RUN" \
  -e "CPK_MANAGED_IMAGE=$IMAGE_ID" \
  -e "CPK_MANAGED_RESULT_VOLUME=$RUN-results" \
  -e "CPK_MANAGED_HOST_TESTS=$PWD/products/cloudflared_connector/tests" \
  "${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}" \
  python /source/products/cloudflared_connector/tests/packaged_managed_witness.py "$CONTROLLER_MODE"

exit 0  # One EXIT cleanup attempt for both normal and observation paths.
