#!/usr/bin/env bash
# Opt-in diagnostic in the SAME successful CPK producer job; never publishes.
set -euo pipefail
umask 077
ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY='docker.io/library/python@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8'
POLICY_DIGEST="${POLICY#*@}"
UMOCI_SHA='b51c267ec394499e42c6fde47f240b7b7dba57ea49df0b5acd304378b82a3b71'
refuse() { echo 'Published CPK image remains published; account inspection HOLD' >&2; exit 1; }
valid_inputs() {
  . "$ROOT/scripts/root_artifact_shell.sh"
  root_artifact_reference cpk-server "$REFERENCE" && [[ "$SOURCE" =~ ^[0-9a-f]{40}$ ]]
}
cleanup_acquisition() {
  local remaining mounts backing_after associated
  remaining="$(docker ps -a --filter "label=org.openj92.cpk.account-acquisition=$RUN" --format '{{.ID}}')" || return 1
  [ -z "$remaining" ] || return 1
  mounts="$(findmnt --json --list --output TARGET,SOURCE)" || return 1
  printf '%s\n' "$mounts" | jq -e --arg target "$MOUNT" --arg source "$LOOP" '
    (.filesystems | type) == "array" and
    ([.filesystems[] | select(.target == $target)] | length == 1 and .[0].source == $source)' >/dev/null || return 1
  backing_after="$(sudo -n losetup --noheadings --output BACK-FILE "$LOOP")" || return 1
  [ "$backing_after" = "$BACKING" ] || return 1
  sudo -n umount "$MOUNT" || return 1
  # findmnt exit 1 can mean an error. Only a successful full inventory proves absence.
  mounts="$(findmnt --json --list --output TARGET,SOURCE)" || return 1
  printf '%s\n' "$mounts" | jq -e --arg target "$MOUNT" '
    (.filesystems | type) == "array" and (.filesystems | length) > 0 and
    all(.filesystems[]; .target != $target)' >/dev/null || return 1
  sudo -n losetup --detach "$LOOP" || return 1
  associated="$(sudo -n losetup --noheadings --output NAME --associated "$BACKING")" || return 1
  [ -z "$associated" ] || return 1
  rm -- "$BACKING" || return 1
  rmdir "$MOUNT"
}
status() {
  jq -n --arg reference "$REFERENCE" --arg source "$SOURCE" --arg controller "$CONTROLLER" \
    --arg stage "$STAGE" --arg result "$1" \
    '{schema:"cpk.root-account-attempt.v1",publication:"succeeded",image_reference:$reference,
      source_revision:$source,controller_image_id:$controller,inspection:$result,stage:$stage}' \
    > "$RECORDS/public/status.json"
}
inspect_accounts() {
  local result
  STAGE=offline-inspection
  status hold
  if sh "$ROOT/scripts/inspect_root_accounts.sh" "$CONTROLLER" "$WORK/input" "$WORK/tools" \
      "$RECORDS/inspection" "$REFERENCE" "$SOURCE"; then
    return 0
  else
    result="$?"
  fi
  case "$result" in
    40) STAGE=offline-input-setup ;;
    41) STAGE=offline-layout-validation ;;
    42) STAGE=offline-tool-validation ;;
    43) STAGE=offline-unpack-launch ;;
    44) STAGE=offline-unpack-timeout ;;
    45) STAGE=offline-unpack-nonzero ;;
    46) STAGE=offline-account-projection ;;
    47) STAGE=offline-result-serialization ;;
    60) STAGE=offline-outer-timeout ;;
    61) STAGE=offline-controller-killed-or-timeout ;;
    62) STAGE=offline-outer-execution-failure ;;
    65) STAGE=offline-unknown-controller-failure ;;
    *) STAGE=offline-wrapper-failure ;;
  esac
  return 1
}
# Sourcing exposes narrow inspection/status/cleanup owners to ordinary-suite tests.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return 0; fi
# The worker is invoked only by the parent under its whole-phase timeout.
if [ "${1:-}" = --acquire ]; then
  shift
  [ "$#" = 5 ] || refuse
  REFERENCE="$1" SOURCE="$2" WORK="$3" CONTROLLER="$4" RUN="$5"
  valid_inputs || refuse
  INPUT="$WORK/input" TOOLS="$WORK/tools" AUTH="$WORK/auth.json"
  export TMPDIR="$WORK/tmp"
  mkdir "$INPUT" "$TOOLS" "$TMPDIR"
  printf '%s' "$GH_TOKEN" | skopeo login --authfile "$AUTH" --username "$GITHUB_ACTOR" \
    --password-stdin ghcr.io > "$WORK/login.log" 2>&1
  chmod 0600 "$AUTH"
  capture_manifest() {
    local target="$1" output="$2"
    local statuses
    set +e
    skopeo inspect --retry-times 0 --tls-verify=true --authfile "$AUTH" --raw \
      "docker://$target" 2> "$WORK/manifest.error" | head -c 1048577 > "$output"
    statuses=("${PIPESTATUS[@]}")
    set -e
    if [ "${statuses[0]}" != 0 ] || [ "${statuses[1]}" != 0 ]; then refuse; fi
    [ "$(wc -c < "$output")" -le 1048576 ]
  }
  project_manifest() {
    local phase="$1" name="$RUN-$1" remaining
    remaining="$(docker ps -a --filter "name=^/$name$" --format '{{.ID}}')"
    [ -z "$remaining" ]
    timeout --signal=TERM --kill-after=10s 30s docker run --pull never --rm \
      --name "$name" --label "org.openj92.cpk.account-acquisition=$RUN" \
      --cidfile "$WORK/$phase.container-id" --network none --read-only \
      --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
      --memory 256m --pids-limit 32 --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
      --mount "type=bind,source=$ROOT/scripts/root_account_projection.py,target=/source/root_account_projection.py,readonly" \
      --mount "type=bind,source=$INPUT,target=/input,readonly" \
      -e PYTHONDONTWRITEBYTECODE=1 "$CONTROLLER" \
      python /source/root_account_projection.py "--$phase" "$REFERENCE" \
      > "$WORK/$phase.json" 2> "$WORK/$phase.error"
    [ "$(wc -c < "$WORK/$phase.json")" -le 4096 ]
    remaining="$(docker ps -a --filter "name=^/$name$" --format '{{.ID}}')"
    [ -z "$remaining" ]
  }
  capture_manifest "$REFERENCE" "$INPUT/original.json"
  project_manifest select
  PLATFORM="$(jq -er '.platform_manifest_digest | select(test("^sha256:[0-9a-f]{64}$"))' "$WORK/select.json")"
  capture_manifest "${REFERENCE%@*}@$PLATFORM" "$INPUT/platform.json"
  project_manifest admit
  # Metadata admission precedes blob acquisition. No overlay logic lives here.
  skopeo --override-os linux --override-arch amd64 copy --retry-times 0 \
    --src-authfile "$AUTH" --src-tls-verify=true --format oci \
    --dest-oci-accept-uncompressed-layers "docker://${REFERENCE%@*}@$PLATFORM" \
    "oci:$INPUT/layout:inspected" > "$WORK/copy.log" 2>&1
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --max-time 60 --max-filesize 7946424 \
    --output "$TOOLS/umoci" https://github.com/opencontainers/umoci/releases/download/v0.6.0/umoci.linux.amd64 \
    2> "$WORK/tool.error"
  [ "$(wc -c < "$TOOLS/umoci")" = 7946424 ]
  [ "$(sha256sum "$TOOLS/umoci" | cut -d ' ' -f 1)" = "$UMOCI_SHA" ]
  chmod 0500 "$TOOLS/umoci"
  rm -- "$AUTH"
  [ ! -e "$AUTH" ] && [ ! -L "$AUTH" ]
  exit 0
