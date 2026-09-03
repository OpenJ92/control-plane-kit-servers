#!/bin/sh
set -eu
umask 077

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
: "${CPK_SERVER_IMAGE:?supply the accepted immutable server image}"
: "${CPK_SERVERS_TEST_IMAGE:?supply the accepted immutable controller image}"
: "${CPK_PUBLIC_CONVERGENCE_APPROVED:?explicit transition approval required}"
: "${CPK_PUBLIC_CONVERGENCE_DESTRUCTIVE_APPROVED:?explicit removal approval required}"
: "${CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT:?supply a durable evidence parent outside bootstrap}"
test "$CPK_PUBLIC_CONVERGENCE_APPROVED" = 1
test "$CPK_PUBLIC_CONVERGENCE_DESTRUCTIVE_APPROVED" = 1
if [ "${CPK_PUBLIC_CONVERGENCE_PULL_CONFIG+x}" = x ]; then
  printf '%s\n' 'public convergence requires cached images; registry configuration is unsupported' >&2
  exit 2
fi
for image in "$CPK_SERVER_IMAGE" "$CPK_SERVERS_TEST_IMAGE"; do
  case "$image" in sha256:*|*@sha256:*) ;; *) exit 1 ;; esac
done

BOOTSTRAP="$(mktemp -d "${TMPDIR:-/tmp}/cpk-public-convergence.XXXXXXXX")"
EVIDENCE_PARENT="$(CDPATH= cd -- "$CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT" && pwd)"
EVIDENCE="$(mktemp -d "$EVIDENCE_PARENT/cpk-public-convergence-evidence.XXXXXXXX")"
printf 'public convergence evidence: %s\n' "$EVIDENCE"
RESOURCE="cpk-convergence-$(basename "$BOOTSTRAP" | tr '[:upper:].' '[:lower:]-')"
export CPK_PUBLIC_CONVERGENCE_WORKSPACE="$RESOURCE"
NETWORK=""
POSTGRES_CONTAINER=""
SERVER_CONTAINER=""
CONTROLLER_CONTAINER=""

finish() {
  status=$?
  trap - EXIT INT TERM
  if [ "$status" -eq 0 ] && [ ! -s "$EVIDENCE/public-convergence.json" ]; then
    status=1
  fi
  if [ "$status" -eq 0 ]; then
    # These are returned immutable IDs, never name/prefix/label selections.
    docker rm -f "$CONTROLLER_CONTAINER" "$SERVER_CONTAINER" "$POSTGRES_CONTAINER" >/dev/null || status=1
    if [ "$status" -eq 0 ]; then
      docker network rm "$NETWORK" >/dev/null || status=1
    fi
    if [ "$status" -eq 0 ]; then
      rm -f "$BOOTSTRAP/server.env" "$BOOTSTRAP/controller.env" "$BOOTSTRAP/postgres.env"
      rm -f "$BOOTSTRAP/server.id" "$BOOTSTRAP/controller.id" "$BOOTSTRAP/postgres.id"
      rmdir "$BOOTSTRAP"
    fi
  else
    printf '%s\n' 'public convergence stopped; bootstrap and durable history retained' >&2
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for name in "$RESOURCE-server" "$RESOURCE-postgres" "$RESOURCE-controller"; do
  if docker container inspect "$name" >/dev/null 2>&1; then exit 1; fi
done
if docker network inspect "$RESOURCE" >/dev/null 2>&1; then exit 1; fi

docker run --rm --pull=never --network none --read-only \
  --tmpfs /tmp:rw,nosuid,size=16m \
  -v "$ROOT:/source:ro" -v "$BOOTSTRAP:/bootstrap:rw" -w /source \
  -e PYTHONDONTWRITEBYTECODE=1 -e CPK_PUBLIC_CONVERGENCE_WORKSPACE \
  "$CPK_SERVERS_TEST_IMAGE" python -B -c \
  'from pathlib import Path; from scripts.cpk_server_public_graph_convergence import write_bootstrap; write_bootstrap(Path("/bootstrap"))'

NETWORK="$(docker network create --internal "$RESOURCE")"
docker run -d --pull=never --name "$RESOURCE-postgres" \
  --network "$NETWORK" --network-alias cpk-postgres \
  --tmpfs /var/lib/postgresql/data:rw,nosuid,size=512m \
  --env-file "$BOOTSTRAP/postgres.env" \
  --health-cmd 'pg_isready -U cpk -d cpk' --health-interval 1s --health-timeout 2s --health-retries 30 \
  postgres:16-alpine > "$BOOTSTRAP/postgres.id"
read -r POSTGRES_CONTAINER < "$BOOTSTRAP/postgres.id"
ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$POSTGRES_CONTAINER")" = healthy ]; then
    ready=1
    break
  fi
  if [ "$attempt" -lt 30 ]; then sleep 1; fi
done
test "$ready" = 1

docker run -d --pull=never --name "$RESOURCE-server" \
  --network "$NETWORK" --network-alias cpk-server \
  --group-add "${CPK_DOCKER_SOCKET_GROUP:-0}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file "$BOOTSTRAP/server.env" \
  -e CPK_SERVER_MODE=execution-capable -e CPK_CONTROL_AUTH_VERIFIER=static-development \
  -e CPK_RUNTIME_INTERPRETERS=docker -e CPK_INGRESS_INTERPRETERS=none \
  -e CPK_PORT=8080 -e CPK_PRODUCT_MATERIAL_RESOLVER=none \
  "$CPK_SERVER_IMAGE" > "$BOOTSTRAP/server.id"
read -r SERVER_CONTAINER < "$BOOTSTRAP/server.id"

docker run -d --pull=never --read-only --name "$RESOURCE-controller" \
  --network "$NETWORK" --tmpfs /tmp:rw,nosuid,size=64m \
  -v "$ROOT:/source:ro" -v "$EVIDENCE:/evidence:rw" -w /source --env-file "$BOOTSTRAP/controller.env" \
  -e PYTHONDONTWRITEBYTECODE=1 -e CPK_PUBLIC_CONVERGENCE_WORKSPACE \
  -e CPK_PUBLIC_CONVERGENCE_PULL_AUTHORITY=0 \
  "$CPK_SERVERS_TEST_IMAGE" python -B -m scripts.cpk_server_public_graph_convergence \
  --approve-transitions --approve-destructive \
  --report /evidence/public-convergence.json \
  --nodes "${CPK_PUBLIC_CONVERGENCE_NODES:-4}" --capacity "${CPK_PUBLIC_CONVERGENCE_CAPACITY:-32}" > "$BOOTSTRAP/controller.id"
read -r CONTROLLER_CONTAINER < "$BOOTSTRAP/controller.id"
result="$(docker wait "$CONTROLLER_CONTAINER")"
docker logs "$CONTROLLER_CONTAINER"
test "$result" = 0
