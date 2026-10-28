"""Public setup wire composition and bounded partial acknowledgement targets."""
import copy
import importlib
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from dynamic_setup_fixtures import setup_inputs, owner_responses


class DynamicRootSetupTests(unittest.TestCase):
    def exercise(self, fault=None, *, desired_graph="desired-from-read"):
        fixture, plan, root, private, material, intent = setup_inputs(self)
        cli = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_cli")
        progress = fixture.root / "setup-progress"
        workspace = plan["input"]["installation"]["workspace_id"]
        created, granted, permission, managed, assignment = owner_responses(plan, private)
        calls = []
        administration = private["administration"]
        def call(route, *, path_parameters, payload, credential_role):
            calls.append(route)
            self.assertEqual(credential_role, "operator")
            if route.startswith("command."):
                saved = json.loads((progress / "progress.json").read_bytes())
                self.assertEqual(saved["pending"], route)
            if route == "command.workspace-administration.create":
                self.assertEqual(path_parameters, {})
                self.assertEqual(payload, {"workspace_id": workspace,
                    "name": plan["input"]["setup"]["workspace_name"], "metadata": {},
                    "idempotency_key": administration["workspace_creation_idempotency_key"]})
                result = copy.deepcopy(created)
                if fault == "create-identity":
                    result["receipt"]["actor"]["subject_id"] = "different-private-actor"
                return result
            self.assertEqual(path_parameters.get("workspace_id"), workspace)
            if route == "command.workspace-permission.grant":
                self.assertEqual(payload, administration["permission_grants"][0])
                return granted
            if route == "read.workspace-permission":
                self.assertEqual(payload, {"target": private["installer"]})
                return {**permission, "revision": 2} if fault == "permission-read" else permission
            if route == "command.secret-provider.register":
                return {"registration_id": "provider-observed"}
            if route == "read.secret-provider-detail":
                return {"workspace_id": workspace, "secret_provider": {"registration_id": "provider-observed"}}
            if route == "command.runtime-authority.register":
                return {"registration_id": "authority-observed", "workspace_id": workspace,
                    "authority_ref": "root-docker-access", "runtime_kind": "docker", "status": "active"}
            if route == "read.runtime-authority-detail":
                return {"workspace_id": workspace, "runtime_authority": {"registration_id": "authority-observed",
                    "workspace_id": workspace, "authority_ref": "root-docker-access", "runtime_kind": "docker", "status": "active"}}
            if route == "command.managed-runtime-access.grant":
                expected = {key: value for key, value in administration["management_grant"].items()
                    if key != "registration_from"}
                self.assertEqual(payload, {**expected, "registration_id": "authority-observed"})
                if fault == "lost-management-reply":
                    raise TimeoutError("private-setup-transport-canary")
                if fault == "management-registration":
                    return owner_responses(plan, private, registration="different-registration")[3]
                return managed
            if route == "read.managed-runtime-assignment":
                self.assertEqual(payload, {"runtime_id": administration["management_grant"]["runtime_id"],
                    "authority_ref": "root-docker-access"})
                return assignment
            if route == "command.runtime-authority-delivery.register":
                return {"delivery_id": "delivery-observed"}
            if route == "read.runtime-authority-delivery-detail":
                return {"workspace_id": workspace, "runtime_authority_delivery": {"delivery_id": "delivery-observed"}}
            if route == "command.product.import":
                return {"registration_id": "product-observed", "workspace_id": workspace, "status": "active",
                    "reference": ProductReference.from_document(ProductDescriptorCodec().decode_document(
                        payload["descriptor_document"])).descriptor()}
            if route == "read.workspace":
                return {"workspace": {"workspace_id": workspace, "current_graph_id": "current-observed",
                    "desired_graph_id": desired_graph}}
            if route == "read.current-graph":
                return {"graph_id": "current-observed", "assigned": True}
            if route == "read.desired-graph":
                if fault == "desired-assignment":
                    return {"graph_id": desired_graph, "assigned": desired_graph is None}
                if fault == "desired-identity":
                    return {"graph_id": "unrelated-desired", "assigned": desired_graph is not None}
                return {"graph_id": desired_graph, "assigned": desired_graph is not None}
            self.fail("unexpected public setup route")

        with patch.object(cli, "Path", side_effect=lambda path: progress if path == "/tmp/cpk-bootstrap-progress" else Path(path)), \
                patch("socket.create_connection"), \
                patch("control_plane_kit_servers_cpk_server.client.transport.PublicHttpTransport") as transport:
            transport.return_value.call.side_effect = call
            if fault is None:
                result = cli.public_setup(plan, root / "credential")
                self.assertEqual(result["status"], "authenticated-local-setup")
                self.assertEqual([route for route in calls if route.startswith("command.")], plan["setup_routes"])
            else:
                with self.assertRaises(fixture.api.RootBootstrapError) as caught:
                    cli.public_setup(plan, root / "credential")
                self.assertNotIn("private-setup-transport-canary", str(caught.exception))
                self.assertIsNone(caught.exception.__context__)
        self.assertTrue(calls, "dynamic setup never reached its public administration entrance")
        self.assertEqual(calls[0], "command.workspace-administration.create")
        saved = json.loads((progress / "progress.json").read_bytes())
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        raw = (progress / "progress.json").read_bytes()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as stream:
            entry = tarfile.TarInfo("progress.json")
            entry.uid, entry.mode, entry.size = 10001, 0o600, len(raw)
            stream.addfile(entry, io.BytesIO(raw))
        helper = SimpleNamespace(id="setup-helper", attrs={"Image": plan["driver_image_id"]}, labels={},
            get_archive=lambda path: ([archive.getvalue()], {}))
        client = SimpleNamespace(info=lambda: {"ID": "synthetic-engine"},
            containers=SimpleNamespace(get=lambda identity: helper))
        inspected = runtime._setup_progress(client, {"engine_id": "synthetic-engine", "setup_helper_id": helper.id,
            "driver_image_id": plan["driver_image_id"], "labels": {}, "setup_uid": 10001,
            "plan_digest": plan["digest"], "setup_workspace_id": workspace, "setup_routes": plan["setup_routes"]})
        self.assertEqual(inspected, saved)
        self.assertEqual(saved["status"], "complete" if fault is None else "in-progress")
        serialized = json.dumps(saved)
        for secret in ("installer-private", "private-create-key", "private-setup-grant-key", "private-management-key",
                "synthetic-private-installer-token", "different-private-actor", "private-setup-transport-canary"):
            self.assertNotIn(secret, serialized)
        if fault == "create-identity":
            self.assertEqual(calls, ["command.workspace-administration.create"])
        elif fault == "permission-read":
            self.assertEqual(calls[-1], "read.workspace-permission")
            self.assertNotIn("command.secret-provider.register", calls)
        elif fault in ("management-registration", "lost-management-reply"):
            self.assertEqual(calls[-1], "command.managed-runtime-access.grant")
            self.assertNotIn("command.runtime-authority-delivery.register", calls)
            self.assertEqual(calls.count("command.managed-runtime-access.grant"), 1)
            self.assertIn("command.workspace-permission.grant", [value["route"] for value in saved["commands"]])
            if fault == "lost-management-reply":
                self.assertEqual(saved["pending"], "command.managed-runtime-access.grant")
        elif fault in ("desired-assignment", "desired-identity"):
            self.assertEqual(calls[-1], "read.desired-graph")

    def test_dynamic_setup_uses_actual_administration_results_and_exact_registration_binding(self):
        self.exercise()

    def test_fresh_workspace_can_have_no_assigned_desired_graph(self):
        self.exercise(desired_graph=None)

    def test_desired_graph_assignment_and_identity_must_match_authoritative_workspace(self):
        for fault, desired_graph in (("desired-assignment", None), ("desired-identity", None),
                ("desired-assignment", "desired-from-read")):
            with self.subTest(fault=fault, desired_graph=desired_graph):
                self.exercise(fault, desired_graph=desired_graph)

    def test_mismatched_creation_or_permission_readback_stops_before_ordinary_registration(self):
        for fault in ("create-identity", "permission-read"):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_management_mismatch_or_lost_reply_preserves_prior_acknowledgements_without_retry(self):
        for fault in ("management-registration", "lost-management-reply"):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_private_commitment_or_credential_refusal_precedes_http_and_progress(self):
        for fault in ("intent", "credential", "known-nonadmin"):
            with self.subTest(fault=fault):
                fixture, plan, root, private, _, _ = setup_inputs(self)
                if fault == "intent":
                    private["administration"]["workspace_creation_idempotency_key"] = "changed-private-key"
                    fixture.private_write(root / "workspace-intent.json", fixture.api.canonical(private))
                elif fault == "credential":
                    fixture.private_write(root / "credential", b"unknown-private-credential")
                else:
                    policy = json.loads((root / "workspace-authority.json").read_bytes())
                    private["installer"] = policy["known_identities"][1]
                    document = copy.deepcopy(plan["input"])
                    fixture.bind_intent(document, (root / "workspace-authority.json").read_bytes(), private)
                    plan = fixture.plan(document)
                    private["plan_digest"] = plan["digest"]
                    fixture.private_write(root / "plan.json", fixture.api.canonical(plan))
                    fixture.private_write(root / "workspace-intent.json", fixture.api.canonical(private))
                    principals = json.loads((root / "principals.json").read_bytes())
                    principals[0]["subject_id"] = private["installer"]["subject_id"]
                    fixture.private_write(root / "principals.json", fixture.api.canonical(principals))
                cli = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_cli")
                progress = fixture.root / "setup-progress"
                with patch.object(cli, "Path", side_effect=lambda path: progress if path == "/tmp/cpk-bootstrap-progress" else Path(path)), \
                        patch("socket.create_connection") as ready, \
                        patch("control_plane_kit_servers_cpk_server.client.transport.PublicHttpTransport") as transport:
                    with self.assertRaises(fixture.api.RootBootstrapError):
                        cli.public_setup(plan, root / "credential")
                ready.assert_not_called()
                transport.assert_not_called()
                self.assertFalse(progress.exists())
