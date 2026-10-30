"""Source-only A→B→C acceptance witness in the maintained Servers smoke gate.

The smoke owns PostgreSQL/container cleanup. This executable owns a fresh
schema, real Operations producers, and named deterministic external ports.
It does not prove provider deployment or the production local transport.
"""
import asyncio
import importlib.metadata
import json
import os
from dataclasses import replace
from uuid import uuid4

from control_plane_kit_core.operations import EffectAttemptIdentity, EffectAttemptStatus
from control_plane_kit_core.planning import ReconcileNode, RemoveNodeResource, StartNode
from control_plane_kit_core.topology import DeploymentGraph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from receiver_acceptance_material import AuthoredMaterial
from receiver_acceptance_operations import (
    IsolatedOperationsSchema, OperationsApplicationFactory, OperationsEffectPorts,
    PublicOperationsDriver, CoordinatorStopped, register_material,
)
from receiver_acceptance_ports import ComputeSubstitute, IngressSubstitute, SignedHealthComposition, synthetic_runtime_registration


def verify_provenance():
    """Apparatus check; no behavioral claim can precede normal installed pins."""
    pins = {
        "control-plane-kit-core": "7afef43f3d3b981094e37dcb3062b6e3a4f3d674",
        "control-plane-kit-operations": "802a4ce07cf1df4676138dbba1b68092e6cc79e9",
        "control-plane-kit-server-sdk": "220f63169e4bac79653937e97727406255279f7b",
        "control-plane-kit-secrets": "09442303740ed2e648cf354e35dd61df93974b9c",
        "control-plane-kit-interpreters": "71ab335d45ee804f2aec33c519639c75313626f0",
    }
    for name, commit in pins.items():
        direct = json.loads(importlib.metadata.distribution(name).read_text("direct_url.json"))
        assert direct["url"].endswith("/archive/" + commit + ".zip"), name
    print("receiver acceptance: normal installed dependency provenance passed", flush=True)


def origin(schema, receiver="a" * 32):
    with schema.unit_of_work() as uow:
        return uow.stores.graphs.receiver_introduction("workspace-a", receiver)


def configuration_accounting(schema, compute, expected_slots, label, unaccepted_refs=frozenset()):
    """Observe owner truth; absence from current is never cleanup permission."""
    refs = tuple(compute.configuration_refs.values())
    assert refs and len(refs) <= 32
    with schema.unit_of_work() as uow:
        current = uow.stores.configuration_acceptance.read_current_configuration("workspace-a")
        uses = uow.stores.configuration_acceptance.read_configuration_use("workspace-a", refs)
        history = {ref.allocation_id: uow.stores.configuration_preparation.read_allocation_evidence(ref)
            for ref in refs}
    assert current.state == uses.state == "complete"
    assert current.manifest_slot_count == expected_slots
    assert current.bindings == uses.bindings
    # This compute substitute emits no configuration-completion evidence, so
    # no E4 accepted-transfer disposition is asserted. These original claims
    # must retain complete historical protection; unexplained absence fails.
    assert all(value.state == "complete" for value in history.values()), "unexplained configuration evidence absence"
    for allocation_id, evidence in history.items():
        if evidence.state == "complete":
            assert evidence.birth.ref == compute.configuration_refs[allocation_id]
            assert evidence.claims and all(value.ref == evidence.birth.ref for value in evidence.claims)
    bindings = {(value.ref.node_id, value.ref.artifact_id): value.ref for value in current.bindings}
    assert len(bindings) == expected_slots
    current_ids = {value.allocation_id for value in bindings.values()}
    assert unaccepted_refs <= set(compute.configuration_refs)
    assert not unaccepted_refs & current_ids
    print(json.dumps({"configuration_accounting": label, "allocations": [
        {"allocation_id": ref.allocation_id, "node_id": ref.node_id, "artifact_id": ref.artifact_id,
         "role": ("unaccepted-fault" if ref.allocation_id in unaccepted_refs else
             "current" if ref.allocation_id in current_ids else "superseded-or-historical"),
         "historical_protection": history[ref.allocation_id].state,
         "physical_staging": "unmodeled", "cleanup": "unproven"}
        for ref in sorted(refs, key=lambda value:value.allocation_id)]}, sort_keys=True), flush=True)
    return bindings, history


