#!/bin/sh
# Retained-root action proposal, never part of ordinary validation.
set -eu
exec 2>/dev/null
stage=arguments
finish() {
  status=$?
  trap - 0
  if [ "$status" != 0 ]; then
    printf '{"schema":"cpk399.launch.v1","status":"HOLD","stage":"%s","retry":false}\n' "$stage"
  fi
  exit "$status"
}
trap finish 0
[ "$#" = 4 ] || exit 2
ACTION=$1 APPROVED_DIGEST=$2 HUMAN=$3 BOOTSTRAP=$4
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$SOURCE"
[ -z "$(git status --porcelain)" ] || exit 2
[ -z "${DOCKER_HOST:-}${DOCKER_TLS:-}${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ] || exit 2
for input in "$ACTION" "$HUMAN" "$BOOTSTRAP"; do
  case "$input" in /*) ;; *) exit 2 ;; esac
  case "$input" in *','*|*'..'*|*'
'*) exit 2 ;; esac
  [ -f "$input" ] && [ ! -L "$input" ] || exit 2
done
case "$APPROVED_DIGEST" in *[!0-9a-f]*) exit 2 ;; esac
[ "${#APPROVED_DIGEST}" = 64 ] || exit 2
action_hash=$(shasum -a 256 "$ACTION"); [ "${action_hash%% *}" = "$APPROVED_DIGEST" ] || exit 2
script_hash=$(shasum -a 256 scripts/grandparent_cpk_cutover.py); script_hash=${script_hash%% *}
launcher_hash=$(shasum -a 256 scripts/grandparent_cpk_cutover.sh); launcher_hash=${launcher_hash%% *}
owner_hash=$(shasum -a 256 scripts/gateway_packaged_owner.sh); owner_hash=${owner_hash%% *}
daemon_hash=$(shasum -a 256 scripts/docker_witness_daemon.sh); daemon_hash=${daemon_hash%% *}
source_commit=$(git rev-parse HEAD)
jq -e --arg sha "$script_hash" --arg launcher "$launcher_hash" --arg owner "$owner_hash" \
 --arg daemon "$daemon_hash" --arg source "$source_commit" --arg human "$HUMAN" \
 '.schema=="cpk399.cutover-approval.v1" and .source_commit==$source and
 .launcher_sha256==$launcher and .owner_sha256==$owner and .daemon_admission_sha256==$daemon and
 .credential_source==$human and .credential_target=="/credentials/human.bearer" and
 .credential_subject=="cpk163-gparent-20261109-human" and .reader_uid==501 and .reader_gid==20 and
 .reader_endpoint=="http://127.0.0.1:18163" and
 .driver_image=="sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80" and
 .script_sha256==$sha and .quiescence_confirmed==true and .exposure_reviewed==true and
 .private_wiring_reuse_approved==true and .verification_bearer_use_approved==true and
 (.approval_reference|type=="string")' "$ACTION" >/dev/null
stage=approved-custody-metadata
credential_component=$HUMAN
while [ "$credential_component" != / ]; do
  [ ! -L "$credential_component" ] || exit 2
  credential_component=$(dirname -- "$credential_component")
done
credential_metadata=$(stat -c '%u:%g:%a:%s' "$HUMAN" 2>/dev/null || stat -f '%u:%g:%Lp:%z' "$HUMAN")
[ "$credential_metadata" = 501:20:400:64 ] || exit 2
bootstrap_hash=$(shasum -a 256 "$BOOTSTRAP")
[ "${bootstrap_hash%% *}" = c451d7cffad919297c3a669db6ca920271d3038526b2a8248cd8201ce7a41279 ] || exit 2
stage=daemon
. ./scripts/docker_witness_daemon.sh
docker_witness_daemon
GW_DAEMON=$image_witness_daemon
[ "$GW_DAEMON" = d23d00aa-b281-448d-bc95-c8e47efeeea2 ] || exit 2
DRIVER=sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80
[ "$(docker image inspect "$DRIVER" --format '{{.Id}}')" = "$DRIVER" ] || exit 2
GW_RUN=cpk399-gparent-mcp-switch-20261114-01
GW_RECORDS=/private/tmp/$GW_RUN
[ ! -e "$GW_RECORDS" ] && [ ! -L "$GW_RECORDS" ] || exit 2
. ./scripts/gateway_packaged_owner.sh
GW_ROLES=maintenance GW_VOLUMES='' GW_RESERVED=0
[ -z "$(docker ps -aq --no-trunc --filter "name=^/$GW_RUN-maintenance$")" ] || exit 2
[ -z "$(docker ps -aq --no-trunc --filter "label=cpk.test-run=$GW_RUN")" ] || exit 2
umask 077
mkdir -m 700 "$GW_RECORDS"
GW_OWNER=$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')
[ "${#GW_OWNER}" = 64 ] || exit 2
GW_RESERVED=1
stage=maintenance-helper
helper_status=0
output=$(gw_run maintenance --network host \
  --read-only --user 0 --cap-drop ALL --cap-add DAC_READ_SEARCH --cap-add SETUID --cap-add SETGID \
  --security-opt no-new-privileges \
  --cpus 1 --memory 512m --pids-limit 128 --tmpfs /tmp:rw,nosuid,nodev,size=32m \
  --log-driver none --env PYTHONDONTWRITEBYTECODE=1 --env HTTP_PROXY= --env HTTPS_PROXY= \
  --env ALL_PROXY= --env http_proxy= --env https_proxy= --env all_proxy= \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount "type=bind,source=$SOURCE/scripts/grandparent_cpk_cutover.py,target=/maintenance.py,readonly" \
  --mount "type=bind,source=$ACTION,target=/proposal/action.json,readonly" \
  --mount "type=bind,source=$BOOTSTRAP,target=/proposal/bootstrap.json,readonly" \
  --mount "type=bind,source=$HUMAN,target=/credentials/human.bearer,readonly" \
  --mount "type=bind,source=$GW_RECORDS,target=/evidence" \
  --entrypoint python "$DRIVER" /maintenance.py --execute-reviewed-cutover "$APPROVED_DIGEST") || helper_status=$?
# Never kill a possibly running maintenance action after a lost client response.
# Reuse cleanup only after exact helper identity and terminal outcome are known.
stage=helper-terminal
[ -s "$GW_RECORDS/maintenance.cid" ] || exit 1
helper_id=$(cat "$GW_RECORDS/maintenance.cid")
[ "${#helper_id}" = 64 ] || exit 1
case "$helper_id" in *[!0-9a-f]*) exit 1 ;; esac
terminal=$(docker inspect "$helper_id" --format '{{.State.Status}}|{{.State.ExitCode}}')
[ "$terminal" = "exited|$helper_status" ] || exit 1
stage=helper-cleanup
gw_cleanup
stage=bounded-result
printf '%s\n' "$output" | jq -ce 'select(.schema=="cpk399.maintenance.v1" and
 (.status=="verified" or .status=="HOLD") and .retry==false)'
exit "$helper_status"
