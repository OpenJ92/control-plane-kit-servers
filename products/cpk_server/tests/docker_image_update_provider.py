"""Real pinned Secrets HTTP process for the owned #251 signing fixture."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx

from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference, SecretReference, SecretUseIntent, SecretValue,
)
from control_plane_kit_interpreters.secret_provider import ControlPlaneKitSecretsClient
from control_plane_kit_servers_cpk_server.server import (
    CpkServerBootstrapConfiguration, _secret_provider_composition,
)
from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
from products.secrets_server.tests.secrets_control_fixtures import SourceControlAuthority

from docker_image_update_ports import FixtureBoundaryFailure


SIGNING = {
    "transit": ("health-secrets", "secret://health-secrets/keys/transit",
        "gateway.node-health-read-transit-signing-key"),
    "workload": ("health-secrets", "secret://health-secrets/keys/workload",
        "workload.node-health-read-signing-key"),
    "surface": ("unlisted-surface", "secret://unlisted-surface/keys/surface",
        "gateway.probe-signing-key"),
}


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
                    {"action": "secret.write", "workspace_id": self.workspace_id},
                    {"action": "secret.resolve", "workspace_id": self.workspace_id,
                     "intents": [row[2] for row in SIGNING.values()]},
                ],
            }]))
            control = secrets_control_configuration_artifact(SourceControlAuthority(self.workspace_id).configuration())
            wrapper = self._private("control.json", control.content)
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
                    name: self.endpoint for name in ("health-secrets", "unlisted-surface")}),
                "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": json.dumps({
                    "secret://bootstrap/" + name + "/client-token": str(token)
                    for name in ("health-secrets", "unlisted-surface")}),
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
        for family, (provider, reference, intent) in SIGNING.items():
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

    def __exit__(self, *_):
        self._stop()
