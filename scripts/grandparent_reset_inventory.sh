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
owns_output=0 worker=0
query_pid='' error_pid=''
finish() {
  code=$?
  if [ "${BASH_SUBSHELL:-0}" != 0 ]; then exit "$code"; fi
  trap - EXIT HUP INT TERM
  # Only the reservation owner cleans files, after its supervisor has quiesced
  # the complete worker process group. No raw numeric PID signals in Bash.
  if [ "$owns_output" = 1 ]; then
    rm -f -- "$output/query.out" "$output/query.err" "$output/records" "$output/stderr-present" "$output/worker.expected"
    rmdir -- "$output/worker.claimed" 2>/dev/null || :
  fi
  if [ "$code" != 0 ] && [ "$final_reported" = 0 ]; then
    printf '{"schema":"cpk399.reset-inventory-launch.v1","status":"HOLD","stage":"%s","retry":false,"service_mutation":false,"credential_use":false}\n' "$stage"
  fi
  exit "$code"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
if [ "${1:-}" = --worker ]; then worker=1; shift; fi
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
 ([.runner_sha256,.reducer_sha256,.supervisor_sha256,.daemon_sha256,.manifest_sha256,.plan_sha256,.queries_sha256]|
 all(type=="string" and test("^[0-9a-f]{64}$")))' "$ACTION" >/dev/null
[ -z "$(git status --porcelain)" ] || exit 2
[ "$(git rev-parse HEAD)" = "$(jq -r .source_commit "$ACTION")" ] || exit 2
for pair in 'runner_sha256 scripts/grandparent_reset_inventory.sh' 'reducer_sha256 scripts/grandparent_reset_inventory.jq' 'supervisor_sha256 scripts/grandparent_metadata_supervisor.pl' 'daemon_sha256 scripts/docker_witness_daemon.sh'; do
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
umask 077
if [ "$worker" = 0 ]; then
  [ ! -e "$output" ] && [ ! -L "$output" ] || exit 2
  mkdir -m 700 "$output"
  owns_output=1
  mkfifo -m 600 "$output/query.out" "$output/query.err" "$output/records"
  nonce=$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')
  [[ "$nonce" =~ ^[0-9a-f]{64}$ ]] || exit 2
  printf '%s' "$nonce" | shasum -a 256 | cut -d ' ' -f 1 > "$output/worker.expected"
  exec 9<<< "$nonce"
  unset nonce
  stage=collection
  code=0
  perl scripts/grandparent_metadata_supervisor.pl group 300 -- bash "$0" --worker "$ACTION" "$EXPECTED" >/dev/null || code=$?
  exec 9<&-
  if [ "$code" = 124 ]; then stage=phase-deadline; fi
  if [ ! -s "$output/report.json" ] || [ "$(wc -c < "$output/report.json")" -gt 262144 ] ||
     ! jq -e '.schema=="cpk399.reset-inventory-observation.v1" and (.status=="observed" or .status=="HOLD")' "$output/report.json" >/dev/null ||
     { [ "$code" != 0 ] && jq -e '.status=="observed"' "$output/report.json" >/dev/null; }; then
    printf '{"schema":"cpk399.reset-inventory-observation.v1","status":"HOLD","stage":"%s","failure_category":"supervised-collection-refused","retry":false,"service_mutation":false,"credential_use":false,"backing_path_bind_access":"unresolved","external_routing":"unresolved","can_satisfy_retirement_exclusivity":false}\n' "$stage" > "$output/report.json"
    code=1
  fi
  cat "$output/report.json"
  final_reported=1
  [ "$code" = 0 ] && jq -e '.status=="observed"' "$output/report.json" >/dev/null || exit 1
  exit 0
fi
[ -d "$output" ] && [ ! -L "$output" ] && [ -p "$output/records" ] || exit 2
# Only the reserving parent provides this anonymous, single-use capability.
# It is not an application credential and is never returned in the report.
IFS= read -r nonce <&9 || exit 2
exec 9<&-
[[ "$nonce" =~ ^[0-9a-f]{64}$ ]] || exit 2
[ -f "$output/worker.expected" ] && [ ! -L "$output/worker.expected" ] || exit 2
nonce_hash=$(printf '%s' "$nonce" | shasum -a 256); nonce_hash=${nonce_hash%% *}
unset nonce
[ "$nonce_hash" = "$(cat "$output/worker.expected")" ] || exit 2
mkdir -m 700 "$output/worker.claimed"
rm -- "$output/worker.expected"
unset nonce_hash
started=$(date +%s)
docker_reads=0 host_reads=0

# The POSIX supervisor retains the CLI child until all signalling is complete.
read_query() {
  local kind=$1 limit=$2 remaining duration rc errors capture_rc
  shift 2
  [ ! -e "$output/phase-expired" ] && [ -p "$output/query.out" ] && [ -p "$output/query.err" ] || return 1
  remaining=$((300 - $(date +%s) + started))
  [ "$remaining" -gt 0 ] || return 1
  duration=30; [ "$remaining" -ge 30 ] || duration=$remaining
  case "$kind" in
    docker) docker_reads=$((docker_reads+1)); [ "$docker_reads" -le 160 ] || return 1 ;;
    host|listener) host_reads=$((host_reads+1)); [ "$host_reads" -le 4 ] || return 1 ;;
  esac
  ( head -c 1 < "$output/query.err" | wc -c ) > "$output/stderr-present" & error_pid=$!
  perl scripts/grandparent_metadata_supervisor.pl process "$duration" -- "$@" > "$output/query.out" 2> "$output/query.err" & query_pid=$!
  set +e
  value=$(perl scripts/grandparent_metadata_supervisor.pl capture "$limit" < "$output/query.out"); capture_rc=$?
  wait "$query_pid"; rc=$?
  wait "$error_pid"
  set -e
  query_pid='' error_pid=''
  errors=$(tr -d '[:space:]' < "$output/stderr-present")
  [ "$capture_rc" = 0 ] && [ "$errors" = 0 ] || return 1
  value=${value%$'\001'}
  last_query_rc=$rc
  if [ "$kind" = listener ] && [ "$rc" = 1 ] && [ -z "$value" ]; then return 0; fi
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
  docker_binary=$(command -v docker)
  docker() { read_query docker 4096 "$docker_binary" "$@" || return 1; printf '%s\n' "$value"; }
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
    read_query listener 32768 lsof +c 0 -nP "-iTCP:$port" -sTCP:LISTEN -F pcfn
    printf '%s' "$value" | jq -Rsc --arg port "$port" --arg rc "$last_query_rc" '{kind:"listener",port:$port,no_match:($rc=="1"),lines:split("\n")}' | project_emit listener
  done
  stage=visible-forwarders
  read_query host 1048576 ps -axo pid=,ppid=,comm=
  printf '%s' "$value" | jq -Rsc '{kind:"processes",lines:split("\n")}' | project_emit processes
  stage=closing-sets
  closing=$(set -e; enumerate); emit "$closing"
  read_query docker 4096 docker info --format '{{.ID}}'
  printf '%s' "$value" | jq -Rse --arg expected "$image_witness_daemon" '.==($expected+"\n")' >/dev/null
  [ "$(( $(date +%s) - started ))" -le 300 ]
  jq -cn --arg finished "$(date +%s)" '{kind:"complete",engine_matches:true,finished:$finished}'
}
stage=collection
set +e
( trap 'rc=$?; set +e; if [ "$rc" != 0 ]; then
    printf "{\"kind\":\"failure\",\"stage\":\"%s\"}\n" "$stage"
  fi' EXIT
  set -e; collect ) > "$output/records" & collector_pid=$!
jq -cse --slurpfile manifest "$MANIFEST" --slurpfile plan "$PLAN" --slurpfile action "$ACTION" \
  --arg mode report --arg approval_sha256 "$EXPECTED" --arg source "$(git rev-parse HEAD)" \
  --arg started "$started" --arg finished "$(date +%s)" -f scripts/grandparent_reset_inventory.jq \
  < "$output/records" > "$output/report.json" & report_pid=$!
wait "$report_pid"; rc=$?
wait "$collector_pid"; collector_rc=$?
set -e
[ "$(wc -c < "$output/report.json")" -le 262144 ] || exit 1
jq -e '.schema=="cpk399.reset-inventory-observation.v1" and (.status=="observed" or .status=="HOLD")' "$output/report.json" >/dev/null
cat "$output/report.json"
final_reported=1
[ "$rc" = 0 ] || exit 1
[ "$collector_rc" = 0 ] || exit 1
jq -e '.schema=="cpk399.reset-inventory-observation.v1" and .status=="observed" and
 .backing_path_bind_access=="unresolved" and .external_routing=="unresolved" and
 .can_satisfy_retirement_exclusivity==false' "$output/report.json" >/dev/null
stage=report
