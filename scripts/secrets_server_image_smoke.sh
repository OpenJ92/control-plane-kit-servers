#!/bin/sh
set -eu

IMAGE="${CPK_SECRETS_IMAGE:-control-plane-kit-secrets-server:local}"
BUILD_IMAGE="${CPK_SECRETS_BUILD_IMAGE:-1}"
CONTROLLER_IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
BUILD_CONTROLLER="${CPK_SECRETS_BUILD_CONTROLLER:-1}"
PROFILE="${CPK_SECRETS_SMOKE_PROFILE:-}"
PRODUCT_PULL_POLICY=missing
CHILD_PROFILE=0
PARENT_PROFILE=0
PARENT_INITIAL_VERIFIED=0
PARENT_RESTART_VERIFIED=0
PARENT_BASE_VERIFIED=0
PARENT_DERIVED_VERIFIED=0
PARENT_BUILD_ATTEMPTED=0
PARENT_BUILD_TERMINATED=0
PARENT_BASE_REFERENCE=localhost/control-plane-kit-servers/secrets-server@sha256:0d36584018d93305045631a1ee981d5a8850e16fd4532d765eb43a1a823dc095
CHILD_RESERVED=0
CHILD_SOURCE=''
CHILD_REFERENCE=''
CHILD_OWNER=''
INITIAL_VERIFIED=0
RESTART_VERIFIED=0
SAMPLES_VERIFIED=0
INITIAL_SAMPLES_VERIFIED=0
RESTART_SAMPLES_VERIFIED=0
PROVENANCE_VERIFIED=0
LOGS_VERIFIED=0
CHILD_PHASE=admission
invalid_inputs() {
  echo 'secrets-server image smoke: invalid profile or build inputs' >&2
  exit 2
}
case "$BUILD_IMAGE:$BUILD_CONTROLLER" in 0:0|0:1|1:0|1:1) ;; *) invalid_inputs ;; esac
if [ -z "$PROFILE" ]; then
  case "$BUILD_IMAGE" in 1) PROFILE=wrapped-source ;; 0) PROFILE=published-baseline ;; esac
fi
case "$PROFILE:$BUILD_IMAGE" in
  wrapped-child:1|wrapped-parent:1)
    if [ "$PROFILE" = wrapped-parent ]; then PARENT_PROFILE=1; fi
    CHILD_PROFILE=1
    PRODUCT_PULL_POLICY=never
    [ "$BUILD_CONTROLLER" = 0 ] || invalid_inputs
    : "${CPK_SECRETS_CHILD_RUN:?select the fresh Secrets run}"
    : "${CPK_SECRETS_CHILD_RECORDS:?select its canonical fresh receipt directory}"
    : "${CPK_RECEIVER_DAEMON_ID:?select the reviewed local daemon}"
    printf '%s\n' "$CPK_SECRETS_CHILD_RUN" | grep -Eq '^cpk-secrets-image-smoke-cpk163-[a-z0-9-]{4,32}$' || invalid_inputs
    child_parent=$(CDPATH= cd -- /tmp && pwd -P)
    [ "$CPK_SECRETS_CHILD_RECORDS" = "$child_parent/$CPK_SECRETS_CHILD_RUN" ] || invalid_inputs
    [ ! -e "$CPK_SECRETS_CHILD_RECORDS" ] && [ ! -L "$CPK_SECRETS_CHILD_RECORDS" ] || invalid_inputs
    case "$IMAGE" in localhost/control-plane-kit-servers/secrets-server:cpk163-*) ;; *) invalid_inputs ;; esac
    case "$CONTROLLER_IMAGE" in sha256:*) ;; *) invalid_inputs ;; esac
    [ "${#CONTROLLER_IMAGE}" = 71 ] || invalid_inputs
    case "${CONTROLLER_IMAGE#sha256:}" in *[!0-9a-f]*) invalid_inputs ;; esac
    ;;
  wrapped-source:1) ;;
  published-baseline:0)
    printf '%s\n' "$IMAGE" | grep -Eq '@sha256:[0-9a-f]{64}$' || invalid_inputs
    ;;
  wrapped-artifact:0)
    [ "$BUILD_CONTROLLER" = 0 ] || invalid_inputs
    . ./scripts/root_artifact_shell.sh
    root_artifact_admit secrets-server "$IMAGE" "$CONTROLLER_IMAGE"
    IMAGE="$ROOT_ARTIFACT_IMAGE_ID"
    CONTROLLER_IMAGE="$ROOT_ARTIFACT_CONTROLLER"
    PRODUCT_PULL_POLICY=never
    ;;
  *) invalid_inputs ;;
esac

CONTROL_RECORDS=""
CONTROL_PHASE=""
RUN_ID="cpk-secrets-image-smoke-$$"
if [ "$CHILD_PROFILE" = 1 ]; then RUN_ID=$CPK_SECRETS_CHILD_RUN; fi
LABEL_KEY="cpk.test-run"
NETWORK="$RUN_ID-network"
PROVIDER_BOOTSTRAP="$RUN_ID-provider-bootstrap"
CLIENT_BOOTSTRAP="$RUN_ID-client-bootstrap"
DATA_VOLUME="$RUN_ID-data"
PROVIDER="$RUN_ID-provider"
CHILD_ROLES='provenance bootstrap control-initial control-restart http-sample-initial http-sample-restart wait-initial wait-restart check-initial check-restart logs-initial logs-restart custody-initial custody-restart provider-initial provider-restart'
if [ "$PARENT_PROFILE" = 1 ]; then CHILD_ROLES="$CHILD_ROLES base-validator parent-http-initial parent-http-restart"; fi

child_track() {
  case " $CHILD_ROLES " in *" $1 "*) ;; *) return 1 ;; esac
  (umask 077; : > "$CPK_SECRETS_CHILD_RECORDS/$1.attempt")
}

smoke_run() {
  smoke_role=$1
  shift
  if [ "$CHILD_PROFILE" = 1 ]; then
    child_track "$smoke_role" || return 1
    docker run --pull never --name "$RUN_ID-$smoke_role" \
      --label "cpk.test-owner=$CHILD_OWNER" --cidfile "$CPK_SECRETS_CHILD_RECORDS/$smoke_role.cid" "$@"
  else docker run "$@"
  fi
}

child_volume_identity() {
  child_volume_signature=$(docker volume inspect "$1" --format '{{.Name}}|{{.Driver}}|{{.Scope}}|{{index .Labels "cpk.test-run"}}|{{index .Labels "cpk.test-owner"}}|{{len .Options}}') || return 1
  [ "$child_volume_signature" = "$1|local|local|$RUN_ID|$CHILD_OWNER|0" ]
}

child_create_volume() {
  child_volume=$1
  (umask 077; : > "$CPK_SECRETS_CHILD_RECORDS/$child_volume.volume-attempt") || return 1
  child_created_volume=$(docker volume create --label "$LABEL_KEY=$RUN_ID" --label "cpk.test-owner=$CHILD_OWNER" "$child_volume") || return 1
  [ "$child_created_volume" = "$child_volume" ] || return 1
  child_volume_identity "$child_volume"
}

