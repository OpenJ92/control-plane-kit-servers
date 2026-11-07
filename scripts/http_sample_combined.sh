#!/bin/sh
# One reviewed-source composition fixture, never a package-coordinate override.
set -eu
image=$1
sender_repository=$2
sender_base=e4bd35e828d1c44129f64e702de2b1d2b60f7c87
sender_revision=d5765cdffb4c2a02d4be9b81b401e96c17e4624b
sender_file=src/control_plane_kit_interpreters/probes/http_sample_transport.py
sender_sha256=086144625bf8b30cbd7dbf0277a5db2a0db08ef9f133e9686275e3f284b576c6

git -C "$sender_repository" merge-base --is-ancestor "$sender_base" "$sender_revision"
changed_source=$(git -C "$sender_repository" diff --name-only "$sender_base" "$sender_revision" -- src)
[ "$changed_source" = "$sender_file" ] || { echo 'reviewed sender source boundary differs' >&2; exit 1; }
owned_source=$(mktemp -d /private/tmp/cpk181-reviewed-sender.XXXXXX)
finish() {
  result=$?
  trap - EXIT INT TERM
  rm -rf "$owned_source" || result=1
  [ ! -e "$owned_source" ] || result=1
  if [ "$result" = 0 ]; then
    echo 'reviewed sender export cleanup verified'
  else
    echo 'combined sample proof stopped; reviewed sender export cleanup attempted' >&2
  fi
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
git -C "$sender_repository" archive --format=tar "$sender_revision" src/control_plane_kit_interpreters > "$owned_source/source.tar"
tar -xf "$owned_source/source.tar" -C "$owned_source"
actual_sha256=$(shasum -a 256 "$owned_source/$sender_file")
[ "${actual_sha256%% *}" = "$sender_sha256" ] || { echo 'reviewed sender source hash differs' >&2; exit 1; }

# The immutable archive is read-only, and its only new source is the reviewed
# sender. The installed resolver/security companions remain byte-identical to
# the selected e4bd base. There is no host socket or external container network.
docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$owned_source/src,target=/reviewed-sender/src,readonly" \
  -e PYTHONPATH=/reviewed-sender/src -e PYTHONDONTWRITEBYTECODE=1 \
  -e CPK_REVIEWED_HTTP_SAMPLE_SENDER="$sender_revision" \
  "$image" python -m unittest discover -s products/cpk_local_gateway/tests -p test_http_sample_relay.py -v