async def accepted_history(database_url):
    material = AuthoredMaterial()
    compute = ComputeSubstitute()
    ingress = IngressSubstitute(compute)
    health = SignedHealthComposition(material, compute, ingress)
    def effects():
        return (tuple(compute.calls), tuple(ingress.calls), tuple(health.signed_reads),
            tuple(health.native_reads), tuple(health.keys.calls), dict(compute.identities), frozenset(compute.runtimes))
    schema_name = "cpk_1912_" + uuid4().hex
    with IsolatedOperationsSchema(database_url, schema_name) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: synthetic_runtime_registration(compute)},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
            id_factory=lambda: "receiver-" + uuid4().hex)
        driver = PublicOperationsDriver(factory, workspace_id="workspace-a", effect_snapshot=effects)
        await driver.create_workspace()
        await register_material(driver, material)
        accepted = []
        original = None
        original_x_compute = None
        original_connector = None
        original_ingress = None
        prior_bindings = None
        route_allocations = set()
        for label, graph in (("a", material.a), ("b", material.b), ("c", material.c)):
            start_calls = len(compute.calls)
            start_reads = len(health.signed_reads)
            try:
                accepted.append(await driver.accept(label=label, desired_graph=graph, destructive=label == "c"))
            except CoordinatorStopped:
                # Fixture-side entry observations only; public event/plan
                # correlation above supplies the actual rejected activity.
                print(json.dumps({"receiver_compute_entries": [
                    {"activity_id": value.activity_id.value[:256],
                     "operation": type(value.operation).__name__,
                     "node_id": (getattr(value.operation.target, "node_id", None) or "")[:256]}
                    for value in compute.calls[-32:]],
                    "entries_truncated": len(compute.calls) > 32,
                    "bare_runtime_registration": factory.ports.runtime_interpreters[RuntimeKind.DOCKER] is compute,
                    "generated_connectors": [value.connector_node_id[:256]
                        for value in graph.public_ingresses[:32]],
                    "custody_versions": [value.secret_custody_receipt.version_id[:256]
                        for value in list(ingress.allocations.values())[:32]]}), flush=True)
                raise
            bindings, _ = configuration_accounting(schema, compute, 5 if label == "b" else 4, label)
            route = bindings[("gateway", "gateway-health-targets")]
            assert route.allocation_id not in route_allocations
            route_allocations.add(route.allocation_id)
            if prior_bindings is not None:
                for slot, ref in bindings.items():
                    if slot in prior_bindings and slot != ("gateway", "gateway-health-targets"):
                        assert ref == prior_bindings[slot], "unchanged configuration slot was reallocated"
            prior_bindings = bindings
            current_origin = origin(schema)
            assert current_origin.first_accepted_action_id and current_origin.first_accepted_session_id
            assert current_origin.retired_action_id is None
            if label == "a":
                original = current_origin
                original_x_compute = compute.identities["api"]
                original_connector = compute.identities["connector"]
                original_ingress = dict(ingress.allocations)
            else:
                assert current_origin == original, "X's original acceptance changed"
                assert compute.identities["api"] == original_x_compute, "retained X was replaced"
                assert compute.identities["connector"] == original_connector, "retained connector was replaced"
                assert compute.runtimes == {"docker"}
                assert ingress.allocations == original_ingress, "retained ingress changed"
                replacement, = (request for request in compute.calls[start_calls:]
                    if type(request.operation) is ReconcileNode)
                assert replacement.operation.target.node_id == "gateway"
                assert accepted[-1].plan["derivation_profile"] == "managed-update-v1"
            expected_routes = ("api", "api-y", "self") if label == "b" else ("api", "self")
            reads = health.signed_reads[start_reads:]
            assert reads and all(value[3] == expected_routes for value in reads)
            assert all(value[2] == compute.identities["gateway"] for value in reads)
            if label == "c":
                removed, = (request for request in compute.calls[start_calls:]
                    if type(request.operation) is RemoveNodeResource)
                assert removed.operation.target.node_id == "api-y"
                position = compute.order.index(("RemoveNodeResource", removed.activity_id.value))
                assert all(compute.order.index(("signed-health", value[0])) < position for value in reads)
                assert "api-y" not in compute.installed
                assert origin(schema, "c" * 32).retired_action_id is not None
        for field in ("desired_graph_id", "desired_realized_projection_id", "plan_id"):
            assert len({value.plan[field] for value in accepted}) == 3, field
        assert len({value.claim["run_id"] for value in accepted}) == 3
        assert health.local_reads and len(health.native_reads) == 3 and health.public_dispatches
        # All historical views are queried through the real application by the driver.
        for value in accepted:
            assert value.history["plan"]["plan"] == value.plan
            assert value.history["session"]
            assert value.history["runs"]["items"] and value.history["events"]["items"]
        current_c = await driver.workspace()
        await driver.replay_original("a")
        assert await driver.workspace() == current_c and origin(schema) == original
        teardown = await driver.accept(label="teardown", desired_graph=DeploymentGraph("receiver-teardown"),
            destructive=True)
        retired = origin(schema)
        assert retired.first_accepted_action_id == original.first_accepted_action_id
        assert retired.first_accepted_session_id == original.first_accepted_session_id
        assert retired.retired_action_id and retired.retired_session_id
        assert not compute.installed and not compute.identities and not compute.runtimes and not ingress.allocations
        assert sum(type(value.operation) is StartNode and value.operation.target.node_id == "api"
            for value in compute.calls) == 1
        assert len(ingress.calls) == 2 and [value[0] for value in ingress.calls] == ["create", "remove"]
        bindings, allocation_history = configuration_accounting(schema, compute, 0, "teardown")
        assert not bindings
        complete = sum(value.state == "complete" for value in allocation_history.values())
        print("receiver acceptance: configuration references=" + str(len(allocation_history))
            + ", current=0, complete historical protection=" + str(complete)
            + ", unavailable historical protection=" + str(len(allocation_history) - complete)
            + "; configuration cleanup is not asserted", flush=True)
        print("receiver acceptance: accepted A/B/C, original X, restart replay and approved teardown passed; "
            "generated connector resolution/recipient is synthetic in-memory, not Docker proof", flush=True)
    print("receiver acceptance: isolated schema cleanup completed", flush=True)


