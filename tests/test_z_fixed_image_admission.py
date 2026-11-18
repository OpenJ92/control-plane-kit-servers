"""Early behavioral red for #191; the actual admission function is the subject."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class FixedImageAdmissionTests(unittest.TestCase):
    def test_initial_witness_accepts_both_qualified_execution_forms(self):
        owner = Path(__file__).resolve().parents[1] / "products/cpk_server/tests"
        with patch.object(sys, "path", [str(owner), *sys.path]):
            from live_docker_receiver_reintroduction import _assert_initial_image
            from test_docker_receiver_reintroduction import SelectedStartImageTests
            fixture = SelectedStartImageTests().fixture
            for form in ("config-valued", "manifest-valued"):
                with self.subTest(form=form):
                    placement, record, container = fixture(expected_role="hello_family", proof_form=form)
                    placement.starting(record.request)
                    placement.observed(record)
                    placement.completed(record)
                    _assert_initial_image(placement.engine, placement, "api")
                    self.assertEqual(placement.nodes["api"], container.id)

    def test_initial_witness_refuses_wrong_image_or_foreign_owner(self):
        owner = Path(__file__).resolve().parents[1] / "products/cpk_server/tests"
        with patch.object(sys, "path", [str(owner), *sys.path]):
            from live_docker_receiver_reintroduction import _assert_initial_image
            from test_docker_receiver_reintroduction import SelectedStartImageTests
            from docker_image_update_placement import PREFIX
            from docker_image_update_ports import FixtureBoundaryFailure
            fixture = SelectedStartImageTests().fixture
            for form in ("config-valued", "manifest-valued"):
                for invalid in ("image", "owner"):
                    with self.subTest(form=form, invalid=invalid):
                        placement, record, container = fixture(expected_role="hello_family", proof_form=form)
                        placement.starting(record.request)
                        placement.observed(record)
                        placement.completed(record)
                        if invalid == "image":
                            container.attrs["Image"] = "sha256:" + "0" * 64
                        else:
                            container.labels[PREFIX + "workspace"] = "foreign"
                        with self.assertRaises(FixtureBoundaryFailure):
                            _assert_initial_image(placement.engine, placement, "api")

    def test_admission_refuses_absent_or_disagreeing_interpreter_without_effects(self):
        owner = Path(__file__).resolve().parents[1] / "products/cpk_server/tests"
        with patch.object(sys, "path", [str(owner), *sys.path]):
            from image_identity_test_material import clients
            from live_docker_image_update import inspect_inputs
            for selected in (None, type("Inspection", (), {"image_id": "sha256:" + "f" * 64})()):
                engine, sdk = clients()
                sdk.inspect_image = lambda reference: selected
                engine.containers = Mock()
                with self.subTest(selected=selected), self.assertRaises(ValueError):
                    inspect_inputs(engine, sdk)
                engine.containers.create.assert_not_called()

    def test_linked_manifest_identity_is_admitted_without_rebasing_config_fixture(self):
        owner = Path(__file__).resolve().parents[1] / "products/cpk_server/tests"
        with patch.object(sys, "path", [str(owner), *sys.path]):
            material = importlib.import_module("image_identity_test_material")
            admission = importlib.import_module("live_docker_image_update")
            engine, sdk = material.clients()
            # Establish genuine input validity before exercising the old boundary.
            for role, selected in material.FIXED.items():
                raw = material.manifest_bytes(role)
                self.assertEqual("sha256:" + hashlib.sha256(raw).hexdigest(),
                                 selected["reference"].split("@")[1])
                self.assertEqual(json.loads(raw)["config"]["digest"], selected["image_id"])
                self.assertNotEqual(engine.images.get(selected["reference"]).id,
                                    selected["image_id"])
            observed = admission.inspect_inputs(engine, sdk)
            self.assertEqual(observed.daemon_id, "daemon-a")
            self.assertEqual(set(observed.images), set(material.FIXED))
            for role, selected in material.FIXED.items():
                proof = observed.images[role]
                self.assertEqual(proof.execution_id, selected["reference"].split("@")[1])
                self.assertEqual(proof.config_digest, selected["image_id"])
                self.assertEqual(proof.proof_form, "manifest-valued")
