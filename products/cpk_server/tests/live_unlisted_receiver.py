"""Joined #237 authoring/HTTP/default-SDK/process witness in the owning smoke.

External addresses are explicitly mapped to owned loopback receiver processes.
This is not real Docker interpretation, public gateway delivery or image proof.
"""
import asyncio
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, BlockSpec, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.configuration_installation import (
    ConfigurationInstallationDisposition, ConfigurationInstallationReceipt,
)
from control_plane_kit_core.configuration_invocation import (
    configuration_invocation_correlation_for_request, configuration_invocation_selection_fingerprint,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity,
    ProductReference, ProductRuntimeContract, ProviderRuntimePort,
)
from control_plane_kit_core.planning import StartNode, ReconcileNode, RemoveNodeResource
from control_plane_kit_core.runtime_effects import RuntimeEffectRequest, RuntimeEffectResult, RuntimeEffectFailure
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, Node
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import (
    AuthoredDesiredGraph, PendingReceiverContinuation, ReceiverIntroduction, ReceiverScope,
    GatewayHealthRoutes, GatewayHealthTargetIntent,
)
from control_plane_kit_servers_cpk_server.client.transport import (
    PublicHttpTransport, ClientTransportError,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay import GatewayHealthRelay
from control_plane_kit_servers_cpk_local_gateway.health_transit_verification import gateway_health_transit_verifier_from_artifact
from control_plane_kit_servers_cpk_local_gateway.server import create_app
from control_plane_kit_server_sdk.fastapi import install_cpk_wrapper
from fastapi import FastAPI

from live_receiver_acceptance import verify_provenance
from receiver_acceptance_material import AuthoredMaterial
from receiver_acceptance_operations import (
    IsolatedOperationsSchema, OperationsApplicationFactory, OperationsEffectPorts,
    PublicOperationsDriver, register_material, utc_now,
)
from receiver_acceptance_ports import (
    ComputeSubstitute, IngressSubstitute, SignedHealthComposition, InstalledTransport,
    synthetic_runtime_registration,
)
from unlisted_controller_host import ControllerHost


EXAMPLES = (
    ("counter-example", "counter.py", "/count", "counter-configuration", 8000),
    ("palette-example", "palette.py", "/palette", "palette-settings", 8081),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unsupported_profile_credential(credential, target, material):
    """One intentional wire fault, signed with the existing test-only key.

    Public grant constructors correctly refuse unsupported profiles. Preserve the
    already admitted claims/header and use the same PyJWT EdDSA primitive as the
    installed signer; mutate only the profile after decoding a valid signature.
    """
    encoded = credential.removeprefix("Bearer ")
    def verify(token):
        return jwt.decode(token, material.public["workload"].public_key_pem,
            algorithms=["EdDSA"], audience=core.receiver_node_control_audience(target),
            issuer="cpk-server")
    claims = verify(encoded)
    assert claims["workload_node_health_read"]["profile"] == "workload-node-health-read-grant.v2"
    header = jwt.get_unverified_header(encoded)
    original = json.loads(json.dumps(claims))
    positive = jwt.encode(claims, material.private["workload"], algorithm="EdDSA", headers=header)
    claims["workload_node_health_read"]["profile"] = "workload-node-health-read-grant.v999"
    negative = jwt.encode(claims, material.private["workload"], algorithm="EdDSA", headers=header)
    assert verify(positive) == original and verify(negative) == claims
    assert jwt.get_unverified_header(positive) == jwt.get_unverified_header(negative) == header
    restored = verify(negative)
    restored["workload_node_health_read"]["profile"] = "workload-node-health-read-grant.v2"
    assert restored == original, "negative changed a second claim"
    return "Bearer " + positive, "Bearer " + negative


def controller_identity():
    """Installed distribution files, independent from separately staged examples."""
    distribution = importlib.metadata.distribution("control-plane-kit-servers")
    selected = sorted(str(path) for path in distribution.files
        if str(path).endswith(".py") and "control_plane_kit_servers" in str(path))
    assert selected
    value = hashlib.sha256()
    for name in selected:
        value.update(name.encode())
        value.update(distribution.locate_file(name).read_bytes())
    return value.hexdigest()


class ReceiverProcesses:
    """Own handles, immutable public files and private temporary directories."""
    def __init__(self, root, examples):
        self.root, self.examples = root, examples
        self.children, self.origins, self.paths, self.hashes = {}, {}, {}, {}
        self.starts, self.stops, self.tokens = [], [], {}
        self.application_paths, self.identities = {}, {}
        self.owned_files, self.replacement_started = set(), set()
        self.scope, self.generation = uuid4().hex, 0
        self.port_calls = []

    def launch(self, name):
        assert name not in self.children and len(self.children) < 2
        script = next(item[1] for item in EXAMPLES if item[0] == name)
        environment = {**os.environ, "CPK_WRAPPER_CONFIGURATION_FILE": str(self.paths[name]),
            "PYTHONDONTWRITEBYTECODE": "1"}
        if name in self.application_paths:
            environment["PALETTE_CONFIGURATION_FILE"] = str(self.application_paths[name])
        process = subprocess.Popen([sys.executable, str(self.examples / script)],
            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        self.children[name] = process  # Own the handle before any wait/read can fail.
        self.starts.append((name, process.pid))
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready, "receiver did not announce its owned loopback port"
        line = process.stdout.readline(16)
        assert line.endswith(b"\n") and line.strip().isdigit(), "receiver failed during setup"
        port = int(line)
        assert 0 < port < 65536 and process.poll() is None
        self.origins[name] = f"http://127.0.0.1:{port}"
        business_path = next(item[2] for item in EXAMPLES if item[0] == name)
        with httpx.Client(timeout=2, trust_env=False) as client:
            # A first completed application response proves the serving loop ran.
            response = client.get(self.origins[name] + business_path)
            assert response.status_code == 200 and len(response.content) < 1024
            if name in self.application_paths:
                assert response.json() == json.loads(self.application_paths[name].read_bytes())
        self.generation += 1
        self.identities[name] = digest(json.dumps(
            [self.scope, name, process.pid, self.generation]).encode())
        return process.pid

    def selected_files(self, name, material):
        contract = material.product.runtime_contract
        wrapper = select_receiver_node_control_configuration_artifact(
            artifacts=contract.configuration_artifacts,
            environment=(*material.public_environment, *material.socket_environment),
            control_surfaces=contract.control_surfaces)
        path = Path(wrapper.target_path)
        assert path.parent == self.root / name and path.name == "wrapper.json"
        application = None
        if name == "palette-example":
            application, = (item for item in contract.configuration_artifacts if item != wrapper)
            assert application.artifact_id == "palette-data"
            assert Path(application.target_path) == self.root / name / "colors.json"
            assert application.media_type is ConfigurationMediaType.JSON
            assert PublicStaticEnvironmentBinding("PALETTE_CONFIGURATION_FILE",
                application.target_path) in material.public_environment
        else:
            assert contract.configuration_artifacts == (wrapper,)
        selected = (wrapper,) if application is None else (wrapper, application)
        assert all(item.file_mode.value == "0444" for item in selected)
        return wrapper, application

    def install(self, name, material):
        self.port_calls.append("install")
        wrapper, application = self.selected_files(name, material)
        assert name not in self.children and name not in self.paths
        directory = self.root / name
        directory.mkdir(mode=0o700)
        for artifact in (wrapper,) if application is None else (wrapper, application):
            path = Path(artifact.target_path)
            raw = artifact.content.encode("utf-8")
            self.owned_files.add(path)
            with path.open("xb") as stream:
                stream.write(raw)
            path.chmod(0o444)
            assert path.read_bytes() == raw
        self.paths[name] = Path(wrapper.target_path)
        self.hashes[name] = digest(wrapper.content.encode())
        if application is not None:
            self.application_paths[name] = Path(application.target_path)
        self.launch(name)
        return self.identities[name]

    def replace(self, name, material):
        self.port_calls.append("replace")
        wrapper, application = self.selected_files(name, material)
        assert application is not None and name not in self.replacement_started
        assert self.children[name].poll() is None
        wrapper_path, app_path = self.paths[name], self.application_paths[name]
        assert Path(wrapper.target_path) == wrapper_path
        assert Path(application.target_path) == app_path
        assert not wrapper_path.is_symlink() and not app_path.is_symlink()
        assert wrapper_path.parent.is_dir() and not wrapper_path.parent.is_symlink()
        wrapper_bytes = wrapper_path.read_bytes()
        assert wrapper_bytes == wrapper.content.encode() and digest(wrapper_bytes) == self.hashes[name]
        raw = application.content.encode("utf-8")
        prior = self.identities[name]  # Includes any same-config health restart.
        descriptor, temporary = tempfile.mkstemp(prefix=".colors-", dir=app_path.parent)
        staged = Path(temporary)
        self.owned_files.add(staged)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
        staged.chmod(0o444)
        assert staged.read_bytes() == raw
        # No old-process/file mutation precedes the successful private stage.
        self.replacement_started.add(name)
        self.stop(name)
        os.replace(staged, app_path)
        self.launch(name)
        assert app_path.read_bytes() == raw and wrapper_path.read_bytes() == wrapper_bytes
        return prior, self.identities[name]

    def stop(self, name):
        process = self.children[name]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        else:
            process.wait(timeout=1)
        assert process.poll() is not None
        process.stdout.close()
        self.stops.append((name, process.pid))
        del self.children[name]
        self.origins.pop(name, None)

    def restart(self, name):
        old = self.children[name].pid
        raw = self.paths[name].read_bytes()
        self.stop(name)
        new = self.launch(name)
        assert old != new and digest(raw) == self.hashes[name]
        assert self.paths[name].read_bytes() == raw
        print(json.dumps({"receiver_restart": name, "old_pid": old, "new_pid": new,
            "configuration_sha256": self.hashes[name]}), flush=True)

    def close(self):
        failures = []
        for name in tuple(self.children):
            try:
                self.stop(name)
            except Exception as error:
                failures.append(type(error).__name__)
        for path in self.owned_files:
            path.unlink(missing_ok=True)
        assert not failures and not self.children, "owned receiver process cleanup incomplete"
        assert all(not path.exists() for path in self.owned_files)
        print("unlisted receiver process/file absence verified", flush=True)


class ProcessCompute(ComputeSubstitute):
    """Named local-process substitute, consuming only actual admitted material."""
    def __init__(self, processes):
        super().__init__()
        self.processes = processes

    def execute_with_authority(self, request, authority):
        node = getattr(request.operation.target, "node_id", None)
        names = {item[0] for item in EXAMPLES}
        operation = type(request.operation)
        if node not in names or operation not in (StartNode, ReconcileNode, RemoveNodeResource):
            return super().execute_with_authority(request, authority)
        assert authority.authority_ref == request.authority_ref
        RuntimeEffectRequest.__post_init__(request)
        if operation in (StartNode, ReconcileNode) and any(value.secret_selections for value in request.products):
            return RuntimeEffectResult.unsupported(request.effect_id,
                RuntimeEffectFailure("fixture.process-selected-unsupported", "selected process delivery is not modeled"))
        self.calls.append(request)
        self.order.append((operation.__name__, request.activity_id.value))
        evidence = {"provider_boundary": "249-owned-source-process"}
        begun = False
        try:
            if operation is RemoveNodeResource:
                begun = True
                self.processes.stop(node)
                self.installed.pop(node)
                self.identities.pop(node)
                return RuntimeEffectResult.succeeded(request.effect_id, evidence=evidence)
            correlation = configuration_invocation_correlation_for_request(request)
            for ref in correlation.selection.instances:
                assert self.configuration_refs.get(ref.allocation_id, ref) == ref
            material, = request.products
            if operation is StartNode:
                assert node not in self.installed
                begun = True
                identity = self.processes.install(node, material)
                prior, disposition = None, ConfigurationInstallationDisposition.CREATED
            else:
                assert node in self.installed
                prior, identity = self.processes.replace(node, material)
                disposition = ConfigurationInstallationDisposition.REPLACED
            evidence["configuration_installation_receipt"] = ConfigurationInstallationReceipt(
                correlation.request_fingerprint,
                configuration_invocation_selection_fingerprint(correlation.selection),
                disposition, prior, identity).descriptor()
            result = RuntimeEffectResult.succeeded(request.effect_id, evidence=evidence)
            self.installed[node], self.identities[node] = material, identity
            self.configuration_refs.update((ref.allocation_id, ref) for ref in correlation.selection.instances)
            self.processes.replacement_started.discard(node)
            return result
        except Exception:
            failure = RuntimeEffectFailure("source-process.installation-incomplete",
                "Owned source process installation did not complete.")
            result = (RuntimeEffectResult.uncertain if begun or node in self.processes.replacement_started
                else RuntimeEffectResult.failed)
            return result(request.effect_id, failure)


class LocalReceiverSocketTransport(InstalledTransport):
    """Test-only host-to-loopback mapping; public-address policy stays unchanged."""
    def __init__(self, apps, processes):
        super().__init__(apps)
        self.processes = processes

    async def handle_async_request(self, request):
        name = request.url.host
        if name not in self.processes.origins:
            return await super().handle_async_request(request)
        self.calls.append((name, request.url.path))
        self.processes.tokens[name] = (request.headers["authorization"], request.url.path)
        destination = self.processes.origins[name] + request.url.raw_path.decode("ascii")
        async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = await client.request(request.method, destination,
                headers=request.headers, content=await request.aread())
        assert len(response.content) <= 16384
        return response


class ProcessHealth(SignedHealthComposition):
    def __init__(self, material, compute, ingress, processes):
        super().__init__(material, compute, ingress)
        self.processes, self.restarted, self.configured_ids = processes, set(), {}

    def applications(self):
        # The already accepted bootstrap receiver remains an explicit ASGI fixture.
        # New examples are never imported/constructed in the controller process.
        apps = {}
        if "api" in self.compute.installed:
            app = FastAPI()
            install_cpk_wrapper(app, configuration=self.installed_configuration("api"),
                readiness=lambda: core.NodeHealthReadOutcome.HEALTHY)
            apps["api"] = app
        transport = LocalReceiverSocketTransport(apps, self.processes)
        artifacts = {value.artifact_id: value for value in
            self.compute.installed["gateway"].product.runtime_contract.configuration_artifacts}
        routes = core.ReceiverManagementRoutesCodec().decode_bytes(
            artifacts["gateway-health-targets"].content.encode())
        relay = GatewayHealthRelay(routes,
            gateway_health_transit_verifier_from_artifact(artifacts["gateway-health-transit"]),
            clock=lambda: int(time.time()), transport=transport)
        apps["gateway"] = create_app(health_relay=relay,
            control_configuration=self.installed_configuration("gateway"))
        return apps, routes, transport

    async def observe_signed(self, realization, request, authority):
        result = await super().observe_signed(realization, request, authority)
        name = authority.preparation.request.target.node_id.value
        if name in self.processes.children and name not in self.restarted:
            target = self.installed_configuration(name).target
            self.configured_ids[name] = target.receiver_id
            self.processes.restart(name)
            # Same in-flight authority/preparation; a new signed call reaches a new
            # actual process. No completed effect is redispatched or re-admitted.
            again = await super().observe_signed(realization, request, authority)
            assert self.installed_configuration(name).target == target
            assert again.request == result.request
            self.restarted.add(name)
            return again
        return result


class LoseCompletedPreparation:
    """Drop one real successful HTTP result; never fabricate server responses."""
    def __init__(self, profile):
        self.inner = PublicHttpTransport(profile)
        self.calls, self.preparations = [], []
        self.execution_diagnostics = []
        self.lost = False

    def call(self, route_id, **arguments):
        snapshot = json.loads(json.dumps(arguments))
        self.calls.append((route_id, snapshot))
        observed = route_id in {"command.run.start", "command.deployment.execute"}
        try:
            result = self.inner.call(route_id, **arguments)
        except ClientTransportError as error:
            print(json.dumps({"unlisted_failed_public_route": route_id,
                "error_type": type(error).__name__}), flush=True)
            if observed:
                self.execution_diagnostics.append({"route": route_id,
                    "transport_error": type(error).__name__})
                self.execution_diagnostics = self.execution_diagnostics[-16:]
            raise
        if observed:
            self.execution_diagnostics.append({"route": route_id, **diagnostic_fields(result)})
            self.execution_diagnostics = self.execution_diagnostics[-16:]
        if route_id == "command.deployment.prepare":
            assert result["status"] in ("approval-required", "no-changes")
            self.preparations.append((snapshot, result))
            if not self.lost:
                self.lost = True
                raise ClientTransportError("synthetic loss after completed HTTP preparation")
        return result


def diagnostic_fields(value):
    """Only bounded protocol coordinates/statuses; never payload or failure text."""
    names = ("run_id", "execution_request_id", "run_status", "coordinator_status",
        "effects_attempted", "activity_id", "claim_generation", "event_id",
        "event_type", "ordinal", "status", "plan_id")
    return {key: item for key in names if key in value
        and (item := value[key]) is not None
        and (type(item) is int or type(item) is str and len(item) <= 256)}


class StartFailureDiagnostic:
    """Bounded source coordinates only, before coordinator error sanitization."""
    def __init__(self):
        self.count = 0

    def __call__(self, error):
        if self.count >= 4:
            return
        self.count += 1
        chain, visited = [], set()
        while error is not None and id(error) not in visited and len(chain) < 4:
            visited.add(id(error))
            frames, trace = [], error.__traceback__
            while trace is not None:
                code = trace.tb_frame.f_code
                module = trace.tb_frame.f_globals.get("__name__", "")
                if (type(module) is str and len(module) <= 160
                        and module.startswith(("control_plane_kit_", "receiver_acceptance_operations"))
                        and all(part.isidentifier() for part in module.split("."))):
                    frames.append({"module": module, "function": code.co_name
                        if code.co_name.isidentifier() and len(code.co_name) <= 128 else "anonymous",
                        "line": trace.tb_lineno})
                    frames = frames[-8:]
                trace = trace.tb_next
            kind = type(error).__name__
            chain.append({"kind": kind if kind in {"EffectAttemptStartConflict",
                "EffectAttemptStartDenied", "EffectAttemptStartNotFound", "OperationsRecordError",
                "ReceiverScopeUnavailable", "ReceiverScopeCapacity", "_Unavailable", "_Capacity",
                "ValueError", "TypeError", "KeyError", "AttributeError"} else "other", "frames": frames})
            error = error.__cause__ if error.__cause__ is not None else error.__context__
        print(json.dumps({"unlisted_start_failure": chain}), flush=True)


async def diagnose_execution(client, transport, result):
    journal = client.journal.read(result.operation_ref)
    pending = journal.get("pending_request") or {}
    print(json.dumps({"unlisted_execution_diagnostics": transport.execution_diagnostics,
        "pending_route": pending.get("route_id"),
        "pending_claim_generation": pending.get("body", {}).get("claim_generation"),
        "completed_routes": [item["route_id"] for item in journal["request_history"][-16:]]}), flush=True)
    for route, coordinate, identity in (
        ("read.plan-runs", "plan_id", result.plan_id),
        ("read.run-events", "run_id", result.run_id)):
        if identity is None:
            continue
        try:
            page = await asyncio.to_thread(transport.inner.call, route,
                path_parameters={"workspace_id": "workspace-a", coordinate: identity},
                payload={"limit": 32}, credential_role="operator")
            print(json.dumps({"unlisted_public_diagnostic": route,
                "items": [diagnostic_fields(item) for item in page["items"][:32]],
                "more": page.get("next_cursor") is not None}), flush=True)
        except Exception as error:
            print(json.dumps({"unlisted_public_diagnostic": route,
                "error_type": type(error).__name__}), flush=True)


async def select_pending_baseline(transport, material, *, workspace_id="workspace-a", scopes=None):
    """Public prerequisite for initial deployment, not high-level draft-save proof."""
    async def call(route, payload=None, draft_id=None):
        path = {"workspace_id": workspace_id}
        if draft_id is not None:
            path["draft_id"] = draft_id
        return await asyncio.to_thread(transport.call, route, path_parameters=path,
            payload=payload or {}, credential_role="operator")
    names = ("current_graph_id", "current_realized_projection_id", "desired_graph_id",
        "desired_realized_projection_id", "desired_graph_revision")
    before = (await call("read.workspace"))["workspace"]
    current = await call("read.current-graph")
    empty = DEFAULT_GRAPH_CODEC.decode(current["graph_descriptor"])
    assert not empty.nodes and not empty.runtimes
    assert not transport.preparations
    session = await call("command.operation-session.start", {"workspace_id": workspace_id,
        "title": "Unlisted baseline pending draft", "metadata": {}, "idempotency_key": str(uuid4())})
    draft = await call("command.desired-topology-draft.create", {
        "session_id": session["session_id"], "graph": DEFAULT_GRAPH_CODEC.encode(material.a),
        "title": "Named baseline fixture", "receiver_lifecycle": {key: before[key] for key in names},
        "idempotency_key": str(uuid4())})
    fresh = (await call("read.workspace"))["workspace"]
    assert all(fresh[key] == before[key] for key in names)
    selected = await call("command.desired-topology-draft.select", {
        "session_id": session["session_id"], "revision": draft["revision"],
        "expected_desired_graph_id": fresh["desired_graph_id"],
        "expected_desired_realized_projection_id": fresh["desired_realized_projection_id"],
        "expected_desired_graph_revision": fresh["desired_graph_revision"],
        "receiver_lifecycle": {key: fresh[key] for key in names},
        "idempotency_key": str(uuid4())}, draft["draft_id"])
    after = (await call("read.workspace"))["workspace"]
    assert all(after[key] == before[key] for key in names[:2])
    assert all(selected[key] == draft[key] for key in ("workspace_id", "draft_id", "revision", "graph_id"))
    assert after["desired_graph_id"] == draft["graph_id"]
    assert after["desired_realized_projection_id"] == selected["desired_realized_projection_id"]
    assert after["desired_graph_revision"] == selected["desired_graph_revision"]
    print("unlisted receiver: real pending baseline selected; current remains empty", flush=True)
    return PendingReceiverContinuation(draft["draft_id"], draft["revision"],
        scopes if scopes is not None else (ReceiverScope("gateway", "control"), ReceiverScope("api", "http")))


async def register_surface_verifier(transport, material, *, workspace_id="workspace-a"):
    """237-only public prerequisite; do not expand the 1912 health fixture.

    The selected owner maps surface-read registration to the existing legacy
    gateway.probe-signing-key intent. A separate synthetic provider/reference
    grants only that intent; no health reference permissions are widened.
    """
    private = Ed25519PrivateKey.generate()
    material.private["surface"] = private.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    instant = utc_now()
    intent = "gateway.probe-signing-key"
    reference = "secret://unlisted-surface/keys/surface"
    purpose = "workload-node-control-surface-read"
    async def register(route, payload, *, path=None):
        return await asyncio.to_thread(transport.call, route,
            path_parameters={"workspace_id": workspace_id, **(path or {})}, payload=payload,
            credential_role="operator")
    provider = await register("command.secret-provider.register", {
        "provider_id": "unlisted-surface", "display_name": "Unlisted surface test key custody",
        "provider_kind": "control-plane-kit-secrets", "endpoint_reference": "unlisted-surface",
        "credential_reference": "secret://bootstrap/unlisted-surface/client-token",
        "allowed_reference_prefixes": ["secret://unlisted-surface/keys"],
        "allowed_intents": [intent], "admitted_at": instant,
        "metadata": {"acceptance": "unlisted-sdk-237"}, "idempotency_key": "unlisted-surface-provider"})
    assert provider["status"] == "active" and provider["allowed_intents"] == [intent]
    registered = await register("command.secret-reference.register", {
        "reference": reference, "provider_registration_id": provider["registration_id"],
        "allowed_intents": [intent], "admitted_at": instant,
        "metadata": {"acceptance": "unlisted-sdk-237"}, "idempotency_key": "unlisted-surface-reference"})
    assert registered["status"] == "active" and registered["reference_id"] == reference
    assert registered["allowed_intents"] == [intent]
    key = await register("command.delegation-key.register", {
        "purpose": purpose, "issuer": "cpk-server", "key_id": "unlisted-surface",
        "algorithm": "ed25519", "public_key_pem": public, "private_key_reference": reference,
        "admitted_at": instant, "idempotency_key": "unlisted-surface-key"})
    assert key["status"] == "verify-only" and key["purpose"] == purpose
    active = await register("command.delegation-key.activate", {
        "purpose": purpose,
        "activated_at": instant, "idempotency_key": "unlisted-surface-activate"},
        path={"issuer": "cpk-server", "key_id": "unlisted-surface"})
    assert active["status"] == "active" and active["purpose"] == purpose
    assert active["registration_id"] == key["registration_id"]
    assert active["key_id"] == "unlisted-surface"
    print("unlisted receiver: distinct surface verifier admitted through public owners", flush=True)


def unlisted_graph(material, root):
    nodes = dict(material.a.nodes)
    documents, introductions, routes = {}, [], []
    for name, script, business_path, artifact_id, port in EXAMPLES:
        target_path = str(root / name / "wrapper.json")
        slot = ConfigurationArtifact(artifact_id, target_path, ConfigurationMediaType.JSON, "{}")
        application_slots, application_environment = (), ()
        if name == "palette-example":
            application_slots = (ConfigurationArtifact("palette-data", str(root / name / "colors.json"),
                ConfigurationMediaType.JSON, '{"colors":["indigo","amber"]}'),)
            application_environment = (PublicStaticEnvironmentBinding("PALETTE_CONFIGURATION_FILE",
                application_slots[0].target_path),)
        surface = core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "http"),
            (), (core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS))
        contract = ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("http", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("http", port),),
            capabilities=(CapabilityName.NODE_CONTROLLABLE, CapabilityName.HEALTH_CHECKABLE),
            control_surfaces=(surface,), configuration_artifacts=(slot, *application_slots),
            public_environment=(PublicStaticEnvironmentBinding(
                "CPK_WRAPPER_CONFIGURATION_FILE", target_path), *application_environment))
        document = ProductDescriptorCodec().encode_document(ContainerServerProduct(
            ProductIdentity("independent-sdk-example", name, 1),
            OciImageReference("example.invalid", "source-example/" + name, "sha256:" + "d" * 64), contract))
        documents[name] = document
        reference = ProductReference.from_document(document)
        nodes[name] = Node(name, BlockFamily.APPLICATION,
            BlockSpec(name, capabilities=contract.capabilities, control_surfaces=contract.control_surfaces),
            "container-server", "docker", contract.sockets,
            endpoints={"http": Endpoint(LiteralAddress(f"http://{name}:{port}"), Protocol.HTTP)},
            configuration_artifacts=application_slots, public_environment=application_environment,
            metadata={"product_identity": reference.identity.key,
                "product_descriptor_digest": reference.descriptor_sha256.value})
        scope = ReceiverScope(name, "http")
        introductions.append(ReceiverIntroduction(scope, artifact_id, target_path))
        routes.append(GatewayHealthTargetIntent(name, scope, nodes[name].endpoint("http").url))
    graph = replace(material.a, nodes=nodes, runtimes={"docker":
        replace(material.a.runtimes["docker"], children=tuple(nodes))})
    existing = (
        GatewayHealthTargetIntent("self", ReceiverScope("gateway", "control"), "http://gateway:8000"),
        GatewayHealthTargetIntent("api", ReceiverScope("api", "http"), "http://api:8000"),
    )
    return graph, documents, tuple(introductions), (
        GatewayHealthRoutes(ReceiverScope("gateway", "control"), (*existing, *routes)),)


