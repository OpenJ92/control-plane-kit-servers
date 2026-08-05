#!/bin/sh
set -eu

SERVERS_REPO="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
SECRETS_REPO="${CPK_SECRETS_REPO:-$(CDPATH= cd -- "$SERVERS_REPO/../control-plane-kit-secrets" && pwd)}"
CONTROLLER_IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
SERVER_IMAGE="${CPK_CLOUDFLARE_CUSTODY_SERVER_IMAGE:-control-plane-kit-servers/cpk-server:source-1203}"
SECRETS_IMAGE="${CPK_SECRETS_TEST_IMAGE:-control-plane-kit-secrets:source-1203}"
POSTGRES_IMAGE="${CPK_LIVE_POSTGRES_IMAGE:-postgres:16-alpine}"
BUILD_IMAGES="${CPK_CLOUDFLARE_CUSTODY_BUILD_IMAGES:-1}"
CLOUDFLARE_ENV_FILE="${CPK_CLOUDFLARE_ENV_FILE:-$SERVERS_REPO/env/cloudflare.openj92.local.dev}"
SCENARIO="${CPK_CLOUDFLARE_CUSTODY_SCENARIO:-cloudflare-tunnel-custody}"
SOURCE_LIVE_GATEWAY_IMAGE="${CPK_SOURCE_LIVE_GATEWAY_IMAGE:-}"
SOURCE_LIVE_GATEWAY_SOURCE_COMMIT="${CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT:-}"
RUN_SUFFIX="$(date +%s)-$$"
case "$SCENARIO" in
  cloudflare-tunnel-custody)
    WORKSPACE_ID="workspace-secret-cloudflare-$RUN_SUFFIX"
    PUBLIC_HOSTNAME="cpk-sec1203-$RUN_SUFFIX.openj92.dev"
    ;;
  gateway-key-rotation-overlay)
    WORKSPACE_ID="workspace-gateway-key-rotation-$RUN_SUFFIX"
    PUBLIC_HOSTNAME="cpk-rot1404-$RUN_SUFFIX-gateway.openj92.dev"
    PUBLIC_HOSTNAME_PATTERN="cpk-rot1404-$RUN_SUFFIX-*.openj92.dev"
    if [ -z "$SOURCE_LIVE_GATEWAY_IMAGE" ] || \
       [ -z "$SOURCE_LIVE_GATEWAY_SOURCE_COMMIT" ]; then
      echo "gateway source-live image digest and source commit are required" >&2
      exit 2
    fi
    ;;
  *)
    echo "unsupported Cloudflare custody scenario: $SCENARIO" >&2
    exit 2
    ;;
esac
NETWORK="cpk-secret-cloudflare-source-live-$RUN_SUFFIX"
LABEL="org.openj92.project=control-plane-kit-servers"
WORKSPACE_LABEL_KEY="org.openj92.cpk.workspace"
STATE_ROOT="$(mktemp -d)"
PROVIDER_DATA_DIR="$STATE_ROOT/provider-data"
BOOTSTRAP_DIR="$STATE_ROOT/bootstrap"
CONTROLLER_STATE_DIR="$STATE_ROOT/controller-state"
CONTROLLER_STATE_FILE="$CONTROLLER_STATE_DIR/checkpoint.json"
OPERATIONS_DUMP="$STATE_ROOT/operations.sql"
POSTGRES_CONTAINER=""
SECRETS_CONTAINER=""
SERVER_CONTAINER=""
CONTROLLER_STATUS=0
ABORT_CLEANUP_ATTEMPTED=0

mkdir -p "$PROVIDER_DATA_DIR" "$BOOTSTRAP_DIR" "$CONTROLLER_STATE_DIR"
umask 077

cleanup_workspace_resources() {
  docker ps -aq --filter "label=$WORKSPACE_LABEL_KEY=$WORKSPACE_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker rm -f "$resource" >/dev/null 2>&1 || true
        fi
      done
  docker volume ls -q --filter "label=$WORKSPACE_LABEL_KEY=$WORKSPACE_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker volume rm "$resource" >/dev/null 2>&1 || true
        fi
      done
  docker network ls -q --filter "label=$WORKSPACE_LABEL_KEY=$WORKSPACE_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker network rm "$resource" >/dev/null 2>&1 || true
        fi
      done
}

cleanup() {
  if [ -n "$SERVER_CONTAINER" ]; then
    docker rm -fv "$SERVER_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -n "$SECRETS_CONTAINER" ]; then
    docker rm -fv "$SECRETS_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -n "$POSTGRES_CONTAINER" ]; then
    docker rm -fv "$POSTGRES_CONTAINER" >/dev/null 2>&1 || true
  fi
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  cleanup_workspace_resources
  rm -rf "$STATE_ROOT"
}

