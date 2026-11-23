#!/bin/sh
# Called from the Servers root by the fixed packaged-schema selector.
set -eu
. ./scripts/root_artifact_shell.sh

owner_sha=2ef2edf459d167db3ec5a27b6f7cc35477e3d2920bd551863aedbdce149f2f7d
operations_commit=9b93ac2a2cba03d23de13d63440d8da11d380ead
schema_sha=b7df1c402554fdb1991742a9a2f62812f30a292881c73701fdd5ced29048c4f5
base_digest=sha256:1ba7174ee22461566750a516dac173fdd718ed9b059660f30c3ad3f9db79d0f4

umask 077
records=$(mktemp -d "${TMPDIR:-/tmp}/cpk391-schema.XXXXXXXX")
records=$(cd "$records" && pwd -P)
run=${records##*/}
tag="control-plane-kit-bootstrap-test:$run"
phase=source
build_attempted=0
build_status=unattempted
cleanup=unattempted
printf 'Packaged schema receipts: %s\n' "$records"

tag_images() {
  docker image ls -q --no-trunc --filter "reference=$tag"
}

cleanup_tag() {
  [ "$build_attempted" = 1 ] || return 0
  cleanup=hold
  found=$(tag_images) || return 1
  if [ -z "$found" ]; then
    [ "$build_status" != 0 ] || return 1
    cleanup=absent
    return 0
  fi
  recorded=$(cat "$records/driver.iid") || return 1
  jq -ne --arg iid "$recorded" '$iid | test("^sha256:[0-9a-f]{64}$")' >/dev/null || return 1
  [ "$found" = "$recorded" ] || return 1
  observed=$(docker image inspect --format '{{.Id}}|{{index .Config.Labels "org.openj92.cpk.test-run"}}' "$tag") || return 1
  printf '%s\n' "$observed" > "$records/cleanup.identity" || return 1
  [ "$observed" = "$recorded|$run" ] || return 1
  docker image rm --no-prune "$tag" > "$records/cleanup.output" || return 1
  remaining=$(tag_images) || return 1
  [ -z "$remaining" ] || return 1
  cleanup=removed
}

finish() {
  status=$1
  trap - 0
  trap '' HUP INT TERM
  cleanup_tag || status=1
  disposition=HOLD
  [ "$status" != 0 ] || disposition=PASS
  printf 'result=%s\nphase=%s\nexit=%s\nbuild_exit=%s\ntag=%s\ncleanup=%s\n' \
    "$disposition" "$phase" "$status" "$build_status" "$tag" "$cleanup" > "$records/result"
  printf '%s packaged schema: phase=%s tag_cleanup=%s receipts=%s\n' \
    "$disposition" "$phase" "$cleanup" "$records"
  exit "$status"
}
trap 'finish "$?"' 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

state=$(git status --porcelain)
[ -z "$state" ]
source_commit=$(git rev-parse --verify HEAD)
printf '%s\n' "$source_commit" > "$records/source.commit"
git rev-parse "$source_commit^{tree}" > "$records/source.tree"
context="$records/source"
mkdir "$context"
# Preserve tracked read/execute modes for Docker COPY and the helper UID.
# The enclosing receipt directory stays private to the operator.
git -c tar.umask=0022 archive --output="$records/context.tar" "$source_commit"
tar -xpf "$records/context.tar" -C "$context"
rm "$records/context.tar"
cd "$context"
owner_file=products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_initialization.py
source_hash=$(shasum -a 256 "$owner_file")
[ "${source_hash%% *}" = "$owner_sha" ]

phase=base
base_ref=$(docker run --pull never --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$context,target=/source,readonly" --workdir /source \
  "${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}" python -B scripts/product_image_coordinate.py cpk-server)
root_artifact_reference cpk-server "$base_ref"
[ "${base_ref#*@}" = "$base_digest" ]

# The base owns the registry digest and the new driver owns the run label.
inspect_image() {
  identity_fields='"local_image_id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}},"configured_user":{{json .Config.User}},"layers":{{json .RootFS.Layers}}'
  docker image inspect --format "{$identity_fields,$2}" "$1"
}

inspect_image "$base_ref" '"repo_digests":{{json .RepoDigests}}' > "$records/base.inspect.json"
jq -e --arg ref "$base_ref" --arg digest "$base_digest" '
  select((.repo_digests | index($ref)) != null and (.local_image_id | test("^sha256:[0-9a-f]{64}$"))
    and .os == "linux" and .architecture == "amd64"
    and (.layers | type == "array" and length > 0 and all(.[]; test("^sha256:[0-9a-f]{64}$"))))
  | (.configured_user | capture("^(?<uid>[0-9]+)(:[0-9]+)?$").uid | tonumber) as $uid
  | select($uid == 10001)
  | . + {registry_reference: $ref, registry_digest: $digest, helper_uid: $uid}
' "$records/base.inspect.json" > "$records/base.json"
helper_uid=$(jq -er '.helper_uid' "$records/base.json")

phase=build
preexisting=$(tag_images)
[ -z "$preexisting" ]
export DOCKER_DEFAULT_PLATFORM=linux/amd64
build_attempted=1
build_status=unknown
if root_bootstrap_driver_build "$base_ref" "$run" "$records/driver.iid" "$tag"; then
  build_status=0
else
  build_status=$?
  exit "$build_status"
fi

phase=driver
driver=$(cat "$records/driver.iid")
inspect_image "$tag" '"run_label":{{json (index .Config.Labels "org.openj92.cpk.test-run")}}' > "$records/driver.inspect.json"
jq -e --arg iid "$driver" --arg run "$run" --slurpfile base "$records/base.json" '
  $base[0].layers as $prefix
  | select(($iid | test("^sha256:[0-9a-f]{64}$")) and .local_image_id == $iid
      and .os == "linux" and .architecture == "amd64" and .configured_user == "0"
      and .run_label == $run and (.layers | length) > ($prefix | length)
      and .layers[:($prefix | length)] == $prefix)
  | . + {base_local_image_id: $base[0].local_image_id, base_layer_count: ($prefix | length),
         base_layer_prefix_verified: true}
' "$records/driver.inspect.json" > "$records/driver.json"

probe() {
  probe_uid=$1
  phase="uid-$probe_uid"
  probe_file="$records/$phase"
  if docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --workdir /tmp --user "$probe_uid" \
    --entrypoint python "$driver" -B -c '
import hashlib
import json
import os
from pathlib import Path
from control_plane_kit_servers_cpk_server import bootstrap_initialization as owner

print(json.dumps({
    "effective_uid": os.geteuid(),
    "owner_sha256": hashlib.sha256(Path(owner.__file__).read_bytes()).hexdigest(),
    "correlation": owner.package_correlation(),
}))
' > "$probe_file.json"; then
    probe_status=0
  else
    probe_status=$?
  fi
  printf '%s\n' "$probe_status" > "$probe_file.exit"
  [ "$probe_status" = 0 ] || exit "$probe_status"
  jq -se --argjson uid "$probe_uid" --arg owner "$owner_sha" --arg ops "$operations_commit" --arg sql "$schema_sha" '
    . == [{effective_uid: $uid, owner_sha256: $owner,
           correlation: {operations_commit: $ops, schema_sha256: $sql}}]
  ' "$probe_file.json" >/dev/null
}
probe 0
probe "$helper_uid"
phase=complete
