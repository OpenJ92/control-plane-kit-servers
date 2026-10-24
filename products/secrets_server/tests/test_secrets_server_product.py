from __future__ import annotations

import json
import os
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from control_plane_kit_core.lifecycle import ResourcePersistence
from control_plane_kit_core.products import (
    ProductDescriptorCodec,
    ProductFamily,
    ProductIdentity,
    ProductInstanceConfiguration,
    RetainedDataMount,
    instantiate_product,
)
from control_plane_kit_core.types import Protocol


ROOT = Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "products" / "secrets_server"
DESCRIPTOR = PRODUCT / "product.cpk.json"
BOOTSTRAP = PRODUCT / "bootstrap.contract.json"
DOCKERFILE = PRODUCT / "Dockerfile"
ENTRYPOINT = PRODUCT / "entrypoint.sh"
SMOKE = ROOT / "scripts" / "secrets_server_image_smoke.sh"
COORDINATES = json.loads(
    (ROOT / "coordinates" / "server-products.json").read_text(encoding="utf-8")
)
SECRETS_PIN = COORDINATES["upstreams"]["control_plane_kit_secrets_commit"]


class SecretsServerProductTests(unittest.TestCase):
    def decode(self):
        return ProductDescriptorCodec().decode_document(DESCRIPTOR.read_bytes())

    def test_descriptor_round_trips_as_external_product_contract(self) -> None:
        document = self.decode()
        product = document.product

        self.assertEqual(
            product.identity,
            ProductIdentity("control-plane-kit", "secrets-server", 1),
        )
        self.assertEqual(product.display_name, "secrets-server")
        self.assertIs(product.product_family, ProductFamily.DATA_SERVICE)
        self.assertEqual(product.image.registry, "ghcr.io")
        self.assertEqual(
            product.image.repository,
            "openj92/control-plane-kit-servers/secrets-server",
        )
        self.assertEqual(
            ProductDescriptorCodec().encode_document(product).content,
            DESCRIPTOR.read_bytes(),
        )

    def test_descriptor_exposes_private_http_and_retained_custody(self) -> None:
        product = self.decode().product
        contract = product.runtime_contract

        self.assertEqual(contract.sockets.provider("control").protocol, Protocol.HTTP)
        self.assertEqual(
            {
                port.provider_socket: port.container_port
                for port in contract.provider_ports
            },
            {"control": 8081},
        )
        self.assertEqual(contract.sockets.requirement_names(), ())
        self.assertEqual(
            contract.retained_data_mounts,
            (RetainedDataMount("provider-data", "/var/lib/cpk-secrets"),),
        )
        self.assertIs(
            contract.lifecycle.data_resource("provider-data").persistence,
            ResourcePersistence.RETAINED,
        )

    def test_root_bootstrap_is_explicit_and_non_recursive(self) -> None:
        product = self.decode().product
        bootstrap = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
        descriptor = DESCRIPTOR.read_text(encoding="utf-8").lower()

        self.assertEqual(product.runtime_contract.secret_deliveries, ())
        self.assertEqual(product.runtime_contract.configuration_artifacts, ())
        self.assertEqual(
            {
                item["environment_name"] for item in bootstrap["bootstrap_files"]
            },
            {"CPK_SECRETS_MASTER_KEY_FILE", "CPK_SECRETS_CREDENTIALS_FILE"},
        )
        self.assertTrue(
            all(item["mode"] == "0400" for item in bootstrap["bootstrap_files"])
        )
        self.assertIn("not recursively resolved", " ".join(bootstrap["runtime_inputs"]))
        self.assertNotIn("fernet", descriptor)
        self.assertNotIn("\"token\":", descriptor)

    def test_image_is_non_root_and_pins_provider_source(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("\nUSER 10006\n", dockerfile)
        self.assertIn('--uid 10006 secrets', dockerfile)
        self.assertIn(
            "control-plane-kit-secrets/archive/"
            f"{SECRETS_PIN}.zip",
            dockerfile,
        )
        self.assertNotIn("CPK_SECRETS_DEVELOPMENT_CREDENTIALS_JSON", dockerfile)
        self.assertNotIn("ENV CPK_SECRETS_MASTER_KEY_FILE", dockerfile)
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("/run/secrets/cpk-secrets/master.key", entrypoint)
        self.assertIn('exec "$@"', entrypoint)

    def test_image_smoke_recreates_provider_against_retained_data(self) -> None:
        smoke = SMOKE.read_text(encoding="utf-8")

        self.assertIn('docker rm -f "$PROVIDER"', smoke)
        self.assertGreaterEqual(smoke.count("start_provider"), 3)
        self.assertIn("resolve-after-restart", smoke)
        self.assertIn('"postgres.password"', smoke)
        self.assertIn("generate_delegation_key", smoke)
        self.assertIn("revoke_version", smoke)
        self.assertIn("--network", smoke)
        self.assertNotIn("-p 127.0.0.1", smoke)
        self.assertNotIn("python3", smoke)
        self.assertIn("cpk.test-run", smoke)
        self.assertIn("docker volume create", smoke)
        gate = (ROOT / "test.sh").read_text(encoding="utf-8")
        self.assertIn("CPK_SECRETS_SMOKE_PROFILE=wrapped-source", gate)
        self.assertIn("CPK_SECRETS_BUILD_IMAGE=1 sh scripts/secrets_server_image_smoke.sh", gate)
        self.assertIn("CPK_SECRETS_SMOKE_PROFILE=published-baseline", gate)
        self.assertIn('CPK_SECRETS_IMAGE="$SECRETS_IMAGE"', gate)

    def test_invalid_smoke_profiles_fail_before_all_docker_calls(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            docker = base / "docker"
            docker.write_text('#!/bin/sh\nprintf called >> "$CPK_TEST_DOCKER_MARKER"\nexit 86\n')
            docker.chmod(0o755)
            marker = base / "called"
            cases = (
                {"CPK_SECRETS_SMOKE_PROFILE": "unknown"},
                {"CPK_SECRETS_BUILD_IMAGE": "unknown"},
                {"CPK_SECRETS_BUILD_CONTROLLER": "unknown"},
                {"CPK_SECRETS_SMOKE_PROFILE": "wrapped-source", "CPK_SECRETS_BUILD_IMAGE": "0"},
                {"CPK_SECRETS_SMOKE_PROFILE": "published-baseline", "CPK_SECRETS_BUILD_IMAGE": "1"},
                {"CPK_SECRETS_BUILD_IMAGE": "0", "CPK_SECRETS_IMAGE": "mutable:tag"},
                {"CPK_SECRETS_BUILD_IMAGE": "0", "CPK_SECRETS_IMAGE": "repo@sha256:invalid"},
            )
            for index, overrides in enumerate(cases):
                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith("CPK_SECRETS_")}
                environment.update(PATH=str(base) + ":/usr/bin:/bin",
                                   CPK_TEST_DOCKER_MARKER=str(marker))
                environment.update(overrides)
                with self.subTest(case=index):
                    result = subprocess.run(["/bin/sh", str(SMOKE)], cwd=ROOT, env=environment,
                                            capture_output=True, text=True, timeout=10, check=False)
                    self.assertFalse(marker.exists(), "invalid profile invoked Docker")
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr, "secrets-server image smoke: invalid profile or build inputs\n")

    def test_descriptor_instantiates_without_provider_implementation(self) -> None:
        product = self.decode().product
        block = instantiate_product(
            product,
            "secrets",
            ProductInstanceConfiguration.from_contract(product.runtime_contract),
        )

        self.assertEqual(block.block_id, "secrets")
        self.assertEqual(block.sockets.provider("control").protocol, Protocol.HTTP)


if __name__ == "__main__":
    unittest.main()