finish() {
  status=$?
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] \
    && [ "$CONTROLLER_STATUS" -ne 0 ] \
    && [ "$ABORT_CLEANUP_ATTEMPTED" -eq 0 ] \
    && [ -f "$CONTROLLER_STATE_FILE" ]; then
    ABORT_CLEANUP_ATTEMPTED=1
    echo "source-live controller failed; attempting cpk-server-first abort cleanup" >&2
    if ! run_controller abort-cleanup; then
      echo "source-live abort cleanup remained non-success" >&2
    fi
  fi
  cleanup
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

if [ ! -r "$CLOUDFLARE_ENV_FILE" ]; then
  echo "Cloudflare authority configuration is unavailable" >&2
  exit 1
fi
set -a
. "$CLOUDFLARE_ENV_FILE"
set +a
: "${OPENJ92_CLOUDFLARE_ACCOUNT_ID:?Cloudflare account id is required}"
: "${OPENJ92_CLOUDFLARE_ZONE_ID:?Cloudflare zone id is required}"
: "${OPENJ92_CLOUDFLARE_API_TOKEN:?Cloudflare API token is required}"
: "${OPENJ92_CLOUDFLARE_ZONE:=openj92.dev}"
printf '%s' "$OPENJ92_CLOUDFLARE_API_TOKEN" >"$BOOTSTRAP_DIR/cloudflare-api-token"
unset OPENJ92_CLOUDFLARE_API_TOKEN
unset OPENJ92_CLOUDFLARE_TUNNEL_TOKEN
unset OPENJ92_CLOUDFLARE_TUNNEL_ID

if [ "$BUILD_IMAGES" = "1" ]; then
  docker build -f "$SERVERS_REPO/Dockerfile.test" -t "$CONTROLLER_IMAGE" "$SERVERS_REPO"
  docker build -f "$SERVERS_REPO/products/cpk_server/Dockerfile" -t "$SERVER_IMAGE" "$SERVERS_REPO"
  docker build -f "$SECRETS_REPO/Dockerfile.test" -t "$SECRETS_IMAGE" "$SECRETS_REPO"
fi

docker run --rm \
  -v "$BOOTSTRAP_DIR:/bootstrap" \
  "$SECRETS_IMAGE" \
  python -c '
from pathlib import Path
import os
import secrets
from control_plane_kit_secrets.crypto import encode_master_key_for_file

base = Path("/bootstrap")
base.joinpath("master.key").write_text(
    encode_master_key_for_file(os.urandom(32)),
    encoding="utf-8",
)
base.joinpath("client-token").write_text(
    secrets.token_urlsafe(48),
    encoding="utf-8",
)
base.joinpath("postgres-password").write_text(
    secrets.token_urlsafe(40),
    encoding="utf-8",
)
'

docker run --rm \
  -v "$BOOTSTRAP_DIR:/bootstrap" \
  "$CONTROLLER_IMAGE" \
  python -c '
import json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

