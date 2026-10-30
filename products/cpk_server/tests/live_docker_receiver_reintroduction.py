"""#255 lifecycle through the existing real Docker/public CPK composition."""
import asyncio
from dataclasses import replace
import hashlib
import json
from uuid import uuid4

import control_plane_kit_core as core
from control_plane_kit_core.planning import RemoveNodeResource, StartNode, StopNode
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import ReceiverScope
from control_plane_kit_servers_cpk_server.client.transport import ClientTransportError

from docker_image_update_material import IMAGES
from docker_image_update_placement import owned_resources
from docker_image_update_ports import require_committed_call
from docker_receiver_reintroduction import route_intent, with_nodes
from live_unlisted_receiver import select_pending_baseline


def prepared(client, result):
    journal = client.journal.read(result.operation_ref)
    raw = client.journal.read_preparation(result.operation_ref, journal["preparation"])
    return DEFAULT_GRAPH_CODEC.decode(json.loads(raw)), raw


def wrapper_configuration(graph, name):
    artifact, = [value for value in graph.node(name).configuration_artifacts
        if value.artifact_id == "hello-control"]
    return core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode()), artifact


async def reintroduction_scenario(root, engine, sdk, placement, material, host, transport,
        client, runtime, ingress, health_socket, authored_configurations, apply, read, history, worker_id):
    workspace = material.workspace_id
    assert set(material.graph.nodes) == {"gateway", "connector", "api", "api-y"}
    saved_y = material.graph.node("api-y")
    assert not saved_y.configuration_artifacts
    assert material.graph.node("api").metadata == saved_y.metadata
    saved_y_bytes = json.dumps(DEFAULT_GRAPH_CODEC.encode(material.graph), sort_keys=True).encode()
    (root / "saved-unauthored.json").write_bytes(saved_y_bytes)
    selected = {}

    def observe_prepared(label, *, destructive):
        def observe(result, graph):
            assert result.status == "planned" and result.destructive is destructive
            assert result.required_scope == ("plan:approve-destructive" if destructive else "plan:approve")
            selected[label] = graph
            for name in ("api", "api-y"):
                if name in graph.nodes:
                    configuration, _ = wrapper_configuration(graph, name)
                    authored_configurations[name].append(configuration)
        return observe

    def installed(name, graph):
        container = engine.containers.get(placement.nodes[name])
        mounts = {item["Destination"]: item for item in container.attrs["Mounts"]}
        digests = {}
        for artifact in graph.node(name).configuration_artifacts:
            mount = mounts[artifact.target_path]
            assert mount["Type"] == "volume" and mount["RW"] is False
            digest = sdk.configuration_artifact_digest(mount["Name"])
            assert digest == artifact.content_digest
            digests[artifact.artifact_id] = digest
        return digests

    def effect_snapshot():
        return len(runtime.completed), tuple(ingress.calls), dict(placement.nodes)

    baseline = await select_pending_baseline(transport, material, workspace_id=workspace,
        scopes=(ReceiverScope("gateway", "control"),))
    initial_health = len(health_socket.observations)
    initial, original_source = await apply(material.graph, "reintroduction-initial", pending=baseline,
        introductions=material.introductions, routes=(route_intent(material.graph),),
        prepared_observer=observe_prepared("initial", destructive=False))
    initial_graph, original_bytes = prepared(client, initial)
    assert initial_graph == selected["initial"]
    initial_exchange, = host.prepare_exchanges
    assert initial_exchange.response_status == 200
    initial_history = await history(initial)
    original_source_bytes = original_source.read_bytes()
    x_id, old_y_id = placement.nodes["api"], placement.nodes["api-y"]
    x_configuration, x_wrapper = wrapper_configuration(initial_graph, "api")
    old_y_configuration, old_y_wrapper = wrapper_configuration(initial_graph, "api-y")
    assert x_configuration.target.receiver_id != old_y_configuration.target.receiver_id
    for name in ("api", "api-y"):
        placement.inspect_node(name)
        assert engine.containers.get(placement.nodes[name]).attrs["Image"] == placement.expected_image_id("hello_family")
        assert (name, "readiness", 200) in health_socket.observations[initial_health:]
    starts = [value for value in runtime.completed if type(value.request.operation) is StartNode
        and value.request.operation.target.node_id in {"api", "api-y"}]
    assert len(starts) == 2
    for record in starts:
        product, = [value for value in record.request.products
            if value.node_id == record.request.operation.target.node_id]
        assert product.reference == material.product_reference
    x_installed = installed("api", initial_graph)
    installed("api-y", initial_graph)
    original_context = (await read("read.receiver-authoring-context"))["current"]
    original_x, = [row for row in original_context["receivers"] if row["binding"]["node_id"] == "api"]

    def retained_x(graph):
        assert placement.nodes["api"] == x_id
        assert placement.inspect_node("api").container_id == x_id
        assert wrapper_configuration(graph, "api") == (x_configuration, x_wrapper)
        assert installed("api", graph) == x_installed

    without_y = with_nodes(initial_graph, {name: node for name, node in initial_graph.nodes.items()
        if name != "api-y"})
    effect_offset, health_offset = len(runtime.completed), len(health_socket.observations)
    removal, _ = await apply(without_y, "remove-y", routes=(route_intent(without_y),),
        prepared_observer=observe_prepared("removed", destructive=True))
    removed_graph = selected["removed"]
    removal_history = await history(removal)
    retired = [value for value in runtime.completed[effect_offset:]
        if type(value.request.operation) in (StopNode, RemoveNodeResource)]
    assert [(type(value.request.operation), value.request.operation.target.node_id) for value in retired] == [
        (StopNode, "api-y"), (RemoveNodeResource, "api-y")]
    for record in retired:
        arguments, response = transport.committed[record.request.effect_id]
        require_committed_call(record, response, arguments, removal_history[1], worker_id)
    assert sdk.inspect_container(old_y_id) is None
    assert old_y_id in placement.record["containers"]  # History is not current placement.
    assert placement.nodes.pop("api-y") == old_y_id
    retained_x(removed_graph)
    assert ("api", "readiness", 200) in health_socket.observations[health_offset:]

    # Current fences/new request identity, retired Y identity; replacement absent.
    before_workspace = (await read("read.workspace"))["workspace"]
    before_effects = effect_snapshot()
    stale_payload = {"desired_graph": DEFAULT_GRAPH_CODEC.encode(initial_graph),
        "expected_current": {"authored_graph_id": before_workspace["current_graph_id"],
            "realized_projection_id": before_workspace["current_realized_projection_id"]},
        "expected_desired": {"authored_graph_id": before_workspace["desired_graph_id"],
            "realized_projection_id": before_workspace["desired_realized_projection_id"]},
        "expected_desired_graph_revision": before_workspace["desired_graph_revision"],
        "title": "Refuse retired OCI receiver", "idempotency_key": str(uuid4())}
    before_exchanges = len(host.prepare_exchanges)
    try:
        await asyncio.to_thread(transport.call, "command.deployment.prepare",
            path_parameters={"workspace_id": workspace}, payload=stale_payload, credential_role="operator")
    except ClientTransportError:
        assert len(host.prepare_exchanges) == before_exchanges + 1
        refused = host.prepare_exchanges[-1]
    else:
        raise AssertionError("retired receiver admitted as a fresh request")
    assert json.loads(refused.request_body) == stale_payload and refused.response_status == 409
    assert refused.response_body == {"error": {"status": 409,
        "message": "deployment preparation state is unavailable"}}
    assert (await read("read.workspace"))["workspace"] == before_workspace
    assert effect_snapshot() == before_effects and sdk.inspect_container(old_y_id) is None
    assert await history(initial) == initial_history and await history(removal) == removal_history
    retained_x(removed_graph)

    fresh_graph = with_nodes(removed_graph, {**removed_graph.nodes, "api-y": saved_y})
    effect_offset, health_offset = len(runtime.completed), len(health_socket.observations)
    fresh, fresh_source = await apply(fresh_graph, "fresh-y", introductions=(material.introductions[1],),
        routes=(route_intent(fresh_graph),), prepared_observer=observe_prepared("fresh", destructive=False))
    fresh_authored, fresh_bytes = prepared(client, fresh)
    fresh_source_bytes = fresh_source.read_bytes()
    fresh_history = await history(fresh)
    new_configuration, new_wrapper = wrapper_configuration(fresh_authored, "api-y")
    assert new_configuration.target.receiver_id != old_y_configuration.target.receiver_id
    assert replace(old_y_configuration.target, receiver_id=new_configuration.target.receiver_id) == new_configuration.target
    assert replace(old_y_configuration, target=new_configuration.target) == new_configuration
    for field in ("operation_ref", "plan_id", "run_id"):
        assert len({getattr(value, field) for value in (initial, removal, fresh)}) == 3
    new_y_id = placement.nodes["api-y"]
    assert new_y_id != old_y_id and sdk.inspect_container(old_y_id) is None
    placement.inspect_node("api-y")
    assert installed("api-y", fresh_authored)[new_wrapper.artifact_id] == new_wrapper.content_digest
    started, = [value for value in runtime.completed[effect_offset:] if type(value.request.operation) is StartNode]
    assert started.request.operation.target.node_id == "api-y"
    product, = [value for value in started.request.products if value.node_id == "api-y"]
    assert product.reference == material.product_reference
    arguments, response = transport.committed[started.request.effect_id]
    require_committed_call(started, response, arguments, fresh_history[1], worker_id)
    assert all((name, "readiness", 200) in health_socket.observations[health_offset:] for name in ("api", "api-y"))
    retained_x(fresh_authored)
    context = (await read("read.receiver-authoring-context"))["current"]
    current_x, = [row for row in context["receivers"] if row["binding"]["node_id"] == "api"]
    assert current_x == {**original_x, "binding": {**original_x["binding"],
        "graph_id": context["graph_id"], "realized_projection_id": context["realized_projection_id"]}}
    old_routes, = [value for value in initial_graph.node("gateway").configuration_artifacts
        if value.artifact_id == "gateway-health-targets"]
    new_routes, = [value for value in fresh_authored.node("gateway").configuration_artifacts
        if value.artifact_id == "gateway-health-targets"]
    codec = core.ReceiverManagementRoutesCodec()
    before_routes, after_routes = (codec.decode_bytes(value.content.encode()) for value in (old_routes, new_routes))
    assert replace(before_routes, targets=tuple(replace(value, target=new_configuration.target)
        if value.target_id == "api-y" else value for value in before_routes.targets)) == after_routes

    current_workspace, current_effects = (await read("read.workspace"))["workspace"], effect_snapshot()
    response = await asyncio.to_thread(transport.call, "command.deployment.prepare",
        path_parameters={"workspace_id": workspace}, payload=json.loads(initial_exchange.request_body),
        credential_role="operator")
    assert response == initial_exchange.response_body
    assert host.prepare_exchanges[-1].request_body == initial_exchange.request_body
    def no_new_identity():
        raise AssertionError("historical replay generated a new receiver")
    reconstructed = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_new_identity)
    for previous, expected in ((initial, initial_history), (removal, removal_history)):
        replay = await asyncio.to_thread(reconstructed.apply, previous.operation_ref, execute_plan=previous.plan_id)
        assert (replay.operation_ref, replay.plan_id, replay.run_id) == (
            previous.operation_ref, previous.plan_id, previous.run_id)
        assert replay.execution == "succeeded" and replay.advancement == "unverified"
        assert await history(previous) == expected
    assert effect_snapshot() == current_effects
    assert (await read("read.workspace"))["workspace"] == current_workspace
    assert prepared(client, initial)[1] == original_bytes and prepared(client, fresh)[1] == fresh_bytes
    assert original_source.read_bytes() == original_source_bytes and fresh_source.read_bytes() == fresh_source_bytes
    assert (root / "saved-unauthored.json").read_bytes() == saved_y_bytes
    for credential_path in host.credential_files.values():
        credential = credential_path.read_bytes()
        for value in (initial, removal, fresh):
            assert credential not in json.dumps(client.journal.read(value.operation_ref)).encode()
        assert credential not in original_bytes and credential not in fresh_bytes

    placement.detach()
    await apply(DeploymentGraph("reintroduction-teardown"), "reintroduction-teardown",
        prepared_observer=observe_prepared("empty", destructive=True))
    containers, networks, volumes = owned_resources(engine, workspace)
    assert not containers and not networks and not ingress.allocations
    assert all(sdk.inspect_container(identity) is None for identity in (x_id, old_y_id, new_y_id))
    for previous, expected in ((initial, initial_history), (removal, removal_history), (fresh, fresh_history)):
        assert await history(previous) == expected
    print(json.dumps({"docker_receiver_reintroduction": "passed", "workspace": workspace,
        "same_product": material.product_reference.descriptor(), "old_y_container": old_y_id,
        "new_y_container": new_y_id, "retained_x_container": x_id,
        "retired_origin_http_status": refused.response_status, "fresh_receiver_identity": True,
        "original_history_and_replay": "preserved", "public_desired_empty": "converged",
        "historical_configuration_volumes": sum(value.name in placement.record["volumes"] for value in volumes),
        "secret_volumes": sum(value.name in placement.record["secret_volumes"] for value in volumes),
        "initial_request_sha256": hashlib.sha256(initial_exchange.request_body).hexdigest(),
        "ingress": "synthetic", "native": "synthetic"}), flush=True)