async def failed_update(database_url, fault):
    """Joined producer failures retain accepted A; no teardown success is invented."""
    material = AuthoredMaterial()
    compute = ComputeSubstitute()
    ingress = IngressSubstitute(compute)
    health = SignedHealthComposition(material, compute, ingress)
    with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: synthetic_runtime_registration(compute)},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
            id_factory=lambda: "receiver-" + uuid4().hex)
        driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
        await driver.create_workspace()
        await register_material(driver, material)
        await driver.accept(label="a", desired_graph=material.a, destructive=False)
        original = origin(schema)
        before = await driver.workspace()
        original_bindings, _ = configuration_accounting(schema, compute, 4, fault + "-before")
        original_refs = set(compute.configuration_refs)
        reads = tuple(health.signed_reads)
        prior_compute = len(compute.calls)
        prior_key_failures = health.keys.failures
        if fault == "missing-installation-receipt":
            compute.receipt_mode = "missing"
        elif fault == "unavailable-signing-material":
            health.keys.unavailable = True
        else:
            raise ValueError("unknown witness fault")
        failed_run_id = None
        try:
            await driver.accept(label="b", desired_graph=material.b, destructive=False)
        except CoordinatorStopped as stopped:
            failed_run_id = stopped.run_id
            assert stopped.execution["coordinator_status"] == "uncertain"
            assert stopped.execution["run_status"] != "succeeded"
            if fault == "missing-installation-receipt":
                attempted, = (value for value in compute.calls[prior_compute:]
                    if type(value.operation) is ReconcileNode)
                assert attempted.operation.target.node_id == "gateway"
            else:
                assert health.keys.failures == prior_key_failures + 1
                attempted = health.attempted_reads[-1]
            assert attempted.source.run_id.value == stopped.run_id
            identity = EffectAttemptIdentity(attempted.source.run_id, attempted.activity_id.value, 1)
            with schema.unit_of_work() as uow:
                attempt = uow.stores.effect_attempts.get(identity)
                assert attempt.state.status is EffectAttemptStatus.UNCERTAIN
                outcome = uow.stores.effect_outcomes.get(identity, attempt.latest_transition_event.event_id)
                assert outcome is not None
        else:
            raise AssertionError("failed provider boundary fabricated acceptance")
        after = await driver.workspace()
        assert (after["current_graph_id"], after["current_realized_projection_id"]) == (
            before["current_graph_id"], before["current_realized_projection_id"])
        assert origin(schema) == original and original.retired_action_id is None
        delivered = {ref.allocation_id for request in compute.calls[prior_compute:]
            if request.source.run_id.value == failed_run_id and request.configuration_instances is not None
            for ref in request.configuration_instances.instances}
        new_refs = set(compute.configuration_refs) - original_refs
        assert new_refs and new_refs <= delivered, "failed-run allocation delivery was not recorded"
        failed_bindings, _ = configuration_accounting(schema, compute, 4, fault + "-after", frozenset(new_refs))
        assert failed_bindings == original_bindings, "failed update changed exact accepted A bindings"
        assert tuple(health.signed_reads) == reads, "failed prerequisite produced successful health"
        assert not any(type(request.operation) is RemoveNodeResource for request in compute.calls)
        print("receiver acceptance: " + fault + " preserved accepted A and original receiver", flush=True)
    # The isolated failed model is discarded with its schema. Only the positive
    # chain claims approved resource teardown; this is not compensating recovery.


