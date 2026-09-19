#!/bin/sh
set -eu

IMAGE="${CPK_SECRETS_IMAGE:-control-plane-kit-secrets-server:local}"
BUILD_IMAGE="${CPK_SECRETS_BUILD_IMAGE:-1}"
CONTROLLER_IMAGE="${CPK_SERVERS_TEST_IMAGE:-control-plane-kit-servers-test:local}"
BUILD_CONTROLLER="${CPK_SECRETS_BUILD_CONTROLLER:-1}"
PROFILE="${CPK_SECRETS_SMOKE_PROFILE:-}"
invalid_inputs() {
  echo 'secrets-server image smoke: invalid profile or build inputs' >&2
  exit 2
}
case "$BUILD_IMAGE:$BUILD_CONTROLLER" in 0:0|0:1|1:0|1:1) ;; *) invalid_inputs ;; esac
if [ -z "$PROFILE" ]; then
  case "$BUILD_IMAGE" in 1) PROFILE=wrapped-source ;; 0) PROFILE=published-baseline ;; esac
fi
case "$PROFILE:$BUILD_IMAGE" in
  wrapped-source:1) ;;
  published-baseline:0)
    printf '%s\n' "$IMAGE" | grep -Eq '@sha256:[0-9a-f]{64}$' || invalid_inputs
    ;;
  *) invalid_inputs ;;
esac

CONTROL_RECORDS=""
CONTROL_PHASE=""
RUN_ID="cpk-secrets-image-smoke-$$"
LABEL_KEY="cpk.test-run"
NETWORK="$RUN_ID-network"
PROVIDER_BOOTSTRAP="$RUN_ID-provider-bootstrap"
CLIENT_BOOTSTRAP="$RUN_ID-client-bootstrap"
DATA_VOLUME="$RUN_ID-data"
PROVIDER="$RUN_ID-provider"

cleanup_records() {
  [ -n "$CONTROL_RECORDS" ] || return 0
  rm -f "$CONTROL_RECORDS/provider.log" "$CONTROL_RECORDS/log.status" || return 1
  for phase in initial restart; do
    rm -f "$CONTROL_RECORDS/$phase/control.json" \
      "$CONTROL_RECORDS/$phase/surface.headers" "$CONTROL_RECORDS/$phase/health.headers" || return 1
    if [ -d "$CONTROL_RECORDS/$phase" ]; then
      rmdir "$CONTROL_RECORDS/$phase" || return 1
    fi
  done
  rmdir "$CONTROL_RECORDS" || return 1
  [ ! -e "$CONTROL_RECORDS" ] || return 1
  CONTROL_RECORDS=""
}

cleanup_owned() {
  docker ps -aq --filter "label=$LABEL_KEY=$RUN_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker rm -f "$resource" >/dev/null 2>&1 || true
        fi
      done
  docker volume ls -q --filter "label=$LABEL_KEY=$RUN_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker volume rm -f "$resource" >/dev/null 2>&1 || true
        fi
      done
  docker network ls -q --filter "label=$LABEL_KEY=$RUN_ID" \
    | while IFS= read -r resource; do
        if [ -n "$resource" ]; then
          docker network rm "$resource" >/dev/null 2>&1 || true
        fi
      done
}

