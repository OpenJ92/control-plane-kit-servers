#!/bin/sh
# Owning local product build: no service/provider/credential mutation.
set -eu
[ "$#" = 4 ] && [ "$1" = --grandparent-image-build ] || exit 2
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
CORE_REPOSITORY=$2 OPERATIONS_REPOSITORY=$3 INTERPRETERS_REPOSITORY=$4
COHORT=products/cpk_server/grandparent-cohort.json
SOURCE=$(git rev-parse HEAD)
worktree=$(git status --porcelain)
[ -z "$worktree" ] || exit 2
. ./scripts/docker_witness_daemon.sh
docker_witness_daemon
[ "$image_witness_daemon" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 2
BASE=$(jq -er .base "$COHORT")
BASE_ID=$(docker image inspect "$BASE" --format '{{.Id}}')
[ "$BASE_ID" = sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28 ] || exit 2
CONTROLLER=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
[ "$(docker image inspect "$CONTROLLER" --format '{{.Id}}')" = "$CONTROLLER" ] || exit 2
TAG=localhost/control-plane-kit-servers/cpk-grandparent:cpk163-sender-20261109-02
RUN=cpk163-grandparent-artifact-20261109-02
CANONICAL_TMP=$(CDPATH= cd -- /tmp && pwd -P)
RECORDS=$CANONICAL_TMP/$RUN
[ ! -e "$RECORDS" ] && [ ! -L "$RECORDS" ] || exit 2
existing=$(docker image ls -q --filter "reference=$TAG")
[ -z "$existing" ] || exit 2
existing=$(docker ps -aq --filter "name=^/$RUN-provenance$")
[ -z "$existing" ] || exit 2
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
. ./scripts/gateway_packaged_owner.sh
GW_ROLES='base-validator provenance' GW_RUN=$RUN GW_OWNER=$OWNER GW_RECORDS=$RECORDS GW_RESERVED=1 GW_VOLUMES=''
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
    --argjson status "$status" --argjson verified "$VERIFIED" \
    '{source:$source,phase:$phase,run:$run,owner:$owner,exit_code:$status,image:$image,base:$base,
      build_attempted:$attempted,local_oci_base_verified:$local_base,derived_base_layers_verified:$derived_base,
      installed_cohort_verified:$verified,cleanup:$cleanup,retention:$retention,base_retained:$base_retained,
      listening_startup_verified:false,approved_deployment:false}' > "$RECORDS/result.json" || status=1
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$CONTEXT/cohort/core" "$CONTEXT/cohort/operations" "$CONTEXT/cohort/interpreters"
git archive --format=tar "$SOURCE" products/cpk_server/Dockerfile.grandparent \
  products/cpk_server/grandparent-cohort.json products/cpk_server/tests/grandparent_image_check.py > "$RECORDS/recipe.tar"
tar -xf "$RECORDS/recipe.tar" -C "$CONTEXT"
SERVERS=$(jq -er .servers "$COHORT")
git archive --format=tar "$SERVERS" products/cpk_server/src products/cpk_local_gateway/src > "$RECORDS/products.tar"
tar -xf "$RECORDS/products.tar" -C "$CONTEXT"
printf '{}\n' > "$CONTEXT/cohort/source-objects.json"
for role in core operations interpreters server gateway; do
  case "$role" in
    core) repository=$CORE_REPOSITORY; revision=$(jq -er .core "$COHORT"); package=control-plane-kit-core; prefix=$package/src/control_plane_kit_core ;;
    operations) repository=$OPERATIONS_REPOSITORY; revision=$(jq -er .operations "$COHORT"); package=control-plane-kit-operations; prefix=$package/src/control_plane_kit_operations ;;
    interpreters) repository=$INTERPRETERS_REPOSITORY; revision=$(jq -er .interpreters "$COHORT"); package=''; prefix=src/control_plane_kit_interpreters ;;
    server) repository=$ROOT; revision=$SERVERS; prefix=products/cpk_server/src/control_plane_kit_servers_cpk_server ;;
    gateway) repository=$ROOT; revision=$SERVERS; prefix=products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway ;;
  esac
  [ "$(git -C "$repository" rev-parse "$revision^{commit}")" = "$revision" ] || exit 1
  tree=$(git -C "$repository" rev-parse "$revision:$prefix")
  git -C "$repository" ls-tree -r "$revision" "$prefix" > "$CONTEXT/cohort/$role.git-tree"
  case "$role" in
    core|operations)
      git -C "$repository" archive --format=tar "$revision" "$package" > "$RECORDS/$role.tar"
      tar -xf "$RECORDS/$role.tar" -C "$CONTEXT/cohort/$role" --strip-components=1 ;;
    interpreters)
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
gw_run base-validator --rm --network none --read-only --tmpfs /tmp:size=16m \
  --cpus 1 --memory 256m --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --workdir /tmp \
  --mount "type=bind,source=$ROOT/scripts/grandparent_oci.py,target=/oci.py,readonly" \
  --mount "type=bind,source=$RECORDS/base.tar,target=/base.tar,readonly" \
  --mount "type=bind,source=$LAYOUT,target=/layout" \
  "$CONTROLLER" python /oci.py /base.tar /layout > "$RECORDS/local-base.json"
