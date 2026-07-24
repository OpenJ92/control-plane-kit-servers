from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_coordinates.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("apply_coordinates", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load coordinate script")
    module = importlib.util.module_from_spec(spec)
    sys.modules["apply_coordinates"] = module
    spec.loader.exec_module(module)
    return module


class CoordinateGenerationTests(unittest.TestCase):
    def test_coordinate_manifest_is_the_source_for_generated_files(self) -> None:
        module = load_script_module()
        coordinates = module.load_coordinates(module.COORDINATES)
        updates = module.generate_updates(coordinates)

        stale = [
            path.relative_to(ROOT).as_posix()
            for path, content in updates.items()
            if path.read_bytes() != content
        ]

        self.assertEqual(stale, [])

    def test_coordinates_drive_package_and_cpk_server_dependency_pins(self) -> None:
        module = load_script_module()
        coordinates = module.load_coordinates(module.COORDINATES)
        cpk_commit = coordinates["upstreams"]["control_plane_kit_commit"]
        interpreters_commit = coordinates["upstreams"][
            "control_plane_kit_interpreters_commit"
        ]

        for path in (module.PYPROJECT, module.CPK_SERVER_DOCKERFILE):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn(
                    "https://github.com/OpenJ92/control-plane-kit/archive/"
                    f"{cpk_commit}.zip",
                    text,
                )
                self.assertIn(
                    "https://github.com/OpenJ92/control-plane-kit-interpreters/"
                    f"archive/{interpreters_commit}.zip",
                    text,
                )


if __name__ == "__main__":
    unittest.main()
