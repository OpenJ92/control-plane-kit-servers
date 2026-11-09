#!/bin/sh
# Exact source fixtures: pure composition or real isolated key commissioning.
# Neither mode executes an approved deployment.
set -eu
image=$1
core_repository=$2
operations_repository=$3
interpreters_repository=$4
phase=${5:-all}
secrets_repository=${6:-}
secrets_revision=${7:-}
source_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "${CPK_SOURCE_ASSEMBLY_IMAGES+x}" = x ]; then
  case "$phase" in all|red|registrations) sh "$source_root/scripts/http_sample_image_preflight.sh" "$core_repository" ;; esac
fi
source_paths=''
source_mounted=0
source_tmpfs=/tmp
if [ "$phase" = image-inputs ] || [ "$phase" = public-postgres ] || [ "$phase" = public-connectors ] || [ "${CPK_SOURCE_ASSEMBLY_IMAGES+x}" = x ]; then
  source_mounted=1
  source_tmpfs=/tmp:exec
  source_paths=/source:/source/src:/source/scripts:/source/products/cpk_server/src:/source/products/cpk_server/tests:/source/products/secrets_server/src:/source/products/secrets_server/tests:/source/products/cpk_local_gateway/src:/source/products/cloudflared_connector/src:/source/products/postgres_server/src:/source/products/website_server/src:
fi
core_revision=054e5884d89ed6f56141b8fc51ea996f0b6d916b
operations_revision=71db67c5df666d936860cce35b99394e600b2f1f
interpreters_revision=2e2a6b880359c6db98f6c1e41b6de450d8bc681f
case "$phase" in
  public-connectors)
    core_revision=f56bb5c4cfde76764d39c5377d4270c5b23c3ba1
    operations_revision=70154b6698e101159326b08646f2dba90dda87cd
    interpreters_revision=e438f6e522ad0a23a7acef460be08690f48b2e17
    set -- python -m unittest parent_connector_public_inputs_tests -v
    ;;
  public-postgres)
    core_revision=f56bb5c4cfde76764d39c5377d4270c5b23c3ba1
    operations_revision=70154b6698e101159326b08646f2dba90dda87cd
    interpreters_revision=e438f6e522ad0a23a7acef460be08690f48b2e17
    set -- python -m unittest http_sample_installation_tests http_sample_image_launcher_tests \
      test_managed_postgres_installation.ManagedPostgresInstallationTests.test_managed_graph_preserves_file_control_data_and_adds_authenticated_sql \
      test_managed_postgres_installation.ManagedPostgresInstallationTests.test_target_is_validated_with_or_without_optional_website \
      test_managed_postgres_installation.ManagedPostgresInstallationTests.test_receiver_alias_and_missing_verifier_families_are_rejected \
      test_managed_postgres_installation.ManagedPostgresInstallationTests.test_managed_socket_alone_does_not_admit_wrong_file_identity_or_contract \
      test_managed_postgres_installation.ManagedPostgresInstallationTests.test_native_input_keeps_environment_delivery_and_historical_plan -v
    ;;
  image-inputs)
    set -- python -m unittest http_sample_installation_tests http_sample_image_launcher_tests -v
    ;;
  managed-composition)
    core_revision=$6
    operations_revision=$7
    interpreters_revision=$8
    secrets_repository=''
    secrets_revision=''
    for revision in "$core_revision" "$operations_revision" "$interpreters_revision"; do
      case "$revision" in ''|*[!0-9a-f]*) echo 'exact source revision is required' >&2; exit 2 ;; esac
      [ "${#revision}" -eq 40 ] || exit 2
    done
    set -- python -m unittest managed_verification_composition_qualification test_managed_health_bridge test_managed_native_connection test_operations_application_factory -v
    ;;
  gateway-target)
    core_revision=$6
    operations_revision=$7
    secrets_repository=''
    secrets_revision=''
    for revision in "$core_revision" "$operations_revision"; do
      case "$revision" in ''|*[!0-9a-f]*) echo 'exact source revision is required' >&2; exit 2 ;; esac
      [ "${#revision}" -eq 40 ] || exit 2
    done
    case "${8:-}" in
      legacy) set -- python -m unittest gateway_target_qualification.LegacyGatewayTargetTests -v ;;
      full) set -- python -m unittest gateway_target_qualification.FullGatewayTargetTests -v ;;
      *) echo 'gateway target expectation must be legacy or full' >&2; exit 2 ;;
    esac
    ;;
  red) set -- python -m unittest http_sample_installation_tests.FullInstallationHttpSampleTests.test_secrets_companion_covers_original_pair_and_removes_only_its_review -v ;;
  all) set -- sh -c 'cd /tmp && python -m unittest http_sample_installation_tests test_full_http_sample_companion test_source_control_product test_installation_management test_managed_postgres_installation.ManagedPostgresInstallationTests -v && python -m http_sample_installation_assembly' ;;
  registrations)
    case "$secrets_revision" in ''|*[!0-9a-f]*) echo 'exact Secrets source revision is required' >&2; exit 2 ;; esac
    [ "${#secrets_revision}" -eq 40 ] || exit 2
    set -- python -m http_sample_registration_fixture
    ;;
  *) echo 'unsupported source assembly test selection' >&2; exit 2 ;;
