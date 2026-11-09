#!/bin/sh
# Owning local product build: no service/provider/credential mutation.
set -eu
MODE=runtime
case "${1:-}" in
  --grandparent-image-build) [ "$#" = 4 ] || exit 2 ;;
  --bootstrap-driver-image-build) [ "$#" = 6 ] || exit 2; MODE=installer; SECRETS_REPOSITORY=$5; PUBLIC_INPUT=$6 ;;
  *) exit 2 ;;
esac
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
CORE_REPOSITORY=$2 OPERATIONS_REPOSITORY=$3 INTERPRETERS_REPOSITORY=$4
COHORT=products/cpk_server/grandparent-cohort.json
DOCKERFILE=products/cpk_server/Dockerfile.grandparent
CHECK_FILE=products/cpk_server/tests/grandparent_image_check.py
CHECK_PATH=/usr/share/cpk-grandparent/check.py
IMAGE_REPOSITORY=localhost/control-plane-kit-servers/cpk-grandparent
CONTEXT_NAME=cpk-grandparent-base
EXPECTED_BASE=sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28
EXPECTED_USER=10001 EXPECTED_MODULE=control_plane_kit_servers_cpk_server.server
TAG=$IMAGE_REPOSITORY:cpk163-sender-20261109-02
RUN=cpk163-grandparent-artifact-20261109-02
if [ "$MODE" = installer ]; then
  COHORT=products/cpk_server/bootstrap-driver-cohort.json
  DOCKERFILE=products/cpk_server/Dockerfile.bootstrap-driver
  CHECK_FILE=products/cpk_server/tests/bootstrap_driver_image_check.py
  CHECK_PATH=/usr/share/cpk-bootstrap-driver/check.py
  IMAGE_REPOSITORY=localhost/control-plane-kit-servers/cpk-bootstrap-driver
  CONTEXT_NAME=cpk-bootstrap-driver-base
  EXPECTED_BASE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
  EXPECTED_USER=0 EXPECTED_MODULE=control_plane_kit_servers_cpk_server.bootstrap_cli
  TAG=$IMAGE_REPOSITORY:cpk391-20261109-02
  RUN=cpk391-bootstrap-driver-artifact-20261109-02
fi
SOURCE=$(git rev-parse HEAD)
worktree=$(git status --porcelain)
[ -z "$worktree" ] || exit 2
if [ "$MODE" = installer ]; then
  [ -f "$PUBLIC_INPUT" ] && [ ! -L "$PUBLIC_INPUT" ] || exit 2
  [ "$(wc -c < "$PUBLIC_INPUT")" -le 1048576 ] || exit 2
  expected_public=$(jq -er .qualification_public_input_sha256 "$COHORT")
  if command -v sha256sum >/dev/null 2>&1; then
    public_digest=$(sha256sum "$PUBLIC_INPUT")
  else public_digest=$(shasum -a 256 "$PUBLIC_INPUT")
  fi
  [ "${public_digest%% *}" = "$expected_public" ] || exit 2
  website_origin=$(jq -er .lineage.parent_website_origin "$COHORT")
  website_successor=$(jq -er .lineage.parent_website "$COHORT")
  git merge-base --is-ancestor "$website_origin" "$website_successor"
  git diff --quiet "$website_origin" "$website_successor" -- products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py
  for role in loader material parent_website; do
    selected=$(jq -er --arg role "$role" '.lineage[$role]' "$COHORT")
    git merge-base --is-ancestor "$selected" "$SOURCE"
    case "$role" in
      loader) set -- products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py products/cpk_server/src/control_plane_kit_servers_cpk_server/managed_verification_configuration.py ;;
      material) set -- bootstrap.sh products/cpk_server/src/control_plane_kit_servers_cpk_server/root_material_preparation.py products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py ;;
      parent_website) set -- products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py ;;
    esac
    git diff --quiet "$selected" "$SOURCE" -- "$@"
  done
