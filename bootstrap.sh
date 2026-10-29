#!/bin/sh
# External root acquisition using ordinary Docker. No host Python or Compose.
set -eu
usage() {
  echo 'usage: bootstrap.sh plan DRIVER INPUT | apply DRIVER PLAN DIGEST INDEX STATE | inspect DRIVER STATE | inspect-initialization DRIVER PLAN DIGEST INDEX STATE | commission-plan DRIVER INPUT | commission-prepare DRIVER PLAN DIGEST STATE' >&2
  exit 2
}
[ "$#" -ge 2 ] || usage
ACTION="$1"
DRIVER="$2"
shift 2
case "$DRIVER" in sha256:*) ;; *) echo 'driver must be an explicit local image ID' >&2; exit 2 ;; esac
# Never pull or retarget a mutable driver tag.
[ "$(docker image inspect --format '{{.Id}}' "$DRIVER")" = "$DRIVER" ]
commission_hold() {
  echo 'root commissioning custody requires investigation' >&2
  exit 2
}
commission_directory() {
  # Only the explicitly selected hierarchy is eligible for creation. Never
  # normalize away symlinks, dot components, foreign owners or broad modes.
  case "$1" in /*) ;; *) commission_hold ;; esac
  case "$1" in /|*/|*//*|*/./*|*/../*|*/.|*/..|*,*) commission_hold ;; esac
  commission_cr="$(printf '\r')"
  case "$1" in *'
'*|*"$commission_cr"*) commission_hold ;; esac
  commission_uid="$(id -u)"
  commission_gid="$(id -g)"
  commission_remaining="${1#/}"
  commission_path=""
  umask 077
  while [ -n "$commission_remaining" ]; do
    commission_component="${commission_remaining%%/*}"
    if [ "$commission_remaining" = "$commission_component" ]; then
      commission_remaining=""
    else
      commission_remaining="${commission_remaining#*/}"
    fi
    commission_path="$commission_path/$commission_component"
    [ ! -L "$commission_path" ] || commission_hold
    if [ ! -e "$commission_path" ]; then
      mkdir -m 700 -- "$commission_path" || commission_hold
    fi
    [ -d "$commission_path" ] || commission_hold
    commission_metadata="$(stat -c '%u %g %a' -- "$commission_path" 2>/dev/null ||
      stat -f '%u %g %Lp' "$commission_path" 2>/dev/null)" || commission_hold
    # stat returns only the three numeric fields, never user-provided text.
    set -- $commission_metadata
    [ "$#" = 3 ] || commission_hold
    case "$1:$2:$3" in *[!0-9:]*) commission_hold ;; esac
    [ "$1" = "$commission_uid" ] || [ "$1" = 0 ] || commission_hold
    [ "$((0$3 & 0022))" = 0 ] || commission_hold
    if [ -z "$commission_remaining" ]; then
      [ "$1:$2:$3" = "$commission_uid:$commission_gid:700" ] || commission_hold
    fi
  done
}
case "$ACTION" in
  commission-plan)
    [ "$#" = 1 ] || usage
    INPUT="$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
    exec docker run --rm --network none --read-only --cap-drop ALL --user "$(id -u):$(id -g)" \
      --security-opt no-new-privileges --mount "type=bind,source=$INPUT,target=/bootstrap/input.json,readonly" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.root_commissioning plan \
      --input /bootstrap/input.json --preparer "$DRIVER"
    ;;
  commission-prepare)
    [ "$#" = 3 ] || usage
    PLAN="$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
    DIGEST="$2"
    STATE="$3"
    commission_directory "$STATE"
    exec docker run --rm --network none --read-only --cap-drop ALL --user "$(id -u):$(id -g)" \
      --security-opt no-new-privileges \
      --mount "type=bind,source=$PLAN,target=/bootstrap/plan.json,readonly" \
      --mount "type=bind,source=$STATE,target=/commissioning" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.root_commissioning prepare \
      --plan /bootstrap/plan.json --digest "$DIGEST" --preparer "$DRIVER" \
      --state /commissioning --host-state "$STATE"
    ;;
  plan)
    [ "$#" = 1 ] || usage
    INPUT="$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
    exec docker run --rm --network none --read-only --cap-drop ALL --user "$(id -u):$(id -g)" \
      --security-opt no-new-privileges --mount "type=bind,source=$INPUT,target=/bootstrap/input.json,readonly" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli plan \
      --input /bootstrap/input.json --driver "$DRIVER"
    ;;
  apply|inspect|inspect-initialization)
    [ -z "${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ] || usage
    ENDPOINT="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
    case "$ENDPOINT" in unix:///*) ;; *) echo 'bootstrap requires a local Unix Docker context' >&2; exit 2 ;; esac
    ENGINE="$(docker info --format '{{.ID}}')"
    [ -n "$ENGINE" ]
    if [ "$ACTION" != inspect ]; then
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
    if [ "$ACTION" != inspect ]; then
      exec docker run --rm --network none \
        --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
        --mount "type=bind,source=$PLAN,target=/bootstrap/plan.json,readonly" \
        --mount "type=bind,source=$MATERIAL,target=/material,readonly" \
        --mount "type=bind,source=$STATE,target=/state" -e "CPK_BOOTSTRAP_ENGINE_ID=$ENGINE" \
        "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli "$ACTION" \
        --plan /bootstrap/plan.json --driver "$DRIVER" --digest "$DIGEST" --index "/material/$INDEX" --state /state
    fi
    exec docker run --rm --network none \
      --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
      --mount "type=bind,source=$STATE,target=/state,readonly" \
      "$DRIVER" python -m control_plane_kit_servers_cpk_server.bootstrap_cli inspect --state /state
    ;;
  *) usage ;;
esac
