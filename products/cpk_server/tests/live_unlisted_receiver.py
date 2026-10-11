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
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity,
    ProductReference, ProductRuntimeContract, ProviderRuntimePort,
)
from control_plane_kit_core.planning import StartNode, RemoveNodeResource
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, Node
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import (
    AuthoredDesiredGraph, ReceiverIntroduction, ReceiverScope,
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

    def launch(self, name):
        assert name not in self.children and len(self.children) < 2
        script = next(item[1] for item in EXAMPLES if item[0] == name)
        environment = {**os.environ, "CPK_WRAPPER_CONFIGURATION_FILE": str(self.paths[name]),
            "PYTHONDONTWRITEBYTECODE": "1"}
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
        return process.pid

    def install(self, name, material):
        contract = material.product.runtime_contract
        artifact = select_receiver_node_control_configuration_artifact(
            artifacts=contract.configuration_artifacts,
            environment=(*material.public_environment, *material.socket_environment),
            control_surfaces=contract.control_surfaces)
        path = Path(artifact.target_path)
        assert path.parent == self.root / name and path.name == "wrapper.json"
        path.parent.mkdir(mode=0o700)
        raw = artifact.content.encode("utf-8")
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o444)
        self.paths[name], self.hashes[name] = path, digest(raw)
        self.launch(name)

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
        for path in self.paths.values():
            path.unlink(missing_ok=True)
        assert not failures and not self.children, "owned receiver process cleanup incomplete"
        assert all(not path.exists() for path in self.paths.values())
        print("unlisted receiver process/file absence verified", flush=True)


class ProcessCompute(ComputeSubstitute):
    """Named local-process substitute, consuming only actual admitted material."""
    def __init__(self, processes):
        super().__init__()
        self.processes = processes

    def execute_with_authority(self, request, authority):
        result = super().execute_with_authority(request, authority)
        node = getattr(request.operation.target, "node_id", None)
        names = {item[0] for item in EXAMPLES}
        if type(request.operation) is StartNode and node in names:
            self.processes.install(node, self.installed[node])
        elif type(request.operation) is RemoveNodeResource and node in names:
            self.processes.stop(node)
        return result


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
        self.lost = False

    def call(self, route_id, **arguments):
        snapshot = json.loads(json.dumps(arguments))
        self.calls.append((route_id, snapshot))
        result = self.inner.call(route_id, **arguments)
        if route_id == "command.deployment.prepare":
            assert result["status"] == "approval-required"
            self.preparations.append((snapshot, result))
            if not self.lost:
                self.lost = True
                raise ClientTransportError("synthetic loss after completed HTTP preparation")
        return result


async def register_surface_verifier(transport, material):
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
    async def register(route, payload):
        return await asyncio.to_thread(transport.call, route,
            path_parameters={"workspace_id": "workspace-a"}, payload=payload,
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
        "purpose": purpose, "issuer": "cpk-server", "key_id": "unlisted-surface",
        "activated_at": instant, "idempotency_key": "unlisted-surface-activate"})
    assert active["status"] == "active" and active["purpose"] == purpose
    assert active["registration_id"] == key["registration_id"]
    assert active["key_id"] == "unlisted-surface"
    print("unlisted receiver: distinct surface verifier admitted through public owners", flush=True)


def unlisted_graph(material, root):
    nodes = dict(material.a.nodes)
    documents, introductions, routes = {}, [], []
    for name, script, business_path, artifact_id, port in EXAMPLES:
        surface = core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "http"),
            (), (core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS))
        contract = ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("http", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("http", port),),
            capabilities=(CapabilityName.NODE_CONTROLLABLE, CapabilityName.HEALTH_CHECKABLE),
            control_surfaces=(surface,))
        document = ProductDescriptorCodec().encode_document(ContainerServerProduct(
            ProductIdentity("independent-sdk-example", name, 1),
            OciImageReference("example.invalid", "source-example/" + name, "sha256:" + "d" * 64), contract))
        documents[name] = document
        reference = ProductReference.from_document(document)
        nodes[name] = Node(name, BlockFamily.APPLICATION,
            BlockSpec(name, capabilities=contract.capabilities, control_surfaces=contract.control_surfaces),
            "container-server", "docker", contract.sockets,
            endpoints={"http": Endpoint(LiteralAddress(f"http://{name}:{port}"), Protocol.HTTP)},
            metadata={"product_identity": reference.identity.key,
                "product_descriptor_digest": reference.descriptor_sha256.value})
        scope = ReceiverScope(name, "http")
        introductions.append(ReceiverIntroduction(scope, artifact_id, str(root / name / "wrapper.json")))
        routes.append(GatewayHealthTargetIntent(name, scope, nodes[name].endpoint("http").url))
    graph = replace(material.a, nodes=nodes, runtimes={"docker":
        replace(material.a.runtimes["docker"], children=tuple(nodes))})
    existing = (
        GatewayHealthTargetIntent("self", ReceiverScope("gateway", "control"), "http://gateway:8000"),
        GatewayHealthTargetIntent("api", ReceiverScope("api", "http"), "http://api:8000"),
    )
    return graph, documents, tuple(introductions), (
        GatewayHealthRoutes(ReceiverScope("gateway", "control"), (*existing, *routes)),)


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
                    OperationsEffectPorts({RuntimeKind.DOCKER: compute},
                        {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
                    id_factory=lambda: "unlisted-" + uuid4().hex)
                driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
                await driver.create_workspace()
                await register_material(driver, material)
                await driver.accept(label="bootstrap", desired_graph=material.a, destructive=False)
                graph, documents, introductions, routes = unlisted_graph(material, root)
                # Immutable controller image/source precedes these new product registrations.
                with ControllerHost(factory, driver, root / "controller") as host:
                    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
                        denied = await socket.get(host.endpoint + "/workspaces/workspace-a")
                        assert denied.status_code == 401
                    transport = LoseCompletedPreparation(host.profile)
                    await register_surface_verifier(transport, material)
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
                    result = await asyncio.to_thread(restarted.apply, planned.operation_ref,
                        execute_plan=planned.plan_id, approve_plan=planned.plan_id,
                        approve_destructive_plan=planned.plan_id)
                    assert result.status == "converged", result.descriptor()
                    assert health.restarted == {item[0] for item in EXAMPLES}
                    assert len(set(health.configured_ids.values())) == 2
                    authored = DEFAULT_GRAPH_CODEC.decode(json.loads(prepared_bytes))
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
