#!/bin/sh
set -eu
umask 077

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

# Persistent installation disposal is deliberately not a client exit action.
persistent_demo() {
  mode="$1"
  : "${CPK_DEMO_INSTALLATION_DIR:?supply a durable private installation directory}"
  : "${CPK_SERVER_IMAGE:?supply the accepted server image ID}"
  : "${CPK_SERVERS_TEST_IMAGE:?supply the accepted controller image ID}"
  : "${CPK_DEMO_POSTGRES_IMAGE:?supply the accepted Postgres image ID}"
  INSTALLATION="$CPK_DEMO_INSTALLATION_DIR"
  RESOURCE="${CPK_DEMO_INSTALLATION_NAME:-cpk-demo-primary}"
  case "$INSTALLATION" in /*) ;; *) return 2 ;; esac
  case "$RESOURCE" in ''|*[!a-z0-9-]*) return 2 ;; esac
  test "${#RESOURCE}" -le 48
  if [ "${CPK_PUBLIC_CONVERGENCE_PULL_CONFIG+x}" = x ]; then
    printf '%s\n' 'public convergence requires cached images; registry configuration is unsupported' >&2
    return 2
  fi
  for image in "$CPK_SERVER_IMAGE" "$CPK_SERVERS_TEST_IMAGE" "$CPK_DEMO_POSTGRES_IMAGE"; do
    case "$image" in sha256:*) ;; *) return 2 ;; esac
    test "$(docker image inspect -f '{{.Id}}' "$image")" = "$image"
  done
  if [ "$mode" = bootstrap ]; then
    test "${CPK_DEMO_BOOTSTRAP_APPROVED:-0}" = 1
    : "${CPK_DEMO_PROVIDER_URL:?supply the existing authorized custody endpoint}"
    : "${CPK_DEMO_PROVIDER_CREDENTIAL_FILE:?supply the existing server-only custody credential file}"
    : "${CPK_DEMO_TOKEN_REFERENCE:?supply the existing opaque application tunnel reference}"
    test -f "$CPK_DEMO_PROVIDER_CREDENTIAL_FILE"
    test ! -L "$CPK_DEMO_PROVIDER_CREDENTIAL_FILE"
    test -s "$CPK_DEMO_PROVIDER_CREDENTIAL_FILE"
    test ! -e "$INSTALLATION"
    test ! -L "$INSTALLATION"
    mkdir -m 700 "$INSTALLATION"
    for name in "$RESOURCE-server" "$RESOURCE-postgres"; do
      if docker container inspect "$name" >/dev/null 2>&1; then return 1; fi
    done
    if docker network inspect "$RESOURCE" >/dev/null 2>&1; then return 1; fi
    if docker volume inspect "$RESOURCE-postgres-data" >/dev/null 2>&1; then return 1; fi
    export CPK_PUBLIC_CONVERGENCE_WORKSPACE="${CPK_DEMO_APPLICATION_WORKSPACE:-demo-hello-world}"
    export CPK_DEMO_WORKSPACES="${CPK_DEMO_WORKSPACES:-demo-hello-world,demo-sandbox}"
    docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,size=16m \
      -v "$ROOT:/source:ro" -v "$INSTALLATION:/installation:rw" \
      -v "$CPK_DEMO_PROVIDER_CREDENTIAL_FILE:/provider-credential:ro" -w /source \
      -e PYTHONDONTWRITEBYTECODE=1 -e CPK_PUBLIC_CONVERGENCE_WORKSPACE \
      -e CPK_DEMO_WORKSPACES -e CPK_DEMO_PROVIDER_URL -e CPK_DEMO_TOKEN_REFERENCE \
      "$CPK_SERVERS_TEST_IMAGE" python -B -c '
from pathlib import Path
from scripts.cpk_server_public_graph_convergence import write_persistent_bootstrap
try:
    write_persistent_bootstrap(Path("/installation"))
except Exception:
    raise SystemExit("persistent bootstrap configuration rejected") from None
'
    printf '%s\n' "$RESOURCE" > "$INSTALLATION/name"
    printf '%s\n' "$CPK_SERVER_IMAGE" > "$INSTALLATION/server-image"
    printf '%s\n' "$CPK_SERVERS_TEST_IMAGE" > "$INSTALLATION/controller-image"
    printf '%s\n' "$CPK_DEMO_POSTGRES_IMAGE" > "$INSTALLATION/postgres-image"
    printf '%s\n' "$CPK_PUBLIC_CONVERGENCE_WORKSPACE" > "$INSTALLATION/workspace"
    read -r OWNERSHIP < "$INSTALLATION/ownership.id"
    docker network create --label "org.openj92.cpk.installation=$OWNERSHIP" "$RESOURCE" > "$INSTALLATION/network.id"
    docker volume create --label "org.openj92.cpk.installation=$OWNERSHIP" "$RESOURCE-postgres-data" > "$INSTALLATION/volume"
    # Docker volume create may return an existing name: never initialize it
    # unless this fresh invocation's ownership marker is actually present.
    test "$(docker volume inspect -f '{{index .Labels "org.openj92.cpk.installation"}}' "$RESOURCE-postgres-data")" = "$OWNERSHIP"
    docker volume inspect -f '{{.CreatedAt}}' "$RESOURCE-postgres-data" > "$INSTALLATION/volume-created"
    read -r NETWORK < "$INSTALLATION/network.id"
    docker run -d --pull=never --name "$RESOURCE-postgres" --network "$NETWORK" --network-alias cpk-postgres \
      --mount "type=volume,source=$RESOURCE-postgres-data,target=/var/lib/postgresql/data" \
      --env-file "$INSTALLATION/postgres.env" \
      --health-cmd 'pg_isready -U cpk -d cpk' --health-interval 1s --health-timeout 2s --health-retries 30 \
      "$CPK_DEMO_POSTGRES_IMAGE" > "$INSTALLATION/postgres.id"
    read -r POSTGRES_CONTAINER < "$INSTALLATION/postgres.id"
    ready=0
    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
      if [ "$(docker inspect -f '{{.State.Health.Status}}' "$POSTGRES_CONTAINER")" = healthy ]; then ready=1; break; fi
      if [ "$attempt" -lt 30 ]; then sleep 1; fi
    done
    test "$ready" = 1
    docker run -d --pull=never --name "$RESOURCE-server" --network "$NETWORK" --network-alias cpk-server \
      --group-add "${CPK_DOCKER_SOCKET_GROUP:-0}" -p 127.0.0.1:18080:8080 \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v "$INSTALLATION/provider-client-token:/run/secrets/cpk-provider/client-token:ro" \
      --env-file "$INSTALLATION/server.env" \
      -e CPK_SERVER_MODE=execution-capable -e CPK_CONTROL_AUTH_VERIFIER=static-development \
      -e CPK_RUNTIME_INTERPRETERS=docker -e CPK_INGRESS_INTERPRETERS=none \
      -e CPK_PORT=8080 -e CPK_PRODUCT_MATERIAL_RESOLVER=provider \
      "$CPK_SERVER_IMAGE" > "$INSTALLATION/server.id"
    printf '%s\n' ready > "$INSTALLATION/ready"
    printf '%s\n' 'persistent bootstrap created; custody and application connectivity require admission'
    return
  fi

  test "$mode" = attach
  test "${CPK_PUBLIC_CONVERGENCE_APPROVED:-0}" = 1
  test -d "$INSTALLATION"
  test ! -L "$INSTALLATION"
  for file in ready name ownership.id server-image controller-image postgres-image network.id volume volume-created workspace server.id postgres.id application.json controller.env provider-client-token; do
    test -f "$INSTALLATION/$file"
    test ! -L "$INSTALLATION/$file"
    test -s "$INSTALLATION/$file"
  done
  read -r recorded < "$INSTALLATION/name"; test "$recorded" = "$RESOURCE"
  read -r recorded < "$INSTALLATION/server-image"; test "$recorded" = "$CPK_SERVER_IMAGE"
  read -r recorded < "$INSTALLATION/controller-image"; test "$recorded" = "$CPK_SERVERS_TEST_IMAGE"
  read -r recorded < "$INSTALLATION/postgres-image"; test "$recorded" = "$CPK_DEMO_POSTGRES_IMAGE"
  read -r NETWORK < "$INSTALLATION/network.id"
  read -r OWNERSHIP < "$INSTALLATION/ownership.id"
  read -r SERVER_CONTAINER < "$INSTALLATION/server.id"
  read -r POSTGRES_CONTAINER < "$INSTALLATION/postgres.id"
  for id in "$NETWORK" "$SERVER_CONTAINER" "$POSTGRES_CONTAINER"; do
    case "$id" in ''|*[!a-f0-9]*) return 1 ;; esac
    test "${#id}" -eq 64
  done
  test "$(docker network inspect -f '{{.Id}}' "$NETWORK")" = "$NETWORK"
  test "$(docker network inspect -f '{{.Name}}' "$NETWORK")" = "$RESOURCE"
  test "$(docker network inspect -f '{{index .Labels "org.openj92.cpk.installation"}}' "$NETWORK")" = "$OWNERSHIP"
  test "$(docker volume inspect -f '{{index .Labels "org.openj92.cpk.installation"}}' "$RESOURCE-postgres-data")" = "$OWNERSHIP"
  read -r recorded < "$INSTALLATION/volume-created"
  test "$(docker volume inspect -f '{{.CreatedAt}}' "$RESOURCE-postgres-data")" = "$recorded"
  test "$(docker inspect -f '{{.Image}} {{.State.Running}}' "$SERVER_CONTAINER")" = "$CPK_SERVER_IMAGE true"
  test "$(docker inspect -f '{{.Image}} {{.State.Health.Status}}' "$POSTGRES_CONTAINER")" = "$CPK_DEMO_POSTGRES_IMAGE healthy"
  test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$POSTGRES_CONTAINER")" = "$RESOURCE-postgres-data"
  test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/run/secrets/cpk-provider/client-token"}}{{.Source}} {{.RW}}{{end}}{{end}}' "$SERVER_CONTAINER")" = "$INSTALLATION/provider-client-token false"
  test "$(docker inspect -f "{{range .NetworkSettings.Networks}}{{if eq .NetworkID \"$NETWORK\"}}{{.NetworkID}}{{end}}{{end}}" "$SERVER_CONTAINER")" = "$NETWORK"
  test "$(docker inspect -f "{{range .NetworkSettings.Networks}}{{if eq .NetworkID \"$NETWORK\"}}{{.NetworkID}}{{end}}{{end}}" "$POSTGRES_CONTAINER")" = "$NETWORK"
  read -r CPK_PUBLIC_CONVERGENCE_WORKSPACE < "$INSTALLATION/workspace"
  export CPK_PUBLIC_CONVERGENCE_WORKSPACE
  : "${CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT:?supply a durable client evidence parent}"
  EVIDENCE="$(mktemp -d "$CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT/cpk-retained-application.XXXXXXXX")"
  set -- --approve-transitions --retained-application /application.json
  if [ "${CPK_DEMO_CREATE_WORKSPACE:-0}" = 1 ]; then set -- "$@" --create-workspace; fi
  if [ "${CPK_PUBLIC_CONVERGENCE_DESTRUCTIVE_APPROVED:-0}" = 1 ]; then set -- "$@" --approve-destructive; fi
  docker run -d --pull=never --read-only --network "$NETWORK" --tmpfs /tmp:rw,nosuid,size=64m \
    -v "$ROOT:/source:ro" -v "$EVIDENCE:/evidence:rw" \
    -v "$INSTALLATION/application.json:/application.json:ro" -w /source --env-file "$INSTALLATION/controller.env" \
    -e PYTHONDONTWRITEBYTECODE=1 -e CPK_PUBLIC_CONVERGENCE_WORKSPACE -e CPK_PUBLIC_CONVERGENCE_PULL_AUTHORITY=0 \
    "$CPK_SERVERS_TEST_IMAGE" python -B -m scripts.cpk_server_public_graph_convergence "$@" \
    --report /evidence/public-convergence.json --nodes "${CPK_PUBLIC_CONVERGENCE_NODES:-1}" \
    --active-node "${CPK_DEMO_ACTIVE_NODE:-1}" --capacity "${CPK_PUBLIC_CONVERGENCE_CAPACITY:-4}" > "$EVIDENCE/controller.id"
  read -r CONTROLLER_CONTAINER < "$EVIDENCE/controller.id"
  result="$(docker wait "$CONTROLLER_CONTAINER")"
  docker logs "$CONTROLLER_CONTAINER"
  printf '%s\n' "$result" > "$EVIDENCE/client-exit"
  printf 'retained application evidence: %s\n' "$EVIDENCE"
  test "$result" = 0
  test -s "$EVIDENCE/public-convergence.json"
  docker rm "$CONTROLLER_CONTAINER" >/dev/null
}

case "${CPK_PUBLIC_CONVERGENCE_MODE:-disposable}" in
  bootstrap|attach)
    persistent_demo "$CPK_PUBLIC_CONVERGENCE_MODE"
    exit $?
    ;;
  disposable) ;;
  *) exit 2 ;;
esac

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