base = Path("/bootstrap")
private_key = Ed25519PrivateKey.generate()
base.joinpath("gateway-private-key.pem").write_bytes(
    private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
base.joinpath("gateway-public-key.pem").write_text(
    public_pem,
    encoding="utf-8",
)
rotation_key = Ed25519PrivateKey.generate()
base.joinpath("gateway-rotation-key-a.pem").write_bytes(
    rotation_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
base.joinpath("gateway-rotation-key-a-public.pem").write_bytes(
    rotation_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)
'

BOOTSTRAP_DIR="$BOOTSTRAP_DIR" SCENARIO="$SCENARIO" python3 -c '
import json
import os
from pathlib import Path

token = Path(os.environ["BOOTSTRAP_DIR"], "client-token").read_text(encoding="utf-8")
intents = [
    "cloudflare.api-token",
    "cloudflare.tunnel-token",
    "gateway.probe-signing-key",
    "oci.pull-credential",
]
if os.environ["SCENARIO"] == "gateway-key-rotation-overlay":
    intents.append("postgres.password")
grants = [
    {
        "action": "secret.write",
        "workspace_id": "*",
        "intents": intents,
    },
    {
        "action": "secret.resolve",
        "workspace_id": "*",
        "intents": intents,
    },
    {"action": "secret.revoke", "workspace_id": "*"},
    {"action": "secret.metadata", "workspace_id": "*"},
]
if os.environ["SCENARIO"] == "gateway-key-rotation-overlay":
    grants.extend(
        (
            {
                "action": "secret.generate-delegation-key",
                "workspace_id": "*",
                "intents": ["gateway.probe-signing-key"],
            },
            {"action": "secret.rotate", "workspace_id": "*"},
        )
    )
credentials = [{
    "subject": "cpk-server-source-live",
    "token": token,
    "grants": grants,
}]
Path(os.environ["BOOTSTRAP_DIR"], "credentials.json").write_text(
    json.dumps(credentials, separators=(",", ":"), sort_keys=True),
    encoding="utf-8",
)
'
chmod 0400 "$BOOTSTRAP_DIR"/*

CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON="$(
  WORKSPACE_ID="$WORKSPACE_ID" SCENARIO="$SCENARIO" python3 -c '
import json
import os

workspace_id = os.environ["WORKSPACE_ID"]
operator_scopes = [
    "hub:instance:create",
    "hub:instance:read",
    "instance:workspace:read",
    "instance:workspace:edit",
    "plan:request",
    "plan:approve",
    "plan:approve-destructive",
    "plan:execute",
    "execution:operate",
    "runtime-authority:register",
    "runtime-authority:read",
    "runtime-authority:revoke",
    "runtime-authority:use",
    "ingress-authority:register",
    "ingress-authority:read",
    "ingress-authority:revoke",
    "ingress-authority:use",
    "secret-provider:register",
    "secret-provider:read",
    "secret-provider:revoke",
    "secret-provider:use",
    "gateway-probe:use",
    "delegation-key:register",
    "delegation-key:read",
    "delegation-key:activate",
    "delegation-key:retire",
    "delegation-key:revoke",
    "delegation-key:use",
]
if os.environ["SCENARIO"] == "gateway-key-rotation-overlay":
    operator_scopes.extend(
        (
            "delegation-key:rotate",
            "delegation-key:rotate-approve",
        )
    )
worker_scopes = [
    "execution:operate",
    "secret-provider:use",
]
print(json.dumps([
    {
        "credential": "present",
        "subject_id": "hosted-operator",
        "kind": "operator",
        "workspace_grants": {workspace_id: operator_scopes},
    },
    {
        "credential": "worker-present",
        "subject_id": "hosted-worker",
        "kind": "worker",
        "workspace_grants": {workspace_id: worker_scopes},
    },
], separators=(",", ":"), sort_keys=True))
'
)"

PROVIDER_ROUTES_JSON='{"source-live-secrets":"http://cpk-secrets:8081"}'
PROVIDER_BOOTSTRAP_FILES_JSON='{"secret://bootstrap/provider/client-token":"/run/secrets/cpk-provider/client-token"}'

docker network create "$NETWORK" >/dev/null

POSTGRES_CONTAINER="$(docker run -d \
  --label "$LABEL" \
  --network "$NETWORK" \
  --network-alias cpk-postgres \
  -e POSTGRES_DB=cpk \
  -e POSTGRES_USER=cpk \
  -e POSTGRES_PASSWORD=cpk \
  "$POSTGRES_IMAGE")"

POSTGRES_READY=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if docker exec "$POSTGRES_CONTAINER" psql -U cpk -d cpk -c 'SELECT 1' >/dev/null 2>&1; then
    POSTGRES_READY=1
    break
  fi
  sleep 1
done
if [ "$POSTGRES_READY" != "1" ]; then
  echo "operations Postgres did not become query-ready" >&2
  exit 1
fi

SECRETS_CONTAINER="$(docker run -d \
  --label "$LABEL" \
  --network "$NETWORK" \
  --network-alias cpk-secrets \
  -v "$PROVIDER_DATA_DIR:/var/lib/cpk-secrets" \
  -v "$BOOTSTRAP_DIR/master.key:/run/secrets/cpk-secrets/master-key:ro" \
  -v "$BOOTSTRAP_DIR/credentials.json:/run/secrets/cpk-secrets/credentials.json:ro" \
  -e CPK_SECRETS_DATABASE_PATH=/var/lib/cpk-secrets/secrets.sqlite3 \
  -e CPK_SECRETS_MASTER_KEY_FILE=/run/secrets/cpk-secrets/master-key \
  -e CPK_SECRETS_CREDENTIALS_FILE=/run/secrets/cpk-secrets/credentials.json \
  -e CPK_SECRETS_PROVIDER_ID=control-plane-kit \
  "$SECRETS_IMAGE" \
  python -m uvicorn control_plane_kit_secrets.server:app \
    --host 0.0.0.0 --port 8081 --log-level warning)"

SECRETS_READY=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if docker run --rm \
    --network "$NETWORK" \
    "$SECRETS_IMAGE" \
    python -c '
from urllib.request import urlopen
with urlopen("http://cpk-secrets:8081/health/ready", timeout=2) as response:
    raise SystemExit(0 if response.status == 200 else 1)
' >/dev/null 2>&1; then
    SECRETS_READY=1
    break
  fi
  sleep 1
done
if [ "$SECRETS_READY" != "1" ]; then
  echo "secrets provider did not become ready" >&2
  exit 1
fi

if command -v gh >/dev/null 2>&1 && GHCR_TOKEN="$(gh auth token 2>/dev/null)"; then
  BOOTSTRAP_DIR="$BOOTSTRAP_DIR" GHCR_TOKEN="$GHCR_TOKEN" python3 -c '
import json
import os
from pathlib import Path

Path(os.environ["BOOTSTRAP_DIR"], "ghcr-pull-credential.json").write_text(
    json.dumps(
        {"username": "OpenJ92", "password": os.environ["GHCR_TOKEN"]},
        separators=(",", ":"),
        sort_keys=True,
    ),
    encoding="utf-8",
)
Path(os.environ["BOOTSTRAP_DIR"], "ghcr-token-sentinel").write_text(
    os.environ["GHCR_TOKEN"],
    encoding="utf-8",
)
'
  unset GHCR_TOKEN
fi
if [ ! -s "$BOOTSTRAP_DIR/ghcr-pull-credential.json" ]; then
  echo "GHCR pull authority is unavailable" >&2
  exit 1
fi
chmod 0400 \
  "$BOOTSTRAP_DIR/ghcr-pull-credential.json" \
  "$BOOTSTRAP_DIR/ghcr-token-sentinel"

SERVER_CONTAINER="$(docker run -d \
  --label "$LABEL" \
  --network "$NETWORK" \
  --network-alias cpk-server \
  --group-add "${CPK_DOCKER_SOCKET_GROUP:-0}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$BOOTSTRAP_DIR/client-token:/run/secrets/cpk-provider/client-token:ro" \
  -e CPK_SERVER_MODE=execution-capable \
  -e CPK_CONTROL_AUTH_VERIFIER=static-development \
  -e CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON="$CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON" \
  -e CPK_PORT=8080 \
  -e CPK_RUNTIME_INTERPRETERS=docker \
  -e CPK_INGRESS_INTERPRETERS=cloudflare \
  -e CPK_PUBLIC_DNS_RESOLVER_ENDPOINT="${CPK_PUBLIC_DNS_RESOLVER_ENDPOINT:-https://1.1.1.1/dns-query}" \
  -e CPK_PRODUCT_MATERIAL_RESOLVER=provider \
  -e CPK_MATERIAL_PROVIDER_ROUTES_JSON="$PROVIDER_ROUTES_JSON" \
  -e CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON="$PROVIDER_BOOTSTRAP_FILES_JSON" \
  -e CPK_GATEWAY_PROBE_SIGNER=ed25519 \
  -e CPK_WORKPLACE_DATABASE_URL=postgresql://cpk:cpk@cpk-postgres:5432/cpk \
  -e CPK_ACTIVITY_HISTORY_DATABASE_URL=postgresql://cpk:cpk@cpk-postgres:5432/cpk \
  -e CPK_OBSERVER_STATE_DATABASE_URL=postgresql://cpk:cpk@cpk-postgres:5432/cpk \
  -e CPK_GRAPH_TOPOLOGY_DATABASE_URL=postgresql://cpk:cpk@cpk-postgres:5432/cpk \
  "$SERVER_IMAGE")"

run_controller() {
  mode="$1"
  docker run --rm \
    --label "$LABEL" \
    --network "$NETWORK" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$BOOTSTRAP_DIR:/run/secrets/cpk-source-live:ro" \
    -v "$CONTROLLER_STATE_DIR:/run/cpk-source-live-state" \
    -e CPK_HOSTED_ACTIVITY_BASE_URL=http://cpk-server:8080 \
    -e CPK_HOSTED_ACTIVITY_SERVER_CONTAINER="$SERVER_CONTAINER" \
    -e CPK_HOSTED_ACTIVITY_SERVERS_REPO=/app \
    -e CPK_HOSTED_ACTIVITY_WORKSPACE_ID="$WORKSPACE_ID" \
    -e CPK_PUBLIC_GATEWAY_HOSTNAME="$PUBLIC_HOSTNAME" \
    -e CPK_PUBLIC_GATEWAY_ALLOWED_HOSTNAME_PATTERN="${PUBLIC_HOSTNAME_PATTERN:-}" \
    -e CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO="$SCENARIO" \
    -e CPK_SECRET_PROVIDER_SOURCE_LIVE_MODE="$mode" \
    -e CPK_SOURCE_LIVE_STATE_FILE=/run/cpk-source-live-state/checkpoint.json \
    -e CPK_SOURCE_LIVE_FAIL_AFTER_PHASE="${CPK_SOURCE_LIVE_FAIL_AFTER_PHASE:-}" \
    -e CPK_SECRET_PROVIDER_CONTAINER="$SECRETS_CONTAINER" \
    -e CPK_SECRET_PROVIDER_TOKEN_FILE=/run/secrets/cpk-source-live/client-token \
    -e CPK_SECRET_PROVIDER_BOOTSTRAP_DIR=/run/secrets/cpk-source-live \
    -e CPK_GATEWAY_PROBE_PRIVATE_KEY_FILE=/run/secrets/cpk-source-live/gateway-private-key.pem \
    -e CPK_SOURCE_LIVE_GATEWAY_IMAGE="$SOURCE_LIVE_GATEWAY_IMAGE" \
    -e CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT="$SOURCE_LIVE_GATEWAY_SOURCE_COMMIT" \
    -e OPENJ92_CLOUDFLARE_ACCOUNT_ID="$OPENJ92_CLOUDFLARE_ACCOUNT_ID" \
    -e OPENJ92_CLOUDFLARE_ZONE_ID="$OPENJ92_CLOUDFLARE_ZONE_ID" \
    -e OPENJ92_CLOUDFLARE_ZONE="$OPENJ92_CLOUDFLARE_ZONE" \
    -e CPK_OPERATIONS_DATABASE_URL=postgresql://cpk:cpk@cpk-postgres:5432/cpk \
    "$CONTROLLER_IMAGE" \
    python scripts/cpk_server_secret_provider_source_live.py
}

set +e
run_controller run
CONTROLLER_STATUS=$?
set -e
if [ "$CONTROLLER_STATUS" -ne 0 ]; then
  docker inspect --format \
    '{"component":"cpk-server","status":"{{.State.Status}}","running":{{.State.Running}},"exit_code":{{.State.ExitCode}},"oom_killed":{{.State.OOMKilled}}}' \
    "$SERVER_CONTAINER" >&2 || true
  docker inspect --format \
    '{"component":"secrets-provider","status":"{{.State.Status}}","running":{{.State.Running}},"exit_code":{{.State.ExitCode}},"oom_killed":{{.State.OOMKilled}}}' \
    "$SECRETS_CONTAINER" >&2 || true
  exit "$CONTROLLER_STATUS"
fi

docker exec "$POSTGRES_CONTAINER" pg_dump -U cpk -d cpk >"$OPERATIONS_DUMP"
for secret_file in \
  cloudflare-api-token \
  client-token \
  gateway-private-key.pem \
  gateway-rotation-key-a.pem \
  gateway-rotation-key-a-public.pem \
  ghcr-pull-credential.json \
  ghcr-token-sentinel \
  postgres-password
do
  if [ ! -f "$BOOTSTRAP_DIR/$secret_file" ]; then
    continue
  fi
  if docker logs "$SERVER_CONTAINER" 2>&1 \
    | grep -F -f "$BOOTSTRAP_DIR/$secret_file" >/dev/null 2>&1; then
    echo "cpk-server logs contain forbidden source-live material" >&2
    exit 1
  fi
  if docker logs "$SECRETS_CONTAINER" 2>&1 \
    | grep -F -f "$BOOTSTRAP_DIR/$secret_file" >/dev/null 2>&1; then
    echo "provider logs contain forbidden source-live material" >&2
    exit 1
  fi
  if grep -aF -f "$BOOTSTRAP_DIR/$secret_file" "$OPERATIONS_DUMP" >/dev/null 2>&1; then
    echo "operations database contains forbidden source-live material" >&2
    exit 1
  fi
  if grep -aF -f "$BOOTSTRAP_DIR/$secret_file" \
    "$PROVIDER_DATA_DIR/secrets.sqlite3" >/dev/null 2>&1; then
    echo "provider database contains plaintext source-live secret" >&2
    exit 1
  fi
done

cleanup
SERVER_CONTAINER=""
SECRETS_CONTAINER=""
POSTGRES_CONTAINER=""

sh "$SERVERS_REPO/scripts/docker_residue_audit.sh"
echo "cpk-server Cloudflare generated-secret custody source-live smoke passed"