child_cleanup_owned() {
  child_cleanup_failed=0
  child_daemon || return 1
  for child_role in $CHILD_ROLES; do
    [ -f "$CPK_SECRETS_CHILD_RECORDS/$child_role.attempt" ] || continue
    child_name="$RUN_ID-$child_role"
    if child_id=$(docker ps -aq --no-trunc --filter "name=^/$child_name$"); then :; else child_cleanup_failed=1; continue; fi
    [ -n "$child_id" ] || continue
    case "$child_id" in *[!0-9a-f]*) child_cleanup_failed=1; continue ;; esac
    [ "${#child_id}" = 64 ] || { child_cleanup_failed=1; continue; }
    if [ -s "$CPK_SECRETS_CHILD_RECORDS/$child_role.cid" ]; then
      child_captured_id=$(cat "$CPK_SECRETS_CHILD_RECORDS/$child_role.cid") || { child_cleanup_failed=1; continue; }
      [ "$child_captured_id" = "$child_id" ] || { child_cleanup_failed=1; continue; }
    fi
    child_identity=$(docker inspect "$child_id" --format '{{.Name}}|{{index .Config.Labels "cpk.test-run"}}|{{index .Config.Labels "cpk.test-owner"}}') || { child_cleanup_failed=1; continue; }
    [ "$child_identity" = "/$child_name|$RUN_ID|$CHILD_OWNER" ] || { child_cleanup_failed=1; continue; }
    child_daemon || return 1
    docker rm -f "$child_id" >/dev/null 2>&1 || child_cleanup_failed=1
    child_remaining=$(docker ps -aq --no-trunc --filter "id=$child_id") || { child_cleanup_failed=1; continue; }
    [ -z "$child_remaining" ] || child_cleanup_failed=1
  done
  for child_volume in "$PROVIDER_BOOTSTRAP" "$CLIENT_BOOTSTRAP" "$DATA_VOLUME"; do
    [ -f "$CPK_SECRETS_CHILD_RECORDS/$child_volume.volume-attempt" ] || continue
    child_present=$(docker volume ls -q --filter "name=$child_volume") || { child_cleanup_failed=1; continue; }
    [ -n "$child_present" ] || continue
    [ "$child_present" = "$child_volume" ] || { child_cleanup_failed=1; continue; }
    child_volume_identity "$child_volume" || { child_cleanup_failed=1; continue; }
    child_holders=$(docker ps -aq --filter "volume=$child_volume") || { child_cleanup_failed=1; continue; }
    [ -z "$child_holders" ] || { child_cleanup_failed=1; continue; }
    child_daemon || return 1
    docker volume rm "$child_volume" >/dev/null 2>&1 || child_cleanup_failed=1
    child_remaining=$(docker volume ls -q --filter "name=$child_volume") || { child_cleanup_failed=1; continue; }
    [ -z "$child_remaining" ] || child_cleanup_failed=1
  done
  if [ -f "$CPK_SECRETS_CHILD_RECORDS/network.attempt" ]; then
    child_network_id=$(docker network ls --no-trunc -q --filter "name=^$NETWORK$") || return 1
    if [ -n "$child_network_id" ]; then
      child_network_identity=$(docker network inspect "$child_network_id" --format '{{.Name}}|{{.Driver}}|{{.Scope}}|{{.Internal}}|{{index .Labels "cpk.test-run"}}|{{index .Labels "cpk.test-owner"}}') || return 1
      [ "$child_network_identity" = "$NETWORK|bridge|local|true|$RUN_ID|$CHILD_OWNER" ] || return 1
      child_daemon || return 1
      docker network rm "$child_network_id" >/dev/null 2>&1 || child_cleanup_failed=1
      child_remaining=$(docker network ls -q --filter "id=$child_network_id") || return 1
      [ -z "$child_remaining" ] || child_cleanup_failed=1
    fi
  fi
  # Unknown same-label objects are evidence of uncertain ownership, not an
  # invitation to remove them. Only the fixed attempted roles above are removed.
  for child_kind in container volume network; do
    case "$child_kind" in container) set -- ps -aq ;; volume) set -- volume ls -q ;; network) set -- network ls -q ;; esac
    child_remaining=$(docker "$@" --filter "label=$LABEL_KEY=$RUN_ID") || { child_cleanup_failed=1; continue; }
    [ -z "$child_remaining" ] || child_cleanup_failed=1
  done
  return "$child_cleanup_failed"
}

child_daemon() {
  child_observed_daemon=$(docker info --format '{{.ID}}') || return 1
  [ "$child_observed_daemon" = "$CPK_RECEIVER_DAEMON_ID" ]
}

child_source() {
  child_status=$(git status --porcelain) || return 1
  [ -z "$child_status" ] || return 1
  child_head=$(git rev-parse HEAD) || return 1
  [ "$child_head" = "$CHILD_SOURCE" ]
}

child_runtime() {
  CHILD_PHASE="$CONTROL_PHASE-process"
  child_daemon
  docker inspect "$PROVIDER" --format '{"id":{{json .Id}},"image":{{json .Image}},"path":{{json .Path}},"args":{{json .Args}}}' \
    > "$CPK_SECRETS_CHILD_RECORDS/$CONTROL_PHASE-runtime.json"
  jq -e --arg image "$IMAGE" '.image==$image and (.path=="cpk-secrets-entrypoint" or .path=="/usr/local/bin/cpk-secrets-entrypoint") and .args==["uvicorn","control_plane_kit_servers_secrets_server.server:create_app","--factory","--host","0.0.0.0","--port","8081"]' \
    "$CPK_SECRETS_CHILD_RECORDS/$CONTROL_PHASE-runtime.json" >/dev/null
  docker exec "$PROVIDER" python -c '
import json
with open("/proc/1/status", "rb") as stream:
    raw = stream.read(16385)
rows = [line.split()[1:] for line in raw.splitlines() if line.startswith(b"Uid:")]
if len(raw)>16384 or len(rows)!=1 or len(rows[0])!=4 or int(rows[0][1])!=10006:
    raise SystemExit(1)
print(json.dumps({"pid":1,"effective_uid":10006}))
' > "$CPK_SECRETS_CHILD_RECORDS/$CONTROL_PHASE-process.json"
}

