#!/bin/sh
set -eu

PRODUCT_ID="${1:-}"
TAG="${2:-extract-f}"
OWNER="${GHCR_OWNER:-openj92}"
PACKAGE="${GHCR_PACKAGE:-control-plane-kit-servers}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"

cd "$ROOT"

case "$PRODUCT_ID" in
  cpk-server)
    DOCKERFILE="products/cpk_server/Dockerfile"
    IMAGE_NAME="cpk-server"
    ;;
  hello-server)
    DOCKERFILE="products/hello_server/Dockerfile"
    IMAGE_NAME="hello-server"
    ;;
  http-active-router)
    DOCKERFILE="products/http_active_router/Dockerfile"
    IMAGE_NAME="http-active-router"
    ;;
  http-multiplexer)
    DOCKERFILE="products/http_multiplexer/Dockerfile"
    IMAGE_NAME="http-multiplexer"
    ;;
  cpk-local-gateway)
    DOCKERFILE="products/cpk_local_gateway/Dockerfile"
    IMAGE_NAME="cpk-local-gateway"
    ;;
  cloudflared-connector)
    DOCKERFILE="products/cloudflared_connector/Dockerfile"
    IMAGE_NAME="cloudflared-connector"
    ;;
  secrets-server)
    DOCKERFILE="products/secrets_server/Dockerfile"
    IMAGE_NAME="secrets-server"
    ;;
  *)
    echo "unsupported product id: $PRODUCT_ID" >&2
    exit 2
    ;;
esac

IMAGE="ghcr.io/$OWNER/$PACKAGE/$IMAGE_NAME:$TAG"

if [ "$PRODUCT_ID" = hello-server ]; then
  [ "$OWNER" = openj92 ] && [ "$PACKAGE" = control-plane-kit-servers ]
  SOURCE_COMMIT="$(git rev-parse HEAD)"
  [ "$TAG" = "hello-271-$SOURCE_COMMIT" ]
  [ -z "$(git status --porcelain)" ]
  sh scripts/check_hello_package.sh before-push "$SOURCE_COMMIT"
fi

docker run --rm \
  -v "$ROOT:/source:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /source && PYTHONPATH=/source/src python scripts/apply_coordinates.py --check'

if [ "$PRODUCT_ID" = hello-server ]; then
  docker build --platform linux/amd64 \
    --label "org.opencontainers.image.revision=$SOURCE_COMMIT" \
    -f "$DOCKERFILE" -t "$IMAGE" .
  [ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE")" = linux/amd64 ]
  [ "$(docker image inspect --format '{{.Config.User}}' "$IMAGE")" = hello ]
  HELLO_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
  [ "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" = "$SOURCE_COMMIT" ]
  # Recheck immediately before the consequential step; no retry on ambiguity.
  sh scripts/check_hello_package.sh before-push "$SOURCE_COMMIT"
else
  docker build -f "$DOCKERFILE" -t "$IMAGE" .
fi
docker push "$IMAGE"

if [ "$PRODUCT_ID" = hello-server ]; then
  [ "$(docker image inspect --format '{{.Id}}' "$IMAGE")" = "$HELLO_IMAGE_ID" ]
  REPOSITORY="${IMAGE%:*}"
  # Capture inspection first so a pipe cannot hide an inspection failure.
  REPO_DIGESTS="$(docker image inspect "$HELLO_IMAGE_ID" --format '{{range .RepoDigests}}{{println .}}{{end}}')"
  REFERENCE="$(printf '%s\n' "$REPO_DIGESTS" | sh scripts/select_repository_digest.sh "$REPOSITORY")"
  sh scripts/check_hello_package.sh published "$SOURCE_COMMIT" "$REFERENCE"
  printf 'hello-server reference=%s image_id=%s source=%s platform=linux/amd64 user=hello(uid10002)\n' "$REFERENCE" "$HELLO_IMAGE_ID" "$SOURCE_COMMIT"
  echo "Qualify this actual pulled-by-digest Hello artifact with both declarations before installed use. Source startup evidence does not qualify this rebuilt image. Historical catalogue coordinates remain unchanged." >&2
else
  docker image inspect "$IMAGE" --format "{{index .RepoDigests 0}}"
  echo "Update coordinates/server-products.json with the verified published digest; regenerate coordinates in Docker and validate with ./test.sh." >&2
fi
