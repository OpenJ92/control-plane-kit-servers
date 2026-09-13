import ast
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
COORDINATES = json.loads(
    (ROOT / "coordinates" / "server-products.json").read_text(encoding="utf-8")
)
CPK_PIN = COORDINATES["upstreams"]["control_plane_kit_commit"]
INTERPRETERS_PIN = COORDINATES["upstreams"][
    "control_plane_kit_interpreters_commit"
]
SDK_PIN = COORDINATES["upstreams"]["control_plane_kit_server_sdk_commit"]


class PackageMetadataTests(unittest.TestCase):
    def test_pyproject_names_package_and_pins_cpk_dependencies(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]

        self.assertEqual(project["name"], "control-plane-kit-servers")
        self.assertEqual(project["version"], "0.1.0")
        self.assertIn(
            "control-plane-kit-core @ "
            f"https://github.com/OpenJ92/control-plane-kit/archive/{CPK_PIN}.zip"
            "#subdirectory=control-plane-kit-core",
            project["dependencies"],
        )
        self.assertIn(
            "control-plane-kit-operations @ "
            f"https://github.com/OpenJ92/control-plane-kit/archive/{CPK_PIN}.zip"
            "#subdirectory=control-plane-kit-operations",
            project["dependencies"],
        )
        self.assertIn(
            "control-plane-kit-interpreters[cloudflare,docker,gateway,public-dns] @ "
            "https://github.com/OpenJ92/control-plane-kit-interpreters/archive/"
            f"{INTERPRETERS_PIN}.zip",
            project["dependencies"],
        )
        self.assertFalse(any(item.startswith("fastapi") for item in project["dependencies"]))
        self.assertIn(
            "control-plane-kit-server-sdk[fastapi] @ "
            "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
            f"{SDK_PIN}.zip",
            project["dependencies"],
        )
        self.assertIn("uvicorn>=0.30", project["dependencies"])
        self.assertEqual(project["requires-python"], ">=3.12")

    def test_installed_dependency_coordinates_and_sdk_verification_imports(self) -> None:
        expected = {
            "control-plane-kit-core": {
                "url": f"https://github.com/OpenJ92/control-plane-kit/archive/{CPK_PIN}.zip",
                "subdirectory": "control-plane-kit-core",
            },
            "control-plane-kit-operations": {
                "url": f"https://github.com/OpenJ92/control-plane-kit/archive/{CPK_PIN}.zip",
                "subdirectory": "control-plane-kit-operations",
            },
            "control-plane-kit-interpreters": {
                "url": "https://github.com/OpenJ92/control-plane-kit-interpreters/archive/"
                f"{INTERPRETERS_PIN}.zip",
            },
            "control-plane-kit-server-sdk": {
                "url": "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
                f"{SDK_PIN}.zip",
            },
        }
        checks = textwrap.dedent("""
            import importlib.metadata
            import json
            import sys
            import unittest

            self = unittest.TestCase()
            for name, expected in json.loads(sys.argv[1]).items():
                direct = json.loads(importlib.metadata.distribution(name).read_text("direct_url.json"))
                self.assertEqual(direct["url"], expected["url"])
                self.assertEqual(direct.get("subdirectory"), expected.get("subdirectory"))
            from control_plane_kit_server_sdk.stdlib import install_cpk_control_routes
            from control_plane_kit_server_sdk.health import WorkloadNodeHealthReadDispatcher
            from control_plane_kit_server_sdk.verification import Ed25519WorkloadNodeHealthReadVerifier
            from control_plane_kit_server_sdk.fastapi import install_cpk_control_routes as install_fastapi
            self.assertEqual(importlib.metadata.version("fastapi"), "0.141.1")
            self.assertEqual(importlib.metadata.version("starlette"), "1.6.0")
            self.assertTrue(callable(install_fastapi))
            self.assertTrue(callable(install_cpk_control_routes))
            self.assertTrue(callable(WorkloadNodeHealthReadDispatcher))
            self.assertTrue(callable(Ed25519WorkloadNodeHealthReadVerifier))
        """)
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", checks, json.dumps(expected)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_root_import_is_lightweight_and_exposes_catalogue_entrance(self) -> None:
        # Other owners may legitimately import HTTP clients in the suite process.
        checks = textwrap.dedent("""
            import sys
            import unittest

            sys.path.insert(0, sys.argv[1])
            self = unittest.TestCase()
            import control_plane_kit_servers

            self.assertEqual(control_plane_kit_servers.__version__, "0.1.0")
            catalogue = control_plane_kit_servers.load_catalogue()
            self.assertEqual(
                [item.product_id for item in catalogue],
                [
                    "cloudflared-connector",
                    "cpk-local-gateway",
                    "cpk-server",
                    "cpk-server-docker",
                    "cpk-server-docker-cloudflare",
                    "hello-server",
                    "http-active-router",
                    "http-multiplexer",
                    "postgres-server",
                    "secrets-server",
                ],
            )
            self.assertNotIn("fastapi", sys.modules)
            self.assertNotIn("httpx", sys.modules)
            self.assertNotIn("control_plane_kit_servers_cpk_server.server", sys.modules)
            self.assertNotIn("control_plane_kit_servers_hello_server.server", sys.modules)
            self.assertNotIn(
                "control_plane_kit_servers_http_active_router.server",
                sys.modules,
            )
            self.assertNotIn(
                "control_plane_kit_servers_http_multiplexer.server",
                sys.modules,
            )
            self.assertNotIn(
                "control_plane_kit_servers_cpk_local_gateway.server",
                sys.modules,
            )
        """)
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", checks, str(SRC)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_catalogue_is_completed_immutable_declaration_assembly(self) -> None:
        sys.path.insert(0, str(SRC))
        try:
            from control_plane_kit_servers.catalogue import load_catalogue

            catalogue = load_catalogue()
            self.assertEqual(
                [item.product_id for item in catalogue],
                [
                    "cloudflared-connector",
                    "cpk-local-gateway",
                    "cpk-server",
                    "cpk-server-docker",
                    "cpk-server-docker-cloudflare",
                    "hello-server",
                    "http-active-router",
                    "http-multiplexer",
                    "postgres-server",
                    "secrets-server",
                ],
            )
            self.assertTrue(all(item.status == "completed" for item in catalogue))
            self.assertIsInstance(catalogue, tuple)
        finally:
            sys.path.remove(str(SRC))
            sys.modules.pop("control_plane_kit_servers", None)
            sys.modules.pop("control_plane_kit_servers.catalogue", None)

    def test_package_source_does_not_import_process_or_product_implementations(self) -> None:
        forbidden_imports = {
            "fastapi",
            "httpx",
            "docker",
            "subprocess",
            "control_plane_kit_servers.products.cpk_server",
            "control_plane_kit_servers.products.hello_server",
            "control_plane_kit_servers.products.http_active_router",
            "control_plane_kit_servers.products.http_multiplexer",
            "control_plane_kit_servers.products.cpk_local_gateway",
        }
        findings: list[tuple[Path, str]] = []
        for path in sorted((SRC / "control_plane_kit_servers").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports:
                            findings.append((path, alias.name))
                elif isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
                    findings.append((path, node.module))

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
