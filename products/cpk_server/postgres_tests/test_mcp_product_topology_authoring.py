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
from control_plane_kit_core.products import OciImageReference, ProductDescriptorCodec
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_core.types import Protocol
from control_plane_kit_operations.cpk_server import (
    CpkServerLifecycleService, CpkServerPlanningService, CpkServerReadService,
    CpkServerUnsupportedService,
)
from control_plane_kit_operations.product_topology_authoring import ProductTopologyAuthoringService
from control_plane_kit_operations.products import InlineDescriptorSource, ProductRegistrationService
from control_plane_kit_operations.workflows import IdempotencyKey, OperationCommandService
from control_plane_kit_operations.workspaces import CreateWorkspace, WorkspaceCommandService

from draft_catalogue_fixture import DraftCatalogueFixture, NOW, principal
from test_standard_mcp import StandardMcpFixture


ROOT = Path(__file__).resolve().parents[3]
START = "command.operation-session.start"
SAVE = "command.desired-topology-draft.create"
SELECT_TOOL = "select_desired_topology_draft"


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
                products=ProductRegistrationService(self.unit_of_work),
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

    async def test_register_portable_managed_connector_alongside_active_seed(self):
        lane = ROOT / "products" / "cloudflared_connector"
        codec = ProductDescriptorCodec()
        seed = codec.decode_document((lane / "product.cpk.json").read_bytes())
        managed = codec.decode_document((lane / "product.managed.cpk.json").read_bytes())
        documents = (seed, managed)
        receipts = []
        async with self.client(self.mode) as writer:
            for document in documents:
                receipt = await self.call(writer, "import_product_descriptor", {
                    "descriptor_document": json.loads(document.content), "imported_at": NOW,
                    "idempotency_key": "admit-" + document.product.identity.name})
                self.assertEqual(receipt["status"], "active")
                self.assertEqual(receipt["reference"], {
                    "identity": document.product.identity.descriptor(),
                    "descriptor_sha256": document.content_digest})
                receipts.append(receipt)
        self.assertNotEqual(receipts[0]["registration_id"], receipts[1]["registration_id"])

        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                base_url="http://127.0.0.1:8080", headers={"Authorization": "Bearer reader-token"}) as http:
            async with self.client(self.mode, http=http) as fresh:
                page = await self.call(fresh, "list_registered_products", {"limit": 100})
                self.assertIsNone(page["next_cursor"])
                listed = [item["reference"] for item in page["items"]]
                for document, receipt in zip(documents, receipts, strict=True):
                    self.assertEqual(listed.count(receipt["reference"]), 1)
                    detail = (await self.call(fresh, "get_registered_product",
                        {"descriptor_sha256": document.content_digest}))["product"]
                    self.assertEqual(detail["reference"], receipt["reference"])
                    self.assertEqual(detail["registration_id"], receipt["registration_id"])
                    self.assertEqual(detail["status"], "active")
                    self.assertEqual(detail["image"]["digest"], document.product.image.digest)
                    if document == managed:
                        self.assertEqual(detail["image"]["platforms"], [
                            {"os": "linux", "architecture": "amd64", "variant": None}])
                        self.assertEqual(detail["contract"]["provider_ports"], [
                            {"provider_socket": "control", "container_port": 8000}])

    async def test_import_wrapped_connector_then_recover_exact_registration(self):
        from control_plane_kit_servers_cloudflared_connector import managed
        from products.cloudflared_connector.retained_qualification import REFERENCE

        tool = "import_product_descriptor"
        codec = ProductDescriptorCodec()
        seed = codec.decode_document((ROOT / "products/cloudflared_connector/product.cpk.json").read_bytes())
        # Compose a disposable declaration from the wrapped product owner and the
        # retained release. The seed file itself describes a different image.
        repository, digest = REFERENCE.split("@")
        registry, path = repository.split("/", 1)
        document = codec.encode_document(replace(seed.product,
            display_name=None, description=None, image=OciImageReference(registry, path, digest),
            runtime_contract=managed.declared_runtime_contract()))
        reference = {"identity": document.product.identity.descriptor(), "descriptor_sha256": document.content_digest}
        args = {"descriptor_document": json.loads(document.content), "imported_at": NOW,
                "idempotency_key": "import-connector"}

        async with self.client(self.mode) as writer:
            tools = {item.name: item for item in (await writer.list_tools()).tools}
            self.assertIn(tool, set(tools))
            self.assertFalse(tools[tool].annotations.read_only_hint)
            before = await self.call(writer, "list_registered_products", {"limit": 100})
            for extra in ({"actor_id": "forged"}, {"source": {"path": "/tmp/descriptor"}},
                          {"registry_credentials": "fixture-private"}, {"expected_revision": 0}):
                result = await writer.call_tool(tool, {"workspace_id": "workspace-a", **args, **extra})
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["error"]["status"], 400)
            for field in ("configuration_artifacts", "secret_deliveries"):
                material = deepcopy(args)
                material["descriptor_document"]["product"]["runtime_contract"][field] = [{"content": "fixture-private"}]
                rejected = await writer.call_tool(tool, {"workspace_id": "workspace-a", **material})
                self.assertEqual(rejected.structured_content["error"]["status"], 400)
                self.assertNotIn("fixture-private", str(rejected.structured_content))
            bound = deepcopy(args)
            sockets = bound["descriptor_document"]["product"]["runtime_contract"]["sockets"]
            sockets["requirements"]["database"] = {
                "protocol": Protocol.POSTGRES.descriptor(), "env_bindings": [], "required": False,
                "binding": "runtime-control", "secret_deliveries": [{"kind": "environment",
                    "environment_name": "DATABASE_PASSWORD", "reference_id": "secret://fixture/password",
                    "intent": "postgres.password"}]}
            codec.decode_document(bound["descriptor_document"])  # Valid owner contract, outside this public input.
            rejected = await writer.call_tool(tool, {"workspace_id": "workspace-a", **bound})
            self.assertEqual(rejected.structured_content["error"]["status"], 400)
            self.assertNotIn("secret://fixture/password", str(rejected.structured_content))
            oversized = {**args, "idempotency_key": "x" * 65536}
            rejected = await writer.call_tool(tool, {"workspace_id": "workspace-a", **oversized})
            self.assertEqual(rejected.structured_content["error"]["status"], 413)
            wrong = await writer.call_tool(tool, {"workspace_id": "workspace-b", **args})
            self.assertTrue(wrong.is_error)
            self.assertIn(wrong.structured_content["error"]["status"], (403, 404))
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                    base_url="http://127.0.0.1:8080", headers={"Authorization": "Bearer reader-token"}) as http:
                async with self.client(self.mode, http=http) as reader:
                    denied = await reader.call_tool(tool, {"workspace_id": "workspace-a", **args})
                    self.assertTrue(denied.is_error)
                    self.assertEqual(denied.structured_content["error"]["status"], 403)
            self.assertEqual(await self.call(writer, "list_registered_products", {"limit": 100}), before)

        lost = await self.assert_transport_loss(tool, args)
        self.assertEqual(lost.sends, 1)
        async with self.client(self.mode) as fresh:
            listed = await self.call(fresh, "list_registered_products", {"limit": 100})
            self.assertEqual([i["reference"] for i in listed["items"] if i["reference"] == reference], [reference])
            detail = await self.call(fresh, "get_registered_product", {"descriptor_sha256": document.content_digest})
            self.assertEqual(detail["product"]["reference"], reference)
            # A separately requested duplicate preserves the original admission.
            duplicate = await self.call(fresh, tool, {**args, "idempotency_key": "separate-import"})
            self.assertEqual((detail["product"]["image"]["digest"], detail["product"]["status"]), (digest, "active"))
            self.assertEqual(duplicate["product"], {"display_name": None, "description": None})
            self.assertEqual(duplicate["workspace_id"], "workspace-a")
            self.assertEqual(duplicate["reference"], reference)
            self.assertEqual(duplicate["registration_id"], detail["product"]["registration_id"])
            http = await self.http.post("/workspaces/workspace-a/products/import", json=args)
            self.assertEqual(http.json(), duplicate)
            conflict = {**args, "descriptor_document": json.loads(seed.content)}
            refused = await fresh.call_tool(tool, {"workspace_id": "workspace-a", **conflict})
            self.assertTrue(refused.is_error)
            print("Wrapped connector catalog fixture:", reference, "conflict status:", refused.structured_content["error"]["status"])
            missing = await fresh.call_tool("get_registered_product", {
                "workspace_id": "workspace-a", "descriptor_sha256": seed.content_digest})
            self.assertEqual(missing.structured_content["error"]["status"], 404)
            self.assertEqual(await self.call(fresh, "list_registered_products", {"limit": 100}), listed)
            self.assertEqual(await self.call(fresh, "get_registered_product",
                {"descriptor_sha256": document.content_digest}), detail)

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

    async def selection_input(self, draft, workspace=None):
        if workspace is None:
            workspace = (await self.http.get("/workspaces/workspace-a")).json()["workspace"]
        return {"session_id": self.sessions[draft.workspace_id], "draft_id": draft.draft_id,
            "revision": draft.revision, "idempotency_key": uuid4().hex,
            **{"expected_" + field: workspace[field] for field in (
                "desired_graph_id", "desired_realized_projection_id", "desired_graph_revision")}}

    async def test_select_exact_older_revision_readback_and_http_replay(self):
        first = self.create()
        newer = self.catalogue().execute(self.revise_command(first))
        before = (await self.http.get("/workspaces/workspace-a")).json()["workspace"]
        args = await self.selection_input(first, before)
        async with self.client(self.mode) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertIn(SELECT_TOOL, tools)
            self.assertFalse(tools[SELECT_TOOL].annotations.read_only_hint)
            schema = Draft202012Validator(tools[SELECT_TOOL].input_schema)
            unassigned = dict(args, workspace_id="workspace-a", expected_desired_graph_id=None,
                expected_desired_realized_projection_id=None, expected_desired_graph_revision=0)
            self.assertTrue(schema.is_valid(unassigned))
            for field in ("expected_desired_graph_id", "expected_desired_realized_projection_id",
                    "expected_desired_graph_revision", "revision", "session_id", "idempotency_key", "draft_id"):
                self.assertFalse(schema.is_valid({k: v for k, v in unassigned.items() if k != field}))
            args["receiver_lifecycle"] = {field: before[field] for field in (
                "current_graph_id", "current_realized_projection_id", "desired_graph_id",
                "desired_realized_projection_id", "desired_graph_revision")}
            selected = await self.call(client, SELECT_TOOL, args)
        self.assertEqual({k: selected[k] for k in first.descriptor()}, first.descriptor())
        self.assertNotEqual(selected["graph_id"], newer.graph_id)
        self.assertEqual(selected["desired_graph_revision"], before["desired_graph_revision"] + 1)
        async with self.client(self.mode) as reader:
            after = (await self.call(reader, "get_workspace", {}))["workspace"]
            desired = await self.call(reader, "get_desired_graph", {})
            revision = await self.call(reader, "get_desired_topology_draft_revision",
                {"draft_id": first.draft_id, "revision": first.revision})
        self.assertEqual(desired["authored_graph_id"], revision["graph_id"])
        self.assertEqual(desired["graph_id"], first.graph_id)
        self.assertEqual(desired["realized_projection_id"], selected["desired_realized_projection_id"])
        self.assertEqual(after["desired_graph_revision"], selected["desired_graph_revision"])
        for key in ("current_graph_id", "current_realized_projection_id"):
            self.assertEqual(after[key], before[key])
        # A deliberate cross-surface replay tests owner parity. No automatic replay in the client.
        path = f"/workspaces/workspace-a/desired-topology-drafts/{first.draft_id}/select"
        body = {k: v for k, v in args.items() if k != "draft_id"}
        replay = await self.http.post(path, json=body)
        self.assertEqual((replay.status_code, replay.json()), (200, selected))
        conflict = await self.http.post(path, json=dict(body, revision=newer.revision))
        self.assertEqual(conflict.status_code, 409)
        actions = [r[0] for r in self.rows("cpk_operation_actions") if r[0]["action_type"] == "select-desired-topology-draft"]
        self.assertEqual([r["payload"] for r in actions], [dict(selected, receiver_lifecycle=args["receiver_lifecycle"])])

    async def test_first_selection_from_unassigned_desired(self):
        workspace_id = "workspace-new"
        WorkspaceCommandService(self.unit_of_work, clock=lambda: NOW, id_factory=lambda: uuid4().hex).create(
            CreateWorkspace(workspace_id, "Fresh workspace", "operator-a", IdempotencyKey(uuid4().hex)))
        self.sessions[workspace_id] = self.start_session(workspace_id)
        first = self.create(workspace=workspace_id, graph=DeploymentGraph("first desired"))
        self.grants[b"valid-token"] = principal(workspace_id)
        scope = {"workspace_id": workspace_id}
        async with self.client(self.mode) as client:
            before = (await self.call(client, "get_workspace", scope))["workspace"]
            self.assertIsNone(before["desired_graph_id"])
            self.assertIsNone(before["desired_realized_projection_id"])
            self.assertEqual(before["desired_graph_revision"], 0)
            arguments = await self.selection_input(first, before)
            receipt = await self.call(client, SELECT_TOOL, {**scope, **arguments})
        async with self.client(self.mode) as reader:
            after = (await self.call(reader, "get_workspace", scope))["workspace"]
            desired = await self.call(reader, "get_desired_graph", scope)
        self.assertEqual(after["desired_graph_revision"], 1)
        self.assertEqual(after["desired_graph_id"], first.graph_id)
        self.assertEqual(desired["realized_projection_id"], receipt["desired_realized_projection_id"])
        self.assertEqual(after["current_graph_id"], before["current_graph_id"])

    async def test_selection_rechecks_permission_and_fences_stale_inputs(self):
        draft = self.create()
        args = await self.selection_input(draft)
        base = self.truth()
        async with self.client(self.mode) as client:
            self.grants[b"valid-token"] = principal(scopes=(PolicyScope.INSTANCE_WORKSPACE_READ,))
            denied = await client.call_tool(SELECT_TOOL, dict(args, workspace_id="workspace-a"))
            self.assertEqual(denied.structured_content["error"]["status"], 403)
            self.grants[b"valid-token"] = principal()
            for changes, status in (({"actor_id": "forged"}, 400), ({"revision": 0}, 400),
                    ({"expected_desired_graph_revision": True}, 400),
                    ({"expected_desired_graph_revision": args["expected_desired_graph_revision"] + 1}, 409),
                    ({"expected_desired_realized_projection_id": "stale-projection"}, 409)):
                with self.subTest(changes=changes):
                    denied = await client.call_tool(SELECT_TOOL, {"workspace_id": "workspace-a", **args, **changes})
                    self.assertTrue(denied.is_error)
                    self.assertEqual(denied.structured_content["error"]["status"], status)
            self.assertEqual(self.truth(), base)
            selected = await self.call(client, SELECT_TOOL, args)
            stale = await client.call_tool(SELECT_TOOL, dict(args, workspace_id="workspace-a", idempotency_key=uuid4().hex))
            self.assertEqual(stale.structured_content["error"]["status"], 409)
            same_target = await self.call(client, SELECT_TOOL, await self.selection_input(draft))
            self.assertEqual(same_target["desired_graph_revision"], selected["desired_graph_revision"] + 1)

    async def approved_admission(self):
        from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
        from control_plane_kit_servers_cpk_server.operations_application import (
            OperationsApplicationFactory, OperationsEffectPorts, OperationsIdFactories)

        def unexpected_effect(*args, **kwargs):
            self.fail("Operator admission attempted an external effect")

        draft = await self.save_once(await self.preview())
        ports = OperationsEffectPorts(None, None, None, HealthReceiverDecoders(()),
            unexpected_effect, disabled_runtime_adapter=unexpected_effect)
        factory = OperationsApplicationFactory(self.unit_of_work, ports,
            OperationsIdFactories(*(lambda: uuid4().hex for _ in range(5))), clock=lambda: NOW)
        self.host.services.update({role: CountedService(owner, self.dispatches)
            for role, owner in factory().services.items()})
        async with self.client(self.mode) as operator:
            workspace = (await self.call(operator, "get_workspace", {}))["workspace"]
            await self.call(operator, SELECT_TOOL, {
                "session_id": self.saved_session_id, "draft_id": draft["draft_id"], "revision": draft["revision"],
                "idempotency_key": uuid4().hex, **{"expected_" + key: workspace[key] for key in
                    ("desired_graph_id", "desired_realized_projection_id", "desired_graph_revision")}})
            workspace = (await self.call(operator, "get_workspace", {}))["workspace"]
            prepared = await self.call(operator, "prepare_deployment", {
                "draft_id": draft["draft_id"], "revision": draft["revision"],
                "title": "Admission reconnect test", "idempotency_key": uuid4().hex,
                "expected_desired_graph_revision": workspace["desired_graph_revision"],
                **{"expected_" + side: {"authored_graph_id": workspace[side + "_graph_id"],
                    "realized_projection_id": workspace[side + "_realized_projection_id"]}
                    for side in ("current", "desired")}})
            self.assertEqual(prepared["status"], "approval-required")
            plan = await self.call(operator, "get_plan_detail", {"plan_id": prepared["plan_id"]})
        args = {"session_id": plan["plan"]["session_id"],
                "plan_id": prepared["plan_id"], "approval_request_id": prepared["approval_request_id"]}
        args["idempotency_key"] = uuid4().hex
        approver = principal(scopes=(PolicyScope.PLAN_APPROVE,))
        self.grants[b"reviewer"] = replace(approver, identity=replace(approver.identity, subject_id="reviewer-a"))
        decision = await self.http.post(f"/workspaces/workspace-a/approvals/{args['approval_request_id']}/decision",
            headers={"Authorization": "Bearer reviewer"}, json={"session_id": args["session_id"],
                "decision": "approved", "idempotency_key": uuid4().hex})
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(self.rows("cpk_execution_requests"), [])
        return args

    async def test_operator_receives_exact_queued_request_before_worker_claim(self):
        args = await self.approved_admission()
        async with self.client(self.mode) as operator:
            receipt = await self.call(operator, "admit_deployment", args)
        (row,), = self.rows("cpk_execution_requests")
        self.assertEqual(receipt["execution_request_id"], row["request_id"])
        self.assertEqual((receipt["workspace_id"], receipt["session_id"], receipt["plan_id"]),
            ("workspace-a", args["session_id"], args["plan_id"]))
        self.assertEqual((row["requested_by"], row["idempotency_key"], row["approval_request_id"]),
            ("operator-a", args["idempotency_key"], args["approval_request_id"]))
        self.assertEqual((receipt["status"], receipt["replayed"]), ("queued", False))
        self.assertEqual(self.rows("cpk_activity_runs"), [])
        self.assertEqual(self.rows("cpk_effect_attempts"), [])

    async def test_admission_reply_lost_after_commit_before_worker_claim(self):
        args = await self.approved_admission()
        lost = await self.assert_transport_loss("admit_deployment", args)
        self.assertEqual((lost.sends, lost.dropped), (1, True))

        # This independent connection is test-owner evidence only. The fresh client
        # below has no access to the queued row or to the lost request ID.
        (request,), = self.rows("cpk_execution_requests")
        self.assertEqual((request["workspace_id"], request["plan_id"], request["status"]),
                         ("workspace-a", args["plan_id"], "queued"))
        self.assertEqual(request["idempotency_key"], args["idempotency_key"])
        self.assertEqual(self.rows("cpk_activity_runs"), [])
        self.assertEqual(self.rows("cpk_effect_attempts"), [])
        committed = self.truth(), self.runtime_truth()
        marker = len(self.dispatches)
        async with self.client(self.mode) as reader:
            views = [
                await self.call(reader, "get_session_detail", {"session_id": args["session_id"]}),
                await self.call(reader, "get_plan_detail", {"plan_id": args["plan_id"]}),
                await self.call(reader, "get_approval_detail", {"approval_id": args["approval_request_id"]}),
            ]
            runs = await self.call(reader, "list_plan_runs", {"plan_id": args["plan_id"]})
            self.assertEqual(runs["items"], [])
            self.assertNotIn(args["idempotency_key"], json.dumps([views, runs]))
            guidance = next(tool.description for tool in (await reader.list_tools()).tools
                            if tool.name == "admit_deployment")
            self.assertIn("submission unknown", guidance)
            self.assertIn("do not resend", guidance)
        self.assertEqual(self.dispatches[marker:], ["read.session-detail", "read.plan-detail",
            "read.approval-detail", "read.plan-runs"])
        self.assertEqual((self.truth(), self.runtime_truth()), committed)

    async def test_lost_selection_reply_observes_pointer_without_resending(self):
        draft = self.create()
        args = await self.selection_input(draft)
        transport = await self.assert_transport_loss(SELECT_TOOL, args)
        self.assertEqual(transport.sends, 1)
        async with self.client(self.mode) as reader:
            desired = await self.call(reader, "get_desired_graph", {})
            workspace = (await self.call(reader, "get_workspace", {}))["workspace"]
        self.assertEqual(desired["graph_id"], draft.graph_id)
        self.assertEqual(workspace["desired_graph_revision"], args["expected_desired_graph_revision"] + 1)
        self.assertEqual(self.dispatches.count("command.desired-topology-draft.select"), 1)

    def ingress_extension(self, base, product, registration_id):
        return {"schema": "registered-product-ingress-extension.v1",
            "base": {key: base[key] for key in ("draft_id", "revision", "graph_id")},
            "runtime_id": "demo-docker",
            "connector": {"node_id": "connector", "product": product, "receiver_id": "a" * 32,
                "provider_socket": "control"},
            "ingress": {"ingress_id": "hello-public", "authority_ref": "hello-public",
                "registration_id": registration_id, "hostname": "hello.example.test",
                "target": {"node_id": "mux", "provider_socket": "internal"},
                "exposure": "https", "lifecycle": "ephemeral"}}

    async def test_extension_revise_bounds_an_inconsistent_owner_receipt(self):
        base = {"draft_id": "draft-a", "revision": 2, "graph_id": "graph-r2"}
        extension = self.ingress_extension(base, self.references["hello"], "fixture-registration")
        args = {"workspace_id": "workspace-a", "session_id": self.sessions["workspace-a"],
            "draft_id": base["draft_id"], "expected_head_revision": 2, "idempotency_key": "receipt",
            "product_recipe": extension, "expected_proposal_commitment": {
                "profile": "registered-product-ingress-extension-public.v1", "sha256": "a" * 64},
            "receiver_lifecycle": {"current_graph_id": "current", "current_realized_projection_id": "projection",
                "desired_graph_id": None, "desired_realized_projection_id": None, "desired_graph_revision": 0}}
        calls = []
        def inconsistent(request):
            calls.append(request.route_id)
            return {"workspace_id": "workspace-a", "draft_id": "another-draft", "revision": 3,
                "graph_id": "fixture-private-result"}
        self.host.services[ControlPlaneServiceRole.PLANNING].handle = inconsistent
        async with self.client(self.mode) as client:
            result = await client.call_tool("revise_desired_topology_draft", args)
            self.assertEqual(calls, ["command.desired-topology-draft.revise"])
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["status"], 503)
            self.assertNotIn("fixture-private-result", str(result.content))
            for invalid in ({**args, "graph": {"name": "x", "nodes": {}, "edges": {}, "runtimes": {}}},
                            {k: v for k, v in args.items() if k != "receiver_lifecycle"}):
                refused = await client.call_tool("revise_desired_topology_draft", invalid)
                self.assertTrue(refused.is_error)
            self.assertEqual(calls, ["command.desired-topology-draft.revise"])

    async def test_complete_graph_create_revise_and_fresh_sdk_readback(self):
        workspace = "workspace-a"
        graph = DEFAULT_GRAPH_CODEC.encode(self.graph("first full graph"))
        revised = DEFAULT_GRAPH_CODEC.encode(self.graph("second full graph"))
        base = {"workspace_id": workspace, "session_id": self.sessions[workspace]}
        create = {**base, "graph": graph, "title": "Full graph", "idempotency_key": "full-create"}
        async with self.client(self.mode) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertIn("revise_desired_topology_draft", sorted(tools))
            first = await self.call(client, "create_desired_topology_draft", create)
            self.assertEqual(first["revision"], 1)
            revise = {**base, "draft_id": first["draft_id"], "expected_head_revision": 1,
                      "idempotency_key": "full-revise", "graph": revised}
            second = await self.call(client, "revise_desired_topology_draft", revise)
            self.assertEqual((second["workspace_id"], second["draft_id"], second["revision"]),
                             (workspace, first["draft_id"], 2))
            self.assertNotEqual(second["graph_id"], first["graph_id"])
            self.assertEqual(await self.call(client, "revise_desired_topology_draft", revise), second)
            refused = await client.call_tool("revise_desired_topology_draft", {**revise, "idempotency_key": "stale"})
            self.assertEqual(refused.structured_content["error"]["status"], 409)
            for change in ({"actor_id": "synthetic-private-canary"}, {"product_recipe": {}},
                           {"graph": {"extra": "synthetic-private-canary"}}):
                refused = await client.call_tool("create_desired_topology_draft", {**create, **change})
                self.assertTrue(refused.is_error)
                self.assertNotIn("synthetic-private-canary", str(refused.content))
        async with self.client(self.mode) as fresh:
            for receipt, authored in ((first, graph), (second, revised)):
                args = {"draft_id": receipt["draft_id"], "revision": receipt["revision"]}
                detail = await self.call(fresh, "get_desired_topology_draft_revision", args)
                http = await self.http.get(f"/workspaces/{workspace}/desired-topology-drafts/{receipt['draft_id']}/revisions/{receipt['revision']}")
                self.assertEqual(detail, http.json())
                with self.unit_of_work() as uow:
                    self.assertEqual(uow.stores.graphs.get(receipt["graph_id"]).graph_descriptor, authored)

    async def test_pre_registered_complete_child_graph_through_standard_sdk(self):
        bundle = json.loads(Path("/tmp/cpk-synthetic-child.json").read_text(encoding="utf-8"))
        workspace, graph = bundle["workspace"], bundle["graph"]
        scope = {"workspace_id": workspace}
        self.assertEqual(len(graph["nodes"]), 8)
        self.assertEqual(len(graph["public_ingresses"]), 3)
        WorkspaceCommandService(self.unit_of_work, clock=lambda: NOW, id_factory=lambda: uuid4().hex).create(
            CreateWorkspace(workspace, "Synthetic child workspace", "operator-a", IdempotencyKey(uuid4().hex)))
        # Authoring requires an already admitted catalogue. This fixture does not
        # qualify the import of configured products through the public MCP tool.
        with self.unit_of_work() as uow:
            for data in bundle["products"]:
                doc = ProductDescriptorCodec().decode_document(data)
                uow.stores.registered_products.register(workspace_id=workspace, descriptor_document=doc,
                    source=InlineDescriptorSource(), imported_by="operator-a", imported_at=NOW)
            uow.commit()
        self.grants[b"valid-token"] = principal(workspace)
        self.grants[b"reader-token"] = principal(workspace, scopes=(PolicyScope.INSTANCE_WORKSPACE_READ,))
        async with self.client(self.mode) as writer:
            state = (await self.call(writer, "get_workspace", scope))["workspace"]
            pins = {key: state[key] for key in ("current_graph_id", "current_realized_projection_id",
                "desired_graph_id", "desired_realized_projection_id", "desired_graph_revision")}
            started = await self.call(writer, "start_operation_session",
                {**scope, "title": "Synthetic child draft", "idempotency_key": "child-start"})
            args = {**scope, "session_id": started["session_id"], "receiver_lifecycle": pins}
            first = await self.call(writer, "create_desired_topology_draft",
                {**args, "graph": graph, "title": "Synthetic child", "idempotency_key": "child-create"})
            amended = {**graph, "name": graph["name"] + " amended"}
            second = await self.call(writer, "revise_desired_topology_draft", {**args, "graph": amended,
                "draft_id": first["draft_id"], "expected_head_revision": 1, "idempotency_key": "child-revise"})
        self.http.headers["Authorization"] = "Bearer reader-token"
        async with self.client(self.mode) as fresh:
            for receipt, expected in ((first, graph), (second, amended)):
                args = {**scope, "draft_id": receipt["draft_id"], "revision": receipt["revision"]}
                detail = await self.call(fresh, "get_desired_topology_draft_revision_metadata", args)
                metadata = {
                    role: [{k: v for k, v in artifact.items() if k != "content"} for artifact in files]
                    for role, node in expected["nodes"].items() if (files := node["configuration_artifacts"])
                }
                self.assertTrue(metadata, "fixture must include at least one configured file")
                self.assertTrue(detail == {**receipt, "kind": "desired-topology-draft-revision-metadata",
                    "configuration_artifacts": metadata}, "exact revision file metadata did not match")
                self.assertFalse("BEGIN PUBLIC KEY" in json.dumps(detail), "metadata read included a file body")
                http = await self.http.get(
                    f"/workspaces/{workspace}/desired-topology-drafts/{receipt['draft_id']}/revisions/{receipt['revision']}/metadata")
                self.assertEqual(http.status_code, 200)
                self.assertTrue(http.json() == detail, "HTTP and MCP metadata reads differ")
                with self.unit_of_work() as uow:
                    self.assertTrue(uow.stores.graphs.get(receipt["graph_id"]).graph_descriptor == expected,
                        "persisted child graph differs from the complete authored input")
            after = (await self.call(fresh, "get_workspace", scope))["workspace"]
            self.assertEqual({key: after[key] for key in pins}, pins)

    async def test_lost_full_graph_revision_reply_submits_once(self):
        draft = self.create()
        graph = DEFAULT_GRAPH_CODEC.encode(self.graph("after interrupted reply"))
        args = {"session_id": self.sessions["workspace-a"], "draft_id": draft.draft_id,
                "expected_head_revision": draft.revision, "idempotency_key": "revise-lost", "graph": graph}
        transport = await self.assert_transport_loss("revise_desired_topology_draft", args)
        self.assertEqual(transport.sends, 1)
        async with self.client(self.mode) as reader:
            observed = await self.call(reader, "get_desired_topology_draft_revision",
                {"draft_id": draft.draft_id, "revision": draft.revision + 1})
        with self.unit_of_work() as uow:
            self.assertEqual(uow.stores.graphs.get(observed["graph_id"]).graph_descriptor, graph)
        self.assertEqual(self.dispatches.count("command.desired-topology-draft.revise"), 1)

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
