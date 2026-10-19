#!/bin/bash
set -euo pipefail

ROOT="${SOURCE_ROOT:?}"
DIAGNOSTIC_SCRIPT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/$(basename -- "$0")"
SUMMARY="${RUNNER_TEMP:?}/cpk-postgres-recovery-summary.jsonl"
HELPER_TAG="cpk-postgres-recovery-helper:${GITHUB_RUN_ID:?}"
HELPER_META_NAME="cpk-postgres-recovery-helper-meta-${GITHUB_RUN_ID}"
HELPER_ID=""
CURRENT_RUN=""
CURRENT_RECORDS=""
COMMAND_PID=""
ATTEMPT_TIMEOUT=480
BUILD_TIMEOUT=480
HELPER_BASE='python:3.12-slim'
POSTGRES_BASE='postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777'

: > "$SUMMARY"
cd "$ROOT"

record() {
  jq -cn "$@" >> "$SUMMARY"
}

terminal_failure() {
  local class="$1" stage="$2"
  record --arg type result --arg status "$class" --arg stage "$stage" \
    '{type:$type,status:$status,stage:$stage,acceptance:false}'
  exit 1
}

docker_bounded() {
  timeout --signal=TERM --kill-after=5s 30s docker "$@"
}

owned_container_ids() {
  docker_bounded container ls -aq --no-trunc \
    --filter "label=org.openj92.cpk.test-run=$1"
}

owned_volume_names() {
  docker_bounded volume ls -q --filter "label=org.openj92.cpk.test-run=$1"
}

owned_network_ids() {
  docker_bounded network ls -q --no-trunc \
    --filter "label=org.openj92.cpk.test-run=$1"
}

image_ids_for_tag() {
  docker_bounded image ls -q --no-trunc --filter "reference=$1"
}

helper_metadata_container_ids() {
  docker_bounded container ls -aq --no-trunc \
    --filter "name=^/${HELPER_META_NAME}$"
}

cleanup_attempt() {
  local run="$1" records="$2" failed=0 identity owner tag identities
  if ! identities="$(owned_container_ids "$run")"; then failed=1; identities=""; fi
  while read -r identity; do
    [ -n "$identity" ] || continue
    if ! owner="$(docker_bounded container inspect --format \
      '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$identity")"; then
      failed=1; continue
    fi
    if [ "$owner" != "$run" ]; then failed=1; continue; fi
    docker_bounded container rm -f "$identity" >/dev/null || failed=1
  done <<< "$identities"
  if ! identities="$(owned_volume_names "$run")"; then failed=1; identities=""; fi
  while read -r identity; do
    [ -n "$identity" ] || continue
    if ! owner="$(docker_bounded volume inspect --format \
      '{{index .Labels "org.openj92.cpk.test-run"}}' "$identity")"; then
      failed=1; continue
    fi
    if [ "$owner" != "$run" ]; then failed=1; continue; fi
    docker_bounded volume rm "$identity" >/dev/null || failed=1
  done <<< "$identities"
  if ! identities="$(owned_network_ids "$run")"; then failed=1; identities=""; fi
  while read -r identity; do
    [ -n "$identity" ] || continue
    if ! owner="$(docker_bounded network inspect --format \
      '{{index .Labels "org.openj92.cpk.test-run"}}' "$identity")"; then
      failed=1; continue
    fi
    if [ "$owner" != "$run" ]; then failed=1; continue; fi
    docker_bounded network rm "$identity" >/dev/null || failed=1
  done <<< "$identities"
  tag="control-plane-kit-postgres-source:$run"
  if ! identities="$(image_ids_for_tag "$tag")"; then failed=1; identities=""; fi
  if [ -n "$identities" ]; then
    if ! owner="$(docker_bounded image inspect --format \
      '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$tag")"; then
      failed=1
    elif [ "$owner" != "$run" ]; then
      failed=1
    else
      docker_bounded image rm "$tag" >/dev/null || failed=1
    fi
  fi
  rm -f "$records/control.json" "$records/password" "$records/10-witness.sql" \
    "$records/witness-output" || failed=1
  rmdir "$records/wrong-owner-data" 2>/dev/null || true
  rmdir "$records" || failed=1
  if ! identities="$(owned_container_ids "$run")"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  if ! identities="$(owned_volume_names "$run")"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  if ! identities="$(owned_network_ids "$run")"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  if ! identities="$(image_ids_for_tag "$tag")"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  record --arg type cleanup --arg run "$run" --argjson passed "$([ "$failed" = 0 ] && echo true || echo false)" \
    '{type:$type,run:$run,passed:$passed}'
  [ "$failed" = 0 ]
}