finish() {
  status=$?
  trap - EXIT INT TERM
  cleanup_owned
  if docker ps -aq --filter "label=$LABEL_KEY=$RUN_ID" | grep . \
    || docker volume ls -q --filter "label=$LABEL_KEY=$RUN_ID" | grep . \
    || docker network ls -q --filter "label=$LABEL_KEY=$RUN_ID" | grep .; then
    echo "secrets-server image smoke left owned Docker resources" >&2
    status=1
  fi
  cleanup_records || { echo 'secrets-server fixture cleanup incomplete' >&2; status=1; }
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

if [ "$BUILD_IMAGE" = "1" ]; then
  docker build -f products/secrets_server/Dockerfile -t "$IMAGE" .
fi
if [ "$BUILD_CONTROLLER" = "1" ]; then
  docker build -f Dockerfile.test -t "$CONTROLLER_IMAGE" .
fi

CONTROL_RECORDS="$(mktemp -d)"
chmod 700 "$CONTROL_RECORDS"

docker network create --label "$LABEL_KEY=$RUN_ID" "$NETWORK" >/dev/null
docker volume create --label "$LABEL_KEY=$RUN_ID" "$PROVIDER_BOOTSTRAP" >/dev/null
docker volume create --label "$LABEL_KEY=$RUN_ID" "$CLIENT_BOOTSTRAP" >/dev/null
docker volume create --label "$LABEL_KEY=$RUN_ID" "$DATA_VOLUME" >/dev/null

docker run --rm -i \
  --label "$LABEL_KEY=$RUN_ID" \
  --user 0:0 \
  --mount "type=volume,src=$PROVIDER_BOOTSTRAP,dst=/provider-bootstrap" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client-bootstrap" \
  --mount "type=volume,src=$DATA_VOLUME,dst=/provider-data" \
  --entrypoint python \
  "$IMAGE" \
  - <<'PY'
import json
import os
from pathlib import Path
import secrets

from control_plane_kit_secrets.crypto import encode_master_key_for_file

os.umask(0o077)
provider = Path("/provider-bootstrap")
client = Path("/client-bootstrap")
token = secrets.token_urlsafe(48)
provider.joinpath("master.key").write_text(
    encode_master_key_for_file(os.urandom(32)),
    encoding="utf-8",
)
provider.joinpath("credentials.json").write_text(
    json.dumps(
        [
            {
                "subject": "image-smoke-client",
                "token": token,
                "grants": [
                    {
                        "action": "secret.write",
                        "workspace_id": "workspace-image-smoke",
                    },
                    {
                        "action": "secret.generate-delegation-key",
                        "workspace_id": "workspace-image-smoke",
                        "intents": ["gateway.probe-signing-key"],
                    },
                    {
                        "action": "secret.resolve",
                        "workspace_id": "workspace-image-smoke",
                        "intents": [
                            "gateway.probe-signing-key",
                            "postgres.password",
                        ],
                    },
                    {
                        "action": "secret.revoke",
                        "workspace_id": "workspace-image-smoke",
                    },
                ],
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    ),
    encoding="utf-8",
)
client.joinpath("provider-token").write_text(token, encoding="ascii")
client.joinpath("application-value").write_text(
    secrets.token_urlsafe(40),
    encoding="ascii",
)
for path in provider.iterdir():
    path.chmod(0o400)
    os.chown(path, 10006, 10006)
for path in client.iterdir():
    path.chmod(0o400)
os.chown("/provider-bootstrap", 10006, 10006)
os.chown("/provider-data", 10006, 10006)
PY

start_provider() {
  set -- \
    --name "$PROVIDER" \
    --label "$LABEL_KEY=$RUN_ID" \
    --network "$NETWORK" \
    --network-alias secrets-provider \
    --mount "type=volume,src=$PROVIDER_BOOTSTRAP,dst=/run/secrets/cpk-secrets,readonly" \
    --mount "type=volume,src=$DATA_VOLUME,dst=/var/lib/cpk-secrets"
  if [ "$PROFILE" = wrapped-source ]; then
    set -- "$@" --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE/control.json,target=/etc/cpk/secrets-server/control.json,readonly"
  fi
  docker create "$@" "$IMAGE" >/dev/null
  docker start "$PROVIDER" >/dev/null
}

prepare_control() {
  [ "$PROFILE" = wrapped-source ] || return 0
  CONTROL_PHASE="$1"
  mkdir -m 700 "$CONTROL_RECORDS/$CONTROL_PHASE"
  docker run --rm --label "$LABEL_KEY=$RUN_ID" --network none \
    --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE,target=/fixture" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py \
    generate /fixture "$RUN_ID"
}

check_control() {
  [ "$PROFILE" = wrapped-source ] || return 0
  docker run --rm --label "$LABEL_KEY=$RUN_ID" --user 0:0 --network "$NETWORK" \
    --mount "type=bind,source=$CONTROL_RECORDS/$CONTROL_PHASE,target=/fixture,readonly" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py check /fixture
  echo "secrets-server $CONTROL_PHASE signed source control passed"
}

wait_ready() {
  docker run --rm -i \
    --label "$LABEL_KEY=$RUN_ID" \
    --network "$NETWORK" \
    "$CONTROLLER_IMAGE" \
    python - <<'PY'
import time

import httpx

for attempt in range(30):
    try:
        response = httpx.get("http://secrets-provider:8081/health/ready", timeout=1.0)
        if response.status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
else:
    raise SystemExit("secrets-server did not become ready")
PY
}

assert_logs_redacted() {
  (umask 077; : > "$CONTROL_RECORDS/provider.log"; : > "$CONTROL_RECORDS/log.status")
  # The limiter's success cannot hide failed retrieval. The producer records its
  # own exit status, which the checker requires independently of the byte bound.
  if (
    set +e
    docker logs "$PROVIDER" 2>&1
    log_status=$?
    printf '%s\n' "$log_status" > "$CONTROL_RECORDS/log.status"
  ) | head -c 1048577 > "$CONTROL_RECORDS/provider.log"; then
    :
  else
    echo 'Secrets smoke fixture failed' >&2
    return 1
  fi
  set -- logs /fixture /client
  if [ "$PROFILE" = wrapped-source ]; then
    set -- "$@" "/fixture/$CONTROL_PHASE"
  fi
  docker run --rm --label "$LABEL_KEY=$RUN_ID" --user 0:0 --network none \
    --mount "type=bind,source=$CONTROL_RECORDS,target=/fixture,readonly" \
    --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/client,readonly" \
    "$CONTROLLER_IMAGE" python products/secrets_server/tests/source_control_fixture.py "$@"
}

prepare_control initial
start_provider
wait_ready
check_control

docker run --rm -i \
  --label "$LABEL_KEY=$RUN_ID" \
  --network "$NETWORK" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/run/secrets/image-smoke,readonly" \
  "$CONTROLLER_IMAGE" \
  python - <<'PY'
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
    SecretValue,
)
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsClient,
    SecretProviderBootstrapRegistry,
    SecretProviderClientCode,
    SecretProviderClientError,
)

workspace_id = "workspace-image-smoke"
endpoint = SecretProviderEndpointReference("control-plane-kit")
credential = SecretReference("secret://bootstrap/provider-token")
registry = SecretProviderBootstrapRegistry(
    endpoints={endpoint: "http://secrets-provider:8081"},
    credential_files={
        credential: Path("/run/secrets/image-smoke/provider-token")
    },
)
client = ControlPlaneKitSecretsClient(
    registry.configuration_for(
        endpoint_reference=endpoint,
        credential_reference=credential,
    )
)

application_reference = SecretReference(
    "secret://control-plane-kit/application/postgres-password"
)
application_value = SecretValue(
    Path("/run/secrets/image-smoke/application-value").read_text("ascii")
)
written = client.write(
    workspace_id=workspace_id,
    reference=application_reference,
    value=application_value,
    intent=SecretUseIntent.POSTGRES_PASSWORD,
    caller_subject="image-smoke-client",
    correlation_id="image-smoke-write",
)
assert written.reference == application_reference

delegation_reference = SecretReference(
    "secret://control-plane-kit/gateway/key-b"
)
arguments = {
    "workspace_id": workspace_id,
    "reference": delegation_reference,
    "purpose": DelegationKeyPurpose.GATEWAY_PROBE,
    "issuer": "cpk-server",
    "caller_subject": "cpk-server",
    "correlation_id": "image-smoke-key-b",
}
generated = client.generate_delegation_key(**arguments)
replayed = client.generate_delegation_key(**arguments)
assert not generated.replayed
assert replayed.replayed
assert replayed.metadata == generated.metadata
assert replayed.public_key == generated.public_key

resolved = client.resolve(
    workspace_id=workspace_id,
    reference=delegation_reference,
    intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,
    caller_subject="gateway-probe-signer",
    correlation_id="image-smoke-resolve-b",
    version_id=generated.metadata.version_id,
)
private_key = serialization.load_pem_private_key(
    resolved.value.reveal().encode("ascii"),
    password=None,
)
derived_public = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
assert derived_public == generated.public_key.public_key_pem

revoked = client.revoke_version(
    workspace_id=workspace_id,
    reference=delegation_reference,
    version_id=generated.metadata.version_id,
    version_number=generated.metadata.version_number,
    caller_subject="cpk-server",
    correlation_id="image-smoke-revoke-b",
)
assert revoked.status == "revoked"
try:
    client.resolve(
        workspace_id=workspace_id,
        reference=delegation_reference,
        intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,
        caller_subject="gateway-probe-signer",
        correlation_id="image-smoke-resolve-revoked-b",
        version_id=generated.metadata.version_id,
    )
except SecretProviderClientError as error:
    assert error.code is SecretProviderClientCode.REVOKED
else:
    raise AssertionError("revoked delegation key remained resolvable")

assert "PRIVATE KEY" not in repr(generated)
assert "PRIVATE KEY" not in repr(replayed)
print("secrets-server initial contract passed")
PY

assert_logs_redacted
docker rm -f "$PROVIDER" >/dev/null

prepare_control restart
start_provider
wait_ready
check_control

docker run --rm -i \
  --label "$LABEL_KEY=$RUN_ID" \
  --network "$NETWORK" \
  --mount "type=volume,src=$CLIENT_BOOTSTRAP,dst=/run/secrets/image-smoke,readonly" \
  "$CONTROLLER_IMAGE" \
  python - <<'PY'
from pathlib import Path

from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
)
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsClient,
    SecretProviderBootstrapRegistry,
)

endpoint = SecretProviderEndpointReference("control-plane-kit")
credential = SecretReference("secret://bootstrap/provider-token")
reference = SecretReference(
    "secret://control-plane-kit/application/postgres-password"
)
registry = SecretProviderBootstrapRegistry(
    endpoints={endpoint: "http://secrets-provider:8081"},
    credential_files={
        credential: Path("/run/secrets/image-smoke/provider-token")
    },
)
client = ControlPlaneKitSecretsClient(
    registry.configuration_for(
        endpoint_reference=endpoint,
        credential_reference=credential,
    )
)
resolved = client.resolve(
    workspace_id="workspace-image-smoke",
    reference=reference,
    intent=SecretUseIntent.POSTGRES_PASSWORD,
    caller_subject="image-smoke-client",
    correlation_id="image-smoke-resolve-after-restart",
)
expected = Path("/run/secrets/image-smoke/application-value").read_text("ascii")
assert resolved.value.reveal() == expected
print("secrets-server restart contract passed")
PY

assert_logs_redacted
echo "secrets-server image smoke passed ($PROFILE)"