fi
. ./scripts/docker_witness_daemon.sh
docker_witness_daemon
[ "$image_witness_daemon" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 2
BASE=$(jq -er .base "$COHORT")
BASE_ID=$(docker image inspect "$BASE" --format '{{.Id}}')
[ "$BASE_ID" = "$EXPECTED_BASE" ] || exit 2
CONTROLLER=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
[ "$(docker image inspect "$CONTROLLER" --format '{{.Id}}')" = "$CONTROLLER" ] || exit 2
CANONICAL_TMP=$(CDPATH= cd -- /tmp && pwd -P)
RECORDS=$CANONICAL_TMP/$RUN
[ ! -e "$RECORDS" ] && [ ! -L "$RECORDS" ] || exit 2
existing=$(docker image ls -q --filter "reference=$TAG")
[ -z "$existing" ] || exit 2
WITNESS_ROLES='base-validator provenance qualification'
[ "$MODE" != installer ] || WITNESS_ROLES="$WITNESS_ROLES schema-owner"
for role in $WITNESS_ROLES; do
  existing=$(docker ps -aq --filter "name=^/$RUN-$role$")
  [ -z "$existing" ] || exit 2
done
for kind in container volume network; do
  case "$kind" in container) set -- ps -aq ;; volume) set -- volume ls -q ;; network) set -- network ls -q ;; esac
  existing=$(docker "$@" --filter "label=cpk.test-run=$RUN")
  [ -z "$existing" ] || exit 2
done
mkdir -m 700 "$RECORDS"
OWNER=$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')
[ "${#OWNER}" = 64 ] || exit 1
CONTEXT=$RECORDS/context
LAYOUT=$RECORDS/base-layout
PHASE=source-export REFERENCE='' IMAGE='' VERIFIED=false CLEANUP=verified BUILD_ATTEMPTED=false
LOCAL_BASE=false DERIVED_BASE=false BUILD_TERMINATED=false
QUALIFIED=false SCHEMA_VERIFIED=false
. ./scripts/gateway_packaged_owner.sh
GW_ROLES=$WITNESS_ROLES GW_RUN=$RUN GW_OWNER=$OWNER GW_RECORDS=$RECORDS GW_RESERVED=1 GW_VOLUMES=''
GW_DAEMON=d23d00aa-b281-448d-bc95-c8e47efeeea2
finish() {
  status=$?
  trap - EXIT INT TERM
  gw_cleanup || { status=1; CLEANUP=unverified; }
  if [ "$BUILD_ATTEMPTED" = true ] && [ "$BUILD_TERMINATED" = false ]; then
    status=1; CLEANUP=unverified
  else
    rm -rf "$CONTEXT" "$LAYOUT" || { status=1; CLEANUP=unverified; }
    rm -f "$RECORDS/base.tar" "$RECORDS/export.status" || { status=1; CLEANUP=unverified; }
    [ ! -e "$CONTEXT" ] && [ ! -e "$LAYOUT" ] && [ ! -e "$RECORDS/base.tar" ] || { status=1; CLEANUP=unverified; }
  fi
  retention=not-built
  if [ "$BUILD_ATTEMPTED" = true ]; then retention=unverified; fi
  if [ -n "$REFERENCE" ]; then
    retention=unverified
    if gw_daemon && retained=$(docker image inspect "$REFERENCE" --format '{{.Id}}') && [ "$retained" = "$IMAGE" ]; then
      retention=verified
    else status=1
    fi
  fi
  base_retained=unverified
  if gw_daemon && retained_base=$(docker image inspect "$BASE" --format '{{.Id}}') && [ "$retained_base" = "$BASE_ID" ]; then
    base_retained=verified
  else status=1
  fi
  jq -n --arg source "$SOURCE" --arg phase "$PHASE" --arg run "$RUN" --arg owner "$OWNER" \
    --arg image "$REFERENCE" --arg base "$BASE" --arg cleanup "$CLEANUP" --arg retention "$retention" \
    --arg base_retained "$base_retained" --argjson attempted "$BUILD_ATTEMPTED" \
    --argjson local_base "$LOCAL_BASE" --argjson derived_base "$DERIVED_BASE" \
    --arg mode "$MODE" --argjson qualified "$QUALIFIED" --argjson schema_owner "$SCHEMA_VERIFIED" \
    --argjson status "$status" --argjson verified "$VERIFIED" \
    '{source:$source,phase:$phase,run:$run,owner:$owner,exit_code:$status,image:$image,base:$base,
      build_attempted:$attempted,local_oci_base_verified:$local_base,derived_base_layers_verified:$derived_base,
      artifact_role:$mode,normal_cli_plans_verified:$qualified,
      initialization_schema_owner_verified:$schema_owner,
      installed_cohort_verified:$verified,cleanup:$cleanup,retention:$retention,base_retained:$base_retained,
      listening_startup_verified:false,approved_deployment:false}' > "$RECORDS/result.json" || status=1
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$MODE" = installer ]; then
  cp -P "$PUBLIC_INPUT" "$RECORDS/qualification-public-root.json"
  [ -f "$RECORDS/qualification-public-root.json" ] && [ ! -L "$RECORDS/qualification-public-root.json" ] || exit 1
  if command -v sha256sum >/dev/null 2>&1; then
    copied_public=$(sha256sum "$RECORDS/qualification-public-root.json")
  else copied_public=$(shasum -a 256 "$RECORDS/qualification-public-root.json")
  fi
  [ "${copied_public%% *}" = "$expected_public" ] || exit 1