LOCAL_BASE=true
rm -f "$RECORDS/base.tar" "$RECORDS/export.status"
docker_witness_daemon
[ "$image_witness_daemon" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 1
PHASE=build
BUILD_ATTEMPTED=true
docker buildx build --builder "$DOCKER_CONTEXT" --platform linux/amd64 --pull=false --load \
  --build-context "cpk-grandparent-base=oci-layout://$LAYOUT@${BASE#*@}" \
  --label "org.opencontainers.image.revision=$SOURCE" --label "cpk.test-run=$RUN" --label "cpk.test-owner=$OWNER" \
  --iidfile "$RECORDS/image.id" --metadata-file "$RECORDS/build-metadata.json" \
  -f "$CONTEXT/products/cpk_server/Dockerfile.grandparent" -t "$TAG" "$CONTEXT" > "$RECORDS/build.log" 2>&1
BUILD_TERMINATED=true
IMAGE=$(cat "$RECORDS/image.id")
docker_witness_daemon
[ "$image_witness_daemon" = "$GW_DAEMON" ] || exit 1
docker image inspect "$IMAGE" --format '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"user":{{json .Config.User}},"entrypoint":{{json (index .Config "Entrypoint")}},"cmd":{{json .Config.Cmd}},"os":{{json .Os}},"architecture":{{json .Architecture}}}' > "$RECORDS/image.json"
jq -e '.user=="10001" and ((.entrypoint//[])|length==0) and .cmd==["python","-m","control_plane_kit_servers_cpk_server.server"] and .os=="linux" and .architecture=="amd64"' "$RECORDS/image.json" >/dev/null
REFERENCE=$(jq -er --slurpfile metadata "$RECORDS/build-metadata.json" \
  '[.digests[]|select(.==("localhost/control-plane-kit-servers/cpk-grandparent@"+$metadata[0]["containerimage.digest"]))]|unique|if length==1 then .[0] else error("missing exact digest") end' "$RECORDS/image.json")
[ "$(docker image inspect "$REFERENCE" --format '{{.Id}}')" = "$IMAGE" ] || exit 1
docker image inspect "$IMAGE" --format '{{json .RootFS.Layers}}' > "$RECORDS/derived-layers.json"
jq -e --slurpfile base "$RECORDS/local-base.json" \
  'length>=($base[0].rootfs_diff_ids|length) and .[0:($base[0].rootfs_diff_ids|length)]==$base[0].rootfs_diff_ids' \
  "$RECORDS/derived-layers.json" >/dev/null
DERIVED_BASE=true
PHASE=installed-cohort
gw_run provenance --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python "$IMAGE" /usr/share/cpk-grandparent/check.py verify > "$RECORDS/installed-cohort.json"
jq -e '.effective_uid==10001' "$RECORDS/installed-cohort.json" >/dev/null
worktree=$(git status --porcelain)
[ -z "$worktree" ] && [ "$(git rev-parse HEAD)" = "$SOURCE" ] || exit 1
VERIFIED=true PHASE=complete
