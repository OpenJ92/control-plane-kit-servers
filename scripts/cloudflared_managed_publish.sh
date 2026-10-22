#!/bin/sh
# Explicit managed product producer. Invocation requires a reviewed artifact release.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
TAG="${1:?source-bound tag required}"
SOURCE="$(git rev-parse HEAD)"
[ -z "$(git status --porcelain)" ]
[ "$TAG" = "managed-$SOURCE" ]
[ "${GHCR_OWNER:-openj92}" = openj92 ]
[ "${GHCR_PACKAGE:-control-plane-kit-servers}" = control-plane-kit-servers ]
REPOSITORY=ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector
DESTINATION="$REPOSITORY:$TAG"
RECEIPTS="${CPK_MANAGED_RELEASE_RECEIPTS:?new absolute evidence directory required}"
case "$RECEIPTS" in /*) ;; *) exit 2 ;; esac
[ ! -e "$RECEIPTS" ] && [ ! -L "$RECEIPTS" ]
PARENT="$(dirname -- "$RECEIPTS")"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ]
[ "$(CDPATH= cd -- "$PARENT" && pwd -P)" = "$PARENT" ]
umask 077
mkdir -m 700 "$RECEIPTS"
ENDPOINT='users/OpenJ92/packages/container/control-plane-kit-servers%2Fcloudflared-connector'
metadata() {
  mkdir -m 700 "$RECEIPTS/$1"
  gh api "$ENDPOINT" > "$RECEIPTS/$1/package.json"
  gh api --paginate --slurp "$ENDPOINT/versions?per_page=100" > "$RECEIPTS/$1/versions.json"
}
metadata preflight
# No build or upload to an absent/public/wrong package or colliding tag.
jq -e '.name == "control-plane-kit-servers/cloudflared-connector" and .package_type == "container" and .visibility == "private"' "$RECEIPTS/preflight/package.json" >/dev/null
jq -e --arg tag "$TAG" 'type == "array" and length > 0 and all(.[]; type == "array") and all(.[][]; (.metadata.container.tags | type == "array") and (.metadata.container.tags | index($tag) | not))' "$RECEIPTS/preflight/versions.json" >/dev/null
./test.sh --managed-connector-controller --receipt-dir "$RECEIPTS/controller"
CONTROLLER="$(cat "$RECEIPTS/controller/image.id")"
policy() {
  docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$ROOT,target=/source,readonly" \
    --mount "type=bind,source=$RECEIPTS,target=/evidence,readonly" \
    "$CONTROLLER" python /source/products/cloudflared_connector/release.py "$@"
}
policy package /evidence/preflight "$SOURCE" > "$RECEIPTS/preflight/validated.json"
# Local candidate has no registry publication tag until qualification succeeds.
set +e
docker buildx build --load --platform linux/amd64 \
  --label org.opencontainers.image.source=https://github.com/OpenJ92/control-plane-kit-servers \
  --label "org.opencontainers.image.revision=$SOURCE" \
  --iidfile "$RECEIPTS/candidate.id" --metadata-file "$RECEIPTS/build-metadata.json" \
  -f products/cloudflared_connector/Dockerfile.managed . > "$RECEIPTS/build.log" 2>&1
RESULT=$?
set -e
printf '%s\n' "$RESULT" > "$RECEIPTS/build.exit"
[ "$RESULT" = 0 ] || exit "$RESULT"
CANDIDATE="$(cat "$RECEIPTS/candidate.id")"
./test.sh --managed-connector-candidate --image-id "$CANDIDATE" --source "$SOURCE" \
  --controller-image-id "$CONTROLLER" --controller-receipt "$RECEIPTS/controller/controller.json" \
  --receipt-dir "$RECEIPTS/qualification"
policy qualified /evidence/qualification/qualification.json "$CANDIDATE" "$SOURCE"
[ "$(docker image inspect "$CANDIDATE" --format '{{.Id}}')" = "$CANDIDATE" ]
[ "$(docker image inspect "$CANDIDATE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$SOURCE" ]
[ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$SOURCE" ]
metadata before-push
policy package /evidence/before-push "$SOURCE" > "$RECEIPTS/before-push/validated.json"
docker tag "$CANDIDATE" "$DESTINATION"
[ "$(docker image inspect "$DESTINATION" --format '{{.Id}}')" = "$CANDIDATE" ]
set +e
docker push "$DESTINATION" > "$RECEIPTS/push.log" 2>&1
RESULT=$?
set -e
printf '%s\n' "$RESULT" > "$RECEIPTS/push.exit"
[ "$RESULT" = 0 ] || exit "$RESULT"
[ "$(docker image inspect "$DESTINATION" --format '{{.Id}}')" = "$CANDIDATE" ]
# Resolve the actual remote tag, then verify immutable bytes against build output.
docker buildx imagetools inspect --raw "$DESTINATION" > "$RECEIPTS/remote-index.json"
DIGEST="sha256:$(shasum -a 256 "$RECEIPTS/remote-index.json" | cut -d ' ' -f 1)"
[ "$DIGEST" = "$(jq -r '.["containerimage.digest"]' "$RECEIPTS/build-metadata.json")" ]
REFERENCE="$REPOSITORY@$DIGEST"
metadata published
policy package /evidence/published "$SOURCE" "$DIGEST" > "$RECEIPTS/published/validated.json"
if jq -e '.manifests' "$RECEIPTS/remote-index.json" >/dev/null; then
  PLATFORM="$(jq -er '[.manifests[] | select(.platform.os == "linux" and .platform.architecture == "amd64")] | if length == 1 then .[0].digest else error("platform") end' "$RECEIPTS/remote-index.json")"
  docker buildx imagetools inspect --raw "$REPOSITORY@$PLATFORM" > "$RECEIPTS/remote-platform.json"
  [ "sha256:$(shasum -a 256 "$RECEIPTS/remote-platform.json" | cut -d ' ' -f 1)" = "$PLATFORM" ]
else
  PLATFORM="$DIGEST"
  cp "$RECEIPTS/remote-index.json" "$RECEIPTS/remote-platform.json"
fi
CONFIG="$(jq -er .config.digest "$RECEIPTS/remote-platform.json")"
[ "$CONFIG" = "$(jq -r '.["containerimage.config.digest"]' "$RECEIPTS/build-metadata.json")" ]
docker buildx imagetools inspect "$REPOSITORY@$PLATFORM" --format '{{json .Image}}' > "$RECEIPTS/remote-config.json"
jq -e --arg source "$SOURCE" '.os == "linux" and .architecture == "amd64" and .config.Labels["org.opencontainers.image.revision"] == $source' "$RECEIPTS/remote-config.json" >/dev/null
QUALIFICATION_HASH="$(shasum -a 256 "$RECEIPTS/qualification/qualification.json" | cut -d ' ' -f 1)"
jq -n --arg reference "$REFERENCE" --arg candidate "$CANDIDATE" --arg source "$SOURCE" \
  --arg platform "$PLATFORM" --arg config "$CONFIG" --arg qualification "$QUALIFICATION_HASH" \
  '{schema:"cpk.cloudflared-managed-publication.v1",reference:$reference,candidate_id:$candidate,source_commit:$source,platform_manifest:$platform,config_digest:$config,qualification_sha256:$qualification,visibility:"private",status:"verified"}' > "$RECEIPTS/publication.json"
printf 'Managed image published and correspondence verified: %s\n' "$REFERENCE"
echo 'Package qualification/publication does not establish real tunnel connection or installation pull permission.'
