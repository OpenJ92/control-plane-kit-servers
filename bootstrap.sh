#!/bin/sh
# External root acquisition using ordinary Docker. No host Python or Compose.
set -eu
usage() {
  echo 'usage: bootstrap.sh plan DRIVER INPUT | apply DRIVER PLAN DIGEST INDEX STATE | inspect DRIVER STATE' >&2
  exit 2
}
[ "$#" -ge 2 ] || usage
ACTION="$1"
DRIVER="$2"
shift 2
case "$DRIVER" in sha256:*) ;; *) echo 'driver must be an explicit local image ID' >&2; exit 2 ;; esac
# Never pull or retarget a mutable driver tag.
[ "$(docker image inspect --format '{{.Id}}' "$DRIVER")" = "$DRIVER" ]
case "$ACTION" in
  plan)
    [ "$#" = 1 ] || usage
    INPUT="$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
    exec docker run --rm --network none --read-only --cap-drop ALL --user "$(id -u):$(id -g)" \
      --security-opt no-new-privileges --mount "type=bind,source=$INPUT,target=/bootstrap/input.json,readonly" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli plan \
      --input /bootstrap/input.json --driver "$DRIVER"
    ;;
  apply|inspect)
    [ -z "${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ] || usage
    ENDPOINT="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
    case "$ENDPOINT" in unix:///*) ;; *) echo 'bootstrap requires a local Unix Docker context' >&2; exit 2 ;; esac
    ENGINE="$(docker info --format '{{.ID}}')"
    [ -n "$ENGINE" ]
    if [ "$ACTION" = apply ]; then
      [ "$#" = 4 ] || usage
      PLAN="$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
      DIGEST="$2"
      MATERIAL="$(CDPATH= cd -- "$(dirname -- "$3")" && pwd)"
      INDEX="$(basename -- "$3")"
      STATE="$4"
    else
      [ "$#" = 1 ] || usage
      STATE="$1"
    fi
    umask 077
    mkdir -p -- "$STATE"
    STATE="$(CDPATH= cd -- "$STATE" && pwd)"
    if [ "$ACTION" = apply ]; then
      exec docker run --rm --network none \
        --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
        --mount "type=bind,source=$PLAN,target=/bootstrap/plan.json,readonly" \
        --mount "type=bind,source=$MATERIAL,target=/material,readonly" \
        --mount "type=bind,source=$STATE,target=/state" -e "CPK_BOOTSTRAP_ENGINE_ID=$ENGINE" \
        "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli apply \
        --plan /bootstrap/plan.json --driver "$DRIVER" --digest "$DIGEST" --index "/material/$INDEX" --state /state
    fi
    exec docker run --rm --network none \
      --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
      --mount "type=bind,source=$STATE,target=/state,readonly" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli inspect --state /state
    ;;
  *) usage ;;
esac
