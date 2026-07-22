import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "products" / "cpk_server"


class CpkServerImageBootstrapTests(unittest.TestCase):
    def test_dockerfile_runs_cpk_server_as_non_root_with_explicit_entrypoint(self) -> None:
        dockerfile = (PRODUCT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("python:3.12-slim", dockerfile)
        self.assertIn("USER cpk", dockerfile)
        self.assertIn("control_plane_kit_servers_cpk_server.server", dockerfile)
        self.assertIn("EXPOSE 8080", dockerfile)
        self.assertNotIn("apt-get", dockerfile)
        self.assertNotIn("latest", dockerfile)

    def test_bootstrap_contract_is_explicit_and_secret_free(self) -> None:
        contract = json.loads((PRODUCT / "bootstrap.contract.json").read_text(encoding="utf-8"))
        rendered = json.dumps(contract, sort_keys=True).lower()

        self.assertEqual(contract["schema"], "cpk-server.bootstrap-contract")
        self.assertEqual(
            [item["name"] for item in contract["environment"]],
            ["CPK_SERVER_MODE", "CPK_CONTROL_AUTH_CONFIGURED", "CPK_PORT"],
        )
        self.assertNotIn("postgres://", rendered)
        self.assertNotIn("token", rendered.replace("auth_configured", ""))
        self.assertNotIn("secret", rendered)

    def test_product_stub_remains_unpublished_until_descriptor_issue(self) -> None:
        descriptor = json.loads((PRODUCT / "product.cpk.json").read_text(encoding="utf-8"))

        self.assertEqual(descriptor["status"], "composition-only-not-published")
        self.assertEqual(descriptor["publishing_issue"], "#816")

    def test_host_side_smoke_script_builds_runs_and_cleans_owned_image(self) -> None:
        smoke = (ROOT / "scripts" / "cpk_server_image_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("docker build", smoke)
        self.assertIn("products/cpk_server/Dockerfile", smoke)
        self.assertIn("docker run", smoke)
        self.assertIn("/health/live", smoke)
        self.assertIn("/health/ready", smoke)
        self.assertIn("/mcp", smoke)
        self.assertIn("org.openj92.project=control-plane-kit-servers", smoke)
        self.assertIn("docker rm -f", smoke)
        self.assertNotIn("docker system prune", smoke)
        self.assertNotIn("docker volume prune", smoke)


if __name__ == "__main__":
    unittest.main()
