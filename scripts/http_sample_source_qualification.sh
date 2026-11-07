#!/bin/sh
# Exact reviewed-source pure qualification. This is not the approved-run witness.
set -eu
image=$1
core_repository=$2
operations_repository=$3
interpreters_repository=$4
core_revision=054e5884d89ed6f56141b8fc51ea996f0b6d916b
operations_revision=a50a51dcbad8c47198a9e166bf168d06813a239b
interpreters_revision=2e2a6b880359c6db98f6c1e41b6de450d8bc681f
owned_source=$(mktemp -d /private/tmp/cpk181-source-qualification.XXXXXX)
finish() {
  result=$?
  trap - EXIT INT TERM
  rm -rf "$owned_source" || result=1
  [ ! -e "$owned_source" ] || result=1
  [ "$result" != 0 ] || echo 'source qualification exports cleanup verified'
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$owned_source/core" "$owned_source/operations" "$owned_source/interpreters"
git -C "$core_repository" archive --format=tar "$core_revision" control-plane-kit-core/src/control_plane_kit_core > "$owned_source/core.tar"
tar -xf "$owned_source/core.tar" -C "$owned_source/core" --strip-components=1
git -C "$operations_repository" archive --format=tar "$operations_revision" control-plane-kit-operations/src/control_plane_kit_operations > "$owned_source/operations.tar"
tar -xf "$owned_source/operations.tar" -C "$owned_source/operations" --strip-components=1
git -C "$interpreters_repository" archive --format=tar "$interpreters_revision" src/control_plane_kit_interpreters > "$owned_source/interpreters.tar"
tar -xf "$owned_source/interpreters.tar" -C "$owned_source/interpreters"
printf 'pure qualification source Core=%s Operations=%s Interpreters=%s\n' \
  "$core_revision" "$operations_revision" "$interpreters_revision"
docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$owned_source,target=/reviewed-http-sample,readonly" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/reviewed-http-sample/core/src:/reviewed-http-sample/operations/src:/reviewed-http-sample/interpreters/src:/app/products/cpk_server/tests:/app/scripts \
  "$image" python -m unittest http_sample_linked_qualification -v
