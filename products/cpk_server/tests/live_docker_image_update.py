"""#251 public-client Docker image replacement in the existing owning smoke.

Only ingress allocation/native connection/public routing are synthetic. Docker,
signing provider, SDK health sockets, operation history and business bodies run.
"""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

import docker
import httpx
import jwt
import control_plane_kit_core as core
from control_plane_kit_core.planning import ReconcileNode
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
from docker_image_update_identity import bind_fixed_images, fixed_manifest_bytes, qualify_fixed_image
from docker_declaration_update import declaration_documents, declaration_graph, current_route_intent
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
    daemon_id = engine.info().get("ID")
    for role, value in IMAGES.items():
        image = engine.images.get(value["reference"])
        selected = sdk.inspect_image(value["reference"])
        if selected is None or selected.image_id != image.id:
            raise ValueError("artifact interpreter observation differs")
        if not matches_image_reference(value["reference"], selected.repo_digests):
            raise ValueError("artifact interpreter reference differs")
        observed[role] = qualify_fixed_image(role, reference=value["reference"],
            manifest_bytes=fixed_manifest_bytes(role), image_attrs=image.attrs,
            interpreter_image_id=selected.image_id)
    assert observed["hello_a"].execution_id != observed["hello_b"].execution_id
    if engine.info().get("ID") != daemon_id:
        raise ValueError("artifact qualification daemon changed")
    return bind_fixed_images(daemon_id, observed)