fi
mkdir -p "$CONTEXT/cohort/core" "$CONTEXT/cohort/operations" "$CONTEXT/cohort/interpreters"
set --
[ "$MODE" != installer ] || set -- products/cpk_server/tests/bootstrap_driver_imports.py
git archive --format=tar "$SOURCE" "$DOCKERFILE" "$COHORT" "$CHECK_FILE" \
  products/cpk_server/tests/grandparent_image_check.py "$@" > "$RECORDS/recipe.tar"
tar -xf "$RECORDS/recipe.tar" -C "$CONTEXT"
ROLES='core operations interpreters server gateway'
if [ "$MODE" = installer ]; then
  SERVERS=$SOURCE
  ROLES='core operations interpreters secrets servers'
  mkdir "$CONTEXT/cohort/secrets" "$CONTEXT/cohort/servers"
  git archive --format=tar "$SOURCE" > "$RECORDS/products.tar"
  tar -xf "$RECORDS/products.tar" -C "$CONTEXT/cohort/servers"
  jq --arg source "$SOURCE" '.servers=$source' "$COHORT" > "$CONTEXT/$COHORT"
else
  SERVERS=$(jq -er .servers "$COHORT")
  git archive --format=tar "$SERVERS" products/cpk_server/src products/cpk_local_gateway/src > "$RECORDS/products.tar"
  tar -xf "$RECORDS/products.tar" -C "$CONTEXT"
