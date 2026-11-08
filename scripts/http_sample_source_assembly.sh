#!/bin/sh
# Pure complete-child composition diagnostic. No provider or approved run.
set -eu
image=$1
core_repository=$2
operations_repository=$3
interpreters_repository=$4
phase=${5:-all}
case "$phase" in
  red) set -- python -m unittest http_sample_installation_tests.FullInstallationHttpSampleTests.test_secrets_companion_covers_original_pair_and_removes_only_its_review -v ;;
  all) set -- sh -c 'cd /tmp && python -m unittest http_sample_installation_tests test_full_http_sample_companion test_source_control_product test_installation_management test_managed_postgres_installation.ManagedPostgresInstallationTests -v && python -m http_sample_installation_assembly' ;;
  *) echo 'unsupported source assembly test selection' >&2; exit 2 ;;
esac
core_revision=054e5884d89ed6f56141b8fc51ea996f0b6d916b
operations_revision=71db67c5df666d936860cce35b99394e600b2f1f
interpreters_revision=2e2a6b880359c6db98f6c1e41b6de450d8bc681f
owned_source=$(mktemp -d /private/tmp/cpk181-source-assembly.XXXXXX)
finish() {
  result=$?
  trap - EXIT INT TERM
  rm -rf "$owned_source" || result=1
  [ ! -e "$owned_source" ] || result=1
  [ "$result" != 0 ] || echo 'pure assembly exports cleanup verified; no approved run executed'
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
printf 'pure assembly source Core=%s Operations=%s Interpreters=%s\n' \
  "$core_revision" "$operations_revision" "$interpreters_revision"
docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$owned_source,target=/reviewed-http-sample,readonly" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE \
  -e PYTHONPATH=/reviewed-http-sample/core/src:/reviewed-http-sample/operations/src:/reviewed-http-sample/interpreters/src:/app:/app/products/cpk_server/tests:/app/products/secrets_server/tests:/app/scripts \
  "$image" "$@"
