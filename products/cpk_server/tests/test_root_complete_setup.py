"""Fourth actual product import through existing setup transport/checkpoints."""
from contextlib import nullcontext
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from root_complete_fixtures import complete_input
from test_root_bootstrap import DRIVER, installation_input


class CompleteRootSetupTests(unittest.TestCase):
    def exercise(self, *, enabled=True, fault=None):
        api = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        cli = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_cli")
        document = complete_input() if enabled else installation_input()
        try:
            plan = api.plan_root_bootstrap(document, driver_image_id=DRIVER)
        except api.RootBootstrapError:
            self.fail("reviewed complete-root public input is not admitted")
        workspace = document["installation"]["workspace_id"]
        imported, commands = [], []
        with TemporaryDirectory() as directory:
            progress = Path(directory) / "progress"
            credential = Path(directory) / "credential"
            credential.write_text("synthetic-operator-credential")
            credential.chmod(0o400)
            with patch.object(cli, "Path", side_effect=lambda path: progress if path == "/tmp/cpk-bootstrap-progress" else Path(path)), \
                    patch("socket.create_connection"), \
                    patch("control_plane_kit_servers_cpk_server.client.transport.PublicHttpTransport") as transport:
                def call(route, *, path_parameters, payload, credential_role):
                    self.assertEqual(credential_role, "operator")
                    self.assertEqual(path_parameters["workspace_id"], workspace)
                    if route.startswith("command."):
                        commands.append(route)
                        saved = json.loads((progress / "progress.json").read_text())
                        self.assertEqual(saved["pending"], route)
                        self.assertEqual(len(saved["commands"]), len(commands) - 1)
                    if route == "command.workspace.create":
                        return {"workspace": {"workspace_id": workspace, "current_graph_id": "current",
                            "desired_graph_id": "desired"}, "replayed": False}
                    if route == "command.product.import":
                        product = payload["descriptor_document"]
                        imported.append(product)
                        if len(imported) == 4 and fault == "interrupted":
                            raise TimeoutError("synthetic transport interruption")
                        reference = ProductReference.from_document(ProductDescriptorCodec().decode_document(product)).descriptor()
                        if len(imported) == 4 and fault == "wrong-reference":
                            reference = ProductReference.from_document(ProductDescriptorCodec().decode_document(imported[0])).descriptor()
                        return {"registration_id": "product-" + str(len(imported)), "workspace_id": workspace,
                            "status": "active", "reference": reference}
                    if route == "command.secret-provider.register": return {"registration_id": "provider"}
                    if route == "command.runtime-authority.register": return {"registration_id": "authority"}
                    if route == "command.runtime-authority-delivery.register": return {"delivery_id": "delivery"}
                    if route == "read.secret-provider-detail":
                        return {"workspace_id": workspace, "secret_provider": {"registration_id": "provider"}}
                    if route == "read.runtime-authority-detail":
                        return {"workspace_id": workspace, "runtime_authority": {"registration_id": "authority"}}
                    if route == "read.runtime-authority-delivery-detail":
                        return {"workspace_id": workspace, "runtime_authority_delivery": {"delivery_id": "delivery"}}
                    if route == "read.workspace": return {"workspace": {"workspace_id": workspace}}
                    if route == "read.current-graph": return {"graph_id": "current", "assigned": True}
                    if route == "read.desired-graph": return {"graph_id": "desired"}
                    self.fail("unexpected public setup route")
                transport.return_value.call.side_effect = call
                expected_error = (TimeoutError if fault == "interrupted" else api.RootBootstrapError)
                with self.assertRaises(expected_error) if fault else nullcontext():
                    result = cli.public_setup(plan, credential)
                profile = transport.call_args.args[0]
                self.assertEqual(profile.credentials,
                    {role: credential for role in ("operator", "approver", "worker")})
                saved = json.loads((progress / "progress.json").read_text())
                expected = plan["setup_products"] if enabled else list(plan["input"]["installation"]["products"].values())
                self.assertEqual(imported, expected)
                self.assertEqual(commands, plan["setup_routes"])
                self.assertEqual(len(imported), 4 if enabled else 3)
                self.assertNotIn("synthetic-operator-credential", json.dumps(saved))
                if fault:
                    self.assertEqual(saved["status"], "in-progress")
                    if fault == "interrupted":
                        self.assertEqual(saved["pending"], "command.product.import")
                        self.assertEqual(len(saved["commands"]), len(plan["setup_routes"]) - 1)
                    else:
                        self.assertIsNone(saved["pending"])
                        self.assertNotIn("reference", saved["commands"][-1])
                else:
                    self.assertEqual(saved["status"], "complete")
                    self.assertIsNone(saved["pending"])
                    self.assertEqual(result["external_endpoint"], "unverified")
                    self.assertEqual(result["commands"], saved["commands"])
                    recorded = [item["reference"] for item in saved["commands"] if item["route"] == "command.product.import"]
                    self.assertEqual(recorded, [ProductReference.from_document(
                        ProductDescriptorCodec().decode_document(item)).descriptor() for item in expected])
                self.assertEqual(transport.return_value.call.call_count,
                    len(commands) + (3 if fault else 6))

    def test_complete_setup_imports_exact_four_products_and_preserves_reference_progress(self):
        self.exercise()

    def test_absent_setup_preserves_original_three_product_path(self):
        self.exercise(enabled=False)

    def test_fourth_product_wrong_reference_cannot_complete_setup(self):
        self.exercise(fault="wrong-reference")

    def test_interrupted_fourth_import_retains_pending_without_redispatch(self):
        self.exercise(fault="interrupted")
