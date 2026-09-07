"""Catalogue composition laws; scripted public replies, no Operations engine."""
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


def overview():
    return {
        "workspace_id": "workspace-a", "kind": "operator-overview",
        "graphs": {
            "current": {"assigned": True, "graph_id": "current", "realized_projection_id": "cp"},
            "desired": {"assigned": True, "graph_id": "graph-old", "realized_projection_id": "dp", "revision": 4,
                        "draft": {"state": "selected", "selected": {"draft_id": "draft-a", "revision": 1, "graph_id": "graph-old"},
                                  "head": {"draft_id": "draft-a", "revision": 2, "graph_id": "graph-new"}}},
            "relation": "diverged"},
        "workflow": {"selection": "none", "session": None, "plan": None, "approval": None,
                     "run_selection": "none", "run": None, "prepared_draft": {"state": "none", "revision": None}},
        "history": {"items": [{"secret": "DO-NOT-PRINT"}]},
        "next_action": {"state": "available", "operation_id": "command.deployment.prepare",
                        "required_scopes": ["instance:workspace:edit", "plan:request"], "coordinates": {"workspace_id": "workspace-a"}}}


class CatalogueTransport:
    def __init__(self, *, lose=None, session_status="open", corrupt=None):
        self.calls = []
        self.lose = lose
        self.session_status = session_status
        self.corrupt = corrupt
        self.observation = overview()
        self.before_mutation = None

    def call(self, route_id, *, path_parameters, payload, credential_role):
        record = {"route_id": route_id, "path_parameters": dict(path_parameters),
                  "payload": copy.deepcopy(dict(payload)), "credential_role": credential_role}
        self.calls.append(record)
        if route_id.startswith("command.") and self.before_mutation:
            self.before_mutation(record)
        if route_id == self.lose:
            self.lose = None
            from control_plane_kit_servers_cpk_server.client import ClientTransportError
            raise ClientTransportError()
        if route_id == "read.workspace":
            result = {"workspace": {"workspace_id": "workspace-a", "desired_graph_id": "graph-old",
                                   "desired_realized_projection_id": "dp", "desired_graph_revision": 4}}
        elif route_id == "command.operation-session.start":
            result = {"session_id": "session-a", "action_id": "start-a", "action_type": "start-operation-session",
                      "ordinal": 1, "status": self.session_status, "replayed": False}
        elif route_id == "read.session-detail":
            result = {"session": {"workspace_id": "workspace-a", "session_id": "session-a", "status": self.session_status}}
        elif route_id == "command.desired-topology-draft.create":
            result = {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 1, "graph_id": "graph-new"}
        elif route_id == "command.desired-topology-draft.revise":
            result = {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": payload["expected_head_revision"] + 1, "graph_id": "graph-new"}
        elif route_id == "command.desired-topology-draft.select":
            result = {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": payload["revision"], "graph_id": "graph-old",
                      "desired_realized_projection_id": "identity-old", "desired_graph_revision": payload["expected_desired_graph_revision"] + 1}
        elif route_id == "read.operator-overview":
            result = copy.deepcopy(self.observation)
        elif route_id == "read.desired-topology-drafts":
            result = {"workspace_id": "workspace-a", "collection": "desired-topology-drafts", "items": [
                {"workspace_id": "workspace-a", "draft_id": "draft-a", "title": "DO-NOT-PRINT", "head_revision": 2,
                 "created_at": "2026-09-07T00:00:00Z", "deleted_at": None}], "next_cursor": None}
        elif route_id == "read.desired-topology-draft-revision":
            result = {"workspace_id": "workspace-a", "kind": "desired-topology-draft-revision", "draft_id": "draft-a", "revision": 1,
                      "graph_id": "graph-old", "created_at": "2026-09-07T00:00:00Z", "graph_descriptor": {"secret": "DO-NOT-PRINT"}}
        else:
            raise AssertionError("unexpected public route " + route_id)
        if self.corrupt:
            result = self.corrupt(route_id, result)
        return result


class CatalogueClientTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(PRODUCT_SRC))
        self.addCleanup(sys.path.remove, str(PRODUCT_SRC))
        from control_plane_kit_servers_cpk_server.client import TopologyClient
        self.assertTrue(callable(getattr(TopologyClient, "draft_save", None)), "missing maintained catalogue client")
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "graph.json"
        self.graph = {"opaque": {"provider": [1, "unchanged"]}, "nodes": []}
        self.path.write_text(json.dumps(self.graph))
        self.sequence = 0

    def tearDown(self):
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith("control_plane_kit_servers_cpk_server."):
                sys.modules.pop(name, None)

    def client(self, transport, state="state", workspace="workspace-a"):
        from control_plane_kit_servers_cpk_server.client import TopologyClient, ClientProfile
        def identity():
            self.sequence += 1
            return str(UUID(int=self.sequence, version=4))
        return TopologyClient(ClientProfile("https://cpk.example", workspace,
                              {role: self.root / (role + ".token") for role in ("operator", "approver", "worker")},
                              self.root / state), transport=transport, identity_factory=identity)

    def journal(self, result, state="state"):
        return json.loads((self.root / state / "invocations" / (result.operation_ref + ".json")).read_text())

    def test_reads_are_bounded_public_observations_without_graph_title_or_mutation(self):
        from control_plane_kit_servers_cpk_server.client.cli import _parser
        for arguments in (("overview",), ("draft", "show", "draft-a", "--revision", "1"),
                          ("draft", "save", str(self.path)), ("draft", "select", "draft-a", "--revision", "1")):
            self.assertIn(_parser().parse_args(["--profile", "test", *arguments]).command, ("overview", "draft"))
        transport = CatalogueTransport()
        client = self.client(transport)
        viewed = client.overview().descriptor()
        self.assertEqual(viewed["observation"]["graphs"]["desired"]["draft"]["selected"]["revision"], 1)
        listed = client.draft_list(limit=1).descriptor()
        shown = client.draft_show("draft-a", 1).descriptor()
        self.assertEqual(listed["observation"][0]["head_revision"], 2)
        self.assertEqual(shown["observation"]["graph_id"], "graph-old")
        self.assertNotIn("DO-NOT-PRINT", json.dumps([viewed, listed, shown]))
        self.assertFalse(any(c["route_id"].startswith("command.") for c in transport.calls))
        self.assertFalse((self.root / "state").exists())

    def test_save_and_revise_persist_before_each_dispatch_and_preserve_opaque_graph(self):
        for kind in ("save", "revise"):
            with self.subTest(kind=kind):
                transport = CatalogueTransport()
                state = kind
                def before(call):
                    files = list((self.root / state / "invocations").glob("*.json"))
                    retained = json.loads(files[0].read_text())
                    self.assertEqual(retained["schema"], "cpk.client-catalogue-invocation.v1")
                    self.assertNotIn('"opaque"', files[0].read_text())
                    if call["route_id"].endswith("start"):
                        self.assertIsNone(retained["start_response"])
                    else:
                        self.assertEqual(retained["start_response"]["session_id"], "session-a")
                        self.assertEqual(retained["draft_request"]["idempotency_key"], call["payload"]["idempotency_key"])
                transport.before_mutation = before
                client = self.client(transport, state)
                result = client.draft_save(self.path, title="PRIVATE-TITLE") if kind == "save" else client.draft_revise("draft-a", self.path, 1)
                self.assertEqual(result.status, "recorded")
                self.assertEqual(result.descriptor()["start_action_id"], "start-a")
                self.assertEqual(result.descriptor()["revision"]["revision"], 1 if kind == "save" else 2)
                mutations = [c for c in transport.calls if c["route_id"].startswith("command.")]
                self.assertEqual(len(mutations), 2)
                self.assertEqual(mutations[-1]["payload"]["graph"], self.graph)
                self.assertEqual(mutations[-1]["payload"]["session_id"], "session-a")
                self.assertTrue(all(c["credential_role"] == "operator" for c in transport.calls))
                self.assertNotIn("PRIVATE-TITLE", json.dumps(result.descriptor()))

    def test_selection_preserves_exact_revision_and_initial_fences_without_prepare(self):
        transport = CatalogueTransport()
        result = self.client(transport).draft_select("draft-a", 1)
        call = transport.calls[-1]
        self.assertEqual(call["payload"], {"session_id": "session-a", "revision": 1,
            "expected_desired_graph_id": "graph-old", "expected_desired_realized_projection_id": "dp",
            "expected_desired_graph_revision": 4, "idempotency_key": self.journal(result)["intent"]["idempotency_key"]})
        self.assertEqual(call["path_parameters"], {"workspace_id": "workspace-a", "draft_id": "draft-a"})
        self.assertEqual(result.descriptor()["selection"], {"desired_realized_projection_id": "identity-old", "desired_graph_revision": 5})
        self.assertFalse(any("deployment" in c["route_id"] for c in transport.calls))

    def test_response_loss_restarts_exact_start_or_draft_request_and_completed_receipt_is_historical(self):
        for route in ("command.operation-session.start", "command.desired-topology-draft.select"):
            with self.subTest(route=route):
                state = route.split(".")[-2]
                transport = CatalogueTransport(lose=route)
                result = self.client(transport, state).draft_select("draft-a", 1)
                self.assertEqual(result.status, "attention-required")
                self.assertEqual(result.exit_code, 4)
                if route.endswith("select"):
                    transport.session_status = "closed"
                retried = self.client(transport, state).draft_resume(result.operation_ref)
                self.assertEqual(retried.status, "recorded")
                calls = [c for c in transport.calls if c["route_id"] == route]
                self.assertEqual(calls[0], calls[1])
                self.assertEqual(sum(c["route_id"] == "read.workspace" for c in transport.calls), 1)
                before = len(transport.calls)
                self.assertEqual(self.client(transport, state).draft_resume(result.operation_ref).status, "recorded")
                self.assertEqual(len(transport.calls), before)

    def test_fresh_closed_session_and_malformed_or_foreign_receipts_stop_before_draft(self):
        cases = [("closed", None), ("cancelled", None)]
        for field, bad in (("ordinal", True), ("replayed", 1), ("action_type", "cancel-operation-session"), ("status", "unknown"), ("action_id", "\nbad")):
            cases.append(("open", lambda route, result, field=field, bad=bad: {**result, field: bad} if route.endswith(".start") else result))
        cases.append(("open", lambda route, result: {"session": {**result["session"], "workspace_id": "foreign"}} if route == "read.session-detail" else result))
        for index, (status, corrupt) in enumerate(cases):
            with self.subTest(index=index):
                transport = CatalogueTransport(session_status=status, corrupt=corrupt)
                result = self.client(transport, str(index)).draft_save(self.path)
                self.assertEqual(result.status, "attention-required")
                self.assertFalse(any(c["route_id"].startswith("command.desired") for c in transport.calls))

    def test_stale_denial_and_overflow_never_rebase_or_replace_session(self):
        from control_plane_kit_servers_cpk_server.client import ClientTransportError, ClientInputError
        def deny(route, result):
            if route.endswith(".select"):
                raise ClientTransportError()
            return result
        transport = CatalogueTransport(corrupt=deny)
        result = self.client(transport).draft_select("draft-a", 1)
        self.assertEqual(result.status, "attention-required")
        self.assertEqual(sum(c["route_id"].endswith(".start") for c in transport.calls), 1)
        self.assertEqual(sum(c["route_id"] == "read.workspace" for c in transport.calls), 1)
        fresh = CatalogueTransport()
        with self.assertRaises(ClientInputError):
            self.client(fresh, "overflow").draft_revise("draft-a", self.path, 2**63 - 1)
        self.assertEqual(fresh.calls, [])

    def test_changed_file_target_and_corrupt_journal_deny_resume_without_mutation(self):
        from control_plane_kit_servers_cpk_server.client import ClientInputError, JournalError
        transport = CatalogueTransport(lose="command.desired-topology-draft.create")
        result = self.client(transport).draft_save(self.path)
        before = len(transport.calls)
        self.path.write_text('{"changed":true}')
        self.assertEqual(self.client(transport).draft_resume(result.operation_ref).status, "attention-required")
        self.assertEqual(len(transport.calls), before)
        with self.assertRaises((ClientInputError, JournalError)):
            self.client(transport, workspace="foreign").draft_resume(result.operation_ref)
        path = self.root / "state" / "invocations" / (result.operation_ref + ".json")
        value = json.loads(path.read_text())
        value["intent"]["unexpected"] = "bad"
        path.write_text(json.dumps(value))
        with self.assertRaises(JournalError):
            self.client(transport).draft_resume(result.operation_ref)
        self.assertEqual(len(transport.calls), before)

    def test_overview_literal_relations_preserve_unavailable_and_reject_malformed(self):
        from control_plane_kit_servers_cpk_server.client import ClientInputError
        transport = CatalogueTransport()
        value = transport.observation
        value["graphs"]["relation"] = "unavailable"
        value["graphs"]["desired"]["revision"] = None
        value["graphs"]["desired"]["draft"] = {"state": "unavailable", "selected": None, "head": None}
        value["workflow"].update(selection="unavailable", run_selection="unavailable", prepared_draft={"state": "unavailable", "revision": None})
        value["next_action"] = {"state": "unavailable", "operation_id": None, "required_scopes": []}
        self.assertEqual(self.client(transport).overview().descriptor()["observation"]["graphs"]["relation"], "unavailable")
        for mutation in (
            lambda v: v["graphs"].update(relation="invented"),
            lambda v: v["graphs"]["current"].update(realized_projection_id=None),
            lambda v: v["workflow"].update(session={"session_id": "partial", "status": "open"}),
            lambda v: v["next_action"].update(operation_id="command.deployment.execute"),
        ):
            with self.subTest(mutation=mutation):
                transport.observation = copy.deepcopy(value)
                mutation(transport.observation)
                with self.assertRaises(ClientInputError):
                    self.client(transport).overview()