cleanup_records() {
  [ -n "$CONTROL_RECORDS" ] || return 0
  records_header_failed=0
  for phase in initial restart; do
    rm -f "$CONTROL_RECORDS/$phase/surface.headers" "$CONTROL_RECORDS/$phase/health.headers" || records_header_failed=1
    [ ! -e "$CONTROL_RECORDS/$phase/surface.headers" ] && [ ! -L "$CONTROL_RECORDS/$phase/surface.headers" ] || records_header_failed=1
    [ ! -e "$CONTROL_RECORDS/$phase/health.headers" ] && [ ! -L "$CONTROL_RECORDS/$phase/health.headers" ] || records_header_failed=1
  done
  [ "$records_header_failed" = 0 ] || return 1
  rm -f "$CONTROL_RECORDS/provider.log" "$CONTROL_RECORDS/log.status" \
    "$CONTROL_RECORDS/artifact-provenance.json" "$CONTROL_RECORDS/artifact-provenance.status" \
    "$CONTROL_RECORDS/artifact-pid1.status" "$CONTROL_RECORDS/artifact-pid1.exit" || return 1
  for phase in initial restart; do
    rm -f "$CONTROL_RECORDS/$phase/control.json" \
      "$CONTROL_RECORDS/$phase/surface.headers" "$CONTROL_RECORDS/$phase/health.headers" || return 1
    rm -f "$CONTROL_RECORDS/$phase/http-samples.json" "$CONTROL_RECORDS/$phase/sample.prepared" \
      "$CONTROL_RECORDS/$phase/sample.ready" "$CONTROL_RECORDS/$phase/sample.passed" || return 1
    if [ -d "$CONTROL_RECORDS/$phase" ]; then
      rmdir "$CONTROL_RECORDS/$phase" || return 1
    fi
  done
  rmdir "$CONTROL_RECORDS" || return 1
  [ ! -e "$CONTROL_RECORDS" ] || return 1
  CONTROL_RECORDS=""
}

cleanup_owned() {
  if [ "$CHILD_PROFILE" = 1 ] && [ "$CHILD_RESERVED" != 1 ]; then return 0; fi
  if [ "$CHILD_PROFILE" = 1 ]; then child_cleanup_owned; return $?; fi
  cleanup_failed=0
  for resource_kind in container volume network; do
    if [ "$CHILD_PROFILE" = 1 ]; then child_daemon || return 1; fi
    case "$resource_kind" in
      container) set -- ps -aq ;;
      volume) set -- volume ls -q ;;
      network) set -- network ls -q ;;
    esac
    if owned="$(docker "$@" --filter "label=$LABEL_KEY=$RUN_ID")"; then
      for resource in $owned; do
        case "$resource_kind" in
          container) docker rm -f "$resource" >/dev/null 2>&1 || cleanup_failed=1 ;;
          volume) docker volume rm -f "$resource" >/dev/null 2>&1 || cleanup_failed=1 ;;
          network) docker network rm "$resource" >/dev/null 2>&1 || cleanup_failed=1 ;;
        esac
      done
    else
      cleanup_failed=1
    fi
    # Independently require a successful authoritative absence observation.
    if remaining="$(docker "$@" --filter "label=$LABEL_KEY=$RUN_ID")"; then
      [ -z "$remaining" ] || cleanup_failed=1
    else
      cleanup_failed=1
    fi
  done
  return "$cleanup_failed"
}

finish() {
  status=$?
  trap - EXIT INT TERM
  child_cleanup=verified
  if ! cleanup_owned; then
    echo "secrets-server image smoke cleanup could not be verified" >&2
    status=1
    child_cleanup=unverified
  fi
  cleanup_records || { echo 'secrets-server fixture cleanup incomplete' >&2; status=1; child_cleanup=unverified; }
  parent_base_retention=not-applicable
  if [ "$PARENT_PROFILE" = 1 ] && [ "$CHILD_RESERVED" = 1 ]; then
    if [ "$PARENT_BUILD_ATTEMPTED" = 1 ] && [ "$PARENT_BUILD_TERMINATED" != 1 ]; then
      status=1; child_cleanup=unverified
    else
      rm -rf "$CPK_SECRETS_CHILD_RECORDS/base-layout" || { status=1; child_cleanup=unverified; }
      rm -f "$CPK_SECRETS_CHILD_RECORDS/base.tar" "$CPK_SECRETS_CHILD_RECORDS/export.status" || { status=1; child_cleanup=unverified; }
      for parent_scratch in base-layout base.tar export.status; do
        [ ! -e "$CPK_SECRETS_CHILD_RECORDS/$parent_scratch" ] || { status=1; child_cleanup=unverified; }
      done
    fi
    parent_base_retention=unverified
    if child_daemon && parent_retained_id=$(docker image inspect "$PARENT_BASE_REFERENCE" --format '{{.Id}}') &&
        [ "$parent_retained_id" = "${PARENT_BASE_REFERENCE#*@}" ]; then
      parent_base_retention=verified
    else status=1
    fi
  fi
  if [ "$CHILD_RESERVED" = 1 ]; then
    child_retention=unverified
    if [ -n "$CHILD_REFERENCE" ] && child_daemon; then
      if child_retained_id=$(docker image inspect "$CHILD_REFERENCE" --format '{{.Id}}'); then
        if [ "$child_retained_id" = "$IMAGE" ]; then child_retention=verified; else status=1; fi
      else status=1
      fi
    else status=1
    fi
    jq -n --arg source "$CHILD_SOURCE" --arg run "$RUN_ID" --arg phase "$CHILD_PHASE" \
      --arg reference "$CHILD_REFERENCE" --arg cleanup "$child_cleanup" --arg retention "$child_retention" \
      --argjson status "$status" --argjson initial "$INITIAL_VERIFIED" --argjson restart "$RESTART_VERIFIED" \
      --argjson samples "$SAMPLES_VERIFIED" --argjson initial_samples "$INITIAL_SAMPLES_VERIFIED" \
      --argjson restart_samples "$RESTART_SAMPLES_VERIFIED" \
      --arg owner "$CHILD_OWNER" --arg daemon "$CPK_RECEIVER_DAEMON_ID" --arg controller "$CONTROLLER_IMAGE" \
      --argjson provenance "$PROVENANCE_VERIFIED" --argjson logs "$LOGS_VERIFIED" \
      --argjson parent "$PARENT_PROFILE" --argjson parent_initial "$PARENT_INITIAL_VERIFIED" \
      --argjson parent_restart "$PARENT_RESTART_VERIFIED" --argjson parent_base "$PARENT_BASE_VERIFIED" \
      --argjson parent_derived "$PARENT_DERIVED_VERIFIED" \
      --arg parent_base_retention "$parent_base_retention" \
      '{source:$source,run:$run,phase:$phase,exit_code:$status,candidate_reference:$reference,
        product_source_base:"85b193bbdc777376c5104029a5ee04e74627cf71",owner_nonce:$owner,
        daemon_id:$daemon,controller_id:$controller,installed_provenance_verified:($provenance==1),
        cleanup:$cleanup,candidate_retention:$retention,initial_custody_verified:($initial==1),
        retained_restart_verified:($restart==1),signed_pair_verified:($samples==1),
        initial_signed_pair_verified:($initial_samples==1),restart_signed_pair_verified:($restart_samples==1),
        revocation_persistence_verified:($restart==1),logs_redacted_verified:($logs==1),
        parent_only_profile:($parent==1),parent_http_initial_verified:($parent_initial==1),
        parent_http_restart_verified:($parent_restart==1),parent_local_oci_base_verified:($parent_base==1),
        parent_base_layers_verified:($parent_derived==1),parent_base_retention:$parent_base_retention,approved_child_run:false}' \
      > "$CPK_SECRETS_CHILD_RECORDS/result.json" || status=1
  fi
  if [ "$status" = 0 ]; then
    echo "secrets-server image smoke passed ($PROFILE)"
    if [ "$PROFILE" = wrapped-artifact ]; then root_artifact_pass; fi
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

