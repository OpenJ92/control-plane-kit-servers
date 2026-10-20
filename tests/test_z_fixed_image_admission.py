"""Early behavioral red for #191; the actual admission function is the subject."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class FixedImageAdmissionTests(unittest.TestCase):
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