cleanup_helper() {
  local identity owner identities failed=0
  if ! identities="$(helper_metadata_container_ids)"; then failed=1; identities=""; fi
  while read -r identity; do
    [ -n "$identity" ] || continue
    if ! owner="$(docker_bounded container inspect --format \
      '{{index .Config.Labels "org.openj92.cpk.diagnostic"}}' "$identity")"; then
      failed=1; continue
    fi
    if [ "$owner" != "${GITHUB_RUN_ID}" ]; then failed=1; continue; fi
    docker_bounded container rm -f "$identity" >/dev/null || failed=1
  done <<< "$identities"
  if ! identities="$(helper_metadata_container_ids)"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  if ! identities="$(image_ids_for_tag "$HELPER_TAG")"; then failed=1; identities=""; fi
  if [ -z "$identities" ]; then
    [ -z "$HELPER_ID" ] || failed=1
  else
    observed="$(docker_bounded image inspect --format '{{.Id}}' "$HELPER_TAG")" || failed=1
    [ -z "$HELPER_ID" ] || [ "$observed" = "$HELPER_ID" ] || failed=1
    [ "$(docker_bounded image inspect --format \
      '{{index .Config.Labels "org.openj92.cpk.diagnostic"}}' "$HELPER_TAG")" = \
      "${GITHUB_RUN_ID}" ] || failed=1
    [ "$failed" != 0 ] || docker_bounded image rm "$HELPER_TAG" >/dev/null || failed=1
  fi
  if ! identities="$(image_ids_for_tag "$HELPER_TAG")"; then failed=1; identities=unknown; fi
  [ -z "$identities" ] || failed=1
  record --arg type cleanup --arg scope helper \
    --argjson passed "$([ "$failed" = 0 ] && echo true || echo false)" \
    '{type:$type,scope:$scope,passed:$passed}'
  [ "$failed" = 0 ]
}

outer_cleanup() {
  local result=$?
  trap - EXIT
  if [ -n "$COMMAND_PID" ] && kill -0 "$COMMAND_PID" 2>/dev/null; then
    kill "$COMMAND_PID" 2>/dev/null || true
    for _ in $(seq 1 150); do
      kill -0 "$COMMAND_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL "$COMMAND_PID" 2>/dev/null || true
    wait "$COMMAND_PID" 2>/dev/null || true
  fi
  if [ -n "$CURRENT_RUN" ]; then
    cleanup_attempt "$CURRENT_RUN" "$CURRENT_RECORDS" || result=1
  fi
  cleanup_helper || result=1
  exit "$result"
}
trap outer_cleanup EXIT

if ! HEAD_ID="$(git rev-parse HEAD)"; then terminal_failure evidence-failure source-head; fi
if [ "$HEAD_ID" != "${EXPECTED_HEAD:?}" ]; then terminal_failure evidence-failure source-head; fi
if ! WORKTREE_STATUS="$(git status --porcelain)"; then
  terminal_failure evidence-failure source-head
fi
if [ -n "$WORKTREE_STATUS" ]; then terminal_failure evidence-failure source-head; fi
if ! SCRIPT_SHA256="$(sha256sum "$DIAGNOSTIC_SCRIPT" | cut -d " " -f 1)"; then
  terminal_failure evidence-failure diagnostic-script