fi
printf '{}\n' > "$CONTEXT/cohort/source-objects.json"
for role in $ROLES; do
  case "$role" in
    core) repository=$CORE_REPOSITORY; revision=$(jq -er .core "$COHORT"); package=control-plane-kit-core; prefix=$package/src/control_plane_kit_core ;;
    operations) repository=$OPERATIONS_REPOSITORY; revision=$(jq -er .operations "$COHORT"); package=control-plane-kit-operations; prefix=$package/src/control_plane_kit_operations ;;
    interpreters) repository=$INTERPRETERS_REPOSITORY; revision=$(jq -er .interpreters "$COHORT"); package=''; prefix=src/control_plane_kit_interpreters ;;
    secrets) repository=$SECRETS_REPOSITORY; revision=$(jq -er .secrets "$COHORT"); package=''; prefix=src/control_plane_kit_secrets ;;
    servers) repository=$ROOT; revision=$SOURCE; prefix='' ;;
    server) repository=$ROOT; revision=$SERVERS; prefix=products/cpk_server/src/control_plane_kit_servers_cpk_server ;;
    gateway) repository=$ROOT; revision=$SERVERS; prefix=products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway ;;
  esac
  [ "$(git -C "$repository" rev-parse "$revision^{commit}")" = "$revision" ] || exit 1
  if [ -z "$prefix" ]; then
    tree=$(git -C "$repository" rev-parse "$revision^{tree}")
    git -C "$repository" ls-tree -r "$revision" > "$CONTEXT/cohort/$role.git-tree"
  else
    tree=$(git -C "$repository" rev-parse "$revision:$prefix")
    git -C "$repository" ls-tree -r "$revision" "$prefix" > "$CONTEXT/cohort/$role.git-tree"
  fi
  if [ "$MODE" = installer ] && [ "$role" = operations ]; then
    [ "$tree" = "$(jq -er .operations_tree "$COHORT")" ] || exit 1
  fi
  case "$role" in
    core|operations)
      git -C "$repository" archive --format=tar "$revision" "$package" > "$RECORDS/$role.tar"
      tar -xf "$RECORDS/$role.tar" -C "$CONTEXT/cohort/$role" --strip-components=1 ;;
    interpreters|secrets)
      git -C "$repository" archive --format=tar "$revision" > "$RECORDS/$role.tar"
      tar -xf "$RECORDS/$role.tar" -C "$CONTEXT/cohort/$role" ;;
  esac
  jq --arg role "$role" --arg revision "$revision" --arg tree "$tree" --arg prefix "$prefix" \
    '.+{($role):{commit:$revision,tree:$tree,prefix:$prefix}}' "$CONTEXT/cohort/source-objects.json" > "$CONTEXT/cohort/next.json"
  mv "$CONTEXT/cohort/next.json" "$CONTEXT/cohort/source-objects.json"
done
cp "$CONTEXT/cohort/source-objects.json" "$RECORDS/source-objects.json"
PHASE=local-base-export
df -Pk "$RECORDS" > "$RECORDS/disk-before.txt"
available=$(awk 'NR==2 {print $4}' "$RECORDS/disk-before.txt")
case "$available" in ''|*[!0-9]*) exit 1 ;; esac
[ "$available" -ge 1048576 ] || exit 1
mkdir -m 700 "$LAYOUT"
# The archive plus extracted blobs are bounded to 512 MiB (+1 overflow byte).
(set +e; docker image save "$BASE"; export_status=$?; printf '%s\n' "$export_status" > "$RECORDS/export.status") \
  | head -c 268435457 > "$RECORDS/base.tar"
[ "$(cat "$RECORDS/export.status")" = 0 ] || exit 1
export_bytes=$(wc -c < "$RECORDS/base.tar")
[ "$export_bytes" -le 268435456 ] || exit 1
set --
[ "$MODE" != installer ] || set -- --controller
gw_run base-validator --rm --network none --read-only --tmpfs /tmp:size=16m \
  --cpus 1 --memory 256m --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --workdir /tmp \
  --mount "type=bind,source=$ROOT/scripts/grandparent_oci.py,target=/oci.py,readonly" \
  --mount "type=bind,source=$RECORDS/base.tar,target=/base.tar,readonly" \
  --mount "type=bind,source=$LAYOUT,target=/layout" \
  "$CONTROLLER" python /oci.py "$@" /base.tar /layout > "$RECORDS/local-base.json"
