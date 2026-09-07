"""Client-owned saved-source transport/restart laws; no backend state machine."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
SAVED_SCHEMA = "cpk.client-saved-invocation.v1"
REQUEST_KEYS = {"draft_id", "revision", "expected_current", "expected_desired",
                "expected_desired_graph_revision", "title", "idempotency_key"}


class SavedClientTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(PRODUCT_SRC))
        self.addCleanup(lambda: sys.path.remove(str(PRODUCT_SRC)))
        from control_plane_kit_servers_cpk_server import client
        self.assertTrue(hasattr(client, "SavedDesiredRevision"), "missing saved desired revision client value")
        self.api = client
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        from test_topology_client import ScriptedTransport, DeterministicIds
        self.ids = DeterministicIds()

        class Transport(ScriptedTransport):
            generation = 1
            no_changes = False
            corrupt_plan = None
            reject_workspace = False

            def call(inner, route_id, **kwargs):
                if route_id == "read.workspace" and inner.reject_workspace:
                    raise AssertionError("historical replay must not read workspace")
                result = super().call(route_id, **kwargs)
                if route_id == "read.workspace":
                    result["workspace"].update(desired_graph_id="graph-desired",
                        desired_realized_projection_id="projection-desired",
                        desired_graph_revision=inner.generation)
                if route_id == "command.deployment.prepare" and inner.no_changes:
                    result.update(status="no-changes")
                    result.pop("approval_request_id")
                if route_id == "read.plan-detail":
                    result["workspace_id"] = "workspace-a"
                    if inner.no_changes:
                        result["plan"].update(base_graph_id="graph-desired",
                            base_realized_projection_id="projection-desired",
                            desired_graph_revision=inner.generation)
                        result["plan"]["payload"]["activities"] = []
                    if inner.corrupt_plan:
                        result["plan"].update({k: v for k, v in inner.corrupt_plan.items() if k != "workspace_id"})
                        if "workspace_id" in inner.corrupt_plan:
                            result["workspace_id"] = inner.corrupt_plan["workspace_id"]
                return result
        self.Transport = Transport

    def client(self, transport, state="state"):
        profile = self.api.ClientProfile("https://cpk.example", "workspace-a",
            {role: self.root / (role + ".token") for role in ("operator", "approver", "worker")},
            self.root / state)
        return self.api.TopologyClient(profile, transport=transport, identity_factory=self.ids)

    def source(self):
        return self.api.SavedDesiredRevision("draft-a", 1)

    def test_exact_saved_body_and_retained_private_request(self):
        transport = self.Transport()
        client = self.client(transport)
        result = client.plan(self.source(), title="Saved intent")
        self.assertEqual(result.status, "planned")
        mutations = [c for c in transport.calls if c["route_id"].startswith("command.")]
        self.assertEqual([c["route_id"] for c in mutations], ["command.deployment.prepare"])
        call = mutations[0]
        body = call["payload"]
        self.assertEqual(set(body), REQUEST_KEYS)
        self.assertEqual((body["draft_id"], body["revision"]), ("draft-a", 1))
        self.assertEqual(body["expected_current"], {"authored_graph_id": "graph-current", "realized_projection_id": "projection-current"})
        self.assertEqual(body["expected_desired"], {"authored_graph_id": "graph-desired", "realized_projection_id": "projection-desired"})
        self.assertEqual(body["expected_desired_graph_revision"], 1)
        self.assertEqual(call["credential_role"], "operator")
        self.assertEqual(call["path_parameters"], {"workspace_id": "workspace-a"})
        journal = client.journal.read(result.operation_ref)
        self.assertEqual(journal["schema"], SAVED_SCHEMA)
        self.assertEqual(journal["desired"], {"draft_id": "draft-a", "revision": 1})
        self.assertEqual(journal["prepare_request"], body)
        self.assertIsNone(journal["pending_request"])
        self.assertNotIn("desired_graph", json.dumps(journal["desired"]))

    def test_lost_response_restart_replays_original_fences_without_workspace_read(self):
        transport = self.Transport(lose_prepare_once=True)
        client = self.client(transport)
        result = client.plan(self.source())
        self.assertEqual(result.status, "attention-required")
        before = client.journal.read(result.operation_ref)
        original = copy.deepcopy(transport.calls[-1])
        self.assertEqual(before["pending_request"]["body"], before["prepare_request"])
        transport.generation = 99
        transport.reject_workspace = True
        restarted = self.client(transport)
        replayed = restarted.resume_prepare(result.operation_ref)
        self.assertEqual(replayed.status, "planned")
        prepares = [c for c in transport.calls if c["route_id"] == "command.deployment.prepare"]
        self.assertEqual(prepares, [original, original])
        self.assertEqual(sum(c["route_id"] == "read.workspace" for c in transport.calls), 1)
        with self.assertRaises(self.api.ClientInputError):
            restarted.resume_prepare(result.operation_ref)
        self.assertEqual(len(prepares), 2)

    def test_fresh_converged_invocation_reads_fresh_fences_and_key_without_select(self):
        transport = self.Transport()
        client = self.client(transport)
        first = client.plan(self.source())
        transport.advanced = True
        transport.no_changes = True
        transport.generation = 8
        second = client.plan(self.source())
        self.assertEqual(second.status, "no-changes")
        self.assertNotEqual(first.operation_ref, second.operation_ref)
        prepares = [c["payload"] for c in transport.calls if c["route_id"] == "command.deployment.prepare"]
        self.assertNotEqual(prepares[0]["idempotency_key"], prepares[1]["idempotency_key"])
        self.assertEqual(prepares[1]["expected_desired_graph_revision"], 8)
        self.assertEqual(prepares[1]["expected_current"], prepares[1]["expected_desired"])
        self.assertEqual(sum(c["route_id"] == "read.workspace" for c in transport.calls), 2)
        self.assertEqual({c["route_id"] for c in transport.calls if c["route_id"].startswith("command.")}, {"command.deployment.prepare"})

    def test_returned_plan_must_correlate_all_submitted_fences(self):
        for field, value in (("workspace_id", "foreign"), ("base_graph_id", "wrong"),
                ("base_realized_projection_id", "wrong"), ("desired_graph_id", "wrong"),
                ("desired_realized_projection_id", "wrong"), ("desired_graph_revision", 2)):
            with self.subTest(field=field):
                transport = self.Transport()
                transport.corrupt_plan = {field: value}
                result = self.client(transport, field).plan(self.source())
                self.assertEqual(result.status, "attention-required")
                self.assertFalse(any(c["route_id"] == "read.approval-detail" for c in transport.calls))
                self.assertEqual([c["route_id"] for c in transport.calls if c["route_id"].startswith("command.")], ["command.deployment.prepare"])

    def test_saved_apply_preserves_exact_destructive_permission_and_result_v1(self):
        transport = self.Transport(destructive=True)
        client = self.client(transport)
        result = client.plan(self.source())
        with self.assertRaises(self.api.ClientInputError):
            client.apply(result.operation_ref, execute_plan="plan-a", approve_plan="plan-a")
        self.assertFalse(any(c["route_id"] == "command.approval.decide" for c in transport.calls))
        completed = client.apply(result.operation_ref, execute_plan="plan-a", approve_destructive_plan="plan-a")
        self.assertEqual(completed.status, "converged")
        self.assertEqual(completed.descriptor()["schema"], result.descriptor()["schema"])
        self.assertEqual(client.journal.read(result.operation_ref)["prepare_request"]["draft_id"], "draft-a")

    def test_closed_journal_rejects_saved_request_corruption_and_catalogue_resume(self):
        transport = self.Transport(lose_prepare_once=True)
        client = self.client(transport)
        result = client.plan(self.source())
        journal = client.journal.read(result.operation_ref)
        from control_plane_kit_servers_cpk_server.client.journal import JournalError
        for change in ({"extra": 1}, {"revision": True}, {"expected_desired": None},
                       {"expected_desired_graph_revision": 0}, {"draft_id": "other"}):
            with self.subTest(change=change):
                altered = copy.deepcopy(journal)
                altered["prepare_request"].update(change)
                with self.assertRaises(JournalError):
                    client.journal.write(result.operation_ref, altered)
        before = len(transport.calls)
        with self.assertRaises(self.api.ClientInputError):
            client.draft_resume(result.operation_ref)
        self.assertEqual(len(transport.calls), before)

    def test_value_bounds_and_cli_source_pairing_before_any_call(self):
        for draft, revision in (("", 1), ("bad\n", 1), ("x" * 513, 1), ("a", True), ("a", 0), ("a", 2**63)):
            with self.subTest(draft=draft, revision=revision), self.assertRaises(self.api.ClientInputError):
                self.api.SavedDesiredRevision(draft, revision)
        from control_plane_kit_servers_cpk_server.client import cli
        invalid = (["--draft", "d"], ["--revision", "1"], ["g.json", "--revision", "1"],
                   ["--resume", "ref", "--revision", "1"], ["g.json", "--draft", "d", "--revision", "1"],
                   ["--draft", "d", "--revision", "01"])
        for args in invalid:
            with self.subTest(args=args), patch.object(cli, "load_profile") as profile, patch.object(cli, "TopologyClient") as factory, contextlib.redirect_stderr(io.StringIO()):
                try:
                    code = cli.main(["--profile", "missing", "plan", *args])
                except SystemExit as error:
                    code = error.code
                self.assertEqual(code, 2)
                profile.assert_not_called()
                factory.assert_not_called()
