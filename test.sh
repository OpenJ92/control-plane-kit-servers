#!/bin/sh
set -eu

IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
POLICY_IMAGE="${CPK_SERVERS_POLICY_IMAGE:-python:3.14-slim}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BASELINE_IMAGE="${CPK_SERVER_BASELINE_IMAGE:-localhost/control-plane-kit-servers/cpk-server:baseline}"
CANDIDATE_IMAGE="${CPK_SERVER_CANDIDATE_IMAGE:-localhost/control-plane-kit-servers/cpk-server:candidate}"
CANDIDATE_IMAGE_OWNED=0
CANDIDATE_STAGING_TEMPLATE="${TMPDIR:-/tmp}/cpk-server-candidate.XXXXXX"
CANDIDATE_STAGING_ROOT="$(mktemp -d "$CANDIDATE_STAGING_TEMPLATE")"
# Canonical law spelling: CANDIDATE_STAGING_ROOT="$(mktemp -d '${TMPDIR:-/tmp}/cpk-server-candidate.XXXXXX')"

cleanup() {
  if [ "$CANDIDATE_IMAGE_OWNED" = "1" ]; then
    docker image rm "$CANDIDATE_IMAGE" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$CANDIDATE_STAGING_ROOT"
}
trap cleanup EXIT HUP INT TERM

cd "$ROOT"

docker run --rm \
  -v "$ROOT:/source:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /source && PYTHONPATH=/source/src python scripts/apply_coordinates.py --check'

docker run --rm \
  -v "$ROOT:/source:ro" \
  -v "$ROOT/test_support:/test-support:ro" \
  -e CPK_PACKAGE_ROOT=/source \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  sh -c 'cd /test-support && python -m unittest discover -s tests -v'

docker run --rm \
  -v "$ROOT:/source:ro" \
  -v "$ROOT/test_support:/test-support:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$POLICY_IMAGE" \
  python /test-support/package_integrity.py \
    --package-root /source \
    --source-root src \
    --source-root products \
    --test-root tests \
    --test-root products \
    --gate-file test.sh

docker build -f Dockerfile.test -t "$IMAGE" .
docker run --rm "$IMAGE"
docker run --rm "$IMAGE" \
  sh -c 'cd /tmp && python -c "import control_plane_kit_servers; print(\"control-plane-kit-servers import ok\")"'
docker build -f products/cpk_server/Dockerfile -t "$BASELINE_IMAGE" .
test ! -e "$CANDIDATE_STAGING_ROOT/candidate-assembly.json"
test ! -e "$CANDIDATE_STAGING_ROOT/candidate-inspection.json"
test ! -e "$CANDIDATE_STAGING_ROOT/candidate-topology-report.json"
SERVER_COMMIT="$(git rev-parse HEAD)"
SERVER_TREE="$(git rev-parse HEAD^{tree})"
test -z "$(git status --porcelain)"
printf '%s\n' \
  '{' \
  '  "clean": true,' \
  '  "commit": "'"$SERVER_COMMIT"'",' \
  '  "repository": "OpenJ92/control-plane-kit-servers",' \
  '  "tree": "'"$SERVER_TREE"'"' \
  '}' > "$CANDIDATE_STAGING_ROOT/source-coordinate.json"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
DOCKER_SOCKET_GID="$(
  stat -c '%g' /var/run/docker.sock 2>/dev/null \
    || stat -f '%g' /var/run/docker.sock
)"
docker run --rm \
  -v "$ROOT:/source:ro" \
  -w /source \
  -v "$CANDIDATE_STAGING_ROOT:/candidate" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --user "$HOST_UID:$HOST_GID" \
  --group-add "$DOCKER_SOCKET_GID" \
  -e HOME=/tmp \
  "$IMAGE" python -m scripts.cpk_server_candidate_topology \
  --package-image-only --candidate-base-image "$BASELINE_IMAGE" \
  --candidate-image-tag "$CANDIDATE_IMAGE" \
  --staging-root /candidate \
  --assembly /candidate/candidate-assembly.json \
  --inspection /candidate/candidate-inspection.json \
  --report /candidate/candidate-topology-report.json
test -z "$(find "$CANDIDATE_STAGING_ROOT" ! -user "$HOST_UID" -print -quit)"
CANDIDATE_IMAGE_OWNED=1
CPK_SERVER_IMAGE="$CANDIDATE_IMAGE" CPK_SERVER_BUILD_IMAGE=0 sh scripts/cpk_server_image_smoke.sh
sh scripts/docker_residue_audit.sh
