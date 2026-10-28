#!/bin/sh
# Offline diagnostic only. Tool/image acquisition is a separate approved step.
set -eu
[ "$#" = 6 ] || { echo 'root account inspection input refused' >&2; exit 2; }
ACCOUNT_CONTROLLER="$1"
ACCOUNT_INPUT="$2"
ACCOUNT_TOOL="$3"
ACCOUNT_OUTPUT="$4"
ACCOUNT_REFERENCE="$5"
ACCOUNT_SOURCE="$6"
ACCOUNT_UID="$(id -u)"
ACCOUNT_GID="$(id -g)"
[ "$ACCOUNT_UID" != 0 ] || { echo 'root account inspection requires a nonroot operator' >&2; exit 2; }
case "$ACCOUNT_CONTROLLER" in sha256:*) ;; *) exit 2 ;; esac
ACCOUNT_HASH="${ACCOUNT_CONTROLLER#sha256:}"
[ "${#ACCOUNT_HASH}" = 64 ] || exit 2
case "$ACCOUNT_HASH" in *[!0-9a-f]*) exit 2 ;; esac
ACCOUNT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
. "$ACCOUNT_ROOT/scripts/root_artifact_shell.sh"
root_artifact_reference cpk-server "$ACCOUNT_REFERENCE" || exit 2
[ "${#ACCOUNT_SOURCE}" = 40 ] || exit 2
case "$ACCOUNT_SOURCE" in *[!0-9a-f]*) exit 2 ;; esac
ACCOUNT_INPUT="$(CDPATH= cd -- "$ACCOUNT_INPUT" && pwd)"
ACCOUNT_TOOL="$(CDPATH= cd -- "$ACCOUNT_TOOL" && pwd)"
# The caller supplies a fresh private output directory. Do not overwrite evidence.
mkdir -m 700 -- "$ACCOUNT_OUTPUT"
ACCOUNT_OUTPUT="$(CDPATH= cd -- "$ACCOUNT_OUTPUT" && pwd)"
umask 077
ACCOUNT_RUN="cpk-account-$(date +%s)-$$"
ACCOUNT_LABEL="org.openj92.cpk.account-inspection=$ACCOUNT_RUN"
command -v timeout >/dev/null
[ "$(docker image inspect "$ACCOUNT_CONTROLLER" --format '{{.Id}}')" = "$ACCOUNT_CONTROLLER" ]
[ "$(docker image inspect "$ACCOUNT_CONTROLLER" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64 ]
[ -z "$(docker ps -a --filter "name=^/$ACCOUNT_RUN$" --format '{{.ID}}')" ]
# The maintained unpacker runs offline as a nonroot user. Tmpfs enforces a
# total unpack limit; neither free-space checks nor individual file limits do.
set +e
timeout --foreground --signal=TERM --kill-after=15s 300s \
  docker run --pull never --rm --name "$ACCOUNT_RUN" --label "$ACCOUNT_LABEL" \
    --cidfile "$ACCOUNT_OUTPUT/container-id" --network none --read-only \
    --user "$ACCOUNT_UID:$ACCOUNT_GID" --cap-drop ALL --security-opt no-new-privileges \
    --memory 5g --pids-limit 64 --cpus 2 \
    --tmpfs "/inspection:rw,noexec,nosuid,nodev,size=4g,uid=$ACCOUNT_UID,gid=$ACCOUNT_GID,mode=0700" \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
    --mount "type=bind,source=$ACCOUNT_ROOT,target=/source,readonly" \
    --mount "type=bind,source=$ACCOUNT_INPUT,target=/input,readonly" \
    --mount "type=bind,source=$ACCOUNT_TOOL,target=/tools,readonly" \
    -e PYTHONDONTWRITEBYTECODE=1 "$ACCOUNT_CONTROLLER" \
    python /source/scripts/root_account_projection.py "$ACCOUNT_REFERENCE" "$ACCOUNT_SOURCE" \
    > "$ACCOUNT_OUTPUT/candidate.json" 2> "$ACCOUNT_OUTPUT/private-error"
ACCOUNT_STATUS=$?
set -e
if [ "$ACCOUNT_STATUS" != 0 ]; then
  echo 'root account inspection HOLD; preserve exact private evidence and inspect owned container' >&2
  exit 1
fi
# A failed inventory is not absence; never delete/retry an ambiguous attempt.
ACCOUNT_REMAINS="$(docker ps -a --no-trunc --filter "label=$ACCOUNT_LABEL" --format '{{.ID}}')" || exit 1
if [ -n "$ACCOUNT_REMAINS" ]; then
  echo 'root account inspection cleanup HOLD' >&2
  exit 1
fi
[ -s "$ACCOUNT_OUTPUT/candidate.json" ]
[ "$(wc -c < "$ACCOUNT_OUTPUT/candidate.json")" -le 4096 ]
mv -- "$ACCOUNT_OUTPUT/candidate.json" "$ACCOUNT_OUTPUT/account-seal.json"
echo 'root account inspection and owned offline container absence passed; independent seal review required'