async def run(database_url):
    from workspace_initialization_acceptance import workspace_initialization_acceptance
    await asyncio.to_thread(workspace_initialization_acceptance, database_url)
    from workspace_setup_acceptance import workspace_setup_acceptance
    await asyncio.to_thread(workspace_setup_acceptance, database_url)
    from workspace_authority_acceptance import workspace_authority_acceptance
    await asyncio.to_thread(workspace_authority_acceptance, database_url)
    from protected_input_preparation import protected_input_preparation
    await asyncio.to_thread(protected_input_preparation, database_url)
    await declared_gateway_preparation(database_url)
    await accepted_history(database_url)
    for fault in ("missing-installation-receipt", "unavailable-signing-material"):
        await failed_update(database_url, fault)


async def declared_gateway_preparation(database_url):
    """Required slots -> real public context -> actual artifacts -> ordinary prepare.

    Uses the existing smoke's isolated Postgres and authenticated application
    service driver. No provider resource or completed lifecycle fact is seeded.
    """
    import control_plane_kit_core as core
    from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
    from control_plane_kit_core.operations import ControlPlaneServiceRole
    from control_plane_kit_core.products import (
        ProductCatalog, ProductDescriptorCodec, ProductInstanceConfiguration,
        ProductReference, instantiate_catalog_product,
    )
    from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, compile_topology
    from control_plane_kit_servers_cpk_local_gateway import health_relay_configuration as relay
    from control_plane_kit_servers_cpk_local_gateway.control_configuration import (
        gateway_control_configuration_artifact, gateway_control_declaration,
    )
    from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
        GatewayHealthTransitConfiguration, gateway_health_transit_configuration_artifact,
    )
    from control_plane_kit_servers_cpk_server.client.authoring import ReceiverScope, prepare_receiver_configuration
    from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
    from receiver_acceptance_operations import utc_now

    material = AuthoredMaterial()
    contract = relay.gateway_health_declared_runtime_contract()
    original = material.documents["gateway"]
    declared = ProductDescriptorCodec().encode_document(replace(original.product,
        identity=replace(original.product.identity, contract_revision=2), runtime_contract=contract))
    material.documents["gateway"] = declared
    decoders = health_receiver_decoders(gateway_documents=(declared,))
    assert not contract.configuration_artifacts
    compute = ComputeSubstitute()
    ingress = IngressSubstitute(compute)
    health = SignedHealthComposition(material, compute, ingress)
    with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: synthetic_runtime_registration(compute)},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, decoders),
            id_factory=lambda: "declared-" + uuid4().hex)
        driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
        await driver.create_workspace()
        await register_material(driver, material)
        # Surface-read is a distinct required public family, even for health-only
        # declarations. Admit it through the same registration owners as health.
        instant = utc_now()
        intent, reference = "gateway.probe-signing-key", "secret://declared-surface/keys/surface"
        purpose = core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ.value
        provider = await driver.register("command.secret-provider.register", {
            "provider_id": "declared-surface", "display_name": "Declaration witness custody",
            "provider_kind": "control-plane-kit-secrets", "endpoint_reference": "declared-surface",
            "credential_reference": "secret://bootstrap/declared-surface/client-token",
            "allowed_reference_prefixes": ["secret://declared-surface/keys"], "allowed_intents": [intent],
            "admitted_at": instant, "metadata": {}, "idempotency_key": "declared-provider"})
        await driver.register("command.secret-reference.register", {
            "reference": reference, "provider_registration_id": provider["registration_id"],
            "allowed_intents": [intent], "admitted_at": instant, "metadata": {},
            "idempotency_key": "declared-reference"})
        await driver.register("command.delegation-key.register", {
            "purpose": purpose, "issuer": "cpk-server", "key_id": "declared-surface",
            "algorithm": "ed25519", "public_key_pem": material.public["workload"].public_key_pem,
            "private_key_reference": reference, "admitted_at": instant, "idempotency_key": "declared-key"})
        await driver.register("command.delegation-key.activate", {
            "purpose": purpose, "issuer": "cpk-server", "key_id": "declared-surface",
            "activated_at": instant, "idempotency_key": "declared-active"})
        path = {"workspace_id": "workspace-a"}
        context = await driver.invoke("read.receiver-authoring-context", ControlPlaneServiceRole.READS, path=path)
        verifiers = await driver.invoke("read.workload-verifier-configuration", ControlPlaneServiceRole.READS,
            path={**path, "purposes": purpose + ",workload-node-health-read"})
        configured = prepare_receiver_configuration(workspace_id="workspace-a", runtime_id="docker",
            scope=ReceiverScope("gateway", "control"), receiver_id="b" * 32,
            declaration=gateway_control_declaration(), context=context,
            verifier_configuration={"workload_verifier_configuration": verifiers["workload_verifier_configuration"]})
        trust = gateway_health_transit_configuration_artifact(GatewayHealthTransitConfiguration(
            configured.target, "cpk-server", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
            (material.public["transit"],)))
        material.configurations["gateway"] = configured
        artifacts = (trust, material.routes(("gateway", "api")), gateway_control_configuration_artifact(configured))
        block = instantiate_catalog_product(ProductCatalog.from_documents((declared,)), declared.product.identity,
            role_id="gateway", configuration=ProductInstanceConfiguration(
                public_environment=contract.public_environment, configuration_artifacts=artifacts, secret_deliveries=()))
        node = compile_topology(DeploymentTopology("declared-gateway",
            DockerRuntime(runtime_id="docker", children=(block,)))).node("gateway")
        desired = replace(material.a, nodes={**material.a.nodes, "gateway": node})
        assert node.metadata["product_descriptor_digest"] == declared.content_digest
        assert node.metadata["product_identity"] == declared.product.identity.key
        before = await driver.workspace()
        prepared = await driver.invoke("command.deployment.prepare", ControlPlaneServiceRole.PLANNING, path=path,
            payload={"desired_graph": DEFAULT_GRAPH_CODEC.encode(desired),
                "expected_current": {"authored_graph_id": before["current_graph_id"],
                    "realized_projection_id": before["current_realized_projection_id"]},
                "expected_desired": None, "expected_desired_graph_revision": before["desired_graph_revision"],
                "title": "Declared gateway preparation", "idempotency_key": "declared-prepare"})
        assert prepared["status"] == "approval-required"
        after = await driver.invoke("read.receiver-authoring-context", ControlPlaneServiceRole.READS, path=path)
        receivers = [value for value in after["desired"]["receivers"] if value["binding"]["node_id"] == "gateway"]
        assert len(receivers) == 1 and receivers[0]["binding"]["receiver_id"] == configured.target.receiver_id
        with schema.unit_of_work() as uow:
            registered = uow.stores.registered_products.get("workspace-a", ProductReference.from_document(declared))
            assert registered.descriptor_document == declared
        assert not compute.calls and not ingress.calls and not health.signed_reads
    print("declared gateway: authenticated context, actual material and ordinary preparation passed", flush=True)


def main():
    verify_provenance()
    database_url = os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"]
    asyncio.run(run(database_url))


if __name__ == "__main__":
    main()
