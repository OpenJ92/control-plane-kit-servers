"""Source-only A→B→C acceptance witness in the maintained Servers smoke gate.

The smoke owns PostgreSQL/container cleanup. This executable owns a fresh
schema, real Operations producers, and named deterministic external ports.
It does not prove provider deployment or the production local transport.
"""
import asyncio
import importlib.metadata
import json
import os
from uuid import uuid4

from control_plane_kit_core.planning import ReconcileNode, RemoveNodeResource, StartNode
from control_plane_kit_core.topology import DeploymentGraph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from receiver_acceptance_material import AuthoredMaterial
from receiver_acceptance_operations import (
    IsolatedOperationsSchema, OperationsApplicationFactory, OperationsEffectPorts,
    PublicOperationsDriver, OperationsSequenceError, register_material,
)
from receiver_acceptance_ports import ComputeSubstitute, IngressSubstitute, SignedHealthComposition


def verify_provenance():
    """Apparatus check; no behavioral claim can precede normal installed pins."""
    pins = {
        "control-plane-kit-core": "ba0bd45e7fa7673b837366f7f5da5f9159b0dee8",
        "control-plane-kit-operations": "cafdc9050ceeb9e430912b9ba9dd034a6712fb1f",
        "control-plane-kit-server-sdk": "23500b1445dc6a748bd92a441e781d7f9ed90299",
        "control-plane-kit-secrets": "d8849bbfe12b9c613ace71ed86531baab2695236",
        "control-plane-kit-interpreters": "67a0d3d13974314fbc49fe8ac9639b2d760216a7",
    }
    for name, commit in pins.items():
        direct = json.loads(importlib.metadata.distribution(name).read_text("direct_url.json"))
        assert direct["url"].endswith("/archive/" + commit + ".zip"), name
    print("receiver acceptance: normal installed dependency provenance passed", flush=True)


def origin(schema, receiver="a" * 32):
    with schema.unit_of_work() as uow:
        return uow.stores.graphs.receiver_introduction("workspace-a", receiver)


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
            OperationsEffectPorts({RuntimeKind.DOCKER: compute},
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
        for label, graph in (("a", material.a), ("b", material.b), ("c", material.c)):
            start_calls = len(compute.calls)
            start_reads = len(health.signed_reads)
            accepted.append(await driver.accept(label=label, desired_graph=graph, destructive=label == "c"))
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
        print("receiver acceptance: accepted A/B/C, original X, restart replay and approved teardown passed", flush=True)
    print("receiver acceptance: isolated schema cleanup completed", flush=True)


async def failed_update(database_url, fault):
    """Joined producer failures retain accepted A; no teardown success is invented."""
    material = AuthoredMaterial()
    compute = ComputeSubstitute()
    ingress = IngressSubstitute(compute)
    health = SignedHealthComposition(material, compute, ingress)
    with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex) as schema:
        factory = OperationsApplicationFactory(schema.unit_of_work,
            OperationsEffectPorts({RuntimeKind.DOCKER: compute},
                {IngressAuthorityProviderKind.CLOUDFLARE: ingress}, health, material.decoders),
            id_factory=lambda: "receiver-" + uuid4().hex)
        driver = PublicOperationsDriver(factory, workspace_id="workspace-a")
        await driver.create_workspace()
        await register_material(driver, material)
        await driver.accept(label="a", desired_graph=material.a, destructive=False)
        original = origin(schema)
        before = await driver.workspace()
        reads = tuple(health.signed_reads)
        if fault == "missing-installation-receipt":
            compute.receipt_mode = "missing"
        elif fault == "unavailable-signing-material":
            health.keys.unavailable = True
        else:
            raise ValueError("unknown witness fault")
        try:
            await driver.accept(label="b", desired_graph=material.b, destructive=False)
        except OperationsSequenceError:
            pass
        else:
            raise AssertionError("failed provider boundary fabricated acceptance")
        after = await driver.workspace()
        assert (after["current_graph_id"], after["current_realized_projection_id"]) == (
            before["current_graph_id"], before["current_realized_projection_id"])
        assert origin(schema) == original and original.retired_action_id is None
        assert tuple(health.signed_reads) == reads, "failed prerequisite produced successful health"
        assert not any(type(request.operation) is RemoveNodeResource for request in compute.calls)
        print("receiver acceptance: " + fault + " preserved accepted A and original receiver", flush=True)
    # The isolated failed model is discarded with its schema. Only the positive
    # chain claims approved resource teardown; this is not compensating recovery.


async def run(database_url):
    await accepted_history(database_url)
    for fault in ("missing-installation-receipt", "unavailable-signing-material"):
        await failed_update(database_url, fault)


def main():
    verify_provenance()
    database_url = os.environ["CPK_RECEIVER_ACCEPTANCE_DATABASE_URL"]
    asyncio.run(run(database_url))


if __name__ == "__main__":
    main()
