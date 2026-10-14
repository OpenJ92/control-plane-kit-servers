"""#251 public-client Docker image replacement in the existing owning smoke.

Only ingress allocation/native connection/public routing are synthetic. Docker,
signing provider, SDK health sockets, operation history and business bodies run.
"""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

import docker
import httpx
import control_plane_kit_core as core
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker import DockerRuntimeInterpreter, DockerRuntimeEffectObserver, DockerSdkClient
from control_plane_kit_interpreters.docker.sdk import matches_image_reference
from control_plane_kit_interpreters.probes.health_transport import SignedGatewayHealthClient
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from control_plane_kit_operations.runtime_authorities import LocalDockerSocketAuthority, RegisteredRuntimeAuthority
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import AuthoredDesiredGraph, ReceiverScope
from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport
from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap

from docker_image_update_material import DockerImageMaterial, IMAGES, selected_metadata
from docker_image_update_placement import (
    OwnedControllerPlacement, SyntheticConnectorConnection, owned_resources, dispose_fixture,
)
from docker_image_update_ports import (
    AttachedPublicTransport, RecordedDockerRuntime, FixtureBoundaryFailure, public_page,
    SyntheticIngressAddressResolver, InstalledGatewaySocketTransport,
    require_committed_call, require_replacement_receipt, emit_failed_apply_evidence,
)
from docker_image_update_provider import SigningProviderProcess, SyntheticIngressAllocation
from live_receiver_acceptance import verify_provenance
from live_unlisted_receiver import select_pending_baseline, register_surface_verifier
from receiver_acceptance_operations import (
    IsolatedOperationsSchema, OperationsApplicationFactory, OperationsEffectPorts,
    PublicOperationsDriver, register_material, utc_now,
)
from unlisted_controller_host import ControllerHost


class PublicRegistration:
    def __init__(self, transport, workspace_id):
        self.transport, self.workspace_id = transport, workspace_id

    async def register(self, route, payload):
        path, body = {"workspace_id": self.workspace_id}, dict(payload)
        if route == "command.delegation-key.activate":
            for name in ("issuer", "key_id"):
                path[name] = body.pop(name)
        return await asyncio.to_thread(self.transport.call, route,
            path_parameters=path, payload=body, credential_role="operator")


def inspect_inputs(engine, sdk):
    observed = {}
    for role, value in IMAGES.items():
        image = engine.images.get(value["reference"])
        selected = sdk.inspect_image(value["reference"])
        assert selected is not None and selected.image_id == image.id == value["image_id"]
        assert matches_image_reference(value["reference"], selected.repo_digests)
        assert (image.attrs["Os"], image.attrs["Architecture"]) == ("linux", "amd64")
        assert image.attrs["Config"]["User"] == value["user"]
        if role == "connector":
            assert image.attrs["Config"]["Entrypoint"] == ["/pause"]
        observed[role] = {"reference": value["reference"], "image_id": image.id,
            "platform": "linux/amd64", "user": value["user"]}
    assert observed["hello_a"]["image_id"] != observed["hello_b"]["image_id"]
    return observed


