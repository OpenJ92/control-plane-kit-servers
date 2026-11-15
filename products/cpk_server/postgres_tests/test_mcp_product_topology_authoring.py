"""Explicit PostgreSQL phase of the owning topology-authoring cohort gate.

This product-local PostgreSQL test root uses normal test_*.py discovery in
test.sh's database phase. The imported Operations fixture owns schema/UoW setup only.
Every walkthrough operation uses the actual public host and released SDK.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from uuid import uuid4

import httpx2
from jsonschema import Draft202012Validator
from psycopg import sql
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_operations.cpk_server import (
    CpkServerLifecycleService, CpkServerPlanningService, CpkServerReadService,
    CpkServerUnsupportedService,
)
from control_plane_kit_operations.product_topology_authoring import ProductTopologyAuthoringService
from control_plane_kit_operations.products import InlineDescriptorSource
from control_plane_kit_operations.workflows import OperationCommandService

from draft_catalogue_fixture import DraftCatalogueFixture, NOW, principal
from test_standard_mcp import StandardMcpFixture


ROOT = Path(__file__).resolve().parents[3]
START = "command.operation-session.start"
SAVE = "command.desired-topology-draft.create"


class CountedService:
    """Observe dispatches without replacing an owner's return or behavior."""
    def __init__(self, owner, calls):
        self.owner, self.calls = owner, calls

    def handle(self, request):
        self.calls.append(request.route_id)
        return self.owner.handle(request)


class FixtureReplyLost(httpx2.ReadError):
    """Only this fixture's injected loss may be handled as the expected error."""


class DropCompletedReply(httpx2.AsyncBaseTransport):
    """Lose one response after the actual ASGI host completed that request."""
    def __init__(self, app, tool):
        self.inner = httpx2.ASGITransport(app=app)
        self.tool, self.sends, self.dropped = tool, 0, False
        self.loss = None

    async def handle_async_request(self, request):
        body = await request.aread()
        try:
            frame = json.loads(body)
        except (ValueError, UnicodeError):
            frame = {}
        matches = (frame.get("method") == "tools/call"
            and frame.get("params", {}).get("name") == self.tool)
        if matches:
            self.sends += 1
        response = await self.inner.handle_async_request(request)
        if matches and not self.dropped:
            await response.aread()
            await response.aclose()
            self.dropped = True
            self.loss = FixtureReplyLost("synthetic completed response loss", request=request)
            raise self.loss
        return response

    async def aclose(self):
        await self.inner.aclose()


