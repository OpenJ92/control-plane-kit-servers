"""#255 same-product retirement/reintroduction using the existing public witness."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import httpx
import control_plane_kit_core as core
from control_plane_kit_core.planning import RemoveNodeResource, StartNode
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import Protocol, RuntimeKind
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from control_plane_kit_servers_cpk_server.client import TopologyClient
from control_plane_kit_servers_cpk_server.client.authoring import (
    AuthoredDesiredGraph, ReceiverIntroduction, ReceiverScope,
    GatewayHealthRoutes, GatewayHealthTargetIntent,
)
from control_plane_kit_servers_cpk_server.client.transport import ClientTransportError
from live_unlisted_receiver import (
    ReceiverProcesses, ProcessCompute, ProcessHealth, LoseCompletedPreparation,
    controller_identity, diagnose_execution, digest, register_surface_verifier,
    select_pending_baseline, unlisted_graph,
)
from receiver_acceptance_material import AuthoredMaterial
from receiver_acceptance_operations import (
    IsolatedOperationsSchema, OperationsApplicationFactory, OperationsEffectPorts,
    PublicOperationsDriver, register_material, utc_now,
)
from receiver_acceptance_ports import IngressSubstitute, synthetic_runtime_registration
from unlisted_controller_host import ControllerHost


X, Y = "counter-example", "counter-y"


def nodes(graph, values):
    return replace(graph, nodes=values, runtimes={"docker":
        replace(graph.runtimes["docker"], children=tuple(values))})


def routes(graph, include_y):
    scopes = (("self", "gateway", "control"), (X, X, "http"))
    if include_y:
        scopes += ((Y, Y, "http"),)
    return (GatewayHealthRoutes(ReceiverScope("gateway", "control"), tuple(
        GatewayHealthTargetIntent(alias, ReceiverScope(name, socket),
            graph.node(name).endpoint(socket).url) for alias, name, socket in scopes)),)


async def read(transport, route, **coordinates):
    return await asyncio.to_thread(transport.call, route,
        path_parameters={"workspace_id": "workspace-a", **coordinates},
        payload={}, credential_role="operator")


async def history(transport, result):
    plan = await read(transport, "read.plan-detail", plan_id=result.plan_id)
    pages = {}
    for route, coordinate in (("read.plan-runs", {"plan_id": result.plan_id}),
            ("read.run-events", {"run_id": result.run_id})):
        items, after = [], None
        for _ in range(8):
            page = await asyncio.to_thread(transport.call, route,
                path_parameters={"workspace_id": "workspace-a", **coordinate},
                payload={"limit": 100, **({"after": after} if after is not None else {})},
                credential_role="operator")
            items.extend(page["items"])
            after = page.get("next_cursor")
            if after is None:
                break
        assert after is None and items, "public history missing or exceeds witness bound"
        pages[route] = items
    return plan["plan"], pages


def prepared(client, result):
    journal = client.journal.read(result.operation_ref)
    raw = (client.journal.root / journal["preparation"]["name"]).read_bytes()
    return DEFAULT_GRAPH_CODEC.decode(json.loads(raw)), raw


async def apply(client, transport, planned):
    assert planned.status == "planned" and type(planned.destructive) is bool
    option = "approve_destructive_plan" if planned.destructive else "approve_plan"
    assert planned.required_scope == ("plan:approve-destructive" if planned.destructive else "plan:approve")
    result = await asyncio.to_thread(client.apply, planned.operation_ref,
        execute_plan=planned.plan_id, **{option: planned.plan_id})
    if result.status != "converged":
        await diagnose_execution(client, transport, result)
    assert result.status == "converged", result.descriptor()
    return result


def require_removal_plan(host, result, before_exchange_count):
    if result.status != "planned":
        exchanges = host.prepare_exchanges[before_exchange_count:]
        evidence = {"receiver_reintroduction_prepare_failure": "remove-y"}
        if len(exchanges) == 1:
            exchange = exchanges[0]
            error = exchange.response_body.get("error", {})
            message = error.get("message") if isinstance(error, dict) else None
            categories = {"deployment preparation request is malformed": "request-malformed",
                "deployment preparation state is unavailable": "state-conflict"}
            evidence.update(http_status=exchange.response_status,
                category=categories.get(message, "unclassified") if isinstance(message, str) else "unclassified",
                request_sha256=digest(exchange.request_body))
        else:
            evidence["exchange"] = ("no prepare exchange observed" if not exchanges
                else "multiple prepare exchanges observed")
        print(json.dumps(evidence), flush=True)
    assert result.status == "planned", result.descriptor()


def write_graph(path, graph):
    path.write_text(json.dumps(DEFAULT_GRAPH_CODEC.encode(graph)), encoding="utf-8")
    return path


async def healthy(processes, name):
    credential, path = processes.tokens[name]
    async with httpx.AsyncClient(timeout=3, trust_env=False) as socket:
        result = await socket.get(processes.origins[name] + path,
            headers={"Authorization": credential})
        assert result.status_code == 200 and len(result.content) <= 16384
        business = await socket.get(processes.origins[name] + "/count")
        assert business.status_code == 200 and len(business.content) <= 1024
        return int(business.text)


async def scenario(host, transport, material, processes, compute, ingress, health, graph, introduction,
        product_reference):
    root = processes.root
    assert set(graph.nodes) == {"gateway", "connector", X, Y}
    baseline = await select_pending_baseline(transport, material,
        scopes=(ReceiverScope("gateway", "control"),))
    source = write_graph(root / "original-unauthored.json", graph)
    original_source = source.read_bytes()
    saved_y = graph.node(Y)
    assert not saved_y.configuration_artifacts and not saved_y.public_environment
    client = TopologyClient(host.profile, transport=transport)
    lost = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(source,
        introductions=introduction, pending=baseline, gateway_health_replacements=routes(graph, True)))
    assert lost.status == "attention-required" and len(transport.preparations) == 1
    original_preparation = host.prepare_exchanges[0]
    authored, original_bytes = prepared(client, lost)
    def no_identity():
        raise AssertionError("original replay regenerated receiver identity")
    replay_client = TopologyClient(host.profile, transport=transport, receiver_identity_factory=no_identity)
    planned = await asyncio.to_thread(replay_client.resume_prepare, lost.operation_ref)
    assert host.prepare_exchanges[1].request_body == original_preparation.request_body
    assert host.prepare_exchanges[1].response_body == original_preparation.response_body
    initial = await apply(replay_client, transport, planned)
    initial_history = await history(transport, initial)
    current = (await read(transport, "read.receiver-authoring-context"))["current"]
    x_row = next(item for item in current["receivers"] if item["binding"]["node_id"] == X)
    x_child, old_y = processes.children[X], processes.children[Y]
    x_bytes, old_y_bytes = processes.paths[X].read_bytes(), processes.paths[Y].read_bytes()
    x_material, x_identity = compute.installed[X], processes.identities[X]
    assert compute.installed[X].reference == compute.installed[Y].reference
    assert compute.installed[X].reference == product_reference
    old_config = core.ReceiverNodeControlConfigurationCodec().decode_bytes(old_y_bytes)
    assert health.installed_configuration(X).target.receiver_id != old_config.target.receiver_id
    before_count = await healthy(processes, X)
    await healthy(processes, Y)

    without_y = nodes(authored, {name: node for name, node in authored.nodes.items() if name != Y})
    assert set(without_y.nodes) == {"gateway", "connector", X}
    remove_source = write_graph(root / "remove-y.json", without_y)
    effect_offset = len(compute.calls)
    before_exchange_count = len(host.prepare_exchanges)
    removal_plan = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(remove_source,
        gateway_health_replacements=routes(without_y, False)))
    require_removal_plan(host, removal_plan, before_exchange_count)
    assert removal_plan.destructive is True
    removal = await apply(client, transport, removal_plan)
    removal_history = await history(transport, removal)
    removed_graph, _ = prepared(client, removal)
    removed, = (item for item in compute.calls[effect_offset:] if type(item.operation) is RemoveNodeResource)
    assert removed.operation.target.node_id == Y
    assert old_y.poll() is not None and Y not in processes.children
    assert not (root / Y).exists() and Y not in compute.installed
    assert all(name != Y for name in processes.paths)

    def retained_x():
        assert processes.children[X] is x_child and x_child.poll() is None
        assert processes.paths[X].read_bytes() == x_bytes
        assert compute.installed[X] == x_material and processes.identities[X] == x_identity

    retained_x()
    assert await healthy(processes, X) > before_count
    before_workspace = (await read(transport, "read.workspace"))["workspace"]
    effects = (tuple(compute.calls), tuple(ingress.calls), tuple(processes.starts), tuple(processes.stops))
    # Fresh fences and key, but retired identity and matching old route material.
    # No replacement receiver yet exists to mask retirement with scope occupancy.
    stale_payload = {"desired_graph": DEFAULT_GRAPH_CODEC.encode(authored),
        "expected_current": {"authored_graph_id": before_workspace["current_graph_id"],
            "realized_projection_id": before_workspace["current_realized_projection_id"]},
        "expected_desired": {"authored_graph_id": before_workspace["desired_graph_id"],
            "realized_projection_id": before_workspace["desired_realized_projection_id"]},
        "expected_desired_graph_revision": before_workspace["desired_graph_revision"],
        "title": "Refuse retired Y origin", "idempotency_key": str(uuid4())}
    exchanges = len(host.prepare_exchanges)
    try:
        await asyncio.to_thread(transport.call, "command.deployment.prepare",
            path_parameters={"workspace_id": "workspace-a"}, payload=stale_payload,
            credential_role="operator")
    except ClientTransportError:
        refused = host.prepare_exchanges[-1]
    else:
        raise AssertionError("retired receiver was freshly admitted")
    assert len(host.prepare_exchanges) == exchanges + 1
    assert json.loads(refused.request_body) == stale_payload and refused.response_status == 409
    assert refused.response_body == {"error": {"status": 409,
        "message": "deployment preparation state is unavailable"}}
    assert (await read(transport, "read.workspace"))["workspace"] == before_workspace
    assert effects == (tuple(compute.calls), tuple(ingress.calls), tuple(processes.starts), tuple(processes.stops))
    assert await history(transport, initial) == initial_history
    assert await history(transport, removal) == removal_history
    retained_x()
    await healthy(processes, X)

    fresh_graph = nodes(removed_graph, {**removed_graph.nodes, Y: saved_y})
    fresh_source = write_graph(root / "fresh-unauthored-y.json", fresh_graph)
    fresh_input_bytes = fresh_source.read_bytes()
    fresh_plan = await asyncio.to_thread(client.plan, AuthoredDesiredGraph(fresh_source,
        introductions=(introduction[1],), gateway_health_replacements=routes(fresh_graph, True)))
    assert fresh_plan.status == "planned", fresh_plan.descriptor()
    fresh_authored, fresh_bytes = prepared(client, fresh_plan)
    fresh_wrapper, = fresh_authored.node(Y).configuration_artifacts
    new_config = core.ReceiverNodeControlConfigurationCodec().decode_bytes(fresh_wrapper.content.encode())
    assert new_config.target.receiver_id != old_config.target.receiver_id
    assert replace(old_config.target, receiver_id=new_config.target.receiver_id) == new_config.target
    assert replace(old_config, target=new_config.target) == new_config
    old_routes, = (item for item in authored.node("gateway").configuration_artifacts
        if item.artifact_id == "gateway-health-targets")
    new_routes, = (item for item in fresh_authored.node("gateway").configuration_artifacts
        if item.artifact_id == "gateway-health-targets")
    old_route_values = core.ReceiverManagementRoutesCodec().decode_bytes(old_routes.content.encode())
    new_route_values = core.ReceiverManagementRoutesCodec().decode_bytes(new_routes.content.encode())
    assert replace(old_route_values, targets=tuple(replace(item, target=new_config.target)
        if item.target_id == Y else item for item in old_route_values.targets)) == new_route_values
    assert len({fresh_plan.operation_ref, initial.operation_ref, removal.operation_ref}) == 3
    effect_offset = len(compute.calls)
    fresh = await apply(client, transport, fresh_plan)
    assert len({fresh.plan_id, initial.plan_id, removal.plan_id}) == 3
    assert len({fresh.run_id, initial.run_id, removal.run_id}) == 3
    started, = (item for item in compute.calls[effect_offset:] if type(item.operation) is StartNode)
    assert started.operation.target.node_id == Y
    assert processes.children[Y] is not old_y and processes.children[Y].poll() is None
    assert processes.paths[Y].read_bytes() == fresh_wrapper.content.encode() != old_y_bytes
    await healthy(processes, Y)
    retained_x()
    later_context = (await read(transport, "read.receiver-authoring-context"))["current"]
    later_x = next(item for item in later_context["receivers"] if item["binding"]["node_id"] == X)
    assert later_x == {**x_row, "binding": {**x_row["binding"],
        "graph_id": later_context["graph_id"], "realized_projection_id": later_context["realized_projection_id"]}}
    fresh_history = await history(transport, fresh)
    assert await history(transport, initial) == initial_history
    assert await history(transport, removal) == removal_history
    current_workspace = (await read(transport, "read.workspace"))["workspace"]
    effects = (tuple(compute.calls), tuple(ingress.calls), tuple(processes.starts), tuple(processes.stops))
    original_replay = await asyncio.to_thread(transport.call, "command.deployment.prepare",
        path_parameters={"workspace_id": "workspace-a"},
        payload=json.loads(original_preparation.request_body), credential_role="operator")
    assert original_replay == original_preparation.response_body
    assert host.prepare_exchanges[-1].request_body == original_preparation.request_body
    for previous, expected in ((initial, initial_history), (removal, removal_history)):
        replay = await asyncio.to_thread(replay_client.apply, previous.operation_ref, execute_plan=previous.plan_id)
        assert (replay.operation_ref, replay.plan_id, replay.run_id) == (
            previous.operation_ref, previous.plan_id, previous.run_id)
        assert replay.execution == "succeeded" and replay.advancement == "unverified"
        assert await history(transport, previous) == expected
    assert (await read(transport, "read.workspace"))["workspace"] == current_workspace
    assert effects == (tuple(compute.calls), tuple(ingress.calls), tuple(processes.starts), tuple(processes.stops))
    assert source.read_bytes() == original_source and fresh_source.read_bytes() == fresh_input_bytes
    assert prepared(client, initial)[1] == original_bytes and prepared(client, fresh)[1] == fresh_bytes
    for credential_path in host.credential_files.values():
        credential = credential_path.read_bytes()
        for result in (initial, removal, fresh):
            assert credential not in json.dumps(client.journal.read(result.operation_ref)).encode()
        assert credential not in original_bytes and credential not in fresh_bytes

    teardown_source = write_graph(root / "teardown.json", DeploymentGraph("reintroduction-teardown"))
    teardown_plan = await asyncio.to_thread(client.plan, teardown_source)
    assert teardown_plan.destructive is True
    await apply(client, transport, teardown_plan)
    assert not compute.installed and not compute.runtimes and not ingress.allocations
    assert not processes.children and not processes.paths
    assert not processes.owned_files and processes.retired_files
    assert all(not path.exists() for path in processes.retired_files)
    for result, expected in ((initial, initial_history), (removal, removal_history), (fresh, fresh_history)):
        assert await history(transport, result) == expected
    print(json.dumps({"receiver_reintroduction": "passed", "same_product": True,
        "retired_origin_http_status": refused.response_status, "new_receiver_identity": True,
        "retained_x": True, "original_history_and_replay": "preserved",
        "public_desired_empty": "converged", "process_files": "absent",
        "runtime_boundary": "owned-source-process", "ingress": "synthetic"}), flush=True)


async def witness():
    frozen = controller_identity()
    material = AuthoredMaterial()
    # Pure pending input: the accepted add/remove relation has exactly X/Y as
    # workloads. The older witness keeps its independent bootstrap api node.
    gateway = material.a.node("gateway")
    gateway = replace(gateway, configuration_artifacts=tuple(
        material.routes(("gateway",)) if item.artifact_id == "gateway-health-targets" else item
        for item in gateway.configuration_artifacts))
    material.a = nodes(material.a, {"gateway": gateway, "connector": material.a.node("connector")})
    with tempfile.TemporaryDirectory(prefix="cpk-reintroduction-") as temporary:
        root = Path(temporary)
        base, documents, _, _ = unlisted_graph(material, root)
        product = documents[X]
        template = base.node(X)
        second = replace(template, node_id=Y, block_spec=replace(template.block_spec, role_id=Y),
            endpoints={"http": Endpoint(LiteralAddress("http://counter-y:8000"), Protocol.HTTP)})
        graph = nodes(material.a, {**material.a.nodes, X: template, Y: second})
        wrapper, = product.product.runtime_contract.configuration_artifacts
        instances = {name: ("counter.py", "/count", wrapper.target_path) for name in (X, Y)}
        processes = ReceiverProcesses(root, Path(os.environ["CPK_UNLISTED_EXAMPLES"]), instances=instances)
        compute = ProcessCompute(processes, node_names=instances)
        ingress = IngressSubstitute(compute)
        health = ProcessHealth(material, compute, ingress, processes)
        try:
            with IsolatedOperationsSchema(os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"],
                    "cpk_1912_reintro_" + uuid4().hex) as schema:
                factory = OperationsApplicationFactory(schema.unit_of_work,
                    OperationsEffectPorts({RuntimeKind.DOCKER: synthetic_runtime_registration(compute)},
                        {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
                    id_factory=lambda: "reintroduction-" + uuid4().hex)
                driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
                await driver.create_workspace()
                await register_material(driver, material)
                with ControllerHost(factory, driver, root / "controller") as host:
                    transport = LoseCompletedPreparation(host.profile)
                    await register_surface_verifier(transport, material)
                    imported = await asyncio.to_thread(transport.call, "command.product.import",
                        path_parameters={"workspace_id": "workspace-a"},
                        payload={"descriptor_document": json.loads(product.content),
                            "imported_at": utc_now(), "idempotency_key": str(uuid4())}, credential_role="operator")
                    assert imported["status"] == "active"
                    introductions = tuple(ReceiverIntroduction(ReceiverScope(name, "http"),
                        wrapper.artifact_id, wrapper.target_path) for name in (X, Y))
                    await scenario(host, transport, material, processes, compute, ingress, health, graph, introductions,
                        ProductReference.from_document(product))
                    assert controller_identity() == frozen
        finally:
            processes.close()
    assert not root.exists()
    print("receiver reintroduction private directory absent; provider/native cleanup remains unproven", flush=True)