async def retained_application_update(host, transport, client, initial, authored, processes, compute, health):
    """Actual retained update via public HTTP; local evidence never writes owner truth."""
    async def read(route, **coordinates):
        return await asyncio.to_thread(transport.call, route,
            path_parameters={"workspace_id": "workspace-a", **coordinates},
            payload={}, credential_role="operator")

    async def history(result):
        plan = await read("read.plan-detail", plan_id=result.plan_id)
        pages = {}
        for route, coordinate in (("read.plan-runs", {"plan_id": result.plan_id}),
                ("read.run-events", {"run_id": result.run_id})):
            items, after = [], None
            for _ in range(8):
                payload = {"limit": 100}
                if after is not None:
                    payload["after"] = after
                page = await asyncio.to_thread(transport.call, route,
                    path_parameters={"workspace_id": "workspace-a", **coordinate},
                    payload=payload, credential_role="operator")
                items.extend(page["items"])
                after = page.get("next_cursor")
                if after is None:
                    break
            assert after is None and items, "public history missing or exceeds witness bound"
            pages[route] = items
        return plan["plan"], pages

    original_history = await history(initial)
    receiver_source = (await read("read.receiver-authoring-context"))["current"]
    wrapper_bytes = {name: path.read_bytes() for name, path in processes.paths.items()}
    old_palette = processes.children["palette-example"]
    old_incarnation = processes.identities["palette-example"]
    counter = processes.children["counter-example"]
    counter_material = compute.installed["counter-example"]
    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
        before_count = await socket.get(processes.origins["counter-example"] + "/count")
        assert before_count.status_code == 200
        before_count = int(before_count.text)
    palette = authored.node("palette-example")
    changed = replace(palette, configuration_artifacts=tuple(
        replace(item, content='{"colors":["teal","coral"]}', source_digest=None)
        if item.artifact_id == "palette-data" else item for item in palette.configuration_artifacts))
    desired = authored.update_node(changed)
    source = processes.root / "retained-desired.json"
    source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(desired)), encoding="utf-8")
    source_bytes = source.read_bytes()
    start_count, stop_count, effect_count = len(processes.starts), len(processes.stops), len(compute.calls)
    process_call_count = len(processes.port_calls)
    planned = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(source))
    assert planned.status == "planned", planned.descriptor()
    option = "approve_destructive_plan" if planned.destructive else "approve_plan"
    updated = await asyncio.to_thread(client.apply, planned.operation_ref,
        execute_plan=planned.plan_id, **{option: planned.plan_id})
    if updated.status != "converged":
        print(json.dumps({"retained_update_process_port_calls":
            len(processes.port_calls) - process_call_count}), flush=True)
        await diagnose_execution(client, transport, updated)
    assert updated.status == "converged", updated.descriptor()
    replacement, = (request for request in compute.calls[effect_count:]
        if type(request.operation) is ReconcileNode)
    assert replacement.operation.target.node_id == "palette-example"
    assert len(processes.starts) == start_count + 1 and len(processes.stops) == stop_count + 1
    assert old_palette.poll() is not None and processes.children["palette-example"].pid != old_palette.pid
    assert processes.identities["palette-example"] != old_incarnation
    assert compute.identities["palette-example"] == processes.identities["palette-example"]
    assert processes.children["counter-example"] is counter and counter.poll() is None
    assert compute.installed["counter-example"] == counter_material
    assert all(processes.paths[name].read_bytes() == raw for name, raw in wrapper_bytes.items())
    selected, = (item for item in changed.configuration_artifacts if item.artifact_id == "palette-data")
    assert processes.application_paths["palette-example"].read_bytes() == selected.content.encode()
    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
        response = await socket.get(processes.origins["palette-example"] + "/palette")
        assert response.status_code == 200 and response.json() == {"colors": ["teal", "coral"]}
        credential, protected_path = processes.tokens["palette-example"]
        healthy = await socket.get(processes.origins["palette-example"] + protected_path,
            headers={"Authorization": credential})
        assert healthy.status_code == 200 and len(healthy.content) <= 16384
        count = await socket.get(processes.origins["counter-example"] + "/count")
        assert count.status_code == 200 and int(count.text) > before_count
    assert health.installed_configuration("palette-example").target.receiver_id == health.configured_ids["palette-example"]
    update_history = await history(updated)
    update_plan = update_history[0]
    updated_source = (await read("read.receiver-authoring-context"))["current"]
    for context, side in ((receiver_source, "base"), (updated_source, "desired")):
        assert (context["graph_id"], context["realized_projection_id"]) == (
            update_plan[side + "_graph_id"], update_plan[side + "_realized_projection_id"])
        assert all((row["binding"]["graph_id"], row["binding"]["realized_projection_id"]) ==
            (context["graph_id"], context["realized_projection_id"]) for row in context["receivers"])
    assert (receiver_source["graph_id"], receiver_source["realized_projection_id"]) != (
        updated_source["graph_id"], updated_source["realized_projection_id"])
    # Selection coordinates advance with the public plan. Every other field,
    # including wrapper bytes, receiver identity and original acceptance, stays exact.
    expected_receivers = [{**row, "binding": {**row["binding"],
        "graph_id": updated_source["graph_id"],
        "realized_projection_id": updated_source["realized_projection_id"]}}
        for row in receiver_source["receivers"]]
    assert updated_source["receivers"] == expected_receivers
    assert await history(initial) == original_history
    assert updated.plan_id != initial.plan_id and updated.run_id != initial.run_id
    effects = (tuple(compute.calls), tuple(processes.starts), tuple(processes.stops))
    def no_identity():
        raise AssertionError("retained operation regenerated identity")
    reconstructed = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_identity)
    replay = await asyncio.to_thread(reconstructed.apply, updated.operation_ref, execute_plan=updated.plan_id)
    assert replay.status == "converged", replay.descriptor()
    noop = await asyncio.to_thread(reconstructed.plan, AuthoredDesiredGraph(source))
    assert noop.status == "no-changes", noop.descriptor()
    no_execution = await asyncio.to_thread(reconstructed.apply, noop.operation_ref, execute_plan=noop.plan_id)
    assert no_execution.status == "no-changes"
    assert (tuple(compute.calls), tuple(processes.starts), tuple(processes.stops)) == effects
    assert await history(initial) == original_history and await history(updated) == update_history
    assert source.read_bytes() == source_bytes
    for credential_path in host.credential_files.values():
        credential = credential_path.read_bytes()
        assert credential not in source_bytes
        assert credential not in json.dumps(reconstructed.journal.read(updated.operation_ref)).encode()
    print("S1 retained app update: selected bytes, new process/business value, protected health, same receiver/wrapper/history, unchanged counter and replay/no-op without replacement passed", flush=True)