async def scenario(root, engine, sdk, placement, material, provider, database_url, *, reintroduction=False):
    workspace = material.workspace_id
    runtime = RecordedDockerRuntime(DockerRuntimeInterpreter(sdk,
        authorized_secret_resolver=provider.composition.authorized_resolver), resources=placement)
    metadata = ObservedMetadataReader(provider.composition.metadata_reader)
    ingress = SyntheticIngressAllocation(provider.composition.secret_custodian, workspace)
    native = SyntheticConnectorConnection(placement, ingress, material)
    registered_authority = None
    authored_configurations = {name: [value] for name, value in material.configurations.items()}
    health_requests = {}

    def check_target(target_id, raw):
        name = "gateway" if target_id == "self" else target_id
        if name not in material.configurations:
            raise FixtureBoundaryFailure("unselected signed relay target")
        request = core.ReceiverHealthReadRequestCodec().decode(raw)
        if not any(request.target == configured.target
                and request.declaration_identity == configured.declaration.identity()
                for configured in authored_configurations[name]):
            raise FixtureBoundaryFailure("signed receiver context differs")
        health_requests[target_id, request.declaration_identity.value] = request
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
            additional_products = () if reintroduction else (
                ("peer", material.documents["api-y"]), ("successor", material.successor))
            for name, document in additional_products:
                result = await registration.register("command.product.import", {
                    "descriptor_document": json.loads(document.content), "imported_at": utc_now(),
                    "idempotency_key": "image-import-" + name})
                assert result["status"] == "active"
            await register_surface_verifier(transport, material, workspace_id=workspace)
            await asyncio.to_thread(provider.seed, material)
            if not reintroduction:
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

            async def apply(graph, name, *, pending=None, refreshes=(), declarations=(), routes=(),
                            introductions=(), prepared_observer=None):
                source = root / (name + ".json")
                source.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(graph)), encoding="utf-8")
                before_prepares = len(host.prepare_exchanges)
                planned = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(source,
                    pending=pending, verifier_refreshes=refreshes, declaration_updates=declarations,
                    introductions=introductions,
                    gateway_health_replacements=routes))
                if reintroduction and planned.status not in {"planned", "no-changes"}:
                    exchanges = host.prepare_exchanges[before_prepares:]
                    diagnostic = {"docker_reintroduction_prepare_failure": name}
                    if len(exchanges) == 1:
                        exchange = exchanges[0]
                        error = exchange.response_body.get("error", {})
                        message = error.get("message") if isinstance(error, dict) else None
                        categories = {"deployment preparation request is malformed": "request-malformed",
                            "deployment preparation state is unavailable": "state-conflict"}
                        diagnostic.update(http_status=exchange.response_status,
                            category=categories.get(message, "unclassified") if isinstance(message, str) else "unclassified",
                            request_sha256=hashlib.sha256(exchange.request_body).hexdigest())
                    else:
                        diagnostic["exchange"] = "none" if not exchanges else "multiple"
                    print(json.dumps(diagnostic), flush=True)
                assert planned.status in {"planned", "no-changes"}, planned.descriptor()
                if prepared_observer is not None:
                    journal = client.journal.read(planned.operation_ref)
                    prepared_graph = DEFAULT_GRAPH_CODEC.decode(json.loads(client.journal.read_preparation(
                        planned.operation_ref, journal["preparation"])))
                    prepared_observer(planned, prepared_graph)
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

            if reintroduction:
                from live_docker_receiver_reintroduction import reintroduction_scenario
                await reintroduction_scenario(root, engine, sdk, placement, material, host, transport,
                    client, runtime, ingress, health_socket, authored_configurations, apply, read, history,
                    bootstrap.worker.identity.subject_id)
                return

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

            # All four original families/replay/no-op laws above retain their
            # original meaning. The coupled proof starts from that retained state.
            client = restarted
            retained_history = [(initial, original_history), *selected_runs]
            retained_keys = await asyncio.to_thread(public_page, transport, "read.delegation-keys", workspace)
            both_document, ready_document = declaration_documents(material, IMAGES["hello_family"]["reference"])
            for name, document in (("both", both_document), ("readiness", ready_document)):
                registered = await registration.register("command.product.import", {
                    "descriptor_document": json.loads(document.content), "imported_at": utc_now(),
                    "idempotency_key": "declaration-import-" + name})
                assert registered["status"] == "active"

            # An ordinary planned image replacement selects the qualified family
            # image; it is not adoption of an externally created resource.
            prior_nodes = dict(placement.nodes)
            before = len(runtime.completed)
            adopted, _ = await apply(consumer_graph(authored, both_document), "family-image")
            journal = client.journal.read(adopted.operation_ref)
            family_graph = DEFAULT_GRAPH_CODEC.decode(json.loads(client.journal.read_preparation(
                adopted.operation_ref, journal["preparation"])))
            assert family_graph == consumer_graph(authored, both_document)
            image_replacement, = [value for value in runtime.completed[before:]
                if type(value.request.operation) is ReconcileNode]
            assert image_replacement.request.operation.target.node_id == "api"
            assert all(placement.nodes[name] == prior_nodes[name] for name in ("gateway", "api-y", "connector"))
            require_selected_recipient(image_replacement, versions[1].version_id,
                prior_nodes["api"], placement.nodes["api"])
            require_replacement_receipt(image_replacement, prior_nodes["api"], placement.nodes["api"])
            assert attribution in await business("api", image_role="hello_family")
            assert {name: installed_configuration(name, family_graph) for name in initial_nodes} == initial_configuration
            family_history = await history(adopted)
            assert image_replacement.request.source.run_id.value == adopted.run_id
            arguments, response = transport.committed[image_replacement.request.effect_id]
            require_committed_call(image_replacement, response, arguments, family_history[1],
                bootstrap.worker.identity.subject_id)
            retained_history.append((adopted, family_history))

            scope = ReceiverScope("api", "internal")
            route_intent = current_route_intent(family_graph)
            codec = core.ReceiverNodeControlConfigurationCodec()
            def artifact(graph, name, identity):
                selected, = [value for value in graph.node(name).configuration_artifacts
                    if value.artifact_id == identity]
                return selected

            old_wrapper = artifact(family_graph, "api", "hello-control")
            old_configuration = codec.decode_bytes(old_wrapper.content.encode())
            old_routes_artifact = artifact(family_graph, "gateway", "gateway-health-targets")
            route_codec = core.ReceiverManagementRoutesCodec()
            old_routes = route_codec.decode_bytes(old_routes_artifact.content.encode())
            cutover_nodes = dict(placement.nodes)
            cutover_before = len(runtime.completed)
            cutover_health_before = len(health_socket.observations)
            old_workspace = (await read("read.workspace"))["workspace"]
            retained_receivers = (await read("read.receiver-authoring-context"))["current"]
            selected_cutover, intermediate = {}, []

            def prepared_cutover(planned, graph):
                selected_cutover.update(plan_id=planned.plan_id, graph=graph)
                selected = codec.decode_bytes(artifact(graph, "api", "hello-control").content.encode())
                assert replace(selected, declaration=old_configuration.declaration) == old_configuration
                assert selected.declaration.surface.health_reads == (core.NodeHealthReadKind.READINESS,)
                # Expectations come from the client's immutable authored artifact,
                # never from changing the fixture's initial configuration in place.
                authored_configurations["api"].append(selected)

            def observe_cutover(record, response):
                if type(record.request.operation) is not ReconcileNode:
                    return
                assert record.request.source.workspace_id == workspace
                assert record.request.source.plan_id == selected_cutover["plan_id"]
                node = record.request.operation.target.node_id
                assert node in {"api", "gateway"}
                records = [value for value in runtime.completed[cutover_before:]
                    if type(value.request.operation) is ReconcileNode]
                assert [value.request.operation.target.node_id for value in records] == (
                    ["api"] if node == "api" else ["api", "gateway"])
                if node != "api":
                    return
                assert len(intermediate) == 0
                assert placement.nodes["api"] != cutover_nodes["api"]
                assert all(placement.nodes[name] == cutover_nodes[name]
                    for name in ("gateway", "api-y", "connector"))
                api_digests = installed_configuration("api", selected_cutover["graph"])
                gateway_digests = installed_configuration("gateway", family_graph)
                assert gateway_digests == initial_configuration["gateway"]
                events = public_page(transport.inner, "read.run-events", workspace,
                    run_id=record.request.source.run_id.value)
                arguments, committed_response = transport.committed[record.request.effect_id]
                assert committed_response is response
                require_committed_call(record, response, arguments, events, bootstrap.worker.identity.subject_id)
                current = transport.inner.call("read.workspace", path_parameters={"workspace_id": workspace},
                    payload={}, credential_role="operator")["workspace"]
                assert current["current_graph_id"] == old_workspace["current_graph_id"]
                intermediate.append({"run_id": record.request.source.run_id.value,
                    "effect_id": record.request.effect_id, "activity_id": record.request.activity_id.value,
                    "api_container": placement.nodes["api"], "gateway_container": placement.nodes["gateway"],
                    "api_configuration_digests": api_digests, "gateway_configuration_digests": gateway_digests})

            transport.committed_observer = observe_cutover
            try:
                cutover, cutover_source = await apply(declaration_graph(family_graph, ready_document),
                    "declaration-cutover", declarations=(scope,), routes=(route_intent,),
                    prepared_observer=prepared_cutover)
            finally:
                transport.committed_observer = None
            final_graph = selected_cutover["graph"]
            cutover_history = await history(cutover)
            assert len(intermediate) == 1 and intermediate[0]["run_id"] == cutover.run_id
            coupled = [value for value in runtime.completed[cutover_before:]
                if type(value.request.operation) is ReconcileNode]
            assert [value.request.operation.target.node_id for value in coupled] == ["api", "gateway"]
            receipts = []
            for record in coupled:
                name = record.request.operation.target.node_id
                assert record.request.source.run_id.value == cutover.run_id
                assert placement.nodes[name] != cutover_nodes[name]
                assert not engine.containers.list(all=True, filters={"id": cutover_nodes[name]})
                receipts.append(require_replacement_receipt(record, cutover_nodes[name], placement.nodes[name]))
                arguments, response = transport.committed[record.request.effect_id]
                require_committed_call(record, response, arguments, cutover_history[1],
                    bootstrap.worker.identity.subject_id)
            assert coupled[0].request.effect_id != coupled[1].request.effect_id
            require_selected_recipient(coupled[0], versions[1].version_id,
                cutover_nodes["api"], placement.nodes["api"])
            assert family_graph.node("api").metadata["oci_image"] == final_graph.node("api").metadata["oci_image"]
            assert attribution in await business("api", image_role="hello_family")
            assert await business("api-y") == peer_body
            assert all(placement.nodes[name] == cutover_nodes[name] for name in ("api-y", "connector"))
            new_wrapper = artifact(final_graph, "api", "hello-control")
            new_configuration = codec.decode_bytes(new_wrapper.content.encode())
            assert replace(new_configuration, declaration=old_configuration.declaration) == old_configuration
            assert new_wrapper.content_digest != old_wrapper.content_digest
            new_routes_artifact = artifact(final_graph, "gateway", "gateway-health-targets")
            new_routes = route_codec.decode_bytes(new_routes_artifact.content.encode())
            assert new_routes_artifact.content_digest != old_routes_artifact.content_digest
            assert replace(new_routes, targets=tuple(replace(value, declaration=old_configuration.declaration)
                if value.target == old_configuration.target else value for value in new_routes.targets)) == old_routes
            restored = {**final_graph.nodes,
                "api": replace(final_graph.node("api"), block_spec=family_graph.node("api").block_spec,
                    metadata=family_graph.node("api").metadata,
                    configuration_artifacts=family_graph.node("api").configuration_artifacts),
                "gateway": replace(final_graph.node("gateway"),
                    configuration_artifacts=family_graph.node("gateway").configuration_artifacts)}
            assert replace(final_graph, nodes=restored) == family_graph
            for name in initial_nodes:
                expected = dict(initial_configuration[name])
                if name == "api":
                    expected[new_wrapper.artifact_id] = new_wrapper.content_digest
                elif name == "gateway":
                    expected[new_routes_artifact.artifact_id] = new_routes_artifact.content_digest
                assert installed_configuration(name, final_graph) == expected
            assert await asyncio.to_thread(public_page, transport, "read.delegation-keys", workspace) == retained_keys
            current_receivers = (await read("read.receiver-authoring-context"))["current"]
            expected_receivers = [{**row, "binding": {**row["binding"],
                "graph_id": current_receivers["graph_id"],
                "realized_projection_id": current_receivers["realized_projection_id"]}}
                for row in retained_receivers["receivers"]]
            selected, = [row for row in expected_receivers if row["binding"]["node_id"] == "api"]
            selected["binding"]["declaration_identity"] = new_configuration.declaration.identity().value
            selected["binding"]["selected_configuration_digest"] = new_wrapper.content_digest
            selected["configuration_artifact"] = new_wrapper.descriptor()
            assert current_receivers["receivers"] == expected_receivers
            assert ("api", "readiness", 200) in health_socket.observations[cutover_health_before:]

            # Read-only SDK refusal check with the same active fixture signing
            # key and an actual public request's authority context. No CPK effect
            # or durable state is fabricated by these supplemental socket reads.
            current_request = health_requests["api", new_configuration.declaration.identity().value]
            assert current_request.target == new_configuration.target
            assert current_request.kind is core.NodeHealthReadKind.READINESS
            family, = [value for value in new_configuration.verifiers
                if value.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ]
            assert material.public["workload"] in family.public_keys
            inspected = placement.inspect_node("api", image_role="hello_family")
            member, = [value for value in inspected.network_attachments if value.network_id == placement.network_id]
            async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
                for declaration, expected_status in ((old_configuration.declaration, 401),
                        (new_configuration.declaration, 200)):
                    request = replace(current_request, declaration_identity=declaration.identity(),
                        request_id="declaration-check-" + uuid4().hex)
                    now = int(time.time())
                    grant = core.DelegatedWorkloadReceiverHealthReadGrant(
                        profile=core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2,
                        canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
                        purpose=family.purpose, issuer=family.issuer, key_id=material.public["workload"].key_id,
                        audience=core.receiver_node_control_audience(request.target), target=request.target,
                        kind=request.kind, declaration_identity=request.declaration_identity,
                        request_id=request.request_id, request_digest=request.canonical_digest(),
                        issued_at=now - 1, not_before=now - 1, expires_at=now + 60,
                        jti="declaration-check-" + uuid4().hex, authority_context=request.authority_context)
                    token = jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at,
                        nbf=grant.not_before, exp=grant.expires_at, jti=grant.jti,
                        workload_node_health_read=grant.descriptor()), material.private["workload"],
                        algorithm="EdDSA", headers={"kid": grant.key_id, "typ": "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"})
                    async with socket.stream("GET", "http://" + member.private_address +
                            ":8000/__control/health/readiness", headers={"Authorization": "Bearer " + token}) as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            assert len(body) + len(chunk) <= 65536
                            body.extend(chunk)
                        assert response.status_code == expected_status
                        if expected_status == 200:
                            result = core.ReceiverHealthReadResultCodec(request, declaration).decode(json.loads(body))
                            assert result.outcome is core.NodeHealthReadOutcome.HEALTHY
                    output = engine.containers.get(placement.nodes["api"]).logs(tail=100)
                    assert len(output) <= 1024 * 1024 and token.encode() not in output

            reconstructed = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_identity)
            effect_count, dispatch_count = len(runtime.completed), len(placement.record["intents"])
            for previous, expected_history in retained_history:
                replay = await asyncio.to_thread(reconstructed.apply, previous.operation_ref, execute_plan=previous.plan_id)
                assert (replay.operation_ref, replay.plan_id, replay.run_id) == (
                    previous.operation_ref, previous.plan_id, previous.run_id)
                assert replay.execution == "succeeded" and replay.advancement == "unverified"
                assert await history(previous) == expected_history
            replay = await asyncio.to_thread(reconstructed.apply, cutover.operation_ref, execute_plan=cutover.plan_id)
            assert (replay.status, replay.execution, replay.advancement) == ("converged", "succeeded", "advanced")
            assert (replay.operation_ref, replay.plan_id, replay.run_id) == (
                cutover.operation_ref, cutover.plan_id, cutover.run_id)
            noop = await asyncio.to_thread(reconstructed.plan, AuthoredDesiredGraph(cutover_source,
                declaration_updates=(scope,), gateway_health_replacements=(route_intent,)))
            assert noop.status == "no-changes"
            assert (await asyncio.to_thread(reconstructed.apply, noop.operation_ref, execute_plan=noop.plan_id)).status == "no-changes"
            assert len(runtime.completed) == effect_count and len(placement.record["intents"]) == dispatch_count
            assert await history(cutover) == cutover_history
            print(json.dumps({"coupled_declaration_update": "passed", "run_id": cutover.run_id,
                "same_image": IMAGES["hello_family"]["reference"], "replacement_order": ["api", "gateway"],
                "receipts": [value.disposition.value for value in receipts], "intermediate": intermediate[0],
                "stale_declaration": "refused", "retained_keys_targets_secrets": "unchanged",
                "reconstructed_replay": "passed", "explicit_declaration_route_noop": "passed"}), flush=True)
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