async def scenario(root, engine, sdk, placement, material, provider, database_url):
    workspace = material.workspace_id
    runtime = RecordedDockerRuntime(DockerRuntimeInterpreter(sdk,
        authorized_secret_resolver=provider.composition.authorized_resolver), resources=placement)
    ingress = SyntheticIngressAllocation(provider.composition.secret_custodian, workspace)
    native = SyntheticConnectorConnection(placement, ingress, material)
    registered_authority = None

    def check_target(target_id, raw):
        name = "gateway" if target_id == "self" else target_id
        if name not in material.configurations:
            raise FixtureBoundaryFailure("unselected signed relay target")
        request = core.ReceiverHealthReadRequestCodec().decode(raw)
        configured = material.configurations[name]
        if request.target != configured.target or request.declaration_identity != configured.declaration.identity():
            raise FixtureBoundaryFailure("signed receiver context differs")
        return raw

    def endpoint_for(raw):
        request = core.ReceiverHealthReadRequestCodec().decode(raw)
        selected = placement.reader.read(workspace_id=workspace, runtime_id="docker",
            authority=registered_authority, gateway_node_id="gateway", socket_name="control", port=8000,
            graph_id=request.authority_context.authored_graph_id)
        return selected.endpoint.address.value

    public = SignedGatewayHealthClient(clock=lambda: int(time.time()),
        public_resolver=SyntheticIngressAddressResolver("cpk-1912.example.invalid"),
        transport=InstalledGatewaySocketTransport("cpk-1912.example.invalid", check_target, endpoint_for))
    health = ManagedHealthBootstrap((material.documents["gateway"],), placement.reader,
        native=native, public_client=public).build(provider.composition.authorized_resolver)
    with IsolatedOperationsSchema(database_url, "cpk_1912_image_" + uuid4().hex) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: runtime},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders,
                DockerRuntimeEffectObserver(sdk, authorized_secret_resolver=provider.composition.authorized_resolver)),
            id_factory=lambda: "image-" + uuid4().hex)
        bootstrap = PublicOperationsDriver(factory, workspace_id=workspace)
        await bootstrap.create_workspace()
        with ControllerHost(factory, bootstrap, root / "controller") as host:
            transport = AttachedPublicTransport(PublicHttpTransport(host.profile), runtime, placement,
                bootstrap.worker.identity.subject_id)
            registration = PublicRegistration(transport, workspace)
            admitted = await register_material(registration, SimpleNamespace(workspace_id=workspace,
                documents={name: material.documents[name] for name in ("gateway", "api", "connector")},
                public=material.public))
            row = admitted["runtime"]
            registered_authority = RegisteredRuntimeAuthority(row["registration_id"], workspace,
                RuntimeAuthorityReference(row["authority_ref"]), RuntimeKind.DOCKER,
                LocalDockerSocketAuthority(), row["admitted_by"], row["admitted_at"])
            assert registered_authority.descriptor() == row
            for name, document in (("peer", material.documents["api-y"]), ("successor", material.successor)):
                result = await registration.register("command.product.import", {
                    "descriptor_document": json.loads(document.content), "imported_at": utc_now(),
                    "idempotency_key": "image-import-" + name})
                assert result["status"] == "active"
            await register_surface_verifier(transport, material, workspace_id=workspace)
            await asyncio.to_thread(provider.seed, material)
            baseline = await select_pending_baseline(transport, material, workspace_id=workspace,
                scopes=(ReceiverScope("gateway", "control"), ReceiverScope("api", "internal"),
                    ReceiverScope("api-y", "internal")))
            client = TopologyClient(host.profile, transport=transport)

            async def read(route, **coordinates):
                return await asyncio.to_thread(transport.call, route,
                    path_parameters={"workspace_id": workspace, **coordinates}, payload={}, credential_role="operator")

            async def history(result):
                plan = await read("read.plan-detail", plan_id=result.plan_id)
                events = await asyncio.to_thread(public_page, transport, "read.run-events", workspace,
                    run_id=result.run_id)
                runs = await asyncio.to_thread(public_page, transport, "read.plan-runs", workspace,
                    plan_id=result.plan_id)
                return plan, events, runs

            async def apply(graph, name, *, pending=None):
                source = root / (name + ".json")
                source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(graph)), encoding="utf-8")
                planned = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(source, pending=pending))
                assert planned.status in {"planned", "no-changes"}, planned.descriptor()
                option = "approve_destructive_plan" if planned.destructive else "approve_plan"
                try:
                    result = await asyncio.to_thread(client.apply, planned.operation_ref,
                        execute_plan=planned.plan_id, **{option: planned.plan_id})
                except Exception:
                    emit_failed_apply_evidence(transport, workspace, None)
                    raise
                if result.status not in {"converged", "no-changes"} or transport.failure is not None:
                    await asyncio.to_thread(emit_failed_apply_evidence, transport, workspace, result)
                transport.require_healthy()
                assert result.status in {"converged", "no-changes"}, result.descriptor()
                return result, source

            initial, initial_source = await apply(material.a, "initial", pending=baseline)
            original_history = await history(initial)
            original_receivers = (await read("read.receiver-authoring-context"))["current"]
            initial_nodes = dict(placement.nodes)
            assert set(initial_nodes) == {"gateway", "api", "api-y", "connector"}
            for name in initial_nodes:
                placement.inspect_node(name)
            prepared = client.journal.read(initial.operation_ref)
            authored = DEFAULT_GRAPH_CODEC.decode(json.loads((client.journal.root /
                prepared["preparation"]["name"]).read_bytes()))

            def installed_configuration(name):
                container = engine.containers.get(placement.nodes[name])
                mounts = {item["Destination"]: item for item in container.attrs["Mounts"]}
                observed = {}
                for artifact in authored.node(name).configuration_artifacts:
                    mount = mounts[artifact.target_path]
                    assert mount["Type"] == "volume" and mount["RW"] is False
                    digest = sdk.configuration_artifact_digest(mount["Name"])
                    assert digest == artifact.content_digest
                    observed[artifact.artifact_id] = digest
                return observed

            initial_configuration = {name: installed_configuration(name) for name in initial_nodes}

            async def business(name):
                inspected = placement.inspect_node(name,
                    image_role="hello_b" if name == "api" and placement.nodes[name] != initial_nodes[name] else None)
                member, = [value for value in inspected.network_attachments if value.network_id == placement.network_id]
                async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
                    async with socket.stream("GET", "http://" + member.private_address + ":8000/") as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            assert len(body) + len(chunk) <= 65536
                            body.extend(chunk)
                        assert response.status_code == 200
                        return bytes(body)

            attribution = b"Served by Control Plane Kit Hello."
            assert attribution not in await business("api")
            peer_body = await business("api-y")
            replacement_graph = authored.update_node(replace(authored.node("api"),
                metadata=selected_metadata(material.successor)))
            before = len(runtime.completed)
            updated, updated_source = await apply(replacement_graph, "successor")
            replacements = [value for value in runtime.completed[before:]
                if type(value.request.operation).__name__ == "ReconcileNode"]
            assert len(replacements) == 1 and replacements[0].request.operation.target.node_id == "api"
            replaced = engine.containers.get(replacements[0].result.evidence["container"])
            assert placement.nodes["api"] == replaced.id
            placement.inspect_node("api", image_role="hello_b")
            assert replaced.id != initial_nodes["api"]
            assert not engine.containers.list(all=True, filters={"id": initial_nodes["api"]})
            assert attribution in await business("api")
            assert await business("api-y") == peer_body
            assert all(placement.nodes[name] == initial_nodes[name] for name in ("gateway", "api-y", "connector"))
            # Payload continuity does not require reusing physical volume identities.
            assert {name: installed_configuration(name) for name in initial_nodes} == initial_configuration
            current_receivers = (await read("read.receiver-authoring-context"))["current"]
            expected = [{**row, "binding": {**row["binding"], "graph_id": current_receivers["graph_id"],
                "realized_projection_id": current_receivers["realized_projection_id"]}}
                for row in original_receivers["receivers"]]
            assert current_receivers["receivers"] == expected
            assert await history(initial) == original_history
            update_history = await history(updated)
            replacement = replacements[0]
            assert replacement.request.source.run_id.value == updated.run_id
            receipt = require_replacement_receipt(replacement, initial_nodes["api"], replaced.id)
            arguments, response = transport.committed[replacement.request.effect_id]
            require_committed_call(replacement, response, arguments, update_history[1],
                bootstrap.worker.identity.subject_id)
            def no_identity():
                raise FixtureBoundaryFailure("retained operation regenerated receiver identity")
            restarted = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_identity)
            effect_count = len(runtime.completed)
            for label, result, expected in (
                    ("historical-initial", initial, ("attention-required", "succeeded", "unverified")),
                    ("current-update", updated, ("converged", "succeeded", "advanced"))):
                replay = await asyncio.to_thread(restarted.apply, result.operation_ref, execute_plan=result.plan_id)
                actual = (replay.status, replay.execution, replay.advancement)
                identity = (replay.operation_ref, replay.plan_id, replay.run_id)
                if actual != expected or identity != (result.operation_ref, result.plan_id, result.run_id):
                    await asyncio.to_thread(emit_failed_apply_evidence, transport, workspace, replay)
                transport.require_healthy()
                assert actual == expected, replay.descriptor()
                assert identity == (result.operation_ref, result.plan_id, result.run_id), replay.descriptor()
                assert len(runtime.completed) == effect_count
                print(json.dumps({"docker_image_replay": label, "status": replay.status,
                    "execution": replay.execution, "advancement": replay.advancement}), flush=True)
            assert await history(initial) == original_history and await history(updated) == update_history
            noop = await asyncio.to_thread(restarted.plan, AuthoredDesiredGraph(updated_source))
            assert noop.status == "no-changes"
            no_execution = await asyncio.to_thread(restarted.apply, noop.operation_ref, execute_plan=noop.plan_id)
            assert no_execution.status == "no-changes"
            assert len(runtime.completed) == effect_count
            assert await history(initial) == original_history and await history(updated) == update_history
            assert native.reads and len(ingress.allocations) == 1
            placement.detach()
            await apply(DeploymentGraph("image-teardown"), "teardown")
            containers, networks, volumes = owned_resources(engine, workspace)
            assert not containers and not networks and not ingress.allocations
            print(json.dumps({"docker_public_image_update": "passed", "workspace": workspace,
                "initial_run": initial.run_id, "replacement_run": updated.run_id,
                "old_container": initial_nodes["api"], "new_container": replaced.id,
                "peer_container": initial_nodes["api-y"], "native": "synthetic",
                "replacement_receipt": receipt.disposition.value,
                "ingress": "synthetic", "historical_configuration_volumes": len(volumes)}), flush=True)


