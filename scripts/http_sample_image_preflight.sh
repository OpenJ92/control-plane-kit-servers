#!/bin/sh
# One isolated cached validation controller, before build/network/provider work.
set -eu
[ "$#" = 1 ] || [ "$#" = 2 ] || exit 2
mode=${2:-}
core_revision=054e5884d89ed6f56141b8fc51ea996f0b6d916b
case "$mode" in
  '') ;;
  --gateway-document|--parent-website|--child-postgres|--sender) core_revision=f56bb5c4cfde76764d39c5377d4270c5b23c3ba1 ;;
  *) exit 2 ;;
esac
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
validator=${CPK_SOURCE_IMAGE_VALIDATOR:?select an exact cached validation controller}
case "$validator" in sha256:*) ;; *) exit 2 ;; esac
[ "${#validator}" = 71 ] || exit 2
case "${validator#sha256:}" in *[!0-9a-f]*) exit 2 ;; esac
[ "$(docker image inspect "$validator" --format '{{.Id}}')" = "$validator" ] || exit 1
preflight_source=$(mktemp -d /tmp/cpk163-image-preflight.XXXXXXXX)
finish_preflight() {
  result=$?
  trap - EXIT INT TERM
  rm -rf "$preflight_source" || result=1
  [ ! -e "$preflight_source" ] || result=1
  exit "$result"
}
trap finish_preflight EXIT
trap 'exit 130' INT TERM
git -C "$1" archive --format=tar "$core_revision" control-plane-kit-core/src/control_plane_kit_core > "$preflight_source/core.tar"
tar -xf "$preflight_source/core.tar" -C "$preflight_source" --strip-components=1
docker run --pull never --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --workdir /tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e CPK_SOURCE_ASSEMBLY_IMAGES -e CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE -e CPK_SOURCE_PARENT_WEBSITE -e CPK_SOURCE_CHILD_POSTGRES \
  -e CPK_SOURCE_GATEWAY_DOCUMENT -e CPK_SOURCE_POSTGRES_DOCUMENT \
  -e CPK_SOURCE_GATEWAY_DOCUMENT_SHA256 -e CPK_SOURCE_POSTGRES_DOCUMENT_SHA256 \
  -e PYTHONPATH=/preflight-core/src:/source/src:/source/products/cpk_local_gateway/src:/source/products/website_server/src:/source/products/postgres_server/src:/source/products/cpk_server/src \
  --mount "type=bind,source=$preflight_source,target=/preflight-core,readonly" \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  "$validator" python /source/scripts/http_sample_image_inputs.py ${mode:+"$mode"}
