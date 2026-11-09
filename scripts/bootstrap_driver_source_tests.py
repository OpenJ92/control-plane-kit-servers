"""Additive installer imports and normal pure CLI composition at owning source."""
import importlib
import os
from pathlib import Path
import unittest
import json

from bootstrap_driver_imports import REQUIRED_IMPORTS, RUNTIME_DEPENDENCIES
from bootstrap_driver_image_check import normal_cli_plans


class BootstrapDriverSourceTests(unittest.TestCase):
    def test_required_installer_modules_resolve_from_selected_source(self):
        source = Path(os.environ["CPK_STARTUP_SOURCE_ROOT"]).resolve()
        for name in REQUIRED_IMPORTS:
            with self.subTest(module=name):
                path = Path(importlib.import_module(name).__file__).resolve()
                expected = Path("/reviewed-http-sample/secrets/src") if name.startswith("control_plane_kit_secrets.") else source
                self.assertTrue(path.is_relative_to(expected))
        for name in RUNTIME_DEPENDENCIES:
            with self.subTest(dependency=name):
                self.assertIsNotNone(importlib.import_module(name).__file__)

    def test_normal_material_and_bootstrap_cli_plans_compose_without_preparation(self):
        source = Path(os.environ["CPK_STARTUP_SOURCE_ROOT"])
        expected = json.loads((source / "products/cpk_server/bootstrap-driver-cohort.json").read_text())["qualification_public_input_sha256"]
        result = normal_cli_plans("sha256:" + "a" * 64, source, os.environ["CPK_BOOTSTRAP_DRIVER_PUBLIC_INPUT"], expected)
        self.assertTrue(result["managed_website_included"])
        self.assertTrue(result["http_import_policy_plan_passed"])
        self.assertTrue(result["http_generation_policy_plan_refused"])
        self.assertFalse(result["real_material_prepared"])
        self.assertTrue(result["health_sender_mounts_and_dynamic_authority_projected"])
