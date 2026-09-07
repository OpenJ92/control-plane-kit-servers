"""Bounded report laws over scripted owning public envelopes."""
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
ROOT_KEYS = {"schema", "workspace_id", "status", "atomic_snapshot", "provider_freshness",
             "elapsed_seconds", "limits", "calls", "operations", "latest_overview"}
OP_KEYS = {"operation_ref", "state", "requested", "session", "association", "plan", "approval", "runs", "issues"}


class ReportTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(PRODUCT_SRC))
        self.addCleanup(sys.path.remove, str(PRODUCT_SRC))
        from control_plane_kit_servers_cpk_server import client
        self.assertTrue(callable(getattr(client.TopologyClient, "report", None)), "missing bounded public report")
        self.api = client
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        from test_topology_client import ScriptedTransport, DeterministicIds
        from test_topology_client_catalogue import overview

        class Transport(ScriptedTransport):
            corrupt = None
            cursor = None
            run_status = "succeeded"
            unavailable = None

            def call(inner, route_id, **kwargs):
                if route_id == inner.unavailable:
                    raise client.ClientTransportError()
                special = {
                    "read.session-detail": {"workspace_id": "workspace-a", "kind": "session-detail", "session": {
                        "workspace_id": "workspace-a", "session_id": "session-a", "status": "closed", "title": "SECRET-TITLE",
                        "metadata": {"deployment_prepare_source": "saved-revision.v1", "deployment_prepare_saved_draft_id": "draft-a",
                                     "deployment_prepare_saved_revision": "1", "deployment_prepare_saved_graph_id": "graph-desired",
                                     "deployment_prepare_intent_sha256": "DO-NOT-PRINT", "private": "http://10.0.0.1/SECRET"}}},
                    "read.desired-topology-draft-revision": {"workspace_id": "workspace-a", "kind": "desired-topology-draft-revision",
                        "draft_id": "draft-a", "revision": 1, "graph_id": "graph-desired", "created_at": "2026-09-07T00:00:00Z", "graph": "SECRET-GRAPH"},
                    "read.plan-runs": {"workspace_id": "workspace-a", "kind": "plan-runs", "limit": 2,
                        "items": [{"run_id": "run-a", "plan_id": "plan-a", "status": inner.run_status}], "next_cursor": inner.cursor},
                    "read.run-events": {"workspace_id": "workspace-a", "kind": "run-events", "limit": 10,
                        "items": [{"event_id": "event-a", "run_id": "run-a", "ordinal": 1, "event_type": "step_uncertain",
                                   "activity_id": "activity-a", "payload": {"credential": "DO-NOT-PRINT"}, "failure": "SECRET"}], "next_cursor": None},
                    "read.operator-overview": overview(),
                }
                if route_id in special:
                    inner.calls.append({"route_id": route_id, **copy.deepcopy(kwargs)})
                    result = special[route_id]
                else:
                    result = super().call(route_id, **kwargs)
                if route_id == "read.workspace":
                    result["workspace"].update(desired_graph_id="graph-desired", desired_realized_projection_id="projection-desired", desired_graph_revision=1)
                if route_id == "read.plan-detail":
                    result.update(workspace_id="workspace-a", kind="plan-detail")
                    result["plan"]["status"] = "planned"
                if route_id == "read.approval-detail":
                    result.update(workspace_id="workspace-a", kind="approval-detail")
                    result["approval"]["plan_id"] = "plan-a"
                if inner.corrupt:
                    result = inner.corrupt(route_id, result)
                return result
        self.transport = Transport()
        self.client = client.TopologyClient(client.ClientProfile("https://cpk.example", "workspace-a",
            {role: self.root / (role + ".token") for role in ("operator", "approver", "worker")}, self.root / "state"),
            transport=self.transport, identity_factory=DeterministicIds())
        self.operation = self.client.plan(client.SavedDesiredRevision("draft-a", 1))
        self.assertEqual(self.operation.status, "planned")
        self.transport.calls.clear()

    def test_provenance_association_and_separate_latest_overview_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        value = self.client.report([self.operation.operation_ref]).descriptor()
        self.assertEqual(set(value), ROOT_KEYS)
        self.assertEqual(value["schema"], "cpk.client-report.v1")
        self.assertFalse(value["atomic_snapshot"])
        self.assertEqual(value["provider_freshness"], "unknown")
        row = value["operations"][0]
        self.assertEqual(set(row), OP_KEYS)
        self.assertEqual(row["requested"]["data"]["provenance"], "transport-provenance")
        self.assertEqual(row["requested"]["data"]["revision"], 1)
        self.assertEqual(row["association"]["state"], "matched")
        self.assertEqual(row["session"]["data"]["server_reported_saved_metadata"]["revision"], "1")
        self.assertEqual(row["runs"]["data"][0]["events"]["data"][0]["event_type"], "step_uncertain")
        self.assertEqual(value["latest_overview"]["data"]["graphs"]["desired"]["draft"]["head"]["revision"], 2)
        self.assertNotIn("revision", value["latest_overview"]["data"]["graphs"]["current"])
        self.assertEqual(self.transport.calls[-1]["route_id"], "read.operator-overview")
        self.assertTrue(all(c["route_id"].startswith("read.") and c["credential_role"] == "operator" for c in self.transport.calls))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        text = json.dumps(value)
        for forbidden in ("DO-NOT-PRINT", "SECRET", "http://10.0.0.1", "idempotency_key", "intent_sha256", "current_revision"):
            self.assertNotIn(forbidden, text)

    def test_mismatch_and_required_foreign_correlations_fail_closed(self):
        cases = (("read.desired-topology-draft-revision", "graph_id", "wrong"),
                 ("read.plan-detail", "workspace_id", "foreign"),
                 ("read.approval-detail", "plan_id", "foreign"),
                 ("read.session-detail", "session_id", None),
                 ("read.plan-runs", "plan_id", "foreign"),
                 ("read.run-events", "run_id", None))
        for route, field, replacement in cases:
            with self.subTest(route=route):
                def corrupt(actual, value):
                    if actual == route:
                        target = value
                        if route == "read.approval-detail": target = value["approval"]
                        if route == "read.session-detail": target = value["session"]
                        if route in {"read.plan-runs", "read.run-events"}: target = value["items"][0]
                        if replacement is None: target.pop(field)
                        else: target[field] = replacement
                    return value
                self.transport.corrupt = corrupt
                value = self.client.report([self.operation.operation_ref]).descriptor()
                self.assertEqual(value["status"], "attention-required")
                self.assertTrue(value["operations"][0]["issues"])
                if route == "read.desired-topology-draft-revision":
                    self.assertEqual(value["operations"][0]["association"]["state"], "mismatch")

    def test_missing_history_and_uncertain_runs_never_become_convergence(self):
        missing = str(UUID(int=999, version=4))
        self.transport.unavailable = "read.session-detail"
        self.transport.run_status = "uncompensated_failure"
        value = self.client.report([missing, self.operation.operation_ref]).descriptor()
        self.assertEqual(value["operations"][0]["state"], "unavailable")
        self.assertEqual(value["operations"][1]["session"]["state"], "unavailable")
        self.assertEqual(value["operations"][1]["runs"]["data"][0]["status"], "uncompensated_failure")
        self.assertNotIn("converged", json.dumps(value))

    def test_single_pages_and_scheduling_budget_include_latest_overview(self):
        self.transport.cursor = {"opaque": "not-followed"}
        value = self.client.report([self.operation.operation_ref]).descriptor()
        self.assertEqual(value["operations"][0]["runs"]["state"], "truncated")
        self.assertEqual(sum(c["route_id"] == "read.plan-runs" for c in self.transport.calls), 1)
        from control_plane_kit_servers_cpk_server.client import report as report_module
        self.transport.calls.clear()
        with patch.object(report_module, "monotonic", side_effect=[0, *([61] * 100)]):
            exhausted = self.client.report([self.operation.operation_ref]).descriptor()
        self.assertEqual(exhausted["latest_overview"]["state"], "truncated")
        self.assertEqual(exhausted["calls"], 0)
        self.assertEqual(self.transport.calls, [])
        self.assertLessEqual(len(json.dumps(value).encode()), 262144)

    def test_explicit_ref_bound_and_closed_limits_before_reads(self):
        for refs in ([], [self.operation.operation_ref] * 2, [str(UUID(int=i, version=4)) for i in range(5)], ["bad"]):
            with self.subTest(refs=refs), self.assertRaises((self.api.ClientInputError, self.api.JournalError)):
                self.client.report(refs)
        self.assertEqual(self.transport.calls, [])
        value = self.client.report([self.operation.operation_ref]).descriptor()
        self.assertEqual(value["limits"], {"operations": 4, "calls": 32, "pages_per_collection": 1,
            "runs_per_plan": 2, "events_per_run": 10, "scheduling_seconds": 60, "output_bytes": 262144})
        self.assertLessEqual(value["calls"], 32)

    def test_file_and_catalogue_transport_provenance_stay_distinct(self):
        path = self.root / "private-graph.json"
        path.write_text('{"opaque": "SECRET-GRAPH"}')
        file_operation = self.client.plan(path)
        from test_topology_client_catalogue import CatalogueTransport
        self.client.transport = CatalogueTransport()
        catalogue_operation = self.client.draft_save(path, title="SECRET-TITLE")
        self.client.transport = self.transport
        self.transport.calls.clear()
        value = self.client.report([file_operation.operation_ref, catalogue_operation.operation_ref]).descriptor()
        file_row, catalogue_row = value["operations"]
        self.assertEqual(file_row["requested"]["data"]["source"], "file")
        self.assertIsNone(file_row["requested"]["data"]["revision"])
        requested = catalogue_row["requested"]["data"]
        self.assertEqual(requested["source"], "catalogue")
        self.assertIsNone(requested["revision"])
        self.assertEqual(requested["receipt_revision"], {"draft_id": "draft-a", "revision": 1, "graph_id": "graph-new"})
        self.assertNotIn(str(path), json.dumps(value))
        self.assertNotIn("SECRET", json.dumps(value))
        self.assertTrue(all(call["route_id"].startswith("read.") for call in self.transport.calls))

    def test_maximum_shape_is_finite_and_cli_renders_same_closed_envelope(self):
        refs = [self.operation.operation_ref]
        for _ in range(3):
            refs.append(self.client.plan(self.api.SavedDesiredRevision("draft-a", 1)).operation_ref)
        def expand(route, value):
            if route == "read.plan-runs":
                value["items"] = [{"run_id": "run-" + str(i), "plan_id": "plan-a", "status": "running"} for i in range(2)]
            if route == "read.run-events":
                run_id = self.transport.calls[-1]["path_parameters"]["run_id"]
                value["items"] = [{"event_id": "event-" + str(i), "run_id": run_id, "ordinal": i + 1,
                                   "event_type": "step_started", "activity_id": "activity-" + str(i)} for i in range(10)]
            return value
        self.transport.corrupt = expand
        self.transport.calls.clear()
        value = self.client.report(refs).descriptor()
        self.assertEqual(value["calls"], 29)
        self.assertEqual(len(value["operations"]), 4)
        self.assertEqual(sum(len(run["events"]["data"]) for row in value["operations"] for run in row["runs"]["data"]), 80)
        self.assertLess(len(json.dumps(value).encode()), 262144)
        from control_plane_kit_servers_cpk_server.client import cli
        from control_plane_kit_servers_cpk_server.client import report as report_module
        import contextlib
        import io
        outputs = []
        with patch.object(cli, "load_profile", return_value=self.client.profile), patch.object(cli, "TopologyClient", return_value=self.client), patch.object(report_module, "monotonic", return_value=0):
            for suffix in ([], ["--json"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = cli.main(["--profile", "private", "report", refs[0], *suffix])
                self.assertEqual(code, 0)
                outputs.append(json.loads(output.getvalue()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(set(outputs[0]), ROOT_KEYS)

    def test_valid_unicode_identifiers_trigger_bounded_output_truncation(self):
        refs = [self.operation.operation_ref]
        for _ in range(3):
            refs.append(self.client.plan(self.api.SavedDesiredRevision("draft-a", 1)).operation_ref)
        def expand(route, value):
            if route == "read.plan-runs":
                value["items"] = [{"run_id": "run-" + str(i), "plan_id": "plan-a", "status": "running"} for i in range(2)]
            if route == "read.run-events":
                run_id = self.transport.calls[-1]["path_parameters"]["run_id"]
                value["items"] = [{"event_id": "😀" * 500 + str(i), "run_id": run_id, "ordinal": i + 1,
                                   "event_type": "step_started", "activity_id": "😀" * 500} for i in range(10)]
            return value
        self.transport.corrupt = expand
        self.transport.calls.clear()
        value = self.client.report(refs).descriptor()
        self.assertEqual(value["calls"], 29)
        self.assertEqual(value["status"], "attention-required")
        self.assertEqual(value["latest_overview"], {"state": "truncated", "data": None})
        self.assertTrue(all(row["state"] == "truncated" and row["issues"] == ["output-truncated"] for row in value["operations"]))
        encoded = json.dumps(value).encode()
        self.assertLessEqual(len(encoded), 262144)
        self.assertNotIn(b"\\ud83d", encoded)
        self.assertTrue(all(c["route_id"].startswith("read.") for c in self.transport.calls))