fi
[ "$#" = 3 ] || refuse
REFERENCE="$1" SOURCE="$2" RECORDS="$3"
valid_inputs || refuse
[ "${GITHUB_ACTIONS:-}" = true ] && [ -n "${GITHUB_RUN_ID:-}" ] || refuse
[ -n "${GITHUB_ACTOR:-}" ] && [ -n "${GH_TOKEN:-}" ] || refuse
[ "$(git -C "$ROOT" rev-parse HEAD)" = "$SOURCE" ] || refuse
SOURCE_STATUS="$(git -C "$ROOT" status --porcelain)" || refuse
[ -z "$SOURCE_STATUS" ] || refuse
[ "$(uname -s)/$(uname -m)" = Linux/x86_64 ] && [ "$(id -u)" != 0 ] || refuse
command -v jq >/dev/null || refuse
mkdir -m 700 -- "$RECORDS"
RECORDS="$(CDPATH= cd -- "$RECORDS" && pwd)"
mkdir "$RECORDS/public"
STAGE=preparation
WORK='' LOOP='' BACKING='' MOUNT='' CONTROLLER=''
finish() {
  local result="$?"
  trap - EXIT
  set +e
  # This exact private auth file belongs to this attempt, including failed copy.
  if [ -n "$WORK" ] && { [ -e "$WORK/auth.json" ] || [ -L "$WORK/auth.json" ]; }; then
    rm -- "$WORK/auth.json"
    if [ -e "$WORK/auth.json" ] || [ -L "$WORK/auth.json" ]; then result=1; fi
  fi
  if [ "$result" != 0 ]; then
    status hold
    echo 'Publication succeeded; account inspection HOLD. Preserve exact owned state; no retry or rollback.' >&2
  fi
  exit "$result"
}
trap finish EXIT
status hold
for tool in docker timeout skopeo curl sha256sum truncate mkfs.ext4 losetup findmnt sudo dpkg-query; do
  command -v "$tool" >/dev/null || refuse