async def witness():
    verify_provenance()
    config = Path(os.environ["DOCKER_CONFIG"])
    config.mkdir(mode=0o700)
    (config / "config.json").write_text("{}", encoding="ascii")
    (config / "config.json").chmod(0o600)
    engine = docker.from_env()
    sdk = DockerSdkClient(client=engine, configuration_helper_image=os.environ["CPK_FROZEN_CONTROLLER_IMAGE"])
    daemon_id = os.environ["CPK_DOCKER_WITNESS_DAEMON"]
    assert engine.info().get("ID") == daemon_id
    controller = engine.containers.get(os.environ["CPK_DOCKER_WITNESS_NAME"])
    assert controller.attrs["Image"] == os.environ["CPK_FROZEN_CONTROLLER_IMAGE"]
    assert controller.labels["org.openj92.cpk.test-run"] == os.environ["CPK_DOCKER_WITNESS_RUN"]
    images = inspect_inputs(engine, sdk)
    workspace = "image-" + uuid4().hex
    assert not any(owned_resources(engine, workspace))
    records = Path(os.environ["CPK_DOCKER_WITNESS_RECORDS"])
    ownership = records / "ownership.json"
    assert not ownership.exists()
    placement = OwnedControllerPlacement(engine, sdk, workspace, controller.id, daemon_id,
        record_path=ownership, run=os.environ["CPK_DOCKER_WITNESS_RUN"])
    print(json.dumps({"docker_image_inputs": images, "daemon_id": daemon_id,
        "controller_id": controller.id, "owned_workspace": workspace}), flush=True)
    database_url = os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"]
    try:
        with tempfile.TemporaryDirectory(prefix="cpk-image-") as directory:
            root = Path(directory)
            material = DockerImageMaterial(workspace)
            with SigningProviderProcess(root / "provider", workspace, database_url) as provider:
                await scenario(root, engine, sdk, placement, material, provider, database_url)
    finally:
        dispose_fixture(placement)
        (records / "managed-resources-absent").write_text("verified\n", encoding="ascii")
        engine.close()


if __name__ == "__main__":
    asyncio.run(witness())
