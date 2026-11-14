#!/bin/sh
# Verification only. No service mutation, Docker socket mount, or switch entry.
set -eu
set -C
exec 2>/dev/null
stage=arguments
finish() {
  status=$?
  trap - 0
  if [ "$status" != 0 ]; then
    printf '{"schema":"cpk399.saved-read-launch.v1","status":"HOLD","stage":"%s","retry":false}\n' "$stage"
  fi
  exit "$status"
}
trap finish 0
[ "$#" = 2 ] || exit 2
ACTION=$1 APPROVED_DIGEST=$2
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$SOURCE"
[ -z "$(git status --porcelain)" ] || exit 2
[ -z "${DOCKER_HOST:-}${DOCKER_TLS:-}${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ] || exit 2
case "$ACTION" in /*) ;; *) exit 2 ;; esac
case "$ACTION" in *','*|*'..'*|*'
'*) exit 2 ;; esac
[ -f "$ACTION" ] && [ ! -L "$ACTION" ] || exit 2
case "$APPROVED_DIGEST" in *[!0-9a-f]*) exit 2 ;; esac
[ "${#APPROVED_DIGEST}" = 64 ] || exit 2
action_hash=$(shasum -a 256 "$ACTION"); [ "${action_hash%% *}" = "$APPROVED_DIGEST" ] || exit 2
reader_hash=$(shasum -a 256 scripts/grandparent_saved_read.py); reader_hash=${reader_hash%% *}
shared_hash=$(shasum -a 256 scripts/grandparent_cpk_cutover.py); shared_hash=${shared_hash%% *}
launcher_hash=$(shasum -a 256 scripts/grandparent_saved_read.sh); launcher_hash=${launcher_hash%% *}
owner_hash=$(shasum -a 256 scripts/gateway_packaged_owner.sh); owner_hash=${owner_hash%% *}
daemon_hash=$(shasum -a 256 scripts/docker_witness_daemon.sh); daemon_hash=${daemon_hash%% *}
source_commit=$(git rev-parse HEAD)
HUMAN=/Users/jacobvartuli/Software/self/control-plane-kit-servers/env/cpk163-gparent-20261109-prepared-02/material/human.bearer
BASELINE=/private/tmp/cpk163-real-graph-canonical-public-20261111/desired.json
jq -e --arg source "$source_commit" --arg reader "$reader_hash" --arg shared "$shared_hash" \
 --arg launcher "$launcher_hash" --arg owner "$owner_hash" --arg daemon "$daemon_hash" \
 --arg human "$HUMAN" --arg baseline "$BASELINE" \
 '.schema=="cpk399.read-only-approval.v1" and .source_commit==$source and
 .reader_sha256==$reader and .shared_reader_sha256==$shared and .launcher_sha256==$launcher and
 .owner_sha256==$owner and .daemon_admission_sha256==$daemon and .read_once_approved==true and
 .run=="cpk399-gparent-saved-read-20261114-02" and .endpoint=="http://127.0.0.1:18163" and
 .credential_source==$human and .baseline_source==$baseline and
 .routes==["read.workspace","read.desired-graph","read.desired-topology-draft-revision","read.desired-topology-draft-revision-attempts"] and
 (.review_reference|type=="string" and length>0)' "$ACTION" >/dev/null
stage=input-metadata
for input in "$HUMAN" "$BASELINE"; do
  [ -f "$input" ] && [ ! -L "$input" ] || exit 2
  component=$input
  while [ "$component" != / ]; do
    [ ! -L "$component" ] || exit 2
    component=$(dirname -- "$component")
  done
done
credential_metadata=$(stat -c '%u:%g:%a:%s' "$HUMAN" 2>/dev/null || stat -f '%u:%g:%Lp:%z' "$HUMAN")
[ "$credential_metadata" = 501:20:400:64 ] || exit 2
baseline_hash=$(shasum -a 256 "$BASELINE")
[ "${baseline_hash%% *}" = f3b0f8a2321e521a989c3a8d84e51c7431b1c8e3056c0e4a0a08c7e05a702e2a ] || exit 2
stage=original-identity
. ./scripts/docker_witness_daemon.sh
docker_witness_daemon
GW_DAEMON=$image_witness_daemon
[ "$GW_DAEMON" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 2
original=$(docker inspect 3584eabe7b2c1c278ea9053f9ac73a16acc85d086c641058f5430549fd887e0f --format '{{.Id}}|{{.Name}}|{{.Image}}|{{.State.Running}}|{{.State.Paused}}|{{.State.Restarting}}|{{json .NetworkSettings.Ports}}')
[ "$original" = '3584eabe7b2c1c278ea9053f9ac73a16acc85d086c641058f5430549fd887e0f|/cpk-cpk163-gparent-20261109-cpk163-gparent-20261109-cpk163-gparent-20261109-cpk|sha256:62e4ee7fe4e8326b762c36306c3a810a15d684cb9d2c22515ac2f092296d2e50|true|false|false|{"8080/tcp":[{"HostIp":"127.0.0.1","HostPort":"18163"}]}' ] || exit 2
DRIVER=sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80
[ "$(docker image inspect "$DRIVER" --format '{{.Id}}')" = "$DRIVER" ] || exit 2
GW_RUN=cpk399-gparent-saved-read-20261114-02
GW_RECORDS=/private/tmp/$GW_RUN
[ ! -e "$GW_RECORDS" ] && [ ! -L "$GW_RECORDS" ] || exit 2
. ./scripts/gateway_packaged_owner.sh
GW_ROLES=verification GW_VOLUMES='' GW_RESERVED=0
[ -z "$(docker ps -aq --no-trunc --filter "name=^/$GW_RUN-verification$")" ] || exit 2
[ -z "$(docker ps -aq --no-trunc --filter "label=cpk.test-run=$GW_RUN")" ] || exit 2
umask 077
mkdir -m 700 "$GW_RECORDS"
GW_OWNER=$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')
[ "${#GW_OWNER}" = 64 ] || exit 2
GW_RESERVED=1
stage=read-only-helper
helper_status=0
output=$(gw_run verification --network host --read-only --user 501:20 --cap-drop ALL \
 --security-opt no-new-privileges --cpus 1 --memory 512m --pids-limit 64 \
 --tmpfs /tmp:rw,nosuid,nodev,size=32m --log-driver none \
 --env PYTHONDONTWRITEBYTECODE=1 --env HTTP_PROXY= --env HTTPS_PROXY= --env ALL_PROXY= \
 --env http_proxy= --env https_proxy= --env all_proxy= \
 --mount "type=bind,source=$SOURCE/scripts/grandparent_saved_read.py,target=/grandparent_saved_read.py,readonly" \
 --mount "type=bind,source=$SOURCE/scripts/grandparent_cpk_cutover.py,target=/grandparent_cpk_cutover.py,readonly" \
 --mount "type=bind,source=$ACTION,target=/proposal/verification.json,readonly" \
 --mount "type=bind,source=$BASELINE,target=/public/desired.json,readonly" \
 --mount "type=bind,source=$HUMAN,target=/credentials/human.bearer,readonly" \
 --entrypoint python "$DRIVER" /grandparent_saved_read.py --verify-saved-read-only "$APPROVED_DIGEST") || helper_status=$?
stage=helper-terminal
[ -s "$GW_RECORDS/verification.cid" ] || exit 1
helper_id=$(cat "$GW_RECORDS/verification.cid")
[ "${#helper_id}" = 64 ] || exit 1
case "$helper_id" in *[!0-9a-f]*) exit 1 ;; esac
[ "$(docker inspect "$helper_id" --format '{{.State.Status}}|{{.State.ExitCode}}')" = "exited|$helper_status" ] || exit 1
stage=owned-helper-cleanup
gw_cleanup
stage=bounded-result
printf '%s\n' "$output" | jq -ce 'select(.schema=="cpk399.saved-read-verification.v1" and
 (.status=="verified" or .status=="HOLD") and .retry==false and .switch_attempted==false and
 .service_mutation==false and .graph_mutation==false)' > "$GW_RECORDS/result.json"
cat "$GW_RECORDS/result.json"
exit "$helper_status"
