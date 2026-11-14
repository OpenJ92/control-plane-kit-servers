#!/bin/bash
# Read-only metadata collection. No service/helper lifecycle or credential input.
set -euo pipefail
set +x
exec 2>/dev/null
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
stage=arguments
output=''
final_reported=0
query_pid='' timer_pid='' error_pid=''
finish() {
  code=$?
  if [ "${BASH_SUBSHELL:-0}" != 0 ]; then exit "$code"; fi
  trap - EXIT HUP INT TERM
  for pid in "$query_pid" "$timer_pid" "$error_pid"; do
    if [ -n "$pid" ]; then kill -TERM "$pid" 2>/dev/null || :; wait "$pid" 2>/dev/null || :; fi
  done
  if [ -n "$output" ]; then
    rm -f -- "$output/query.out" "$output/query.err" "$output/stderr-present"
  fi
  if [ "$code" != 0 ] && [ "$final_reported" = 0 ]; then
    printf '{"schema":"cpk399.reset-inventory-launch.v1","status":"HOLD","stage":"%s","retry":false,"service_mutation":false,"credential_use":false}\n' "$stage"
  fi
  exit "$code"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
[ "$#" = 2 ] || exit 2
ACTION=$1 EXPECTED=$2
case "$ACTION" in /*) ;; *) exit 2 ;; esac
[ -f "$ACTION" ] && [ ! -L "$ACTION" ] || exit 2
[[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]] || exit 2
digest() { local value; value=$(shasum -a 256 "$1"); printf '%s' "${value%% *}"; }
[ "$(digest "$ACTION")" = "$EXPECTED" ] || exit 2
jq -e '.schema=="cpk399.reset-inventory-approval.v1" and .approved==true and
 .optional_path_comparison==false and (.review_reference|type=="string" and length>0) and
 (.source_commit|test("^[0-9a-f]{40}$")) and
 ([.runner_sha256,.reducer_sha256,.daemon_sha256,.manifest_sha256,.plan_sha256,.queries_sha256]|
 all(type=="string" and test("^[0-9a-f]{64}$")))' "$ACTION" >/dev/null
[ -z "$(git status --porcelain)" ] || exit 2
[ "$(git rev-parse HEAD)" = "$(jq -r .source_commit "$ACTION")" ] || exit 2
for pair in 'runner_sha256 scripts/grandparent_reset_inventory.sh' 'reducer_sha256 scripts/grandparent_reset_inventory.jq' 'daemon_sha256 scripts/docker_witness_daemon.sh'; do
  read -r key path <<< "$pair"
  [ "$(digest "$path")" = "$(jq -r --arg key "$key" '.[$key]' "$ACTION")" ] || exit 2
done
MANIFEST=$(jq -r .manifest "$ACTION")
PLAN=$(jq -r .plan "$ACTION")
QUERIES=$(jq -r .queries "$ACTION")
for pair in 'manifest_sha256 manifest' 'plan_sha256 plan' 'queries_sha256 queries'; do
  read -r key field <<< "$pair"
  path=$(jq -r --arg field "$field" '.[$field]' "$ACTION")
  case "$path" in /*) ;; *) exit 2 ;; esac
  [ -f "$path" ] && [ ! -L "$path" ] || exit 2
  [ "$(digest "$path")" = "$(jq -r --arg key "$key" '.[$key]' "$ACTION")" ] || exit 2
done
jq -e '.schema=="cpk399.reset-inventory-proposal.v1" and .executable==false and
 .authority.live_queries_approved==false and .named_volume_scope.can_satisfy_retirement_exclusivity==false' "$PLAN" >/dev/null
jq -e '.schema=="cpk399.reset-inventory-query-shapes.v1" and .executable==false and
 .revision.can_satisfy_retirement_exclusivity==false' "$QUERIES" >/dev/null
output=$(jq -r .output_directory "$ACTION")
case "$output" in /private/tmp/cpk399-reset-inventory-*|/tmp/cpk399-reset-inventory-*) ;; *) output=''; exit 2 ;; esac
case "$output" in *'/../'*|*'/./'*|*','*|*$'\n'*|*' '*|*'/' ) output=''; exit 2 ;; esac
[ ! -e "$output" ] && [ ! -L "$output" ] || { output=''; exit 2; }
umask 077
mkdir -m 700 "$output"
mkfifo -m 600 "$output/query.out" "$output/query.err"
started=$(date +%s)
docker_reads=0 host_reads=0

# Only the exact owned CLI child is signalled on timeout, never a service PID.
# FIFOs carry transient projections; only a stderr-presence boolean is stored.
read_query() {
  local kind=$1 limit=$2 remaining duration rc errors bytes
  shift 2
  remaining=$((300 - $(date +%s) + started))
  [ "$remaining" -gt 0 ] || return 1
  duration=30; [ "$remaining" -ge 30 ] || duration=$remaining
  case "$kind" in
    docker) docker_reads=$((docker_reads+1)); [ "$docker_reads" -le 160 ] || return 1 ;;
    host) host_reads=$((host_reads+1)); [ "$host_reads" -le 4 ] || return 1 ;;
  esac
  ( head -c 1 < "$output/query.err" | wc -c ) > "$output/stderr-present" & error_pid=$!
  "$@" > "$output/query.out" 2> "$output/query.err" & query_pid=$!
  ( sleeper=''
    trap '[ -z "$sleeper" ] || kill -TERM "$sleeper" 2>/dev/null; exit 0' TERM INT HUP
    sleep "$duration" & sleeper=$!; wait "$sleeper"
    kill -TERM "$query_pid" 2>/dev/null || :
    sleep 1 & sleeper=$!; wait "$sleeper"
    kill -KILL "$query_pid" 2>/dev/null || : ) & timer_pid=$!
  set +e
  value=$(head -c "$((limit+1))" < "$output/query.out")
  wait "$query_pid"; rc=$?
  kill -TERM "$timer_pid" 2>/dev/null; wait "$timer_pid" 2>/dev/null
  wait "$error_pid"
  set -e
  query_pid='' timer_pid='' error_pid=''
  errors=$(tr -d '[:space:]' < "$output/stderr-present")
  bytes=$(LC_ALL=C printf '%s' "$value" | wc -c)
  [ "$errors" = 0 ] && [ "$bytes" -le "$limit" ] || return 1
  if [ "$kind" = host ] && [ "$rc" = 1 ] && [ -z "$value" ]; then return 0; fi
  [ "$rc" = 0 ]
}
reduce() {
  jq -ce --arg mode "$1" --slurpfile manifest "$MANIFEST" --slurpfile plan "$PLAN" \
    --slurpfile action "$ACTION" \
    --arg approval_sha256 '' --arg source '' --arg started '' --arg finished '' \
    -f scripts/grandparent_reset_inventory.jq
}
emit() { printf '%s\n' "$1"; }
project_emit() { local record; record=$(reduce "$1"); emit "$record"; }
enumerate() {
  read_query docker 9000 docker container ls --all --quiet --no-trunc
  ids=$(printf '%s' "$value" | jq -Rsc 'split("\n")|map(select(length>0))')
  printf '%s' "$ids" | reduce ids >/dev/null
  read_query docker 32768 docker volume ls --filter label=org.openj92.cpk.installation=cpk163-gparent-20261109 --format '{{json .Name}}'
  volumes=$(printf '%s' "$value" | jq -sc '.')
  read_query docker 9000 docker network ls --no-trunc --filter label=org.openj92.cpk.installation=cpk163-gparent-20261109 --format '{{json .ID}}'
  networks=$(printf '%s' "$value" | jq -sc '.')
  jq -cn --argjson ids "$ids" --argjson volumes "$volumes" --argjson networks "$networks" \
    '{kind:"sets",ids:$ids,volumes:$volumes,networks:$networks}' | reduce sets
}
CONTAINER='{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"state":{{json .State.Status}},"running":{{json .State.Running}},"paused":{{json .State.Paused}},"restarting":{{json .State.Restarting}},"dead":{{json .State.Dead}},"stop_signal":{{json .Config.StopSignal}},"network_mode":{{json .HostConfig.NetworkMode}},"ownership":{"org.openj92.cpk.installation":{{json (index .Config.Labels "org.openj92.cpk.installation")}},"org.openj92.cpk.acquisition":{{json (index .Config.Labels "org.openj92.cpk.acquisition")}},"org.openj92.cpk.bootstrap":{{json (index .Config.Labels "org.openj92.cpk.bootstrap")}},"org.openj92.cpk.maintenance":{{json (index .Config.Labels "org.openj92.cpk.maintenance")}},"org.openj92.cpk.replaces":{{json (index .Config.Labels "org.openj92.cpk.replaces")}}},"mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}{"type":{{json $m.Type}},"name":{{if eq $m.Type "volume"}}{{json $m.Name}}{{else}}null{{end}},"target":{{json $m.Destination}},"rw":{{json $m.RW}}}{{end}}],"configured_mounts":[{{range $i,$m := .HostConfig.Mounts}}{{if $i}},{{end}}{"type":{{json $m.Type}},"name":{{if eq $m.Type "volume"}}{{json $m.Source}}{{else}}null{{end}},"target":{{json $m.Target}}}{{end}}],"binds":{{json .HostConfig.Binds}},"volumes_from":{{json .HostConfig.VolumesFrom}},"networks":[{{$sep := ""}}{{range $name,$n := .NetworkSettings.Networks}}{{$sep}}{{$sep = ","}}{"name":{{json $name}},"id":{{json $n.NetworkID}},"aliases":{{json $n.Aliases}}}{{end}}],"configured_ports":{{json .HostConfig.PortBindings}},"ports":{{json .NetworkSettings.Ports}}}'
VOLUME='{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"options_empty":{{if .Options}}false{{else}}true{{end}},"ownership":{"org.openj92.cpk.installation":{{json (index .Labels "org.openj92.cpk.installation")}},"org.openj92.cpk.acquisition":{{json (index .Labels "org.openj92.cpk.acquisition")}},"org.openj92.cpk.bootstrap":{{json (index .Labels "org.openj92.cpk.bootstrap")}}}}'
NETWORK='{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"internal":{{json .Internal}},"attachable":{{json .Attachable}},"ingress":{{json .Ingress}},"config_only":{{json .ConfigOnly}},"config_from_empty":{{if .ConfigFrom.Network}}false{{else}}true{{end}},"ownership":{"org.openj92.cpk.installation":{{json (index .Labels "org.openj92.cpk.installation")}},"org.openj92.cpk.acquisition":{{json (index .Labels "org.openj92.cpk.acquisition")}},"org.openj92.cpk.bootstrap":{{json (index .Labels "org.openj92.cpk.bootstrap")}}},"members":[{{$sep := ""}}{{range $id,$v := .Containers}}{{$sep}}{{$sep = ","}}{{json $id}}{{end}}]}'
IMAGE='{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}},"repo_digests":{{json .RepoDigests}},"user":{{json .Config.User}},"stop_signal":{{json .Config.StopSignal}}}'

collect() {
  stage=admission
  [ "${DOCKER_CONTEXT:-}" = desktop-linux ]
  [ -z "${DOCKER_HOST:-}${DOCKER_TLS:-}${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ]
  # Use the existing admission function, routing each of its Docker reads through
  # the same deadline/output/stderr guard rather than bypassing it.
  docker() { read_query docker 4096 command docker "$@" || return 1; printf '%s\n' "$value"; }
  . ./scripts/docker_witness_daemon.sh
  docker_witness_daemon
  unset -f docker
  [ "$DOCKER_CONTEXT" = desktop-linux ]
  [ "$image_witness_daemon" = "$(jq -r .engine_id "$MANIFEST")" ]
  emit '{"kind":"admission","engine_matches":true}'
  stage=opening-sets
  opening=$(set -e; enumerate); emit "$opening"
  stage=containers
  while IFS= read -r identity; do
    read_query docker 65536 docker inspect --type container "$identity" --format "$CONTAINER"
    projected=$(printf '%s' "$value" | reduce container)
    [ "$(printf '%s' "$projected" | jq -r .id)" = "$identity" ]
    emit "$projected"
  done < <(printf '%s' "$opening" | jq -r '.ids[]')
  stage=volumes
  while IFS= read -r name; do
    read_query docker 4096 docker volume inspect "$name" --format "$VOLUME"
    printf '%s' "$value" | project_emit volume
  done < <(jq -r '.volume_candidates[].name' "$MANIFEST")
  stage=network
  read_query docker 16384 docker network inspect "$(jq -r .network_candidate.id "$MANIFEST")" --format "$NETWORK"
  printf '%s' "$value" | project_emit network
  stage=image-cache
  while IFS= read -r reference; do
    read_query docker 16384 docker image inspect "$reference" --format "$IMAGE"
    printf '%s' "$value" | jq -c --arg reference "$reference" '.+{reference:$reference}' | project_emit image
  done < <(jq -r '.ordered_queries[]|select(.stage=="five-fresh-image-cache-checks")|.images[].reference' "$PLAN")
  stage=local-listeners
  for port in 18163 18164; do
    read_query host 32768 lsof -nP "-iTCP:$port" -sTCP:LISTEN -F pcfn
    printf '%s' "$value" | jq -Rsc --arg port "$port" '{kind:"listener",port:$port,lines:split("\n")}' | project_emit listener
  done
  stage=visible-forwarders
  read_query host 1048576 ps -axo pid=,ppid=,comm=
  printf '%s' "$value" | jq -Rsc '{kind:"processes",lines:split("\n")}' | project_emit processes
  stage=closing-sets
  closing=$(set -e; enumerate); emit "$closing"
  read_query docker 4096 docker info --format '{{.ID}}'
  [ "$value" = "$image_witness_daemon" ]
  [ "$(( $(date +%s) - started ))" -le 300 ]
  jq -cn --arg finished "$(date +%s)" '{kind:"complete",engine_matches:true,finished:$finished}'
}
stage=collection
set +e
( trap 'rc=$?; if [ "$rc" != 0 ]; then printf "{\"kind\":\"failure\",\"stage\":\"%s\"}\n" "$stage"; fi' EXIT
  set -e; collect ) | jq -cse --slurpfile manifest "$MANIFEST" --slurpfile plan "$PLAN" --slurpfile action "$ACTION" \
  --arg mode report --arg approval_sha256 "$EXPECTED" --arg source "$(git rev-parse HEAD)" \
  --arg started "$started" --arg finished "$(date +%s)" -f scripts/grandparent_reset_inventory.jq \
  | head -c 262145 > "$output/report.json"
rc=$?
set -e
[ "$(wc -c < "$output/report.json")" -le 262144 ] || exit 1
jq -e '.schema=="cpk399.reset-inventory-observation.v1" and (.status=="observed" or .status=="HOLD")' "$output/report.json" >/dev/null
cat "$output/report.json"
final_reported=1
[ "$rc" = 0 ] || exit 1
jq -e '.schema=="cpk399.reset-inventory-observation.v1" and .status=="observed" and
 .backing_path_bind_access=="unresolved" and .external_routing=="unresolved" and
 .can_satisfy_retirement_exclusivity==false' "$output/report.json" >/dev/null
stage=report
