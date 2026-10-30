"""Real encrypted Secrets owners behind one test-only synchronous HTTP bridge."""
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi.testclient import TestClient
import control_plane_kit_core as core
from control_plane_kit_core.secrets import health_signing_intent_for
from control_plane_kit_secrets.api import create_app
from control_plane_kit_secrets.bootstrap import load_provider_credentials
from control_plane_kit_secrets.control import secrets_control_declaration
from control_plane_kit_secrets.crypto import encode_master_key_for_file, load_master_key_file
from control_plane_kit_secrets.custody import admit_provider_custody
from control_plane_kit_secrets.provider_policy import ProviderPolicyStore

from cpk_http_host_fixtures import fixture


PROVIDER = "input-provider"
WORKSPACE = "workspace-input"
TOKEN = "synthetic-input-provider-bootstrap"
MATERIAL = "synthetic-external-token-not-for-history"
PURPOSES = (
    core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
    core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
    core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
)
INTENTS = ("gateway.probe-signing-key", *(health_signing_intent_for(purpose).value for purpose in PURPOSES[1:]))


def protected_file(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(text)


class ProviderTransport(httpx.BaseTransport):
    """Forward to actual provider routes; record only public method/path pairs."""
    def __init__(self, client):
        self.client = client
        self.calls = []

    def handle_request(self, request):
        if (request.url.scheme != "https" or request.url.host != "input-provider.invalid"
                or request.url.port not in (None, 443)):
            raise AssertionError("unexpected provider destination")
        if len(self.calls) >= 200:
            raise AssertionError("provider request budget exceeded")
        self.calls.append((request.method, request.url.path))
        response = self.client.request(request.method, str(request.url), headers=request.headers,
                                       content=request.read(), follow_redirects=False)
        try:
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=response.content, request=request)
        finally:
            response.close()

    def close(self):
        # Per-call httpx.Client owns this bridge, never the shared provider lifetime.
        pass


class ProtectedProvider:
    def __enter__(self):
        self.stack = ExitStack()
        try:
            self.root = Path(self.stack.enter_context(TemporaryDirectory(prefix="cpk-input-provider-")))
            master = self.root / "master.key"
            credentials = self.root / "credentials.json"
            self.token_file = self.root / "provider.token"
            protected_file(master, encode_master_key_for_file(os.urandom(32)))
            protected_file(self.token_file, TOKEN)
            protected_file(credentials, json.dumps([{
                "subject": "input-test-client", "token": TOKEN,
                "grants": [
                    {"action": "secret.generate-delegation-key", "workspace_id": WORKSPACE, "intents": list(INTENTS)},
                    {"action": "secret.write", "workspace_id": WORKSPACE, "intents": ["cloudflare.api-token"]},
                    {"action": "secret.metadata", "workspace_id": WORKSPACE},
                ],
            }]))
            def initialize():
                parsed_credentials = load_provider_credentials({
                    "CPK_SECRETS_CREDENTIALS_FILE": str(credentials),
                })
                database_path = self.root / "custody.sqlite3"
                store, self.audit = admit_provider_custody(database_path,
                    master_key=load_master_key_file(master), provider_id=PROVIDER,
                    credentials=parsed_credentials)
                return store, self.audit, parsed_credentials, ProviderPolicyStore(
                    database_path, provider_id=PROVIDER,
                )
            # Root/provider wrapper trust is test bootstrap only, never a managed signing identity.
            bootstrap = fixture("provider-bootstrap").config
            control = replace(bootstrap, target=replace(bootstrap.target,
                provider_socket_name=core.NodeControlGraphReference(
                    core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control")),
                declaration=secrets_control_declaration())
            app = create_app(control=control, initialize_provider=initialize, provider_id=PROVIDER)
            client = self.stack.enter_context(TestClient(app, base_url="https://input-provider.invalid"))
            self.transport = ProviderTransport(client)
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *failure):
        self.stack.close()
        if self.root.exists():
            raise AssertionError("test-owned provider directory remains")