if [ "$BUILD_IMAGE" = "1" ]; then
  if [ "$CHILD_PROFILE" = 1 ]; then
    . ./scripts/docker_witness_daemon.sh
    docker_witness_daemon
    child_daemon
    CHILD_SOURCE=$(git rev-parse HEAD)
    child_source
    git diff --quiet 85b193bbdc777376c5104029a5ee04e74627cf71 HEAD -- \
      products/secrets_server/src products/secrets_server/Dockerfile products/secrets_server/entrypoint.sh
    [ "$(docker image inspect "$CONTROLLER_IMAGE" --format '{{.Id}}')" = "$CONTROLLER_IMAGE" ] || exit 1
    if [ "$PARENT_PROFILE" = 1 ]; then
      [ "$(docker image inspect "$PARENT_BASE_REFERENCE" --format '{{.Id}}')" = "${PARENT_BASE_REFERENCE#*@}" ] || exit 1
    fi
    child_existing=$(docker image ls -q --filter "reference=$IMAGE")
    [ -z "$child_existing" ] || exit 1
    for child_kind in container volume network; do
      case "$child_kind" in container) set -- ps -aq ;; volume) set -- volume ls -q ;; network) set -- network ls -q ;; esac
      child_existing=$(docker "$@" --filter "label=$LABEL_KEY=$RUN_ID")
      [ -z "$child_existing" ] || exit 1
    done
    for child_volume in "$PROVIDER_BOOTSTRAP" "$CLIENT_BOOTSTRAP" "$DATA_VOLUME"; do
      child_existing=$(docker volume ls -q --filter "name=$child_volume")
      [ -z "$child_existing" ] || exit 1
    done
    child_existing=$(docker network ls -q --filter "name=^$NETWORK$")
    [ -z "$child_existing" ] || exit 1
    for child_role in $CHILD_ROLES; do
      child_name="$RUN_ID-$child_role"
      child_existing=$(docker ps -aq --filter "name=^/$child_name$")
      [ -z "$child_existing" ] || exit 1
    done
    mkdir -m 700 "$CPK_SECRETS_CHILD_RECORDS"
    CHILD_RESERVED=1
    CHILD_OWNER=$(od -An -N32 -tx1 /dev/urandom)
    CHILD_OWNER=$(printf '%s' "$CHILD_OWNER" | tr -d '[:space:]')
    [ "${#CHILD_OWNER}" = 64 ] || exit 1
    case "$CHILD_OWNER" in *[!0-9a-f]*) exit 1 ;; esac
    (umask 077; printf '%s\n' "$CHILD_OWNER" > "$CPK_SECRETS_CHILD_RECORDS/owner.txt")
    CHILD_PHASE=build
    git archive --format=tar "$CHILD_SOURCE" > "$CPK_SECRETS_CHILD_RECORDS/source.tar"
    set --
    secrets_recipe=products/secrets_server/Dockerfile
    if [ "$PARENT_PROFILE" = 1 ]; then
      CHILD_PHASE=parent-local-base
      parent_layout="$CPK_SECRETS_CHILD_RECORDS/base-layout"
      mkdir -m 700 "$parent_layout"
      df -Pk "$CPK_SECRETS_CHILD_RECORDS" > "$CPK_SECRETS_CHILD_RECORDS/disk-before.txt"
      parent_available=$(awk 'NR==2 {print $4}' "$CPK_SECRETS_CHILD_RECORDS/disk-before.txt")
      case "$parent_available" in ''|*[!0-9]*) exit 1 ;; esac
      [ "$parent_available" -ge 1048576 ] || exit 1
      (set +e; docker image save "$PARENT_BASE_REFERENCE"; parent_export_status=$?;
        printf '%s\n' "$parent_export_status" > "$CPK_SECRETS_CHILD_RECORDS/export.status") \
        | head -c 268435457 > "$CPK_SECRETS_CHILD_RECORDS/base.tar"
      [ "$(cat "$CPK_SECRETS_CHILD_RECORDS/export.status")" = 0 ] || exit 1
      parent_export_bytes=$(wc -c < "$CPK_SECRETS_CHILD_RECORDS/base.tar")
      [ "$parent_export_bytes" -le 268435456 ] || exit 1
      smoke_run base-validator --rm --label "$LABEL_KEY=$RUN_ID" --network none --read-only --tmpfs /tmp:size=16m \
        --cpus 1 --memory 256m --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
        --user "$(id -u):$(id -g)" --workdir / \
        --mount "type=bind,source=$PWD/scripts/grandparent_oci.py,target=/grandparent_oci.py,readonly" \
        --mount "type=bind,source=$CPK_SECRETS_CHILD_RECORDS/base.tar,target=/base.tar,readonly" \
        --mount "type=bind,source=$parent_layout,target=/layout" \
        "$CONTROLLER_IMAGE" python -c '
import json
from grandparent_oci import validate_export
print(json.dumps(validate_export("/base.tar", "/layout",
    "sha256:0d36584018d93305045631a1ee981d5a8850e16fd4532d765eb43a1a823dc095",
    expected_user="10006", expected_entrypoint=("cpk-secrets-entrypoint",),
    expected_cmd=["uvicorn","control_plane_kit_servers_secrets_server.server:create_app","--factory","--host","0.0.0.0","--port","8081"]), sort_keys=True))