fi
if ! DOCKER_SERVER="$(docker_bounded version --format '{{.Server.Version}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if ! DOCKER_API="$(docker_bounded version --format '{{.Server.APIVersion}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if ! DOCKER_OS="$(docker_bounded info --format '{{.OSType}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if ! DOCKER_ARCH="$(docker_bounded info --format '{{.Architecture}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if ! STORAGE_DRIVER="$(docker_bounded info --format '{{.Driver}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if ! CGROUP_DRIVER="$(docker_bounded info --format '{{.CgroupDriver}}')"; then
  terminal_failure evidence-failure daemon-profile
fi
if [ -z "$DOCKER_SERVER" ] || [ -z "$DOCKER_API" ] || [ "$DOCKER_OS" != linux ] || \
    [ -z "$STORAGE_DRIVER" ] || [ -z "$CGROUP_DRIVER" ]; then
  terminal_failure evidence-failure daemon-profile
fi
case "$DOCKER_ARCH" in
  amd64|x86_64) ;;
  *) terminal_failure evidence-failure daemon-profile ;;
esac
record --arg type environment --arg head "$HEAD_ID" \
  --arg diagnostic_script_sha256 "$SCRIPT_SHA256" \
  --arg runner_os "${RUNNER_OS}" --arg runner_arch "${RUNNER_ARCH}" \
  --arg runner_image_os "${ImageOS:-unknown}" \
  --arg runner_image_version "${ImageVersion:-unknown}" \
  --arg docker_server "$DOCKER_SERVER" --arg docker_api "$DOCKER_API" \
  --arg docker_os "$DOCKER_OS" --arg docker_arch "$DOCKER_ARCH" \
  --arg storage_driver "$STORAGE_DRIVER" --arg cgroup_driver "$CGROUP_DRIVER" \
  '{type:$type,head:$head,diagnostic_script_sha256:$diagnostic_script_sha256,
    runner_os:$runner_os,runner_arch:$runner_arch,
    runner_image_os:$runner_image_os,runner_image_version:$runner_image_version,
    docker_server:$docker_server,docker_api:$docker_api,docker_os:$docker_os,
    docker_arch:$docker_arch,storage_driver:$storage_driver,cgroup_driver:$cgroup_driver}'

if ! timeout --signal=TERM --kill-after=15s "$BUILD_TIMEOUT" docker pull "$HELPER_BASE"; then
  terminal_failure command-failure helper-base-pull
fi
if ! HELPER_BASE_ID="$(docker_bounded image inspect --format '{{.Id}}' "$HELPER_BASE")"; then
  terminal_failure evidence-failure helper-base
fi
if ! timeout --signal=TERM --kill-after=15s "$BUILD_TIMEOUT" \
  docker build -f Dockerfile.test \
    --label "org.openj92.cpk.diagnostic=${GITHUB_RUN_ID}" \
    -t "$HELPER_TAG" .; then
  terminal_failure command-failure helper-build
fi
if ! HELPER_ID="$(docker_bounded image inspect --format '{{.Id}}' "$HELPER_TAG")"; then
  terminal_failure evidence-failure helper-image
fi
if ! HELPER_METADATA="$(docker_bounded run --rm --network none \
  --name "$HELPER_META_NAME" \
  --label "org.openj92.cpk.diagnostic=${GITHUB_RUN_ID}" \
  "$HELPER_ID" python -c \
  'import json, platform; from importlib.metadata import version; print(json.dumps({"package": version("control-plane-kit-servers"), "python": platform.python_version(), "docker_sdk": version("docker")}))')"; then
  terminal_failure evidence-failure helper-metadata
fi
if ! jq -e 'keys == ["docker_sdk", "package", "python"] and all(.[]; type == "string" and length > 0)' \
    <<< "$HELPER_METADATA" >/dev/null; then
  terminal_failure evidence-failure helper-metadata
fi
if ! HELPER_VERSION="$(jq -r .package <<< "$HELPER_METADATA")"; then
  terminal_failure evidence-failure helper-metadata
fi
if ! PYTHON_VERSION="$(jq -r .python <<< "$HELPER_METADATA")"; then
  terminal_failure evidence-failure helper-metadata
fi
if ! DOCKER_SDK_VERSION="$(jq -r .docker_sdk <<< "$HELPER_METADATA")"; then
  terminal_failure evidence-failure helper-metadata
fi
record --arg type helper --arg image_id "$HELPER_ID" --arg version "$HELPER_VERSION" \
  --arg python_version "$PYTHON_VERSION" --arg docker_sdk_version "$DOCKER_SDK_VERSION" \
  --arg base_reference "$HELPER_BASE" --arg base_image_id "$HELPER_BASE_ID" \
  --arg dockerfile_sha256 "$(sha256sum Dockerfile.test | cut -d " " -f 1)" \
  --arg pyproject_sha256 "$(sha256sum pyproject.toml | cut -d " " -f 1)" \
  '{type:$type,image_id:$image_id,version:$version,
    python_version:$python_version,docker_sdk_version:$docker_sdk_version,
    base_reference:$base_reference,base_image_id:$base_image_id,
    dockerfile_sha256:$dockerfile_sha256,pyproject_sha256:$pyproject_sha256}'