done
[ -n "${ImageOS:-}" ] && [ -n "${ImageVersion:-}" ] || refuse
[ "$(skopeo --version)" = 'skopeo version 1.13.3' ] || refuse
# Borrow only the policy image acquired by this same producer job. Never pull.
CONTROLLER="$(docker image inspect "$POLICY" --format '{{.Id}}')" || refuse
[[ "$CONTROLLER" =~ ^sha256:[0-9a-f]{64}$ ]] || refuse
[ "$(docker image inspect "$CONTROLLER" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64 ] || refuse
DIGESTS="$(docker image inspect "$CONTROLLER" --format '{{range .RepoDigests}}{{println .}}{{end}}')" || refuse
printf '%s\n' "$DIGESTS" | grep -Fx -e "$POLICY" -e "python@$POLICY_DIGEST" >/dev/null || refuse
RUN="cpk-account-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1}"
[[ "$RUN" =~ ^cpk-account-[0-9]+-[0-9]+$ ]] || refuse
WORK="$RECORDS/acquisition"
MOUNT="$WORK" BACKING="$RECORDS/acquisition.img"
mkdir "$MOUNT"
# Fixed file size is an enforced aggregate bound, unlike a free-space check.
truncate -s 3221225472 "$BACKING"
timeout --signal=TERM --kill-after=5s 30s mkfs.ext4 -q -F "$BACKING" > "$RECORDS/filesystem.log" 2>&1
LOOP="$(sudo -n losetup --find --show "$BACKING")"
printf '%s\n' "$LOOP" > "$RECORDS/loop-device"
[ "$(sudo -n losetup --noheadings --output BACK-FILE "$LOOP")" = "$BACKING" ]
sudo -n mount -o nodev,nosuid "$LOOP" "$MOUNT"
[ "$(findmnt --noheadings --mountpoint "$MOUNT" --output SOURCE)" = "$LOOP" ]
[ "$(stat -c %s "$BACKING")" = 3221225472 ]
sudo -n chown "$(id -u):$(id -g)" "$MOUNT"
sudo -n chmod 0700 "$MOUNT"
# Tools execute only after pinned-byte verification; unpacked rootfs is noexec.
STAGE=acquisition
status hold
SKOPEO_HASH="$(sha256sum "$(command -v skopeo)" | cut -d ' ' -f 1)"
SKOPEO_PACKAGE="$(dpkg-query -W -f='${Version}' skopeo)"
jq -n --arg runner_image "${ImageOS:-unknown}" --arg runner_version "${ImageVersion:-unknown}" \
  --arg package "$SKOPEO_PACKAGE" --arg skopeo "$SKOPEO_HASH" --arg umoci "$UMOCI_SHA" \
  --arg controller "$POLICY" --arg source "$SOURCE" \
  '{runner_image:$runner_image,runner_version:$runner_version,skopeo_version:"1.13.3",
    skopeo_package:$package,skopeo_sha256:$skopeo,umoci_version:"0.6.0",umoci_sha256:$umoci,
    controller_reference:$controller,source_revision:$source,acquisition_limit_bytes:3221225472,
    acquisition_timeout_seconds:600,unpack_limit_bytes:4294967296}' > "$RECORDS/public/provenance.json"
# timeout owns the worker process group; no automatic retry follows a timeout.
timeout --signal=TERM --kill-after=15s 600s bash "$0" --acquire \
  "$REFERENCE" "$SOURCE" "$WORK" "$CONTROLLER" "$RUN" > "$WORK/acquisition.log" 2>&1
[ ! -e "$WORK/auth.json" ] && [ ! -L "$WORK/auth.json" ]
sudo -n mount -o remount,ro "$MOUNT"
[ "$(docker image inspect "$POLICY" --format '{{.Id}}')" = "$CONTROLLER" ]
inspect_accounts
STAGE=cleanup
status hold
# An uncertain inventory or different owner blocks cleanup. No force/lazy mount.
cleanup_acquisition
# Only a successful inspection AND observed cleanup may expose the candidate seal.
mv "$RECORDS/inspection/account-seal.json" "$RECORDS/public/account-seal.json"
STAGE=complete
status candidate
printf '%s\n' 'Publication succeeded; account candidate and exact acquisition cleanup complete. Independent seal review required.'