' > "$CPK_SECRETS_CHILD_RECORDS/parent-local-base.json"
      PARENT_BASE_VERIFIED=1
      secrets_recipe=products/secrets_server/Dockerfile.parent
      set -- --pull=false --build-context "cpk-secrets-parent-base=oci-layout://$parent_layout@${PARENT_BASE_REFERENCE#*@}"
      CHILD_PHASE=build
      PARENT_BUILD_ATTEMPTED=1
    fi
    docker buildx build --builder "$DOCKER_CONTEXT" --platform linux/amd64 --load "$@" \
      -f "$secrets_recipe" --label "org.opencontainers.image.revision=$CHILD_SOURCE" \
      --label "$LABEL_KEY=$RUN_ID" --label "cpk.test-owner=$CHILD_OWNER" --iidfile "$CPK_SECRETS_CHILD_RECORDS/image.id" \
      --metadata-file "$CPK_SECRETS_CHILD_RECORDS/build-metadata.json" -t "$IMAGE" - \
      < "$CPK_SECRETS_CHILD_RECORDS/source.tar" > "$CPK_SECRETS_CHILD_RECORDS/build.log" 2>&1
    if [ "$PARENT_PROFILE" = 1 ]; then PARENT_BUILD_TERMINATED=1; fi
    IMAGE=$(cat "$CPK_SECRETS_CHILD_RECORDS/image.id")
    child_daemon
    child_source
    docker image inspect "$IMAGE" --format '{"id":{{json .Id}},"repo_digests":{{json .RepoDigests}},"os":{{json .Os}},"architecture":{{json .Architecture}},"user":{{json .Config.User}},"entrypoint":{{json .Config.Entrypoint}},"cmd":{{json .Config.Cmd}}}' \
      > "$CPK_SECRETS_CHILD_RECORDS/image.json"
    jq -e '.os=="linux" and .architecture=="amd64" and .user=="10006" and .entrypoint==["cpk-secrets-entrypoint"] and .cmd==["uvicorn","control_plane_kit_servers_secrets_server.server:create_app","--factory","--host","0.0.0.0","--port","8081"]' \
      "$CPK_SECRETS_CHILD_RECORDS/image.json" >/dev/null
    CHILD_REFERENCE=$(jq -er --slurpfile metadata "$CPK_SECRETS_CHILD_RECORDS/build-metadata.json" \
      '[.repo_digests[]|select(.==("localhost/control-plane-kit-servers/secrets-server@"+$metadata[0]["containerimage.digest"]))]|unique|if length==1 then .[0] else error("missing exact candidate digest") end' \
      "$CPK_SECRETS_CHILD_RECORDS/image.json")
    [ "$(docker image inspect "$CHILD_REFERENCE" --format '{{.Id}}')" = "$IMAGE" ] || exit 1
    if [ "$PARENT_PROFILE" = 1 ]; then
      docker image inspect "$IMAGE" --format '{{json .RootFS.Layers}}' > "$CPK_SECRETS_CHILD_RECORDS/parent-derived-layers.json"
      jq -e --slurpfile base "$CPK_SECRETS_CHILD_RECORDS/parent-local-base.json" \
        'length>=($base[0].rootfs_diff_ids|length) and .[0:($base[0].rootfs_diff_ids|length)]==$base[0].rootfs_diff_ids' \
        "$CPK_SECRETS_CHILD_RECORDS/parent-derived-layers.json" >/dev/null
      PARENT_DERIVED_VERIFIED=1
    fi
    printf '%s\n' "$CHILD_REFERENCE" > "$CPK_SECRETS_CHILD_RECORDS/candidate-reference.txt"
    CHILD_PHASE=installed-provenance
    set --
    if [ "$PARENT_PROFILE" = 1 ]; then set -- --parent; fi
    smoke_run provenance --rm --label "$LABEL_KEY=$RUN_ID" \
      --network none --read-only \
      --mount "type=bind,source=$PWD/products/secrets_server/tests/image_check.py,target=/witness.py,readonly" \
      --mount "type=bind,source=$PWD/coordinates/server-products.json,target=/coordinates.json,readonly" \
      --entrypoint python "$IMAGE" /witness.py /coordinates.json "$@" > "$CPK_SECRETS_CHILD_RECORDS/installed-origins.json"
    PROVENANCE_VERIFIED=1
  else
    docker build -f products/secrets_server/Dockerfile -t "$IMAGE" .
  fi
fi
if [ "$BUILD_CONTROLLER" = "1" ]; then
  docker build -f Dockerfile.test -t "$CONTROLLER_IMAGE" .
fi

if [ "$CHILD_PROFILE" = 1 ]; then
  CONTROL_RECORDS="$CPK_SECRETS_CHILD_RECORDS/private"
  mkdir -m 700 "$CONTROL_RECORDS"
  mkdir -m 700 "$CPK_SECRETS_CHILD_RECORDS/evidence"
else CONTROL_RECORDS="$(mktemp -d)"
fi
chmod 700 "$CONTROL_RECORDS"

if [ "$CHILD_PROFILE" = 1 ]; then
  child_daemon
  (umask 077; : > "$CPK_SECRETS_CHILD_RECORDS/network.attempt")
  docker network create --internal --label "$LABEL_KEY=$RUN_ID" --label "cpk.test-owner=$CHILD_OWNER" "$NETWORK" >/dev/null
  child_network_identity=$(docker network inspect "$NETWORK" --format '{{.Name}}|{{.Driver}}|{{.Scope}}|{{.Internal}}|{{index .Labels "cpk.test-run"}}|{{index .Labels "cpk.test-owner"}}')
  [ "$child_network_identity" = "$NETWORK|bridge|local|true|$RUN_ID|$CHILD_OWNER" ] || exit 1
else docker network create --label "$LABEL_KEY=$RUN_ID" "$NETWORK" >/dev/null
fi
if [ "$CHILD_PROFILE" = 1 ]; then
  for child_volume in "$PROVIDER_BOOTSTRAP" "$CLIENT_BOOTSTRAP" "$DATA_VOLUME"; do child_create_volume "$child_volume"; done
  CHILD_PHASE=exclusive-bootstrap
  for child_volume in "$PROVIDER_BOOTSTRAP" "$CLIENT_BOOTSTRAP" "$DATA_VOLUME"; do child_volume_identity "$child_volume"; done
  set --
  if [ "$PARENT_PROFILE" = 1 ]; then set -- --parent; fi
  smoke_run bootstrap --rm --label "$LABEL_KEY=$RUN_ID" --network none --user 0:0 \
    --mount "type=volume,src=$PROVIDER_BOOTSTRAP,dst=/provider-bootstrap" \
    --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client-bootstrap" \
    --mount "type=volume,src=$DATA_VOLUME,dst=/provider-data" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/child_bootstrap_fixture.py,target=/seed.py,readonly" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/parent_http_roles_fixture.py,target=/parent_http_roles_fixture.py,readonly" \
    --entrypoint python "$IMAGE" /seed.py "$@"
else
docker volume create --label "$LABEL_KEY=$RUN_ID" "$PROVIDER_BOOTSTRAP" >/dev/null
docker volume create --label "$LABEL_KEY=$RUN_ID" "$CLIENT_BOOTSTRAP" >/dev/null
docker volume create --label "$LABEL_KEY=$RUN_ID" "$DATA_VOLUME" >/dev/null

docker run --rm -i --pull "$PRODUCT_PULL_POLICY" \
  --network none \
  --label "$LABEL_KEY=$RUN_ID" \
  --user 0:0 \
  --mount "type=volume,src=$PROVIDER_BOOTSTRAP,dst=/provider-bootstrap" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client-bootstrap" \
  --mount "type=volume,src=$DATA_VOLUME,dst=/provider-data" \
  --entrypoint python \
  "$IMAGE" \
  - <<'PY'
import json
import os
from pathlib import Path
import secrets

from control_plane_kit_secrets.crypto import encode_master_key_for_file