async def witness():
    verify_provenance()
    frozen = controller_identity()
    image = os.environ["CPK_FROZEN_CONTROLLER_IMAGE"]
    assert image.startswith("sha256:") and len(image) == 71
    examples = Path(os.environ["CPK_UNLISTED_EXAMPLES"])
    assert examples.is_absolute() and all((examples / item[1]).is_file() for item in EXAMPLES)
    print(json.dumps({"frozen_controller_image": image, "installed_source_sha256": frozen,
        "external_examples": {item[1]: digest((examples / item[1]).read_bytes()) for item in EXAMPLES}}), flush=True)
    material = AuthoredMaterial()
    with tempfile.TemporaryDirectory(prefix="cpk-unlisted-") as temporary:
        root = Path(temporary)
        processes = ReceiverProcesses(root, examples)
        compute = ProcessCompute(processes)
        ingress = IngressSubstitute(compute)
        health = ProcessHealth(material, compute, ingress, processes)
        try:
            with IsolatedOperationsSchema(os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"],
                    "cpk_1912_unlisted_" + uuid4().hex) as schema:
                factory = OperationsApplicationFactory(schema.unit_of_work,
                    OperationsEffectPorts({RuntimeKind.DOCKER: synthetic_runtime_registration(compute)},
                        {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
                    id_factory=lambda: "unlisted-" + uuid4().hex,
                    start_failure_observer=StartFailureDiagnostic())
                driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
                await driver.create_workspace()
                await register_material(driver, material)
                graph, documents, introductions, routes = unlisted_graph(material, root)
                # Immutable controller image/source precedes these new product registrations.
                with ControllerHost(factory, driver, root / "controller") as host:
                    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
                        denied = await socket.get(host.endpoint + "/workspaces/workspace-a")
                        assert denied.status_code == 401
                    transport = LoseCompletedPreparation(host.profile)
                    await register_surface_verifier(transport, material)
                    baseline = await select_pending_baseline(transport, material)
                    assert not compute.installed and not compute.runtimes and not ingress.allocations
                    for name, document in documents.items():
                        imported = await asyncio.to_thread(transport.call, "command.product.import",
                            path_parameters={"workspace_id": "workspace-a"},
                            payload={"descriptor_document": json.loads(document.content),
                                "imported_at": utc_now(), "idempotency_key": "unlisted-import-" + name},
                            credential_role="operator")
                        assert imported["status"] == "active"
                    source = root / "desired.json"
                    source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(graph)), encoding="utf-8")
                    original = source.read_bytes()
                    client = TopologyClient(host.profile, transport=transport)
                    pending = await asyncio.to_thread(client.plan,
                        AuthoredDesiredGraph(source, introductions=introductions,
                            pending=baseline,
                            gateway_health_replacements=routes))
                    assert pending.status == "attention-required" and len(transport.preparations) == 1
                    journal = client.journal.read(pending.operation_ref)
                    prepared = client.journal.root / journal["preparation"]["name"]
                    prepared_bytes = prepared.read_bytes()
                    assert json.loads(prepared_bytes) == transport.preparations[0][0]["payload"]["desired_graph"]
                    counts = {route: sum(call[0] == route for call in transport.calls) for route in
                        ("read.receiver-authoring-context", "read.workload-verifier-configuration")}
                    assert set(counts.values()) == {1}
                    def no_regeneration():
                        raise AssertionError("resume regenerated receiver identity")
                    restarted = TopologyClient(host.profile, transport=transport,
                        receiver_identity_factory=no_regeneration)
                    planned = await asyncio.to_thread(restarted.resume_prepare, pending.operation_ref)
                    assert planned.status == "planned" and len(transport.preparations) == 2
                    assert transport.preparations[0][0] == transport.preparations[1][0]
                    assert transport.preparations[0][1]["plan_id"] == transport.preparations[1][1]["plan_id"]
                    exchanges = host.prepare_exchanges
                    assert len(exchanges) == 2 and all(200 <= item.response_status < 300 for item in exchanges)
                    assert exchanges[0].request_body == exchanges[1].request_body
                    assert source.read_bytes() == original and prepared.read_bytes() == prepared_bytes
                    assert all(sum(call[0] == route for call in transport.calls) == count
                        for route, count in counts.items())
                    authored = DEFAULT_GRAPH_CODEC.decode(json.loads(prepared_bytes))
                    for name, document in documents.items():
                        contract = document.product.runtime_contract
                        declared, = (item for item in contract.configuration_artifacts
                            if item.target_path.endswith("/wrapper.json"))
                        node = authored.node(name)
                        selected = select_receiver_node_control_configuration_artifact(
                            artifacts=node.configuration_artifacts,
                            environment=node.public_environment,
                            control_surfaces=node.block_spec.control_surfaces)
                        assert (selected.artifact_id, selected.target_path,
                            selected.media_type, selected.file_mode) == (
                            declared.artifact_id, declared.target_path,
                            declared.media_type, declared.file_mode)
                        assert node.public_environment == contract.public_environment
                        assert selected.content != declared.content == "{}"
                        assert graph.node(name).configuration_artifacts == tuple(
                            item for item in contract.configuration_artifacts if item != declared)
                        assert graph.node(name).public_environment == tuple(
                            item for item in contract.public_environment if item.name != "CPK_WRAPPER_CONFIGURATION_FILE")
                    print("unlisted receiver: generated wrapper slots match declared product contracts", flush=True)
                    assert type(planned.destructive) is bool
                    assert planned.required_scope == (
                        "plan:approve-destructive" if planned.destructive else "plan:approve")
                    approval_option = (
                        "approve_destructive_plan" if planned.destructive else "approve_plan")
                    print(json.dumps({"unlisted_plan_approval": planned.plan_id,
                        "destructive": planned.destructive,
                        "required_scope": planned.required_scope}), flush=True)
                    result = await asyncio.to_thread(restarted.apply, planned.operation_ref,
                        execute_plan=planned.plan_id, **{approval_option: planned.plan_id})
                    if result.status != "converged":
                        try:
                            await diagnose_execution(restarted, transport, result)
                        except Exception as error:
                            print(json.dumps({"unlisted_diagnostic_error": type(error).__name__}), flush=True)
                    assert result.status == "converged", result.descriptor()
                    assert health.restarted == {item[0] for item in EXAMPLES}
                    assert len(set(health.configured_ids.values())) == 2
                    for name, *_ in EXAMPLES:
                        selected = select_receiver_node_control_configuration_artifact(
                            artifacts=authored.node(name).configuration_artifacts,
                            environment=authored.node(name).public_environment,
                            control_surfaces=authored.node(name).block_spec.control_surfaces)
                        assert processes.paths[name].read_bytes() == selected.content.encode()
                        assert processes.hashes[name] == digest(selected.content.encode())
                        configured = core.ReceiverNodeControlConfigurationCodec().decode_bytes(selected.content.encode())
                        families = {item.purpose: item for item in configured.verifiers}
                        assert set(families) == {core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ}
                        assert tuple(key.key_id for key in families[
                            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ].public_keys) == ("unlisted-surface",)
                    first, second = (item[0] for item in EXAMPLES)
                    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
                        credential, protected_path = processes.tokens[first]
                        admitted = await socket.get(processes.origins[first] + protected_path,
                            headers={"Authorization": credential})
                        assert admitted.status_code == 200 and len(admitted.content) <= 16384
                        refused = await socket.get(processes.origins[second] + protected_path,
                            headers={"Authorization": credential})
                        assert refused.status_code in (401, 403) and len(refused.content) <= 16384
                        resigned, unsupported = unsupported_profile_credential(credential,
                            health.installed_configuration(first).target, material)
                        resigned_valid = await socket.get(processes.origins[first] + protected_path,
                            headers={"Authorization": resigned})
                        assert resigned_valid.status_code == 200
                        bad_profile = await socket.get(processes.origins[first] + protected_path,
                            headers={"Authorization": unsupported})
                        assert bad_profile.status_code in (401, 403) and len(bad_profile.content) <= 16384
                        # Same original valid request still succeeds: the process
                        # remains serving and refusal did not replace its state.
                        still_valid = await socket.get(processes.origins[first] + protected_path,
                            headers={"Authorization": resigned})
                        assert still_valid.status_code == 200
                        unknown = await socket.get(processes.origins[second] + "/__control/health/ready",
                            headers={"Authorization": processes.tokens[second][0]})
                        assert unknown.status_code == 404
                    await retained_application_update(host, transport, restarted, result, authored,
                        processes, compute, health)
                    for credential_path in host.credential_files.values():
                        credential = credential_path.read_bytes()
                        assert credential not in prepared_bytes
                        assert credential not in json.dumps(restarted.journal.read(planned.operation_ref)).encode()
                    assert controller_identity() == frozen
                    print("unlisted receiver: real authoring, exact completed-response retry, installed default SDK health, target/profile refusal and PID restart passed", flush=True)
                await driver.accept(label="teardown", desired_graph=DeploymentGraph("unlisted-teardown"), destructive=True)
                assert not compute.installed and not compute.runtimes and not ingress.allocations
        finally:
            processes.close()
    assert not root.exists()
    print("unlisted receiver private directory absence verified; physical E4/provider cleanup unproven", flush=True)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise RuntimeError("unlisted witness interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    asyncio.run(witness())
