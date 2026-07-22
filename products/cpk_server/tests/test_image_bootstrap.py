import importlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "products" / "cpk_server"
PRODUCT_SRC = PRODUCT / "src"
STORE_ENVIRONMENT = [
    "CPK_WORKPLACE_DATABASE_URL",
    "CPK_ACTIVITY_HISTORY_DATABASE_URL",
    "CPK_OBSERVER_STATE_DATABASE_URL",
    "CPK_GRAPH_TOPOLOGY_DATABASE_URL",
]


class CpkServerImageBootstrapTests(unittest.TestCase):
    def test_dockerfile_runs_cpk_server_as_non_root_with_explicit_entrypoint(self) -> None:
        dockerfile = (PRODUCT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("python:3.12-slim", dockerfile)
        self.assertIn("USER cpk", dockerfile)
        self.assertIn("control_plane_kit_servers_cpk_server.server", dockerfile)
        self.assertIn("control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/", dockerfile)
        self.assertIn("control-plane-kit-operations @ https://github.com/OpenJ92/control-plane-kit/archive/", dockerfile)
        self.assertIn("fastapi>=0.115", dockerfile)
        self.assertIn("uvicorn>=0.30", dockerfile)
        self.assertIn("COPY products/cpk_server/src ./products/cpk_server/src", dockerfile)
        self.assertNotIn("COPY products/cpk_server ./products/cpk_server", dockerfile)
        self.assertNotIn("COPY catalogue", dockerfile)
        self.assertNotIn("COPY src ./src", dockerfile)
        self.assertIn("EXPOSE 8080", dockerfile)
        self.assertNotIn("apt-get", dockerfile)
        self.assertNotIn("latest", dockerfile)

    def test_bootstrap_contract_is_explicit_and_secret_free(self) -> None:
        contract = json.loads((PRODUCT / "bootstrap.contract.json").read_text(encoding="utf-8"))
        rendered = json.dumps(contract, sort_keys=True).lower()

        self.assertEqual(contract["schema"], "cpk-server.bootstrap-contract")
        self.assertEqual(
            [item["name"] for item in contract["environment"]],
            [
                "CPK_SERVER_MODE",
                "CPK_CONTROL_AUTH_CONFIGURED",
                "CPK_PORT",
                *STORE_ENVIRONMENT,
            ],
        )
        self.assertNotIn("postgres://", rendered)
        self.assertNotIn("token", rendered.replace("auth_configured", ""))
        self.assertNotIn("secret", rendered)
        self.assertIn("never echoed by readiness", rendered)

    def test_bootstrap_requires_store_endpoints_but_does_not_echo_them(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))
        try:
            server_module = importlib.import_module(
                "control_plane_kit_servers_cpk_server.server"
            )
            environ = {
                "CPK_SERVER_MODE": "execution-capable",
                "CPK_CONTROL_AUTH_CONFIGURED": "true",
                "CPK_PORT": "8080",
                "CPK_WORKPLACE_DATABASE_URL": "postgres://user:pass@workspace/db",
                "CPK_ACTIVITY_HISTORY_DATABASE_URL": "postgres://user:pass@activity/db",
                "CPK_OBSERVER_STATE_DATABASE_URL": "postgres://user:pass@observer/db",
                "CPK_GRAPH_TOPOLOGY_DATABASE_URL": "postgres://user:pass@graph/db",
            }

            config = server_module.CpkServerBootstrapConfiguration.from_environment(
                environ
            )
            with self.assertRaisesRegex(
                server_module.BootstrapConfigurationError,
                "CPK_GRAPH_TOPOLOGY_DATABASE_URL is required",
            ):
                server_module.CpkServerBootstrapConfiguration.from_environment(
                    {
                        key: value
                        for key, value in environ.items()
                        if key != "CPK_GRAPH_TOPOLOGY_DATABASE_URL"
                    }
                )

            self.assertEqual(set(config.store_endpoints), set(STORE_ENVIRONMENT))
            self.assertNotIn("postgres://", repr(config.process_configuration()))
        finally:
            sys.path.remove(str(PRODUCT_SRC))
            for name in list(sys.modules):
                if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                    "control_plane_kit_servers_cpk_server."
                ):
                    sys.modules.pop(name, None)

    def test_hosted_process_is_fastapi_over_operations_boundary(self) -> None:
        source = (
            PRODUCT_SRC / "control_plane_kit_servers_cpk_server" / "server.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from fastapi import FastAPI, Request", source)
        self.assertIn("uvicorn.run", source)
        self.assertIn("CpkServerOperationsApplication", source)
        self.assertIn("cpk_server_services", source)
        self.assertIn("PostgresUnitOfWork", source)
        self.assertNotIn("BaseHTTPRequestHandler", source)
        self.assertNotIn("ThreadingHTTPServer", source)
        self.assertNotIn("_DemoService", source)

    def test_product_descriptor_is_now_published_contract_data(self) -> None:
        descriptor = json.loads((PRODUCT / "product.cpk.json").read_text(encoding="utf-8"))

        self.assertEqual(descriptor["schema"], "control-plane-kit.product")
        self.assertEqual(descriptor["product"]["identity"]["name"], "cpk-server")
        self.assertNotIn("publishing_issue", descriptor)

    def test_host_side_smoke_script_builds_runs_and_cleans_owned_image(self) -> None:
        smoke = (ROOT / "scripts" / "cpk_server_image_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("localhost/control-plane-kit-servers/cpk-server:local", smoke)
        self.assertIn("docker build", smoke)
        self.assertIn("postgres:16-alpine", smoke)
        self.assertIn("products/cpk_server/Dockerfile", smoke)
        self.assertIn("docker run", smoke)
        self.assertIn("CPK_WORKPLACE_DATABASE_URL", smoke)
        self.assertIn("CPK_ACTIVITY_HISTORY_DATABASE_URL", smoke)
        self.assertIn("CPK_OBSERVER_STATE_DATABASE_URL", smoke)
        self.assertIn("CPK_GRAPH_TOPOLOGY_DATABASE_URL", smoke)
        self.assertIn("/health/live", smoke)
        self.assertIn("/health/ready", smoke)
        self.assertIn("/mcp", smoke)
        self.assertIn("Mcp-Method: resources/read", smoke)
        self.assertIn("Mcp-Method: tools/call", smoke)
        self.assertIn("ready response leaked store endpoint", smoke)
        self.assertIn("org.openj92.project=control-plane-kit-servers", smoke)
        self.assertIn("docker rm -f", smoke)
        self.assertIn("docker network rm", smoke)
        self.assertNotIn("docker system prune", smoke)
        self.assertNotIn("docker volume prune", smoke)

    def test_published_image_smoke_uses_ghcr_digest_without_rebuilding(self) -> None:
        smoke = (ROOT / "scripts" / "cpk_server_published_image_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:", smoke)
        self.assertIn("docker pull", smoke)
        self.assertIn("CPK_SERVER_BUILD_IMAGE=0", smoke)
        self.assertIn("scripts/cpk_server_image_smoke.sh", smoke)
        self.assertNotIn("docker build", smoke)


if __name__ == "__main__":
    unittest.main()