os.umask(0o077)
provider = Path("/provider-bootstrap")
client = Path("/client-bootstrap")
token = secrets.token_urlsafe(48)
provider.joinpath("master.key").write_text(
    encode_master_key_for_file(os.urandom(32)),
    encoding="utf-8",
)
provider.joinpath("credentials.json").write_text(
    json.dumps(
        [
            {
                "subject": "image-smoke-client",
                "token": token,
                "grants": [
                    {
                        "action": "secret.write",
                        "workspace_id": "workspace-image-smoke",
                        "intents": ["postgres.password"],
                    },
                    {
                        "action": "secret.generate-delegation-key",
                        "workspace_id": "workspace-image-smoke",
                        "intents": ["gateway.probe-signing-key"],
                    },
                    {
                        "action": "secret.resolve",
                        "workspace_id": "workspace-image-smoke",
                        "intents": [
                            "gateway.probe-signing-key",
                            "postgres.password",
                        ],
                    },
                    {
                        "action": "secret.revoke",
                        "workspace_id": "workspace-image-smoke",
                        "intents": [],
                    },
                ],
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    ),
    encoding="utf-8",
)
client.joinpath("provider-token").write_text(token, encoding="ascii")
client.joinpath("application-value").write_text(
    secrets.token_urlsafe(40),
    encoding="ascii",
)
for path in provider.iterdir():
    path.chmod(0o400)
    os.chown(path, 10006, 10006)
for path in client.iterdir():
    path.chmod(0o400)
os.chown("/provider-bootstrap", 10006, 10006)
os.chown("/provider-data", 10006, 10006)
PY
fi

start_provider() {
  CHILD_PHASE="$CONTROL_PHASE-startup"
  if [ "$CHILD_PROFILE" = 1 ]; then PROVIDER="$RUN_ID-provider-$CONTROL_PHASE"; fi
  set -- \
    --name "$PROVIDER" \
    --label "$LABEL_KEY=$RUN_ID" \
    --network "$NETWORK" \
    --network-alias secrets-provider \
    --mount "type=volume,src=$PROVIDER_BOOTSTRAP,dst=/run/secrets/cpk-secrets,readonly" \
    --mount "type=volume,src=$DATA_VOLUME,dst=/var/lib/cpk-secrets"
  if [ "$CHILD_PROFILE" = 1 ]; then
    child_track "provider-$CONTROL_PHASE" || return 1
    set -- "$@" --label "cpk.test-owner=$CHILD_OWNER" --cidfile "$CPK_SECRETS_CHILD_RECORDS/provider-$CONTROL_PHASE.cid"
  fi
  if [ "$PROFILE" != published-baseline ]; then
    set -- "$@" --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE/control.json,target=/etc/cpk/secrets-server/control.json,readonly"
  fi
  if [ "$CHILD_PROFILE" = 1 ] || { [ "$PROFILE" = wrapped-source ] && [ "$CONTROL_PHASE" = restart ]; }; then
    set -- "$@" -e CPK_HTTP_VERIFICATION_SAMPLES_CONFIGURATION_FILE=/etc/cpk/secrets-server/http-samples.json \
      --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE/http-samples.json,target=/etc/cpk/secrets-server/http-samples.json,readonly"
  fi
  docker create --pull "$PRODUCT_PULL_POLICY" "$@" "$IMAGE" >/dev/null
  if [ "$CHILD_PROFILE" = 1 ]; then
    child_provider_id=$(cat "$CPK_SECRETS_CHILD_RECORDS/provider-$CONTROL_PHASE.cid")
    child_provider_identity=$(docker inspect "$child_provider_id" --format '{{.Name}}|{{index .Config.Labels "cpk.test-run"}}|{{index .Config.Labels "cpk.test-owner"}}')
    [ "$child_provider_identity" = "/$PROVIDER|$RUN_ID|$CHILD_OWNER" ] || return 1
    PROVIDER=$child_provider_id
  fi
  docker start "$PROVIDER" >/dev/null
  if [ "$PROFILE" = wrapped-artifact ]; then
    root_artifact_verify_container "$PROVIDER" "$CONTROL_RECORDS"
  fi
}

prepare_control() {
  [ "$PROFILE" != published-baseline ] || return 0
  CONTROL_PHASE="$1"
  CHILD_PHASE="$CONTROL_PHASE-prepare-control"
  mkdir -m 700 "$CONTROL_RECORDS/$CONTROL_PHASE"
  set --
  control_generator=generate
  if [ "$CHILD_PROFILE" = 1 ]; then
    control_generator=generate-child
    set -- --pull never --mount "type=bind,source=$PWD/products/secrets_server/tests/source_control_fixture.py,target=/app/products/secrets_server/tests/source_control_fixture.py,readonly"
  fi
  smoke_run "control-$CONTROL_PHASE" "$@" --rm --label "$LABEL_KEY=$RUN_ID" --network none \
    --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE,target=/fixture" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py \
    "$control_generator" /fixture "$RUN_ID"
}

check_control() {
  [ "$PROFILE" != published-baseline ] || return 0
  CHILD_PHASE="$CONTROL_PHASE-source-control"
  smoke_run "check-$CONTROL_PHASE" --pull "$PRODUCT_PULL_POLICY" --rm --label "$LABEL_KEY=$RUN_ID" --user 0:0 --network "$NETWORK" \
    --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE,target=/fixture,readonly" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py check /fixture
  echo "secrets-server $CONTROL_PHASE signed source control passed"
}

prepare_child_samples() {
  SAMPLE_HELPER=$(smoke_run "http-sample-$CONTROL_PHASE" -d \
    --label "$LABEL_KEY=$RUN_ID" --network "$NETWORK" --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$PWD/scripts/http_sample_fixture.py,target=/app/scripts/http_sample_fixture.py,readonly" \
    --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE,target=/fixture" \
    "$CONTROLLER_IMAGE" python scripts/http_sample_fixture.py secrets /fixture all-checks)
  child_prepared=0
  for child_attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if [ -f "$CONTROL_RECORDS/$CONTROL_PHASE/sample.prepared" ]; then child_prepared=1; break; fi
    [ "$(docker inspect --format '{{.State.Running}}' "$SAMPLE_HELPER")" = true ] || break
    sleep 1
  done
  [ "$child_prepared" = 1 ] || return 1
}

check_child_samples() {
  CHILD_PHASE="$CONTROL_PHASE-signed-pair"
  : > "$CONTROL_RECORDS/$CONTROL_PHASE/sample.ready"
  child_completed=0
  child_attempt=1
  while [ "$child_attempt" -le 45 ]; do
    child_sample_state=$(docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}' "$SAMPLE_HELPER")
    if [ "${child_sample_state%%|*}" = exited ]; then child_completed=1; break; fi
    sleep 1
    child_attempt=$((child_attempt + 1))
  done
  [ "$child_completed" = 1 ] && [ "$child_sample_state" = 'exited|0' ] || return 1
  jq -e '.checks|map(.check_id)==["live","ready"]' "$CONTROL_RECORDS/$CONTROL_PHASE/sample.passed" >/dev/null
  jq -e 'all(.checks[];.passed==true and .absent_authority_status==401 and .wrong_issuer_status==401)' \
    "$CONTROL_RECORDS/$CONTROL_PHASE/sample.passed" >/dev/null
  cp "$CONTROL_RECORDS/$CONTROL_PHASE/sample.passed" "$CPK_SECRETS_CHILD_RECORDS/$CONTROL_PHASE-samples.json"
  case "$CONTROL_PHASE" in initial) INITIAL_SAMPLES_VERIFIED=1 ;; restart) RESTART_SAMPLES_VERIFIED=1 ;; esac
  if [ "$INITIAL_SAMPLES_VERIFIED" = 1 ] && [ "$RESTART_SAMPLES_VERIFIED" = 1 ]; then SAMPLES_VERIFIED=1; fi
}