for attempt in 1 2 3; do
  CURRENT_RECORDS="$(mktemp -d "${RUNNER_TEMP}/cpk-postgres-recovery.XXXXXX")"
  CURRENT_RUN="cpk-postgres-recovery-${GITHUB_RUN_ID}-${attempt}"
  OUTPUT="$CURRENT_RECORDS/witness-output"
  SOURCE_TAG="control-plane-kit-postgres-source:$CURRENT_RUN"
  STARTED="$(date +%s)"
  set +e
  timeout --signal=TERM --kill-after=15s "$ATTEMPT_TIMEOUT" \
    docker run --rm --name "$CURRENT_RUN-controller" \
      --label "org.openj92.cpk.test-run=$CURRENT_RUN" \
      --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
      --mount "type=bind,source=$ROOT,target=/source,readonly" \
      --mount "type=bind,source=$CURRENT_RECORDS,target=/witness" \
      -e PYTHONPATH=/source/products/postgres_server/src:/source/products/postgres_server/tests \
      -e "CPK_POSTGRES_TEST_RUN=$CURRENT_RUN" \
      -e "CPK_POSTGRES_HOST_RECORDS=$CURRENT_RECORDS" \
      "$HELPER_ID" python /source/products/postgres_server/tests/live_postgres_image.py \
      >"$OUTPUT" 2>&1 &
  COMMAND_PID=$!
  SOURCE_ID=""
  SOURCE_OWNER=""
  while kill -0 "$COMMAND_PID" 2>/dev/null; do
    SOURCE_ID="$(docker_bounded image inspect --format '{{.Id}}' "$SOURCE_TAG" 2>/dev/null || true)"
    if [ -n "$SOURCE_ID" ]; then
      SOURCE_OWNER="$(docker_bounded image inspect --format \
        '{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$SOURCE_TAG" 2>/dev/null || true)"
      break
    fi
    sleep 0.2
  done
  wait "$COMMAND_PID"
  COMMAND_STATUS=$?
  COMMAND_PID=""
  set -e
  EVENT="$(grep -F '{"postgres_source_failure":' "$OUTPUT" | tail -n 1 || true)"
  OUTPUT_BYTES="$(wc -c < "$OUTPUT")"
  OUTPUT_SHA256="$(sha256sum "$OUTPUT" | cut -d " " -f 1)"
  if ! BASE_ID="$(docker_bounded image inspect --format '{{.Id}}' "$POSTGRES_BASE")"; then BASE_ID=""; fi
  CLASS=success
  if [ "$COMMAND_STATUS" = 124 ] || [ "$COMMAND_STATUS" = 137 ]; then CLASS=timeout
  elif [ -n "$EVENT" ]; then CLASS=product-failure
  elif [ "$COMMAND_STATUS" != 0 ]; then CLASS=command-failure
  elif [ -z "$SOURCE_ID" ] || [ "$SOURCE_OWNER" != "$CURRENT_RUN" ] || [ -z "$BASE_ID" ]; then
    CLASS=evidence-failure
  fi
  record --arg type attempt --arg run "$CURRENT_RUN" --argjson attempt "$attempt" \
    --arg class "$CLASS" --argjson command_status "$COMMAND_STATUS" \
    --arg source_image_id "$SOURCE_ID" --arg source_image_owner "$SOURCE_OWNER" \
    --arg native_base_reference "$POSTGRES_BASE" \
    --arg native_base_id "$BASE_ID" \
    --arg helper_image_id "$HELPER_ID" --arg output_sha256 "$OUTPUT_SHA256" \
    --argjson output_bytes "$OUTPUT_BYTES" --argjson elapsed "$(( $(date +%s) - STARTED ))" \
    --argjson structured_event "${EVENT:-null}" \
    '{type:$type,run:$run,attempt:$attempt,class:$class,command_status:$command_status,
      source_image_id:$source_image_id,source_image_owner:$source_image_owner,
      native_base_reference:$native_base_reference,
      native_base_id:$native_base_id,
      helper_image_id:$helper_image_id,output_sha256:$output_sha256,
      output_bytes:$output_bytes,elapsed_seconds:$elapsed,structured_event:$structured_event}'
  cleanup_attempt "$CURRENT_RUN" "$CURRENT_RECORDS"
  CURRENT_RUN=""
  CURRENT_RECORDS=""
  [ "$CLASS" = success ] || exit 1
done

record --arg type result --arg status non_reproduction \
  '{type:$type,status:$status,acceptance:false}'