LOCAL_BASE=true
rm -f "$RECORDS/base.tar" "$RECORDS/export.status"
docker_witness_daemon
[ "$image_witness_daemon" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 1
PHASE=build
BUILD_ATTEMPTED=true
docker buildx build --builder "$DOCKER_CONTEXT" --platform linux/amd64 --pull=false --load \
  --build-context "$CONTEXT_NAME=oci-layout://$LAYOUT@${BASE#*@}" \
  --label "org.opencontainers.image.revision=$SOURCE" --label "cpk.test-run=$RUN" --label "cpk.test-owner=$OWNER" \
  --iidfile "$RECORDS/image.id" --metadata-file "$RECORDS/build-metadata.json" \
  -f "$CONTEXT/$DOCKERFILE" -t "$TAG" "$CONTEXT" > "$RECORDS/build.log" 2>&1
BUILD_TERMINATED=true
IMAGE=$(cat "$RECORDS/image.id")
docker_witness_daemon
[ "$image_witness_daemon" = "$GW_DAEMON" ] || exit 1
docker image inspect "$IMAGE" --format '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"user":{{json .Config.User}},"entrypoint":{{json (index .Config "Entrypoint")}},"cmd":{{json .Config.Cmd}},"os":{{json .Os}},"architecture":{{json .Architecture}}}' > "$RECORDS/image.json"
jq -e --arg user "$EXPECTED_USER" --arg module "$EXPECTED_MODULE" \
  '.user==$user and ((.entrypoint//[])|length==0) and .cmd==["python","-m",$module] and .os=="linux" and .architecture=="amd64"' "$RECORDS/image.json" >/dev/null
REFERENCE=$(jq -er --arg repository "$IMAGE_REPOSITORY" --slurpfile metadata "$RECORDS/build-metadata.json" \
  '[.digests[]|select(.==($repository+"@"+$metadata[0]["containerimage.digest"]))]|unique|if length==1 then .[0] else error("missing exact digest") end' "$RECORDS/image.json")
[ "$(docker image inspect "$REFERENCE" --format '{{.Id}}')" = "$IMAGE" ] || exit 1
docker image inspect "$IMAGE" --format '{{json .RootFS.Layers}}' > "$RECORDS/derived-layers.json"
jq -e --slurpfile base "$RECORDS/local-base.json" \
  'length>=($base[0].rootfs_diff_ids|length) and .[0:($base[0].rootfs_diff_ids|length)]==$base[0].rootfs_diff_ids' \
  "$RECORDS/derived-layers.json" >/dev/null
DERIVED_BASE=true
PHASE=installed-cohort
gw_run provenance --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python "$IMAGE" "$CHECK_PATH" verify > "$RECORDS/installed-cohort.json"
jq -e --argjson user "$EXPECTED_USER" '.effective_uid==$user' "$RECORDS/installed-cohort.json" >/dev/null
VERIFIED=true
if [ "$MODE" = installer ]; then
  PHASE=schema-owner
  gw_run schema-owner --rm --network none --read-only --tmpfs /tmp:size=16m \
    --cpus 1 --memory 256m --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
    --user 10001:10001 --workdir /tmp --entrypoint python \
    "$IMAGE" "$CHECK_PATH" schema-owner > "$RECORDS/initialization-schema-owner.json"
  jq -e '.effective_uid==10001' "$RECORDS/initialization-schema-owner.json" >/dev/null
  SCHEMA_VERIFIED=true
  PHASE=normal-cli-plans
  gw_run qualification --rm --network none --read-only --tmpfs /tmp:size=64m \
    --cpus 2 --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --workdir /tmp --entrypoint python \
    --mount "type=bind,source=$RECORDS/qualification-public-root.json,target=/public-root.json,readonly" \
    "$IMAGE" "$CHECK_PATH" qualify "$IMAGE" /public-root.json > "$RECORDS/normal-cli-plans.json"
  QUALIFIED=true
fi
worktree=$(git status --porcelain)
[ -z "$worktree" ] && [ "$(git rev-parse HEAD)" = "$SOURCE" ] || exit 1
PHASE=complete
