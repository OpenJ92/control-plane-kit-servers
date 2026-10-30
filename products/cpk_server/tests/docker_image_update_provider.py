"""Real pinned Secrets HTTP process for the owned #251 signing fixture."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.parse import quote

import httpx

from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference, SecretReference, SecretUseIntent, SecretValue,
)
from control_plane_kit_interpreters.secret_provider import ControlPlaneKitSecretsClient, canonical_provider_secret_id
from control_plane_kit_servers_cpk_server.server import (
    CpkServerBootstrapConfiguration, _secret_provider_composition,
)
from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
from products.secrets_server.tests.secrets_control_fixtures import SourceControlAuthority

from docker_image_update_ports import FixtureBoundaryFailure
from receiver_acceptance_ports import IngressAllocation
from docker_image_update_material import APPLICATION_REFERENCE, APPLICATION_INTENT


SIGNING = {
    "transit": ("health-secrets", "secret://health-secrets/keys/transit",
        "gateway.node-health-read-transit-signing-key"),
    "workload": ("health-secrets", "secret://health-secrets/keys/workload",
        "workload.node-health-read-signing-key"),
    "surface": ("unlisted-surface", "secret://unlisted-surface/keys/surface",
        "gateway.probe-signing-key"),
}

PROVIDER_ENDPOINTS = ("health-secrets", "unlisted-surface", "generated-secrets", "application-secrets")


class SyntheticIngressAllocation:
    """Synthetic external ingress with real, isolated generated-token custody."""
    def __init__(self, custodian, workspace_id):
        self.custodian, self.workspace_id = custodian, workspace_id
        self.allocations, self.calls = {}, []

    def _require_grant(self, grant):
        if (grant.workspace_id != self.workspace_id
                or grant.endpoint_reference != SecretProviderEndpointReference("generated-secrets")
                or grant.credential_reference != SecretReference("secret://bootstrap/generated-secrets/client-token")
                or grant.intent != SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN
                or not grant.reference.reference_id.startswith("secret://generated/ingress/")):
            raise FixtureBoundaryFailure("synthetic ingress custody differs from fixture")

    def create(self, ingress, *, authority, allocation_name, origin_service_url,
               secret_resolution_grant, secret_custody_grant):
        self._require_grant(secret_custody_grant)
        if allocation_name in self.allocations:
            raise FixtureBoundaryFailure("synthetic ingress allocation already exists")
        receipt = self.custodian.store(secret_custody_grant, SecretValue(secrets.token_urlsafe(48)))
        if not receipt.matches(secret_custody_grant):
            raise FixtureBoundaryFailure("generated custody receipt differs")
        identity = hashlib.sha256(allocation_name.encode()).hexdigest()[:24]
        allocation = IngressAllocation(receipt, "tunnel-" + identity, allocation_name,
            "dns-" + identity, ingress.hostname, "https://" + ingress.hostname)
        self.allocations[allocation_name] = allocation
        self.calls.append(("create", allocation_name))
        return allocation

    def teardown(self, *, authority, resources, secret_resolution_grant, secret_custody_grant):
        self._require_grant(secret_custody_grant)
        matches = [key for key, value in self.allocations.items()
            if value.tunnel_id == resources.tunnel_id and value.dns_record_id == resources.dns_record_id
            and value.secret_custody_receipt.reference == secret_custody_grant.reference
            and value.secret_custody_receipt.provider_registration_id == secret_custody_grant.provider_registration_id]
        if len(matches) != 1:
            raise FixtureBoundaryFailure("synthetic ingress teardown custody differs")
        key, = matches
        self.custodian.revoke(secret_custody_grant)
        self.allocations.pop(key)
        self.calls.append(("remove", key))


class SigningProviderProcess:
    """Private process/files only; public API owns all key writes and resolutions."""
    def __init__(self, root, workspace_id, database_url):
        self.root, self.workspace_id, self.database_url = Path(root), workspace_id, database_url
        self.process = self.listener = None
        self.composition = None
        self.token = secrets.token_urlsafe(48)

    def _private(self, name, content):
        path = self.root / name
        with path.open("x", encoding="utf-8") as output:
            output.write(content)
        path.chmod(0o400)
        return path

    def __enter__(self):
        self.root.mkdir(mode=0o700)
        try:
            root_key = self._private("master.key", base64.urlsafe_b64encode(os.urandom(32)).decode())
            token = self._private("provider.token", self.token)
            credentials = self._private("credentials.json", json.dumps([{
                "subject": "docker-image-signing", "token": self.token,
                "grants": [
                    {"action": "secret.write", "workspace_id": self.workspace_id,
                     "intents": [*[row[2] for row in SIGNING.values()], "cloudflare.tunnel-token",
                         APPLICATION_INTENT.value]},
                    {"action": "secret.rotate", "workspace_id": self.workspace_id,
                     "intents": [APPLICATION_INTENT.value]},
                    {"action": "secret.revoke", "workspace_id": self.workspace_id, "intents": []},
                    {"action": "secret.metadata", "workspace_id": self.workspace_id, "intents": []},
                    {"action": "secret.resolve", "workspace_id": self.workspace_id,
                     "intents": [*[row[2] for row in SIGNING.values()], "cloudflare.tunnel-token",
                         APPLICATION_INTENT.value]},
                ],
            }]))
            control = secrets_control_configuration_artifact(SourceControlAuthority(self.workspace_id).configuration())
            wrapper = self._private("control.json", control.content)
            wrapper.chmod(0o444)  # Public receiver contract; secret bootstrap files stay 0400.
            self.listener = socket.socket()
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(32)
            self.endpoint = "http://127.0.0.1:" + str(self.listener.getsockname()[1])
            environment = {**os.environ,
                "CPK_SECRETS_DATABASE_PATH": str(self.root / "provider.sqlite3"),
                "CPK_SECRETS_PROVIDER_ID": "docker-image-signing",
                "CPK_SECRETS_MASTER_KEY_FILE": str(root_key),
                "CPK_SECRETS_CREDENTIALS_FILE": str(credentials),
                "CPK_WRAPPER_CONFIGURATION_FILE": str(wrapper)}
            environment.pop("CPK_SECRETS_DEVELOPMENT_CREDENTIALS_JSON", None)
            self.process = subprocess.Popen([sys.executable, "-m", "uvicorn",
                "control_plane_kit_secrets.server:app", "--fd", str(self.listener.fileno()),
                "--no-access-log", "--log-level", "error"], env=environment,
                pass_fds=(self.listener.fileno(),), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if self.process.poll() is not None:
                    raise FixtureBoundaryFailure("signing provider exited before readiness")
                try:
                    response = httpx.get(self.endpoint + "/health/ready", timeout=0.5, trust_env=False)
                    status = response.status_code
                    if status == 200:
                        break
                except httpx.TransportError:
                    status = "transport-unavailable"
                time.sleep(0.1)
            else:
                raise FixtureBoundaryFailure("signing provider readiness unavailable")
            settings = {
                "CPK_SERVER_MODE": "execution-capable", "CPK_CONTROL_AUTH_CONFIGURED": "true",
                "CPK_PORT": "8080", "CPK_RUNTIME_INTERPRETERS": "docker",
                "CPK_PRODUCT_MATERIAL_RESOLVER": "provider",
                "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({
                    name: self.endpoint for name in PROVIDER_ENDPOINTS}),
                "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": json.dumps({
                    "secret://bootstrap/" + name + "/client-token": str(token)
                    for name in PROVIDER_ENDPOINTS}),
                **{name: self.database_url for name in ("CPK_WORKPLACE_DATABASE_URL",
                    "CPK_ACTIVITY_HISTORY_DATABASE_URL", "CPK_OBSERVER_STATE_DATABASE_URL",
                    "CPK_GRAPH_TOPOLOGY_DATABASE_URL")},
            }
            self.composition = _secret_provider_composition(
                CpkServerBootstrapConfiguration.from_environment(settings))
            return self
        except Exception:
            self._stop()
            raise

    def seed(self, material):
        # Separate fixture custody only; no new intent, activation or signing path.
        seeds = {**SIGNING, "workload-overlap": ("health-secrets",
            "secret://health-secrets/keys/workload-overlap", "workload.node-health-read-signing-key")}
        for family, (provider, reference, intent) in seeds.items():
            if family not in material.private:
                continue
            client = ControlPlaneKitSecretsClient(self.composition.bootstrap_registry.configuration_for(
                endpoint_reference=SecretProviderEndpointReference(provider),
                credential_reference=SecretReference("secret://bootstrap/" + provider + "/client-token")))
            arguments = dict(workspace_id=self.workspace_id, reference=SecretReference(reference),
                intent=SecretUseIntent(intent), caller_subject="docker-image-signing")
            written = client.write(**arguments, value=SecretValue(material.private[family].decode("ascii")),
                correlation_id="image-write-" + family)
            assert written.reference == arguments["reference"]
            resolved = client.resolve(**arguments, correlation_id="image-resolve-" + family)
            assert resolved.value.reveal() == material.private[family].decode("ascii")

    def _stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.listener is not None:
            self.listener.close()

    def seed_application_versions(self):
        """One create, two public rotations and one revoke; fixture setup only."""
        client = ControlPlaneKitSecretsClient(self.composition.bootstrap_registry.configuration_for(
            endpoint_reference=SecretProviderEndpointReference("application-secrets"),
            credential_reference=SecretReference("secret://bootstrap/application-secrets/client-token")))
        first = client.write(workspace_id=self.workspace_id, reference=APPLICATION_REFERENCE,
            value=SecretValue(secrets.token_urlsafe(48)), intent=APPLICATION_INTENT,
            caller_subject="docker-image-signing", correlation_id="application-write-0")
        assert first.reference == APPLICATION_REFERENCE and first.status == "active" and first.version_number == 1
        assert first.labels.get("intent") == APPLICATION_INTENT.value
        versions = [first]
        for number in (2, 3):
            observed = self._rotate_application_version(client, number)
            assert observed.version_id not in {value.version_id for value in versions}
            versions.append(observed)
        revoked = versions[2]
        observed = client.revoke_version(workspace_id=self.workspace_id, reference=APPLICATION_REFERENCE,
            version_id=revoked.version_id, version_number=revoked.version_number,
            caller_subject="docker-image-signing", correlation_id="application-revoke")
        assert observed.status == "revoked" and observed.version_id == revoked.version_id
        return tuple(versions)

    def _rotate_application_version(self, client, number):
        # The selected client has no rotate method. Use the provider's public
        # setup endpoint once, then its existing exact-version metadata reader.
        secret_id = canonical_provider_secret_id(APPLICATION_REFERENCE)
        path = f"/v1/workspaces/{quote(self.workspace_id, safe='')}/secrets/{quote(secret_id, safe='')}/rotate"
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as transport:
                with transport.stream("POST", self.endpoint + path,
                        headers={"Authorization": "Bearer " + self.token}, json={
                            "value_base64": base64.b64encode(secrets.token_urlsafe(48).encode()).decode(),
                            "intent": APPLICATION_INTENT.value, "labels": {},
                            "caller_subject": "docker-image-signing", "correlation_id": f"application-rotate-{number}"}) as response:
                    if response.status_code != 200:
                        raise ValueError("rotation refused")
                    payload = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        payload.extend(chunk)
                        if len(payload) > 65536:
                            raise ValueError("rotation response exceeds bound")
            document = json.loads(payload)
            assert set(document) == {"outcome", "metadata"} and document["outcome"] == "rotated"
            metadata = document["metadata"]
            assert metadata["workspace_id"] == self.workspace_id and metadata["secret_id"] == secret_id
            assert metadata["status"] == "active" and metadata["labels"] == {"intent": APPLICATION_INTENT.value}
            assert type(metadata["version_number"]) is int and metadata["version_number"] == number
            observed = client.read_metadata(workspace_id=self.workspace_id, reference=APPLICATION_REFERENCE,
                version_id=metadata["version_id"])
            assert observed.version_number == number and observed.status == "active"
            assert observed.labels.get("intent") == APPLICATION_INTENT.value
            return observed
        except Exception:
            # A response failure may follow a committed rotation. Never retry.
            raise FixtureBoundaryFailure("application version setup unconfirmed; no retry") from None

    def __exit__(self, *_):
        self._stop()