wait_ready() {
  smoke_run "wait-$CONTROL_PHASE" --pull "$PRODUCT_PULL_POLICY" --rm -i \
    --label "$LABEL_KEY=$RUN_ID" \
    --network "$NETWORK" \
    "$CONTROLLER_IMAGE" \
    python - <<'PY'
import time

import httpx

for attempt in range(30):
    try:
        response = httpx.get("http://secrets-provider:8081/health/ready", timeout=1.0)
        if response.status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
else:
    raise SystemExit("secrets-server did not become ready")
PY
}

assert_logs_redacted() {
  CHILD_PHASE="$CONTROL_PHASE-log-redaction"
  (umask 077; : > "$CONTROL_RECORDS/provider.log"; : > "$CONTROL_RECORDS/log.status")
  # The limiter's success cannot hide failed retrieval. The producer records its
  # own exit status, which the checker requires independently of the byte bound.
  if (
    set +e
    docker logs "$PROVIDER" 2>&1
    log_status=$?
    printf '%s\n' "$log_status" > "$CONTROL_RECORDS/log.status"
  ) | head -c 1048577 > "$CONTROL_RECORDS/provider.log"; then
    :
  else
    echo 'Secrets smoke fixture failed' >&2
    return 1
  fi
  set -- logs /fixture /client
  if [ "$PARENT_PROFILE" = 1 ]; then set -- logs-parent /fixture /client; fi
  if [ "$PROFILE" != published-baseline ]; then
    set -- "$@" "/fixture/$CONTROL_PHASE"
  fi
  smoke_run "logs-$CONTROL_PHASE" --pull "$PRODUCT_PULL_POLICY" --rm --label "$LABEL_KEY=$RUN_ID" --user 0:0 --network none \
    --mount "type=bind,source=$CONTROL_RECORDS,target=/fixture,readonly" \
    --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client,readonly" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/source_control_fixture.py,target=/app/products/secrets_server/tests/source_control_fixture.py,readonly" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/parent_http_roles_fixture.py,target=/app/products/secrets_server/tests/parent_http_roles_fixture.py,readonly" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py "$@"
}

check_parent_http_roles() {
  [ "$PARENT_PROFILE" = 1 ] || return 0
  CHILD_PHASE="$CONTROL_PHASE-parent-http-roles"
  smoke_run "parent-http-$CONTROL_PHASE" --rm --label "$LABEL_KEY=$RUN_ID" --user 0:0 \
    --network "$NETWORK" --read-only --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client,readonly" \
    --mount "type=bind,source=$CPK_SECRETS_CHILD_RECORDS/evidence,target=/evidence" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/parent_http_roles_fixture.py,target=/parent_http_roles_fixture.py,readonly" \
    --mount "type=bind,source=$PWD/products/secrets_server/tests/source_control_fixture.py,target=/source_control_fixture.py,readonly" \
    "$CONTROLLER_IMAGE" python /parent_http_roles_fixture.py "$CONTROL_PHASE" \
    > "$CPK_SECRETS_CHILD_RECORDS/$CONTROL_PHASE-parent-http.json"
  case "$CONTROL_PHASE" in initial) PARENT_INITIAL_VERIFIED=1 ;; restart) PARENT_RESTART_VERIFIED=1 ;; esac
}

prepare_control initial
if [ "$CHILD_PROFILE" = 1 ]; then prepare_child_samples; fi
CHILD_PHASE=initial-startup
start_provider
wait_ready
if [ "$CHILD_PROFILE" = 1 ]; then child_runtime; check_child_samples; fi
check_control

CHILD_PHASE=initial-custody
set --
if [ "$CHILD_PROFILE" = 1 ]; then
  set -- --pull never -e CPK_SECRETS_EXACT_VERSION_WITNESS=1 \
    --mount "type=bind,source=$CPK_SECRETS_CHILD_RECORDS/evidence,target=/evidence"
fi
smoke_run custody-initial "$@" --rm -i \
  --label "$LABEL_KEY=$RUN_ID" \
  --network "$NETWORK" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/run/secrets/image-smoke,readonly" \
  "$CONTROLLER_IMAGE" \
  python - <<'PY'
from pathlib import Path
import json
import os

from cryptography.hazmat.primitives import serialization

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
    SecretValue,
)
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsClient,
    SecretProviderBootstrapRegistry,
    SecretProviderClientCode,
    SecretProviderClientError,
)

workspace_id = "workspace-image-smoke"
endpoint = SecretProviderEndpointReference("control-plane-kit")
credential = SecretReference("secret://bootstrap/provider-token")
registry = SecretProviderBootstrapRegistry(
    endpoints={endpoint: "http://secrets-provider:8081"},
    credential_files={
        credential: Path("/run/secrets/image-smoke/provider-token")
    },
)
client = ControlPlaneKitSecretsClient(
    registry.configuration_for(
        endpoint_reference=endpoint,
        credential_reference=credential,
    )
)

application_reference = SecretReference(
    "secret://control-plane-kit/application/postgres-password"
)
application_value = SecretValue(
    Path("/run/secrets/image-smoke/application-value").read_text("ascii")
)
written = client.write(
    workspace_id=workspace_id,
    reference=application_reference,
    value=application_value,
    intent=SecretUseIntent.POSTGRES_PASSWORD,
    caller_subject="image-smoke-client",
    correlation_id="image-smoke-write",
)
assert written.reference == application_reference
if os.environ.get("CPK_SECRETS_EXACT_VERSION_WITNESS") == "1":
    exact = client.resolve(workspace_id=workspace_id, reference=application_reference,
        intent=SecretUseIntent.POSTGRES_PASSWORD, caller_subject="image-smoke-client",
        correlation_id="image-smoke-resolve-written-version", version_id=written.version_id)
    assert exact.metadata.version_id == written.version_id
    assert exact.value.reveal() == application_value.reveal()

delegation_reference = SecretReference(
    "secret://control-plane-kit/gateway/key-b"
)
arguments = {
    "workspace_id": workspace_id,
    "reference": delegation_reference,
    "purpose": DelegationKeyPurpose.GATEWAY_PROBE,
    "issuer": "cpk-server",
    "caller_subject": "cpk-server",
    "correlation_id": "image-smoke-key-b",
}
generated = client.generate_delegation_key(**arguments)
replayed = client.generate_delegation_key(**arguments)
assert not generated.replayed
assert replayed.replayed
assert replayed.metadata == generated.metadata
assert replayed.public_key == generated.public_key

resolved = client.resolve(
    workspace_id=workspace_id,
    reference=delegation_reference,
    intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,
    caller_subject="gateway-probe-signer",
    correlation_id="image-smoke-resolve-b",
    version_id=generated.metadata.version_id,
)
private_key = serialization.load_pem_private_key(
    resolved.value.reveal().encode("ascii"),
    password=None,
)
derived_public = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
assert derived_public == generated.public_key.public_key_pem

revoked = client.revoke_version(
    workspace_id=workspace_id,
    reference=delegation_reference,
    version_id=generated.metadata.version_id,
    version_number=generated.metadata.version_number,
    caller_subject="cpk-server",
    correlation_id="image-smoke-revoke-b",
)
assert revoked.status == "revoked"
try:
    client.resolve(
        workspace_id=workspace_id,
        reference=delegation_reference,
        intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,
        caller_subject="gateway-probe-signer",
        correlation_id="image-smoke-resolve-revoked-b",
        version_id=generated.metadata.version_id,
    )
