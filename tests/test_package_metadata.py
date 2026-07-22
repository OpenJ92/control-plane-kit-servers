import ast
from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CORE_PIN = "a04631770efbf59e62b4536cc80a71d42873446d"


class PackageMetadataTests(unittest.TestCase):
    def test_pyproject_names_package_and_pins_core_dependency(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]

        self.assertEqual(project["name"], "control-plane-kit-servers")
        self.assertEqual(project["version"], "0.1.0")
        self.assertIn(
            "control-plane-kit-core @ "
            f"https://github.com/OpenJ92/control-plane-kit/archive/{CORE_PIN}.zip"
            "#subdirectory=control-plane-kit-core",
            project["dependencies"],
        )
        self.assertEqual(project["requires-python"], ">=3.12")

    def test_root_import_is_lightweight_and_exposes_catalogue_entrance(self) -> None:
        sys.path.insert(0, str(SRC))
        try:
            import control_plane_kit_servers

            self.assertEqual(control_plane_kit_servers.__version__, "0.1.0")
            self.assertEqual(control_plane_kit_servers.load_catalogue(), ())
            self.assertNotIn("fastapi", sys.modules)
            self.assertNotIn("httpx", sys.modules)
            self.assertNotIn("control_plane_kit_core", sys.modules)
        finally:
            sys.path.remove(str(SRC))
            sys.modules.pop("control_plane_kit_servers", None)
            sys.modules.pop("control_plane_kit_servers.catalogue", None)

    def test_catalogue_is_empty_immutable_declaration_assembly(self) -> None:
        sys.path.insert(0, str(SRC))
        try:
            from control_plane_kit_servers.catalogue import load_catalogue

            catalogue = load_catalogue()
            self.assertEqual(catalogue, ())
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
            "control_plane_kit_servers.products.hello",
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