async def witness(*, reintroduction=False):
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
    workspace = ("reintroduction-" if reintroduction else "image-") + uuid4().hex
    assert not any(owned_resources(engine, workspace))
    records = Path(os.environ["CPK_DOCKER_WITNESS_RECORDS"])
    ownership = records / "ownership.json"
    assert not ownership.exists()
    if reintroduction:
        from docker_receiver_reintroduction import DockerReintroductionMaterial
        material = DockerReintroductionMaterial(workspace)
    else:
        material = DockerImageMaterial(workspace)
    placement = OwnedControllerPlacement(engine, sdk, workspace, controller.id, daemon_id,
        record_path=ownership, run=os.environ["CPK_DOCKER_WITNESS_RUN"],
        expected_start_roles=material.expected_start_roles if reintroduction else None,
        qualified_images=images)
    print(json.dumps({"docker_image_inputs": images.descriptor(), "daemon_id": daemon_id,
        "controller_id": controller.id, "owned_workspace": workspace}), flush=True)
    database_url = os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"]
    try:
        with tempfile.TemporaryDirectory(prefix="cpk-image-") as directory:
            root = Path(directory)
            with SigningProviderProcess(root / "provider", workspace, database_url) as provider:
                await scenario(root, engine, sdk, placement, material, provider, database_url,
                    reintroduction=reintroduction)
    finally:
        dispose_fixture(placement)
        (records / "managed-resources-absent").write_text("verified\n", encoding="ascii")
        engine.close()


if __name__ == "__main__":
    mode = sys.argv[1:] or ["image-update"]
    if mode not in (["image-update"], ["receiver-reintroduction"]):
        raise ValueError("unknown Docker witness scenario")
    asyncio.run(witness(reintroduction=mode == ["receiver-reintroduction"]))