esac
owned_source=$(mktemp -d /private/tmp/cpk181-source-assembly.XXXXXX)
owned_network=''
owned_database=''
finish() {
  result=$?
  trap - EXIT INT TERM
  if [ -n "$owned_database" ]; then
    docker rm -fv "$owned_database" >/dev/null || result=1
    remaining=$(docker container ls -aq --filter "id=$owned_database") || result=1
    [ -z "$remaining" ] || result=1
  fi
  if [ -n "$owned_network" ]; then
    docker network rm "$owned_network" >/dev/null || result=1
    remaining=$(docker network ls -q --filter "id=$owned_network") || result=1
    [ -z "$remaining" ] || result=1
  fi
  rm -rf "$owned_source" || result=1
  [ ! -e "$owned_source" ] || result=1
  [ "$result" != 0 ] || echo 'source fixture exports and owned resources cleanup verified; no approved run executed'
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
if [ "$phase" = managed-composition ]; then
  git -C "$operations_repository" archive --format=tar "$operations_revision" control-plane-kit-operations/tests > "$owned_source/operations-tests.tar"
  tar -xf "$owned_source/operations-tests.tar" -C "$owned_source/operations" --strip-components=1
fi
git -C "$interpreters_repository" archive --format=tar "$interpreters_revision" src/control_plane_kit_interpreters > "$owned_source/interpreters.tar"
tar -xf "$owned_source/interpreters.tar" -C "$owned_source/interpreters"
network=none
if [ "$phase" = registrations ]; then
  mkdir "$owned_source/secrets"
  git -C "$secrets_repository" archive --format=tar "$secrets_revision" src/control_plane_kit_secrets > "$owned_source/secrets.tar"
  tar -xf "$owned_source/secrets.tar" -C "$owned_source/secrets"
  printf 'registration Secrets source=%s\n' "$secrets_revision"
  scope="cpk163-registration-$(date +%s)-$$"
  owned_network=$(docker network create --internal --label "org.openj92.cpk.test-run=$scope" "$scope")
  owned_database=$(docker run -d --pull never --label "org.openj92.cpk.test-run=$scope" \
    --network "$owned_network" --network-alias cpk163-postgres \
    -e POSTGRES_USER=cpk -e POSTGRES_PASSWORD=cpk-fixture -e POSTGRES_DB=cpk postgres:16-alpine)
  ready=0
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if docker exec "$owned_database" pg_isready -U cpk -d cpk >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  [ "$ready" = 1 ] || { echo 'owned PostgreSQL fixture did not become ready' >&2; exit 1; }
  network=$owned_network
fi
printf 'pure assembly source Core=%s Operations=%s Interpreters=%s\n' \
  "$core_revision" "$operations_revision" "$interpreters_revision"
source_controller() {
  if [ "$source_mounted" = 1 ]; then
    docker run --pull never --mount "type=bind,source=$source_root,target=/source,readonly" --workdir /tmp "$@"
  else docker run "$@"
  fi
}
source_controller --rm --network "$network" --read-only --tmpfs "$source_tmpfs" --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$owned_source,target=/reviewed-http-sample,readonly" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE \
  -e CPK_SOURCE_ASSEMBLY_IMAGES \
  -e CPK_SOURCE_FIXTURE_DATABASE_URL=postgresql://cpk:cpk-fixture@cpk163-postgres:5432/cpk \
  -e "CPK_SOURCE_SECRETS_REVISION=$secrets_revision" \
  -e PYTHONPATH=/reviewed-http-sample/core/src:/reviewed-http-sample/operations/src:/reviewed-http-sample/operations:/reviewed-http-sample/interpreters/src:/reviewed-http-sample/secrets/src:"${source_paths}"/app:/app/products/cpk_server/tests:/app/products/secrets_server/tests:/app/scripts \
  "$image" "$@"
