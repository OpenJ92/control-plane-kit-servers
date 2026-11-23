"""A single public planning request against the owner's qualified, synthetic graph."""
import json
import unittest
from uuid import uuid4

from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_operations.graph_authoring import SecretVersionMetadata, product_references_in_graph
from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
from control_plane_kit_operations.products import InlineDescriptorSource
from control_plane_kit_servers_cpk_server.operations_application import (
    OperationsApplicationFactory, OperationsEffectPorts, OperationsIdFactories,
)
from draft_catalogue_fixture import DraftCatalogueFixture, NOW, principal
from test_standard_mcp import StandardMcpFixture
from tests.test_managed_verification_plan_support import mixed_plan


WORKSPACE = "workspace-a"
PINS = ("current_graph_id", "current_realized_projection_id", "desired_graph_id",
        "desired_realized_projection_id", "desired_graph_revision")


class FixtureMetadata:
    """Answer only for the exact synthetic version selected by the upstream fixture."""
    def __init__(self, selection):
        self.selection = selection

    def read_version(self, request):
        return SecretVersionMetadata(request.correlation_id, request.provider_registration_id,
            request.reference_registration_id, request.selection,
            request.workspace_id == WORKSPACE and request.selection == self.selection)


class FreshManagedPlanningTests(DraftCatalogueFixture, StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    async def post(self, path, body):
        response = await self.http.post(f"/workspaces/{WORKSPACE}/{path}", json=body)
        self.assertEqual(response.status_code, 200, f"fixture setup at {path}")
        return response.json()

    async def call(self, client, name, **arguments):
        result = await client.call_tool(name, {"workspace_id": WORKSPACE, **arguments})
        status = (result.structured_content or {}).get("error", {}).get("status")
        self.assertFalse(result.is_error, f"{name} returned {status}")
        return result.structured_content

    async def pins(self, client):
        workspace = (await self.call(client, "get_workspace"))["workspace"]
        return {key: workspace[key] for key in PINS}

    async def test_fresh_combined_readiness_stops_at_pending_plan_readback(self):
        source = mixed_plan(self)
        graph = DEFAULT_GRAPH_CODEC.decode(source["desired"].graph_descriptor)
        selection, = graph.node("postgres").secret_selections
        selected_products = product_references_in_graph(graph)
        with self.unit_of_work() as uow:
            for product in source["products"]:
                if product.reference in selected_products:
                    uow.stores.registered_products.register(workspace_id=WORKSPACE,
                        descriptor_document=product.descriptor_document, source=InlineDescriptorSource(),
                        imported_by="operator-a", imported_at=NOW)
            uow.commit()

        def unexpected_effect(*args, **kwargs):
            self.fail("planning attempted an external effect")

        ports = OperationsEffectPorts(None, None, None, HealthReceiverDecoders(()), unexpected_effect,
            disabled_runtime_adapter=unexpected_effect, secret_metadata_reader=FixtureMetadata(selection))
        factory = OperationsApplicationFactory(self.unit_of_work, ports,
            OperationsIdFactories(*(lambda: uuid4().hex for _ in range(5))), clock=lambda: NOW)
        self.host.services.update(factory().services)
        grants = {b"valid-token": principal(), b"reader-token": principal(scopes=(PolicyScope.INSTANCE_WORKSPACE_READ,))}
        authenticate = self.host.verifier.authenticate
        self.host.verifier.authenticate = lambda credential: (
            grants[credential] if credential in grants else authenticate(credential))
        reference = selection.reference.reference_id
        provider = await self.post("secret-providers", {
            "provider_id": selection.reference.provider_id.value, "provider_kind": "control-plane-kit-secrets",
            "display_name": "Synthetic planning metadata", "endpoint_reference": "fixture-metadata",
            "credential_reference": "secret://bootstrap/fixture/metadata", "allowed_reference_prefixes": [reference],
            "allowed_intents": [selection.intent.value], "admitted_at": NOW, "idempotency_key": "fixture-provider"})
        await self.post("secret-references", {"reference": reference, "provider_registration_id": provider["registration_id"],
            "allowed_intents": [selection.intent.value], "admitted_at": NOW, "idempotency_key": "fixture-reference"})
        async with self.client() as operator:
            pins = await self.pins(operator)
            graph_wire = DEFAULT_GRAPH_CODEC.encode(graph)
            # Establish the selected version through the same guarded Desired owner used by HTTP clients.
            # Saved-revision selection may carry forward an admitted choice, but cannot mint one.
            await self.post("graphs/desired", {"session_id": self.sessions[WORKSPACE], "graph": graph_wire,
                "explicit_secret_choices": {"postgres": [selection.descriptor()]}, "receiver_lifecycle": pins,
                **{"expected_" + key: pins[key] for key in PINS[2:]}, "idempotency_key": "fixture-version"})
            pins = await self.pins(operator)
            draft = await self.call(operator, "create_desired_topology_draft", session_id=self.sessions[WORKSPACE],
                graph=graph_wire, receiver_lifecycle=pins, title="Fresh managed bootstrap", idempotency_key="fixture-draft")
            revision = {"draft_id": draft["draft_id"], "revision": draft["revision"]}
            await self.call(operator, "select_desired_topology_draft", session_id=self.sessions[WORKSPACE],
                **revision, receiver_lifecycle=pins, idempotency_key="fixture-select",
                **{"expected_" + key: pins[key] for key in PINS[2:]})
            pins = await self.pins(operator)
            self.assertEqual(pins["desired_graph_id"], draft["graph_id"])
            prepared = await self.call(operator, "prepare_deployment", **revision,
                **{"expected_" + side: {"authored_graph_id": pins[side + "_graph_id"],
                    "realized_projection_id": pins[side + "_realized_projection_id"]} for side in ("current", "desired")},
                expected_desired_graph_revision=pins["desired_graph_revision"], title="Fresh combined readiness",
                idempotency_key="fixture-prepare", managed_verification="authenticated-local-postgres-and-http")
        self.assertEqual(prepared["status"], "approval-required")

        self.http.headers["Authorization"] = "Bearer reader-token"
        async with self.client() as reader:
            saved = await self.call(reader, "get_desired_topology_draft_revision", **revision)
            plan = (await self.call(reader, "get_plan_detail", plan_id=prepared["plan_id"]))["plan"]
            approval = (await self.call(reader, "get_approval_detail",
                approval_id=prepared["approval_request_id"]))["approval"]
            self.assertEqual(await self.pins(reader), pins)
            self.assertEqual((await self.call(reader, "list_plan_runs", plan_id=plan["plan_id"]))["items"], [])
        self.assertEqual((plan["base_graph_id"], plan["base_realized_projection_id"], plan["desired_graph_id"],
            plan["desired_realized_projection_id"], plan["desired_graph_revision"]), tuple(pins[key] for key in PINS))
        self.assertEqual(saved["graph_id"], plan["desired_graph_id"])
        self.assertEqual(plan["derivation_profile"], "managed-sql-http-bootstrap-v1")
        self.assertEqual((approval["request_id"], approval["plan_id"], approval["state"], approval["decision"]),
            (prepared["approval_request_id"], plan["plan_id"], "pending", None))
        activities = plan["payload"]["activities"]
        waits = {item["operation"]["target"]["node_id"]: item["activity_id"] for item in activities
            if item["operation"]["kind"] == "wait-for-healthy"}
        self.assertTrue({"api", "postgres"} <= waits.keys(), sorted(waits))
        nodes = saved["graph_descriptor"]["nodes"]
        verification = {}
        for node_id in ("api", "postgres"):
            self.assertEqual(nodes[node_id]["lifecycle"]["ownership"], "owned")
            checks = nodes[node_id]["verification"]["checks"]
            expected = graph.node(node_id).block_spec.verification.descriptor()["checks"]
            self.assertEqual(checks, [{key: check[key] for key in ("kind", "check_id", "provider_socket")}
                                      for check in expected])
            self.assertTrue(checks)
            verification[node_id] = checks
        self.assertEqual(nodes["postgres"]["secret_selections"], "<redacted>")
        with self.unit_of_work() as uow:
            revision_graph = uow.stores.graphs.get(saved["graph_id"]).graph_descriptor
            self.assertEqual(revision_graph["nodes"]["postgres"]["secret_selections"], [selection.descriptor()])
        print("Fresh managed planning readback", json.dumps({"draft": revision, "pins": pins,
            "plan_id": plan["plan_id"], "profile": plan["derivation_profile"], "activities": len(activities),
            "verification_activity_ids": {node: waits[node] for node in ("api", "postgres")}, "checks": verification,
            "approval_request_id": approval["request_id"], "approval_state": approval["state"],
            "version_public_read": "redacted", "fixture_version": selection.version_id}, sort_keys=True))