class AuthoringPersistenceCases(DraftCatalogueFixture, StandardMcpFixture):
    mode = "auto"

    def setUp(self):
        DraftCatalogueFixture.setUp(self)

    def drop_schema(self):
        DraftCatalogueFixture.drop_schema(self)
        self.assertIsNone(self.connection.execute("SELECT to_regnamespace(%s)", (self.schema,)).fetchone()[0])
        print("authoring fixture schema absence verified")

    async def asyncSetUp(self):
        await StandardMcpFixture.asyncSetUp(self)
        self.dispatches = []
        # The host already references this map. Replace all recording services
        # with real owners or explicit unsupported services before any call.
        owners = {role: CpkServerUnsupportedService(role) for role in ControlPlaneServiceRole}
        owners.update({
            ControlPlaneServiceRole.READS: CpkServerReadService(self.unit_of_work),
            ControlPlaneServiceRole.LIFECYCLE: CpkServerLifecycleService(None,
                operations=OperationCommandService(self.unit_of_work, clock=lambda: NOW,
                    id_factory=lambda: uuid4().hex)),
            ControlPlaneServiceRole.PLANNING: CpkServerPlanningService(None,
                desired_topology_drafts=self.catalogue(),
                product_topologies=ProductTopologyAuthoringService(self.unit_of_work)),
        })
        self.host.services.clear()
        self.host.services.update({role: CountedService(owner, self.dispatches) for role, owner in owners.items()})
        self.grants = {
            b"valid-token": principal(),
            b"reader-token": principal(scopes=(PolicyScope.INSTANCE_WORKSPACE_READ,)),
        }
        original_authenticate = self.host.verifier.authenticate
        self.host.verifier.authenticate = lambda credential: (
            self.grants[credential] if credential in self.grants else original_authenticate(credential))
        self.references = {}
        for role, product in (("hello", "hello_server"), ("mux", "http_multiplexer")):
            document = ProductDescriptorCodec().decode_document(
                (ROOT / "products" / product / "product.cpk.json").read_bytes())
            with self.unit_of_work() as uow:
                record = uow.stores.registered_products.register(workspace_id="workspace-a",
                    descriptor_document=document, source=InlineDescriptorSource(),
                    imported_by="operator-a", imported_at=NOW)
                uow.commit()
            self.references[role] = record.reference.descriptor()
        codec = ProductDescriptorCodec()
        foreign = codec.decode_document((ROOT / "products/hello_server/product.cpk.json").read_bytes()).product
        document = codec.encode_document(replace(foreign,
            identity=replace(foreign.identity, name="foreign-workspace-hello")))
        with self.unit_of_work() as uow:
            record = uow.stores.registered_products.register(workspace_id="workspace-b",
                descriptor_document=document, source=InlineDescriptorSource(), imported_by="operator-a", imported_at=NOW)
            uow.commit()
        self.foreign_reference = record.reference.descriptor()

    def truth(self):
        # A new connection/UoW establishes committed truth, independently of
        # the connection that handled the public request.
        tables = ("cpk_operation_sessions", "cpk_operation_actions", "cpk_graph_versions",
            "cpk_desired_topology_drafts", "cpk_desired_topology_draft_revisions")
        with self.unit_of_work() as uow:
            workspace = uow.stores.workspaces.get("workspace-a")
            return {"pointers": (workspace.current_graph_id, workspace.desired_graph_id),
                **{table: uow.stores.connection.execute(sql.SQL(
                    "SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(table))).fetchall() for table in tables}}

    def recipe(self, references):
        def config(environment):
            return dict(public_environment=environment, configuration_artifacts=[], secret_deliveries=[],
                requirement_secret_deliveries=[], runtime_authority_deliveries=[])
        return {"schema": "registered-product-topology.v1", "name": "SDK Hello through multiplexer",
            "runtime": {"runtime_id": "demo-docker", "kind": "docker", "network_name": "demo-net",
                "authority_ref": None, "management": None,
                "lifecycle": {"ownership": "owned", "compute": "ephemeral", "data": []}},
            "nodes": [{"role_id": role, "product": references[role], "configuration": config([
                {"kind": "public-static", "name": name, "value": value}
                for name, value in (("HELLO_MESSAGE", "SDK public greeting"), ("HELLO_COLOR", "blue"),
                    ("HELLO_DEPENDENCIES_JSON", "[]"))] if role == "hello" else [])}
                for role in ("hello", "mux")],
            "connections": [{"edge_id": "hello-to-mux", "provider_role": "hello", "provider_socket": "internal",
                "consumer_role": "mux", "requirement_socket": "primary",
                "protocol": {"transport": "tcp", "application": "http"}}]}

    async def call(self, client, tool, arguments):
        result = await client.call_tool(tool, {"workspace_id": "workspace-a", **arguments})
        self.assertFalse(result.is_error, result.structured_content)
        return result.structured_content

    async def assert_transport_loss(self, tool, arguments):
        # The SDK propagates transport task errors when its Client context
        # exits. Follow the existing planning test across that whole boundary;
        # unrelated errors and helper assertions are never swallowed.
        transport = DropCompletedReply(self.app, tool)
        caught = None
        received = False
        try:
            async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080",
                    headers={"Authorization": "Bearer valid-token"}) as http:
                async with self.client(self.mode, http=http) as client:
                    await client.call_tool(tool, {"workspace_id": "workspace-a", **arguments})
                    received = True
        except* FixtureReplyLost as errors:
            caught = errors
        self.assertFalse(received, "SDK returned a tool result despite injected response loss")
        self.assertIsNotNone(caught, "SDK did not report the injected transport loss")
        self.assertIsNotNone(caught.subgroup(lambda error: error is transport.loss))
        return transport

    async def preview(self):
        before = self.truth()
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                base_url="http://127.0.0.1:8080", headers={"Authorization": "Bearer reader-token"}) as reader:
            async with self.client(self.mode, http=reader) as client:
                discovered = {tool.name: tool for tool in (await client.list_tools()).tools}
                tools = set(discovered)
                self.assertTrue({"preview_product_topology", "start_operation_session",
                    "create_desired_topology_draft"}.issubset(tools), "missing standard authoring tools")
                self.assertTrue(discovered["preview_product_topology"].annotations.read_only_hint)
                for tool in ("start_operation_session", "create_desired_topology_draft"):
                    self.assertFalse(discovered[tool].annotations.read_only_hint)
                    self.assertFalse(discovered[tool].annotations.idempotent_hint)
                save_schema = discovered["create_desired_topology_draft"].input_schema
                receiver = save_schema["properties"]["receiver_lifecycle"]
                self.assertNotIn("receiver_lifecycle", save_schema["required"])
                expectation = {"current_graph_id": "current", "current_realized_projection_id": "projection",
                    "desired_graph_id": None, "desired_realized_projection_id": None, "desired_graph_revision": 0}
                self.assertTrue(Draft202012Validator(receiver).is_valid(expectation))
                self.assertFalse(Draft202012Validator(receiver).is_valid({**expectation, "extra": True}))
                page = await self.call(client, "list_registered_products", {"limit": 100})
                refs = {role: next(item["reference"] for item in page["items"]
                    if item["reference"] == reference) for role, reference in self.references.items()}
                for reference in refs.values():
                    detail = await self.call(client, "get_registered_product",
                        {"descriptor_sha256": reference["descriptor_sha256"]})
                    self.assertEqual(detail["product"]["reference"], reference)
                preview = await self.call(client, "preview_product_topology", {"recipe": self.recipe(refs)})
            http = await reader.post("/workspaces/workspace-a/topology-authoring/preview",
                json={"recipe": self.recipe(refs)})
            self.assertEqual(http.status_code, 200)
            self.assertEqual(http.json(), preview)
        self.assertEqual(self.truth(), before)
        self.assertNotIn("/health/live", json.dumps(preview))
        return preview

    def start_input(self):
        return {"title": "SDK authored topology", "idempotency_key": uuid4().hex}

    def save_input(self, preview, session):
        return {"session_id": session["session_id"], "title": "SDK saved topology", "idempotency_key": uuid4().hex,
            "product_recipe": preview["recipe"], "expected_proposal_commitment": preview["proposal_commitment"]}

    async def save_once(self, preview):
        before = self.truth()
        async with self.client(self.mode) as client:
            session = await self.call(client, "start_operation_session", self.start_input())
            receipt = await self.call(client, "create_desired_topology_draft", self.save_input(preview, session))
        after = self.truth()
        new_sessions = [row[0] for row in after["cpk_operation_sessions"] if row not in before["cpk_operation_sessions"]]
        self.assertEqual([row["session_id"] for row in new_sessions], [session["session_id"]])
        self.assertEqual(self.dispatches.count(START), 1)
        self.assertEqual(self.dispatches.count(SAVE), 1)
        self.assertEqual(after["pointers"], before["pointers"])
        self.assertEqual(set(receipt), {"workspace_id", "draft_id", "revision", "graph_id"})
        self.saved_session_id = session["session_id"]
        return receipt

    async def test_two_products_save_and_fresh_client_exact_readback(self):
        preview = await self.preview()
        receipt = await self.save_once(preview)
        arguments = {"draft_id": receipt["draft_id"], "revision": receipt["revision"]}
        # A new SDK client must use receipt coordinates, not transport state.
        async with self.client(self.mode) as client:
            detail = await self.call(client, "get_desired_topology_draft_revision", arguments)
            repeated = await self.call(client, "get_desired_topology_draft_revision", arguments)
        self.assertEqual(repeated, detail)
        self.assertEqual({key: detail[key] for key in receipt}, receipt)
        graph = detail["graph_descriptor"]
        self.assertEqual(set(graph["nodes"]), {"hello", "mux"})
        self.assertEqual(set(graph["edges"]), {"hello-to-mux"})
        for private in ("/health/live", "/health/ready", "SDK public greeting"):
            self.assertNotIn(private, json.dumps(detail))
        for role, reference in self.references.items():
            node = graph["nodes"][role]
            expected_verification = {"checks": [{"kind": "http", "check_id": check,
                "provider_socket": "internal"} for check in (("live", "ready") if role == "hello" else ("live",))]}
            self.assertEqual(node["block_spec"]["verification"], expected_verification)
            if "verification" in node:
                self.assertEqual(node["verification"], expected_verification)
            if role == "hello":
                self.assertEqual(node["environment_bindings"], [
                    {"kind": "public-static", "name": name, "value": "<redacted>"}
                    for name in ("HELLO_COLOR", "HELLO_DEPENDENCIES_JSON", "HELLO_MESSAGE")])
            else:
                self.assertEqual(node["environment_bindings"], [{"kind": "socket-derived",
                    "name": "MULTIPLEXER_PRIMARY_URL", "value": "<redacted>", "edge_id": "hello-to-mux"}])
            identity = reference["identity"]
            self.assertEqual(node["metadata"]["product_identity"],
                f'{identity["namespace"]}/{identity["name"]}/{identity["contract_revision"]}')
            self.assertEqual(node["metadata"]["product_descriptor_digest"], reference["descriptor_sha256"])
            self.assertEqual(node["runtime_id"], "demo-docker")
        self.assertEqual(set(graph["runtimes"]), {"demo-docker"})
        edge = graph["edges"]["hello-to-mux"]
        self.assertEqual(edge["provider"], {"role": "hello", "socket": "internal"})
        self.assertEqual(edge["consumer"], {"role": "mux", "requirement": "primary"})
        self.assertEqual(edge["protocol"], {"transport": "tcp", "application": "http"})
        self.assertEqual(edge["binding"], "environment")
        self.assertEqual(edge["env_assignments"], "<redacted>")
        with self.unit_of_work() as uow:
            stored = DEFAULT_GRAPH_CODEC.decode(uow.stores.graphs.get(receipt["graph_id"]).graph_descriptor)
        self.assertEqual(stored.node("mux").socket_environment[0].edge_id, "hello-to-mux")
        actions = [row[0] for row in self.truth()["cpk_operation_actions"]
            if row[0]["action_type"] == "create-desired-topology-draft"]
        self.assertEqual([row["payload"] for row in actions], [receipt])
        self.assertEqual([row["session_id"] for row in actions], [self.saved_session_id])
        response = await self.http.get(f'/workspaces/workspace-a/desired-topology-drafts/{receipt["draft_id"]}/revisions/{receipt["revision"]}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), detail)
        self.assertEqual(self.dispatches.count(SAVE), 1)

    async def test_lost_start_reply_stops_before_save_without_resend(self):
        await self.preview()
        before = self.truth()
        transport = await self.assert_transport_loss("start_operation_session", self.start_input())
        self.assertTrue(transport.dropped)
        self.assertEqual(transport.sends, 1)
        self.assertEqual(self.dispatches.count(START), 1)
        self.assertEqual(self.dispatches.count(SAVE), 0)
        after = self.truth()
        self.assertEqual(len(after["cpk_operation_sessions"]), len(before["cpk_operation_sessions"]) + 1)
        for table in ("cpk_graph_versions", "cpk_desired_topology_drafts", "cpk_desired_topology_draft_revisions"):
            self.assertEqual(after[table], before[table])
        self.assertEqual(after["pointers"], before["pointers"])

    async def test_recipe_save_refusals_preserve_truth_and_recheck_current_authority(self):
        preview = await self.preview()
        async with self.client(self.mode) as client:
            session = await self.call(client, "start_operation_session", self.start_input())
            payload = {"workspace_id": "workspace-a", **self.save_input(preview, session)}
            before = self.truth()
            foreign_recipe = deepcopy(preview["recipe"])
            foreign_recipe["nodes"][0]["product"] = self.foreign_reference
            for changed, status in (
                ({"graph": {}}, 400),
                ({"expected_proposal_commitment": {"profile": "registered-product-topology-public.v1", "sha256": "0" * 64}}, 409),
                ({"product_recipe": {**preview["recipe"], "unrecognized": True}}, 400),
                ({"workspace_id": "workspace-b"}, 403),
                ({"product_recipe": foreign_recipe}, 400),
            ):
                result = await client.call_tool("create_desired_topology_draft", {**payload, **changed})
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["error"]["status"], status)
                http_payload = {**payload, **changed}
                workspace_id = http_payload.pop("workspace_id")
                response = await self.http.post(f"/workspaces/{workspace_id}/desired-topology-drafts", json=http_payload)
                self.assertEqual(response.status_code, status)
                self.assertEqual(self.truth(), before)
            # This SDK client was initialized with an editor; every actual HTTP
            # request must still resolve the newly read-only principal.
            self.grants[b"valid-token"] = principal(scopes=(PolicyScope.INSTANCE_WORKSPACE_READ,))
            refused = await client.call_tool("create_desired_topology_draft", payload)
            self.assertTrue(refused.is_error)
            self.assertEqual(refused.structured_content["error"]["status"], 403)
            response = await self.http.post("/workspaces/workspace-a/desired-topology-drafts",
                json={key: value for key, value in payload.items() if key != "workspace_id"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.truth(), before)

    async def test_lost_save_reply_is_unknown_without_resend(self):
        preview = await self.preview()
        async with self.client(self.mode) as client:
            session = await self.call(client, "start_operation_session", self.start_input())
        before = self.truth()
        transport = await self.assert_transport_loss("create_desired_topology_draft", self.save_input(preview, session))
        self.assertTrue(transport.dropped)
        self.assertEqual(transport.sends, 1)
        self.assertEqual(self.dispatches.count(SAVE), 1)
        after = self.truth()
        self.assertEqual(len(after["cpk_desired_topology_draft_revisions"]), len(before["cpk_desired_topology_draft_revisions"]) + 1)
        self.assertEqual(after["pointers"], before["pointers"])
        self.assertEqual(len(after["cpk_operation_sessions"]), len(before["cpk_operation_sessions"]))

    async def test_received_save_receipt_survives_lost_readback(self):
        receipt = await self.save_once(await self.preview())
        before = self.truth()
        transport = await self.assert_transport_loss("get_desired_topology_draft_revision",
            {"draft_id": receipt["draft_id"], "revision": receipt["revision"]})
        self.assertTrue(transport.dropped)
        self.assertEqual(transport.sends, 1)
        self.assertEqual(self.truth(), before)
        self.assertEqual(self.dispatches.count(SAVE), 1)
        async with self.client(self.mode) as client:
            detail = await self.call(client, "get_desired_topology_draft_revision",
                {"draft_id": receipt["draft_id"], "revision": receipt["revision"]})
        self.assertEqual({key: detail[key] for key in receipt}, receipt)
        self.assertEqual(self.truth(), before)
        self.assertEqual(self.dispatches.count(SAVE), 1)
        # Receipt remains known: saved, with readback unavailable; not unsaved.
        self.assertEqual(receipt["workspace_id"], "workspace-a")


class AutoAuthoringPersistenceTests(AuthoringPersistenceCases, unittest.IsolatedAsyncioTestCase):
    mode = "auto"


class LegacyAuthoringPersistenceTests(AuthoringPersistenceCases, unittest.IsolatedAsyncioTestCase):
    mode = "legacy"
