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
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import AuthoredDesiredGraph, ReceiverScope
from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport
from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap

from docker_image_update_material import DockerImageMaterial, IMAGES
from docker_image_update_placement import (
    OwnedControllerPlacement, SyntheticConnectorConnection, owned_resources, dispose_fixture,
)
from docker_image_update_ports import (
    AttachedPublicTransport, RecordedDockerRuntime, FixtureBoundaryFailure, public_page,
    SyntheticIngressAddressResolver, InstalledGatewaySocketTransport,
    require_committed_call, require_replacement_receipt, emit_failed_apply_evidence,
)
from docker_image_update_provider import SigningProviderProcess, SyntheticIngressAllocation
from docker_image_update_selection import (
    PublicSecretChoices, ObservedMetadataReader, consumer_graph, application_content_graph,
    require_selected_recipient,
)
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
    metadata = ObservedMetadataReader(provider.composition.metadata_reader)
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

    health_socket = InstalledGatewaySocketTransport("cpk-1912.example.invalid", check_target, endpoint_for)
    public = SignedGatewayHealthClient(clock=lambda: int(time.time()),
        public_resolver=SyntheticIngressAddressResolver("cpk-1912.example.invalid"),
        transport=health_socket)
    health = ManagedHealthBootstrap((material.documents["gateway"],), placement.reader,
        native=native, public_client=public).build(provider.composition.authorized_resolver)
    with IsolatedOperationsSchema(database_url, "cpk_1912_image_" + uuid4().hex) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: RuntimeAdapterRegistration(runtime,
                exact_version_execute=True, exact_version_execute_with_authority=True)},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders,
                DockerRuntimeEffectObserver(sdk, authorized_secret_resolver=provider.composition.authorized_resolver),
                secret_metadata_reader=metadata),
            id_factory=lambda: "image-" + uuid4().hex)
        bootstrap = PublicOperationsDriver(factory, workspace_id=workspace)
        await bootstrap.create_workspace()
        with ControllerHost(factory, bootstrap, root / "controller") as host:
            transport = AttachedPublicTransport(PublicHttpTransport(host.profile), runtime, placement,
                bootstrap.worker.identity.subject_id)
            registration = PublicRegistration(transport, workspace)
            admitted = await register_material(registration, SimpleNamespace(workspace_id=workspace,
                documents={name: material.documents[name] for name in ("gateway", "api", "connector")},
                public={name: material.public[name] for name in ("transit", "workload")}))
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
            versions = await asyncio.to_thread(provider.seed_application_versions)
            choices = PublicSecretChoices(transport, workspace, runtime, metadata)
            await choices.register()
            baseline = await select_pending_baseline(transport, material, workspace_id=workspace,
                scopes=(ReceiverScope("gateway", "control"), ReceiverScope("api", "internal"),
                    ReceiverScope("api-y", "internal")))
            initial_graph, baseline = await choices.selected_baseline(material.a, versions[0].version_id, baseline)
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

            async def apply(graph, name, *, pending=None, refreshes=()):
                source = root / (name + ".json")
                source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(graph)), encoding="utf-8")
                planned = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(source,
                    pending=pending, verifier_refreshes=refreshes))
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

            initial, initial_source = await apply(initial_graph, "initial", pending=baseline)
            original_history = await history(initial)
            original_receivers = (await read("read.receiver-authoring-context"))["current"]
            initial_nodes = dict(placement.nodes)
            assert set(initial_nodes) == {"gateway", "api", "api-y", "connector"}
            for name in initial_nodes:
                placement.inspect_node(name)
            prepared = client.journal.read(initial.operation_ref)
            authored = DEFAULT_GRAPH_CODEC.decode(json.loads((client.journal.root /
                prepared["preparation"]["name"]).read_bytes()))
            assert authored.node("api").secret_selections == initial_graph.node("api").secret_selections
            started, = [value for value in runtime.completed
                if type(value.request.operation).__name__ == "StartNode"
                and value.request.operation.target.node_id == "api"]
            require_selected_recipient(started, versions[0].version_id, None, initial_nodes["api"])
            arguments, response = transport.committed[started.request.effect_id]
            require_committed_call(started, response, arguments, original_history[1],
                bootstrap.worker.identity.subject_id)

            def installed_configuration(name, graph=None):
                container = engine.containers.get(placement.nodes[name])
                mounts = {item["Destination"]: item for item in container.attrs["Mounts"]}
                observed = {}
                for artifact in (graph or authored).node(name).configuration_artifacts:
                    mount = mounts[artifact.target_path]
                    assert mount["Type"] == "volume" and mount["RW"] is False
                    digest = sdk.configuration_artifact_digest(mount["Name"])
                    assert digest == artifact.content_digest
                    observed[artifact.artifact_id] = digest
                return observed

            initial_configuration = {name: installed_configuration(name) for name in initial_nodes}

            for unavailable in ("missing-version", versions[2].version_id):
                await choices.select(authored, unavailable, refused=True)

            async def business(name, *, image_role=None):
                inspected = placement.inspect_node(name, image_role=image_role)
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
            selected_runs = []
            for label in ("version-only", "image-only", "content-only", "verifier-only"):
                refreshes = ()
                if label == "version-only":
                    replacement_graph = await choices.select(authored, versions[1].version_id)
                elif label == "image-only":
                    replacement_graph = consumer_graph(authored, material.successor)
                elif label == "content-only":
                    replacement_graph = application_content_graph(authored)
                else:
                    # Distinct isolated overlap custody; the original signer stays ACTIVE.
                    original_keys = await asyncio.to_thread(public_page, transport,
                        "read.delegation-keys", workspace)
                    overlap_reference = "secret://health-secrets/keys/workload-overlap"
                    reference = await registration.register("command.secret-reference.register", {
                        "reference": overlap_reference,
                        "provider_registration_id": admitted["providers"]["health"]["registration_id"],
                        "allowed_intents": ["workload.node-health-read-signing-key"],
                        "admitted_at": utc_now(), "metadata": {"acceptance": "receiver-refresh-253"},
                        "idempotency_key": "image-overlap-reference"})
                    assert reference["status"] == "active" and reference["reference_id"] == overlap_reference
                    assert reference["allowed_intents"] == ["workload.node-health-read-signing-key"]
                    overlap = await registration.register("command.delegation-key.register", {
                        "purpose": "workload-node-health-read", "issuer": "cpk-server",
                        "key_id": "health-workload-overlap", "algorithm": "ed25519",
                        "public_key_pem": material.public["workload-overlap"].public_key_pem,
                        "private_key_reference": overlap_reference,
                        "admitted_at": utc_now(), "idempotency_key": "image-verifier-overlap"})
                    assert overlap["status"] == "verify-only"
                    refreshed_keys = await asyncio.to_thread(public_page, transport,
                        "read.delegation-keys", workspace)
                    assert [row for row in refreshed_keys if row["key_id"] != "health-workload-overlap"] == original_keys
                    active, = [row for row in refreshed_keys if row["key_id"] == "health-workload"]
                    assert active["status"] == "active"
                    verifier_snapshot = await read("read.workload-verifier-configuration", purposes=",".join((
                        core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ.value,
                        core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ.value)))
                    assert verifier_snapshot["workspace_id"] == workspace
                    assert verifier_snapshot["kind"] == "workload-verifier-configuration"
                    unchanged_source = root / "ordinary-after-overlap.json"
                    unchanged_source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(authored)), encoding="utf-8")
                    unchanged = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(unchanged_source))
                    assert unchanged.status == "no-changes"
                    replacement_graph = authored
                    refreshes = (ReceiverScope("api", "internal"),)
                prior = placement.nodes["api"]
                before = len(runtime.completed)
                before_health = len(health_socket.observations)
                updated, updated_source = await apply(replacement_graph, label, refreshes=refreshes)
                prepared = client.journal.read(updated.operation_ref)
                journaled = DEFAULT_GRAPH_CODEC.decode(json.loads((client.journal.root /
                    prepared["preparation"]["name"]).read_bytes()))
                changed_wrapper = None
                if refreshes:
                    prior_row, = [row for row in original_receivers["receivers"]
                        if row["binding"]["node_id"] == "api"]
                    wrapper_id = prior_row["configuration_artifact"]["artifact_id"]
                    old_wrapper, = [value for value in authored.node("api").configuration_artifacts
                        if value.artifact_id == wrapper_id]
                    changed_wrapper, = [value for value in journaled.node("api").configuration_artifacts
                        if value.artifact_id == wrapper_id]
                    codec = core.ReceiverNodeControlConfigurationCodec()
                    old_configuration = codec.decode_bytes(old_wrapper.content.encode("utf-8"))
                    new_configuration = codec.decode_bytes(changed_wrapper.content.encode("utf-8"))
                    expected_wrapper = codec.decode({**codec.encode(old_configuration),
                        "verifiers": verifier_snapshot["workload_verifier_configuration"]["verifiers"]})
                    assert new_configuration == expected_wrapper
                    assert new_configuration.target == old_configuration.target
                    assert new_configuration.declaration == old_configuration.declaration
                    assert changed_wrapper.content_digest != old_wrapper.content_digest
                    assert replace(changed_wrapper, content=old_wrapper.content,
                        source_digest=old_wrapper.source_digest) == old_wrapper
                    old_families = {value.purpose: value for value in old_configuration.verifiers}
                    assert {value.purpose for value in new_configuration.verifiers} == set(old_families)
                    for family in new_configuration.verifiers:
                        previous = old_families[family.purpose]
                        if family.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ:
                            assert family.issuer == previous.issuer
                            assert {key.key_id for key in family.public_keys} == {
                                "health-workload", "health-workload-overlap"}
                            assert set(family.public_keys) == {
                                material.public["workload"], material.public["workload-overlap"]}
                        else:
                            assert family.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ
                            assert tuple(key.key_id for key in family.public_keys) == ("unlisted-surface",)
                            assert family != previous
                    restored = replace(journaled.node("api"), configuration_artifacts=tuple(
                        old_wrapper if value.artifact_id == wrapper_id else value
                        for value in journaled.node("api").configuration_artifacts))
                    assert replace(journaled, nodes={**journaled.nodes, "api": restored}) == authored
                else:
                    assert journaled == replacement_graph
                replacements = [value for value in runtime.completed[before:]
                    if type(value.request.operation).__name__ == "ReconcileNode"]
                assert len(replacements) == 1 and replacements[0].request.operation.target.node_id == "api"
                replacement = replacements[0]
                replaced = engine.containers.get(replacement.result.evidence["container"])
                assert placement.nodes["api"] == replaced.id and replaced.id != prior
                assert not engine.containers.list(all=True, filters={"id": prior})
                role = "hello_a" if label == "version-only" else "hello_b"
                assert (attribution in await business("api", image_role=role)) == (role == "hello_b")
                assert await business("api-y") == peer_body
                assert all(placement.nodes[name] == initial_nodes[name] for name in ("gateway", "api-y", "connector"))
                revised_configuration = {name: installed_configuration(name, journaled)
                    for name in initial_nodes}
                for name in initial_nodes:
                    expected_configuration = dict(initial_configuration[name])
                    if label == "content-only" and name == "api":
                        artifact, = [value for value in replacement_graph.node(name).configuration_artifacts
                            if value.artifact_id == "application-settings"]
                        assert artifact.content_digest != expected_configuration[artifact.artifact_id]
                        expected_configuration[artifact.artifact_id] = artifact.content_digest
                    if changed_wrapper is not None and name == "api":
                        expected_configuration[changed_wrapper.artifact_id] = changed_wrapper.content_digest
                    assert revised_configuration[name] == expected_configuration
                initial_configuration = revised_configuration
                assert ("api", "readiness", 200) in health_socket.observations[before_health:]
                require_selected_recipient(replacement, versions[1].version_id, prior, replaced.id)
                receipt = require_replacement_receipt(replacement, prior, replaced.id)
                current_receivers = (await read("read.receiver-authoring-context"))["current"]
                expected = [{**row, "binding": {**row["binding"], "graph_id": current_receivers["graph_id"],
                    "realized_projection_id": current_receivers["realized_projection_id"]}}
                    for row in original_receivers["receivers"]]
                if changed_wrapper is not None:
                    selected, = [row for row in expected if row["binding"]["node_id"] == "api"]
                    selected["configuration_artifact"] = changed_wrapper.descriptor()
                    selected["binding"]["selected_configuration_digest"] = changed_wrapper.content_digest
                    assert await asyncio.to_thread(public_page, transport,
                        "read.delegation-keys", workspace) == refreshed_keys
                assert current_receivers["receivers"] == expected
                assert await history(initial) == original_history
                update_history = await history(updated)
                assert replacement.request.source.run_id.value == updated.run_id
                arguments, response = transport.committed[replacement.request.effect_id]
                require_committed_call(replacement, response, arguments, update_history[1],
                    bootstrap.worker.identity.subject_id)
                for historical, expected_history in selected_runs:
                    assert await history(historical) == expected_history
                selected_runs.append((updated, update_history))
                authored = journaled
                assert authored.node("api").secret_selections == replacement_graph.node("api").secret_selections
                print(json.dumps({"selected_consumer_update": label, "run_id": updated.run_id,
                    "receipt": receipt.disposition.value}), flush=True)
            def no_identity():
                raise FixtureBoundaryFailure("retained operation regenerated receiver identity")
            restarted = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_identity)
            effect_count = len(runtime.completed)
            dispatch_count = len(placement.record["intents"])
            same_client = await asyncio.to_thread(client.apply, updated.operation_ref, execute_plan=updated.plan_id)
            assert (same_client.status, same_client.operation_ref, same_client.plan_id, same_client.run_id) == (
                "converged", updated.operation_ref, updated.plan_id, updated.run_id)
            assert len(runtime.completed) == effect_count and len(placement.record["intents"]) == dispatch_count
            assert await history(updated) == update_history
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
                assert len(placement.record["intents"]) == dispatch_count
                print(json.dumps({"docker_image_replay": label, "status": replay.status,
                    "execution": replay.execution, "advancement": replay.advancement}), flush=True)
            assert await history(initial) == original_history and await history(updated) == update_history
            await choices.replay()
            for historical, expected_history in selected_runs[:-1]:
                replay = await asyncio.to_thread(restarted.apply, historical.operation_ref,
                    execute_plan=historical.plan_id)
                assert (replay.operation_ref, replay.plan_id, replay.run_id) == (
                    historical.operation_ref, historical.plan_id, historical.run_id)
                assert replay.execution == "succeeded" and replay.advancement == "unverified"
                assert await history(historical) == expected_history
                assert len(runtime.completed) == effect_count
                assert len(placement.record["intents"]) == dispatch_count
            noop = await asyncio.to_thread(restarted.plan, AuthoredDesiredGraph(updated_source))
            assert noop.status == "no-changes"
            refresh_noop = await asyncio.to_thread(restarted.plan, AuthoredDesiredGraph(updated_source,
                verifier_refreshes=(ReceiverScope("api", "internal"),)))
            assert refresh_noop.status == "no-changes"
            no_execution = await asyncio.to_thread(restarted.apply, noop.operation_ref, execute_plan=noop.plan_id)
            assert no_execution.status == "no-changes"
            assert len(runtime.completed) == effect_count
            assert len(placement.record["intents"]) == dispatch_count
            assert await history(initial) == original_history and await history(updated) == update_history
            assert native.reads and len(ingress.allocations) == 1
            placement.detach()
            await apply(DeploymentGraph("image-teardown"), "teardown")
            containers, networks, volumes = owned_resources(engine, workspace)
            assert not containers and not networks and not ingress.allocations
            print(json.dumps({"docker_public_image_update": "passed", "workspace": workspace,
                "selected_secret_version_only": "passed", "selected_secret_image_only": "passed",
                "selected_secret_content_only": "passed",
                "retained_receiver_verifier_only": "passed", "active_signer": "unchanged",
                "consumer_delivery": "environment", "unavailable_choices": "refused-before-dispatch",
                "initial_run": initial.run_id, "replacement_run": updated.run_id,
                "old_container": initial_nodes["api"], "new_container": replaced.id,
                "peer_container": initial_nodes["api-y"], "native": "synthetic",
                "replacement_receipt": receipt.disposition.value,
                "ingress": "synthetic",
                "historical_configuration_volumes": sum(volume.name in placement.record["volumes"] for volume in volumes),
                "secret_volumes": sum(volume.name in placement.record["secret_volumes"] for volume in volumes)}), flush=True)


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
