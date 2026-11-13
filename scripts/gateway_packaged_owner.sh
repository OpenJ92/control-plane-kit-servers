# Private resource bookkeeping for the #163 gateway image witness only.
# Sourcing declares functions; it performs no effects.
GW_ROLES='provenance bootstrap postgres cpk secrets gateway signer readiness logs'

gw_daemon() {
  gw_observed=$(docker info --format '{{.ID}}') || return 1
  [ "$gw_observed" = "$GW_DAEMON" ]
}

gw_track() {
  case " $GW_ROLES " in *" $1 "*) ;; *) return 1 ;; esac
  (umask 077; : > "$GW_RECORDS/$1.attempt")
}

gw_run() {
  gw_role=$1
  shift
  gw_daemon || return 1
  gw_track "$gw_role" || return 1
  docker run --pull never --name "$GW_RUN-$gw_role" --cidfile "$GW_RECORDS/$gw_role.cid" \
    --label "cpk.test-run=$GW_RUN" --label "cpk.test-owner=$GW_OWNER" "$@"
}

gw_volume_identity() {
  gw_signature=$(docker volume inspect "$1" --format '{{.Name}}|{{.Driver}}|{{.Scope}}|{{index .Labels "cpk.test-run"}}|{{index .Labels "cpk.test-owner"}}|{{len .Options}}') || return 1
  [ "$gw_signature" = "$1|local|local|$GW_RUN|$GW_OWNER|0" ]
}

gw_volume_create() {
  gw_volume=$1
  gw_daemon || return 1
  (umask 077; : > "$GW_RECORDS/$gw_volume.volume-attempt") || return 1
  gw_created=$(docker volume create --label "cpk.test-run=$GW_RUN" --label "cpk.test-owner=$GW_OWNER" "$gw_volume") || return 1
  [ "$gw_created" = "$gw_volume" ] || return 1
  gw_volume_identity "$gw_volume"
}

gw_network_identity() {
  gw_signature=$(docker network inspect "$1" --format '{{.Name}}|{{.Driver}}|{{.Scope}}|{{.Internal}}|{{index .Labels "cpk.test-run"}}|{{index .Labels "cpk.test-owner"}}') || return 1
  [ "$gw_signature" = "$GW_RUN|bridge|local|true|$GW_RUN|$GW_OWNER" ]
}

gw_wait_signer() {
  gw_signer_id=$(cat "$GW_RECORDS/signer.cid") || return 1
  gw_attempt=1
  while [ "$gw_attempt" -le 90 ]; do
    gw_signer_state=$(docker inspect "$gw_signer_id" --format '{{.State.Status}}|{{.State.ExitCode}}') || return 1
    if [ "${gw_signer_state%%|*}" = exited ]; then
      [ "$gw_signer_state" = 'exited|0' ]
      return $?
    fi
    sleep 1
    gw_attempt=$((gw_attempt+1))
  done
  return 1
}

gw_cleanup() {
  [ "$GW_RESERVED" = 1 ] || return 0
  gw_failed=0
  gw_daemon || return 1
  for gw_role in $GW_ROLES; do
    [ -f "$GW_RECORDS/$gw_role.attempt" ] || continue
    gw_name="$GW_RUN-$gw_role"
    gw_id=$(docker ps -aq --no-trunc --filter "name=^/$gw_name$") || { gw_failed=1; continue; }
    [ -n "$gw_id" ] || continue
    [ "${#gw_id}" = 64 ] || { gw_failed=1; continue; }
    case "$gw_id" in *[!0-9a-f]*) gw_failed=1; continue ;; esac
    if [ -s "$GW_RECORDS/$gw_role.cid" ]; then
      gw_captured=$(cat "$GW_RECORDS/$gw_role.cid") || { gw_failed=1; continue; }
      [ "$gw_captured" = "$gw_id" ] || { gw_failed=1; continue; }
    fi
    gw_identity=$(docker inspect "$gw_id" --format '{{.Name}}|{{index .Config.Labels "cpk.test-run"}}|{{index .Config.Labels "cpk.test-owner"}}') || { gw_failed=1; continue; }
    [ "$gw_identity" = "/$gw_name|$GW_RUN|$GW_OWNER" ] || { gw_failed=1; continue; }
    gw_daemon || return 1
    docker rm -f "$gw_id" >/dev/null 2>&1 || gw_failed=1
    gw_left=$(docker ps -aq --no-trunc --filter "id=$gw_id") || { gw_failed=1; continue; }
    [ -z "$gw_left" ] || gw_failed=1
  done
  for gw_volume in $GW_VOLUMES; do
    [ -f "$GW_RECORDS/$gw_volume.volume-attempt" ] || continue
    gw_present=$(docker volume ls -q --filter "name=$gw_volume") || { gw_failed=1; continue; }
    [ -n "$gw_present" ] || continue
    [ "$gw_present" = "$gw_volume" ] || { gw_failed=1; continue; }
    gw_volume_identity "$gw_volume" || { gw_failed=1; continue; }
    gw_holders=$(docker ps -aq --filter "volume=$gw_volume") || { gw_failed=1; continue; }
    [ -z "$gw_holders" ] || { gw_failed=1; continue; }
    gw_daemon || return 1
    docker volume rm "$gw_volume" >/dev/null 2>&1 || gw_failed=1
    gw_left=$(docker volume ls -q --filter "name=$gw_volume") || { gw_failed=1; continue; }
    [ -z "$gw_left" ] || gw_failed=1
  done
  if [ -f "$GW_RECORDS/network.attempt" ]; then
    gw_network=$(docker network ls --no-trunc -q --filter "name=^$GW_RUN$") || return 1
    if [ -n "$gw_network" ]; then
      gw_network_identity "$gw_network" || return 1
      gw_daemon || return 1
      docker network rm "$gw_network" >/dev/null 2>&1 || gw_failed=1
      gw_left=$(docker network ls -q --filter "id=$gw_network") || return 1
      [ -z "$gw_left" ] || gw_failed=1
    fi
  fi
  for gw_kind in container volume network; do
    case "$gw_kind" in container) set -- ps -aq ;; volume) set -- volume ls -q ;; network) set -- network ls -q ;; esac
    gw_left=$(docker "$@" --filter "label=cpk.test-run=$GW_RUN") || { gw_failed=1; continue; }
    [ -z "$gw_left" ] || gw_failed=1
  done
  return "$gw_failed"
}