except SecretProviderClientError as error:
    assert error.code is SecretProviderClientCode.REVOKED
else:
    raise AssertionError("revoked delegation key remained resolvable")

assert "PRIVATE KEY" not in repr(generated)
assert "PRIVATE KEY" not in repr(replayed)
if os.environ.get("CPK_SECRETS_EXACT_VERSION_WITNESS") == "1":
    Path("/evidence/custody-versions.json").write_text(json.dumps({
        "application_version_id":written.version_id,"application_version_number":written.version_number,
        "revoked_version_id":generated.metadata.version_id,
        "revoked_version_number":generated.metadata.version_number,
        "exact_application_resolve_before_restart":True,"revoked_before_restart":True}, sort_keys=True))
print("secrets-server initial contract passed")
PY
INITIAL_VERIFIED=1
check_parent_http_roles

assert_logs_redacted
if [ "$CHILD_PROFILE" = 1 ]; then
  child_daemon
  child_initial_id=$(jq -er .id "$CPK_SECRETS_CHILD_RECORDS/initial-runtime.json")
  [ "$(docker inspect "$child_initial_id" --format '{{index .Config.Labels "cpk.test-run"}}|{{index .Config.Labels "cpk.test-owner"}}')" = "$RUN_ID|$CHILD_OWNER" ] || exit 1
  docker rm -f "$child_initial_id" >/dev/null
  child_remaining=$(docker ps -aq --no-trunc --filter "id=$child_initial_id")
  [ -z "$child_remaining" ] || exit 1
else docker rm -f "$PROVIDER" >/dev/null
fi

prepare_control restart
if [ "$CHILD_PROFILE" = 1 ]; then prepare_child_samples; fi
if [ "$PROFILE" = wrapped-source ]; then
  SAMPLE_HELPER="$(docker run -d --name "$RUN_ID-http-sample" --label "$LABEL_KEY=$RUN_ID" \
    --network "$NETWORK" --read-only --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$CONTROL_RECORDS/restart,target=/fixture" \
    "$CONTROLLER_IMAGE" python scripts/http_sample_fixture.py secrets /fixture)"
  prepared=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if [ -f "$CONTROL_RECORDS/restart/sample.prepared" ]; then prepared=1; break; fi
    [ "$(docker inspect --format '{{.State.Running}}' "$SAMPLE_HELPER")" = true ] || break
    sleep 1
  done
  [ "$prepared" = 1 ] || { echo 'Secrets source HTTP sample preparation failed' >&2; exit 1; }
fi
start_provider
wait_ready
if [ "$CHILD_PROFILE" = 1 ]; then child_runtime; check_child_samples; fi
check_control
if [ "$PROFILE" = wrapped-source ]; then
  : > "$CONTROL_RECORDS/restart/sample.ready"
  sample_completed=0
  sample_attempt=1
  while [ "$sample_attempt" -le 20 ]; do
    sample_state="$(docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}' "$SAMPLE_HELPER")" || exit 1
    if [ "${sample_state%%|*}" = exited ]; then sample_completed=1; break; fi
    sleep 1
    sample_attempt=$((sample_attempt + 1))
  done
  [ "$sample_completed" = 1 ] && [ "$sample_state" = 'exited|0' ] && [ -f "$CONTROL_RECORDS/restart/sample.passed" ] || {
    echo 'Secrets source signed ready sample failed' >&2; exit 1;
  }
  echo 'Secrets source signed named-listener ready sample passed'
fi

CHILD_PHASE=restart-custody
set --
if [ "$CHILD_PROFILE" = 1 ]; then
  set -- --pull never -e CPK_SECRETS_EXACT_VERSION_WITNESS=1 \
    --mount "type=bind,source=$CPK_SECRETS_CHILD_RECORDS/evidence,target=/evidence"
fi
smoke_run custody-restart "$@" --rm -i \
  --label "$LABEL_KEY=$RUN_ID" \
  --network "$NETWORK" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/run/secrets/image-smoke,readonly" \
  "$CONTROLLER_IMAGE" \
  python - <<'PY'
from pathlib import Path
import json
import os

from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
)
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsClient,
    SecretProviderBootstrapRegistry,
    SecretProviderClientCode,
    SecretProviderClientError,
)

endpoint = SecretProviderEndpointReference("control-plane-kit")
credential = SecretReference("secret://bootstrap/provider-token")
reference = SecretReference(
    "secret://control-plane-kit/application/postgres-password"
)
registry = SecretProviderBootstrapRegistry(
    endpoints={endpoint: "http://secrets-provider:8081"},
    credential_files={
        credential: Path("/run/secrets/image-smoke/provider-token")
    },
)
client = ControlPlaneKitSecretsClient(
    registry.configuration_for(
        endpoint_reference=endpoint,
        credential_reference=credential,
    )
)
version_arguments = {}
if os.environ.get("CPK_SECRETS_EXACT_VERSION_WITNESS") == "1":
    versions = json.loads(Path("/evidence/custody-versions.json").read_text())
    version_arguments["version_id"] = versions["application_version_id"]
resolved = client.resolve(
    workspace_id="workspace-image-smoke",
    reference=reference,
    intent=SecretUseIntent.POSTGRES_PASSWORD,
    caller_subject="image-smoke-client",
    correlation_id="image-smoke-resolve-after-restart",
    **version_arguments,
)
expected = Path("/run/secrets/image-smoke/application-value").read_text("ascii")
assert resolved.value.reveal() == expected
if os.environ.get("CPK_SECRETS_EXACT_VERSION_WITNESS") == "1":
    assert resolved.metadata.version_id == versions["application_version_id"]
    try:
        client.resolve(workspace_id="workspace-image-smoke",
            reference=SecretReference("secret://control-plane-kit/gateway/key-b"),
            intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,caller_subject="gateway-probe-signer",
            correlation_id="image-smoke-resolve-revoked-after-restart",version_id=versions["revoked_version_id"])
    except SecretProviderClientError as error:
        assert error.code is SecretProviderClientCode.REVOKED
    else:
        raise AssertionError("revoked delegation version became resolvable after restart")
    Path("/evidence/restart-custody.json").write_text(json.dumps({
        "application_version_id":resolved.metadata.version_id,"exact_material_retained":True,
        "revoked_version_id":versions["revoked_version_id"],"revoked_after_restart":True,
        "restart_kind":"forced-container-replacement"}, sort_keys=True))
print("secrets-server restart contract passed")
PY
RESTART_VERIFIED=1
check_parent_http_roles

assert_logs_redacted
LOGS_VERIFIED=1
if [ "$PARENT_PROFILE" = 1 ]; then
  [ "$PARENT_INITIAL_VERIFIED" = 1 ] && [ "$PARENT_RESTART_VERIFIED" = 1 ] &&
    [ "$PARENT_BASE_VERIFIED" = 1 ] && [ "$PARENT_DERIVED_VERIFIED" = 1 ] || exit 1
fi
if [ "$CHILD_PROFILE" = 1 ]; then child_daemon; child_source; CHILD_PHASE=complete; fi
