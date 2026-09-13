from __future__ import annotations

import importlib.util
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_coordinates.py"
PRODUCT_IMAGE_SCRIPT = ROOT / "scripts" / "product_image_coordinate.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("apply_coordinates", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load coordinate script")
    module = importlib.util.module_from_spec(spec)
    sys.modules["apply_coordinates"] = module
    spec.loader.exec_module(module)
    return module


def load_product_image_script_module():
    spec = importlib.util.spec_from_file_location(
        "product_image_coordinate",
        PRODUCT_IMAGE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load product image coordinate script")
    module = importlib.util.module_from_spec(spec)
    sys.modules["product_image_coordinate"] = module
    spec.loader.exec_module(module)
    return module


class CoordinateGenerationTests(unittest.TestCase):
    def test_sdk_coordinate_is_required_and_canonical(self) -> None:
        module = load_script_module()
        original = json.loads(module.COORDINATES.read_text(encoding="utf-8"))
        key = "control_plane_kit_server_sdk_commit"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coordinates.json"
            for value in (None, "", "main", "a" * 39, "a" * 41, "A" * 40, 123):
                document = copy.deepcopy(original)
                if value is None:
                    document["upstreams"].pop(key)
                else:
                    document["upstreams"][key] = value
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(module.CoordinateError):
                    module.load_coordinates(path)

    def test_changed_upstreams_regenerate_dependencies_without_rewriting_products(self) -> None:
        module = load_script_module()
        coordinates = module.load_coordinates(module.COORDINATES)
        original = module.generate_updates(coordinates)
        changed = copy.deepcopy(coordinates)
        replacements = {
            "control_plane_kit_commit": "a" * 40,
            "control_plane_kit_interpreters_commit": "b" * 40,
            "control_plane_kit_secrets_commit": "c" * 40,
            "control_plane_kit_server_sdk_commit": "d" * 40,
        }
        changed["upstreams"].update(replacements)
        generated = module.generate_updates(changed)
        destinations = {
            module.PYPROJECT: (
                "control_plane_kit_commit", "control_plane_kit_interpreters_commit",
                "control_plane_kit_server_sdk_commit",
            ),
            module.CPK_SERVER_DOCKERFILE: (
                "control_plane_kit_commit", "control_plane_kit_interpreters_commit",
            ),
            module.CPK_LOCAL_GATEWAY_DOCKERFILE: ("control_plane_kit_commit",),
            module.SECRETS_SERVER_DOCKERFILE: ("control_plane_kit_secrets_commit",),
            module.HELLO_SERVER_DOCKERFILE: ("control_plane_kit_server_sdk_commit",),
            module.HTTP_ACTIVE_ROUTER_DOCKERFILE: ("control_plane_kit_server_sdk_commit",),
            module.HTTP_MULTIPLEXER_DOCKERFILE: ("control_plane_kit_server_sdk_commit",),
        }
        for path, content in generated.items():
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                expected = original[path]
                for key in destinations.get(path, ()):
                    expected = expected.replace(
                        coordinates["upstreams"][key].encode(), replacements[key].encode(),
                    )
                self.assertEqual(content, expected)
        for path, keys in destinations.items():
            for key in keys:
                with self.subTest(path=path.name, upstream=key):
                    self.assertIn(replacements[key].encode(), generated[path])
        self.assertEqual(coordinates["products"], changed["products"])

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

    def test_coordinates_drive_every_generated_dependency_pin(self) -> None:
        module = load_script_module()
        coordinates = module.load_coordinates(module.COORDINATES)
        cpk_commit = coordinates["upstreams"]["control_plane_kit_commit"]
        interpreters_commit = coordinates["upstreams"][
            "control_plane_kit_interpreters_commit"
        ]
        secrets_commit = coordinates["upstreams"][
            "control_plane_kit_secrets_commit"
        ]
        self.assertIn(
            "control-plane-kit-server-sdk[verification] @ "
            "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
            f"{coordinates['upstreams']['control_plane_kit_server_sdk_commit']}.zip",
            module.HELLO_SERVER_DOCKERFILE.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "control-plane-kit-server-sdk[verification] @ "
            "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
            f"{coordinates['upstreams']['control_plane_kit_server_sdk_commit']}.zip",
            module.HTTP_MULTIPLEXER_DOCKERFILE.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "control-plane-kit-server-sdk[verification] @ "
            "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
            f"{coordinates['upstreams']['control_plane_kit_server_sdk_commit']}.zip",
            module.HTTP_ACTIVE_ROUTER_DOCKERFILE.read_text(encoding="utf-8"),
        )

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
        gateway_dockerfile = module.CPK_LOCAL_GATEWAY_DOCKERFILE.read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "https://github.com/OpenJ92/control-plane-kit/archive/"
            f"{cpk_commit}.zip",
            gateway_dockerfile,
        )
        secrets_dockerfile = module.SECRETS_SERVER_DOCKERFILE.read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "https://github.com/OpenJ92/control-plane-kit-secrets/archive/"
            f"{secrets_commit}.zip",
            secrets_dockerfile,
        )

    def test_published_product_smokes_resolve_digest_from_coordinates(self) -> None:
        module = load_product_image_script_module()

        self.assertEqual(
            module.image_execution_reference(
                module.COORDINATES,
                "http-active-router",
            ),
            "ghcr.io/openj92/control-plane-kit-servers/http-active-router@"
            "sha256:a58938fdc5c37bfda1b2b0dbd95fc0bf3ba7391f5ce3b8fdfb3956dccf0a01c8",
        )
        self.assertEqual(
            module.image_execution_reference(
                module.COORDINATES,
                "http-multiplexer",
            ),
            "ghcr.io/openj92/control-plane-kit-servers/http-multiplexer@"
            "sha256:7fd15d9477db02c122e834d62074268a3b947b49b31fa3cad10d6a7737ca4fcb",
        )
        for path, product_id in (
            (
                ROOT / "scripts/http_active_router_published_image_smoke.sh",
                "http-active-router",
            ),
            (
                ROOT / "scripts/http_multiplexer_published_image_smoke.sh",
                "http-multiplexer",
            ),
        ):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    f"python3 scripts/product_image_coordinate.py {product_id}",
                    source,
                )
                self.assertNotIn("DIGEST=", source)

    def test_published_product_source_commit_comes_from_coordinates(self) -> None:
        module = load_product_image_script_module()

        self.assertEqual(
            module.product_source_commit(
                module.COORDINATES,
                "cpk-local-gateway",
            ),
            "37cabc3243269e63750cc23b298706e8297b1ee3",
        )

    def test_published_product_source_commit_must_be_canonical(self) -> None:
        module = load_product_image_script_module()
        document = json.loads(module.COORDINATES.read_text(encoding="utf-8"))
        gateway = next(
            product
            for product in document["products"]
            if product["product_id"] == "cpk-local-gateway"
        )
        gateway["source_commit"] = "main"

        with TemporaryDirectory() as directory:
            path = Path(directory) / "coordinates.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                module.ProductCoordinateError,
                "source commit must be canonical",
            ):
                module.product_source_commit(path, "cpk-local-gateway")

    def test_secrets_build_and_published_sources_remain_distinct_and_truthful(self) -> None:
        module = load_product_image_script_module()
        document = json.loads(module.COORDINATES.read_text(encoding="utf-8"))
        secrets_server = next(
            product
            for product in document["products"]
            if product["product_id"] == "secrets-server"
        )

        self.assertEqual(
            secrets_server["source_commit"],
            "68d0da6aed3a383d6bdc284cf4a6a6063a31487e",
        )
        self.assertEqual(
            document["upstreams"]["control_plane_kit_secrets_commit"],
            "68d0da6aed3a383d6bdc284cf4a6a6063a31487e",
        )
        self.assertEqual(
            secrets_server["image"]["digest"],
            "sha256:41aba38eb255779c8a0230724d9cc4fffd1dc5d5dfbfafdc133f1629139edfe7",
        )


if __name__ == "__main__":
    unittest.main()
