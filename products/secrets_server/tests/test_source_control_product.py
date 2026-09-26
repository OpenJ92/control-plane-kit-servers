"""Product-owned framing and full source composition over the actual Secrets ABI."""
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

from control_plane_kit_core.types import Protocol
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductRuntimeContractCodec,
    ProductInstanceConfiguration, instantiate_product,
)
from secrets_control_fixtures import configuration

ROOT = Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "products" / "secrets_server"
PATH = "/etc/cpk/secrets-server/control.json"
ENVIRONMENT = "CPK_SECRETS_CONTROL_CONFIGURATION_FILE"
ACCEPTED_SECRETS = "43b742d1ecb4b7b1fbabb62890a4045afa7a2fec"


class SecretsSourceControlProductTests(unittest.TestCase):
    def owner(self):
        package = "control_plane_kit_servers_secrets_server"
        self.assertIsNotNone(importlib.util.find_spec(package), "required Secrets product interface is missing")
        name = package + ".configuration"
        self.assertIsNotNone(importlib.util.find_spec(name), "required Secrets product configuration is missing")
        owner = importlib.import_module(name)
        for function in ("secrets_control_configuration_artifact", "secrets_source_runtime_contract"):
            self.assertTrue(callable(getattr(owner, function, None)), "required Secrets product function is missing")
        return owner

    def rejected(self, owner, action):
        with self.assertRaises(owner.SecretsProductConfigurationError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Secrets product control configuration is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_artifact_wraps_actual_service_bytes_with_exact_public_framing(self):
        owner = self.owner()
        from control_plane_kit_secrets.control import (
            decode_secrets_control_configuration, encode_secrets_control_configuration,
        )
        value = configuration()
        artifact = owner.secrets_control_configuration_artifact(value)
        self.assertIs(type(artifact), ConfigurationArtifact)
        self.assertEqual(artifact.artifact_id, "secrets-control")
        self.assertEqual(artifact.target_path, PATH)
        self.assertIs(artifact.media_type, ConfigurationMediaType.JSON)
        self.assertIs(artifact.file_mode, ConfigurationFileMode.READ_ONLY)
        self.assertEqual(artifact.content.encode("utf-8"), encode_secrets_control_configuration(value))
        self.assertEqual(decode_secrets_control_configuration(artifact.content.encode("utf-8")), value)
        self.assertEqual(ConfigurationArtifact.from_descriptor(artifact.descriptor()), artifact)

    def test_complete_source_contract_preserves_every_published_runtime_field(self):
        owner = self.owner()
        value = configuration()
        artifact = owner.secrets_control_configuration_artifact(value)
        current = owner.secrets_source_runtime_contract(artifact)
        published = ProductDescriptorCodec().decode_document((PRODUCT / "product.cpk.json").read_bytes()).product
        old = published.runtime_contract
        self.assertEqual(ProductRuntimeContractCodec().decode(current.descriptor()), current)
        self.assertEqual(current.configuration_artifacts, (artifact,))
        self.assertEqual(current.control_surfaces, (value.declaration.surface,))
        self.assertEqual(set(current.capabilities), set(old.capabilities) | {CapabilityName.NODE_CONTROLLABLE})
        self.assertEqual(current.public_environment, old.public_environment)
        self.assertEqual(replace(current, configuration_artifacts=old.configuration_artifacts,
                                 capabilities=old.capabilities,
                                 control_surfaces=old.control_surfaces), old)
        self.assertEqual(old.configuration_artifacts, ())
        self.assertEqual(old.control_surfaces, ())
        self.assertEqual(current.sockets.provider("control").protocol, Protocol.HTTP)
        self.assertEqual({port.provider_socket: port.container_port for port in current.provider_ports},
                         {"control": 8081})
        checks = {check.check_id: check for check in current.verification.checks}
        self.assertEqual(set(checks), {"live", "ready"})
        for kind, check in checks.items():
            self.assertEqual(check.path, "/health/" + kind)
            self.assertEqual(check.expected_statuses, (200,))
            self.assertEqual((check.policy.timeout_seconds, check.policy.interval_seconds,
                              check.policy.maximum_attempts, check.policy.maximum_evidence_bytes),
                             (5.0, 1.0, 10, 16384))
        block = instantiate_product(replace(published, runtime_contract=current), "source-secrets",
                                    ProductInstanceConfiguration.from_contract(current))
        self.assertEqual(block.block_id, "source-secrets")
        self.assertEqual(block.sockets.provider("control").protocol, Protocol.HTTP)

    def test_source_contract_rejects_wrong_artifact_framing_and_malformed_service_input(self):
        owner = self.owner()
        artifact = owner.secrets_control_configuration_artifact(configuration())
        invalid = (
            None, {}, replace(artifact, artifact_id="wrong-control"),
            replace(artifact, target_path="/etc/cpk/other/control.json"),
            replace(artifact, media_type=ConfigurationMediaType.TEXT),
            replace(artifact, file_mode=ConfigurationFileMode.OWNER_READ_ONLY),
            replace(artifact, content='{"profile":"wrong"}'),
        )
        for index, candidate in enumerate(invalid):
            with self.subTest(case=index):
                self.rejected(owner, lambda: owner.secrets_source_runtime_contract(candidate))
        forged = replace(artifact)
        object.__setattr__(forged, "content", "malformed-json-marker")
        self.rejected(owner, lambda: owner.secrets_source_runtime_contract(forged))
        changed = json.loads(artifact.content)
        changed["surface_read"]["issuer"] = "changed-public-issuer"
        stale = replace(artifact)
        object.__setattr__(stale, "content", json.dumps(changed, sort_keys=True, separators=(",", ":")))
        self.rejected(owner, lambda: owner.secrets_source_runtime_contract(stale))

    def test_artifact_factory_rejects_non_service_and_forged_configuration(self):
        owner = self.owner()
        for candidate in (None, {}, b"not-a-typed-configuration"):
            self.rejected(owner, lambda: owner.secrets_control_configuration_artifact(candidate))
        forged = configuration()
        object.__setattr__(forged, "health_issuer", "invalid issuer marker")
        self.rejected(owner, lambda: owner.secrets_control_configuration_artifact(forged))

    def test_recipe_and_separate_public_bootstrap_contract_match_actual_artifact(self):
        owner = self.owner()
        artifact = owner.secrets_control_configuration_artifact(configuration())
        document = json.loads((PRODUCT / "bootstrap.contract.json").read_text())
        public = document["configuration_files"]
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["path"], artifact.target_path)
        self.assertEqual(public[0]["environment_name"], ENVIRONMENT)
        self.assertTrue(public[0]["required"])
        self.assertEqual(public[0]["maximum_bytes"], 65536)
        self.assertEqual(public[0]["mode"], "0444")
        self.assertEqual({item["environment_name"] for item in document["bootstrap_files"]},
                         {"CPK_SECRETS_MASTER_KEY_FILE", "CPK_SECRETS_CREDENTIALS_FILE"})
        self.assertTrue(all(item["mode"] == "0400" for item in document["bootstrap_files"]))
        self.assertIn("not recursively resolved", " ".join(document["runtime_inputs"]))
        recipe = (PRODUCT / "Dockerfile").read_text()
        self.assertIn(ENVIRONMENT + "=" + PATH, recipe)
        self.assertIn("control-plane-kit-secrets/archive/" + ACCEPTED_SECRETS + ".zip", recipe)
        self.assertIn("\nUSER 10006\n", recipe)
        self.assertIn("EXPOSE 8081", recipe)
        self.assertIn("control_plane_kit_secrets.server:app", recipe)
        coordinates = json.loads((ROOT / "coordinates/server-products.json").read_text())
        self.assertEqual(coordinates["upstreams"]["control_plane_kit_secrets_commit"], ACCEPTED_SECRETS)
        published = next(item for item in coordinates["products"] if item["product_id"] == "secrets-server")
        self.assertEqual(published["source_commit"], "68d0da6aed3a383d6bdc284cf4a6a6063a31487e")
        self.assertEqual(published["image"]["digest"],
                         "sha256:41aba38eb255779c8a0230724d9cc4fffd1dc5d5dfbfafdc133f1629139edfe7")

    def test_installed_product_import_uses_accepted_public_codec_without_private_owners(self):
        self.owner()
        probe = '''
import importlib.metadata, json, sys
import control_plane_kit_servers_secrets_server.configuration
actual = json.loads(importlib.metadata.distribution("control-plane-kit-secrets").read_text("direct_url.json"))
assert actual["url"] == "https://github.com/OpenJ92/control-plane-kit-secrets/archive/" + sys.argv[1] + ".zip"
for name in ("fastapi", "docker", "httpx", "control_plane_kit_operations",
             "control_plane_kit_secrets.api", "control_plane_kit_secrets.server",
             "control_plane_kit_secrets.custody", "control_plane_kit_secrets.store",
             "control_plane_kit_secrets.audit", "control_plane_kit_secrets.bootstrap"):
    assert name not in sys.modules, "product import entered private or effect owner"
'''
        result = subprocess.run([sys.executable, "-I", "-B", "-c", probe, ACCEPTED_SECRETS],
                                capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
