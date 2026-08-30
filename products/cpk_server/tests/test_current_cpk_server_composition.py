import ast
import importlib
import json
from pathlib import Path
import sys
import tomllib
import unittest

from control_plane_kit_core.operations import (
    operator_command_http_routes,
    operator_read_http_routes,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
SERVER_SOURCE = (
    PRODUCT_SRC / "control_plane_kit_servers_cpk_server" / "server.py"
)
CPK_COMMIT = "99aea011df81b20cdb644749b796e12bc8f829c3"
INTERPRETERS_COMMIT = "851514d1e054d699eded1bd59427f2d67b3896f8"
STALE_OPERATIONS_NAMES = frozenset(
    {
        "GatewayKeyRotationApplicationService",
        "GatewayKeyRotationProgramExecutor",
        "IngressReservationCoordinates",
        "IngressReservationObservation",
        "IngressResourcePresence",
        "IngressTunnelObservation",
        "PublicIngressReservationReleasePlanningService",
        "RetainedIngressDeactivationResult",
    }
)
RETIRED_ROUTE_IDS = frozenset(
    {
        "command.gateway-key-rotation.request",
        "command.gateway-key-rotation.request-approval",
        "command.gateway-key-rotation.decide",
        "command.gateway-key-rotation.advance",
        "read.gateway-key-rotation.list",
        "read.gateway-key-rotation.detail",
        "read.gateway-key-rotation.transitions",
        "command.public-ingress-reservation.release-plan",
        "read.public-ingress-resources",
    }
)
RETIRED_RUNTIME_TOKENS = RETIRED_ROUTE_IDS | {
    "/gateway-key-rotations",
    "/public-ingress-resources",
    "/release-plan",
    "plan_public_ingress_reservation_release",
    "gateway-key-rotation-overlay",
}


class CurrentCpkServerCompositionTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in tuple(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def test_canonical_coordinates_select_accepted_packages(self) -> None:
        coordinates = json.loads(
            (ROOT / "coordinates" / "server-products.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            coordinates["upstreams"]["control_plane_kit_commit"], CPK_COMMIT
        )
        self.assertEqual(
            coordinates["upstreams"]["control_plane_kit_interpreters_commit"],
            INTERPRETERS_COMMIT,
        )

    def test_generated_package_and_image_pins_are_exact(self) -> None:
        pyproject = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        dependencies = "\n".join(pyproject["project"]["dependencies"])
        cpk_dockerfile = (
            ROOT / "products" / "cpk_server" / "Dockerfile"
        ).read_text(encoding="utf-8")
        gateway_dockerfile = (
            ROOT / "products" / "cpk_local_gateway" / "Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertEqual(dependencies.count(CPK_COMMIT), 2)
        self.assertEqual(dependencies.count(INTERPRETERS_COMMIT), 1)
        self.assertEqual(cpk_dockerfile.count(CPK_COMMIT), 2)
        self.assertEqual(cpk_dockerfile.count(INTERPRETERS_COMMIT), 1)
        self.assertEqual(gateway_dockerfile.count(CPK_COMMIT), 1)

    def test_complete_retired_operations_inventory_is_absent(self) -> None:
        tree = ast.parse(
            SERVER_SOURCE.read_text(encoding="utf-8"), filename=str(SERVER_SOURCE)
        )
        observed = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in STALE_OPERATIONS_NAMES
        }
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "control_plane_kit_operations"
            for alias in node.names
            if alias.name in STALE_OPERATIONS_NAMES
        }

        self.assertEqual(observed | imported, set())

    def test_retired_routes_are_absent_from_current_core_language(self) -> None:
        route_ids = {
            route.route_id
            for route in (
                *operator_command_http_routes(),
                *operator_read_http_routes(),
            )
        }

        self.assertEqual(route_ids & RETIRED_ROUTE_IDS, set())

    def test_active_runtime_code_does_not_claim_retired_routes(self) -> None:
        findings = {
            str(path.relative_to(ROOT)): tuple(
                sorted(token for token in RETIRED_RUNTIME_TOKENS if token in source)
            )
            for path in sorted((ROOT / "scripts").iterdir())
            if path.suffix in {".py", ".sh"}
            for source in (path.read_text(encoding="utf-8"),)
            if any(token in source for token in RETIRED_RUNTIME_TOKENS)
        }

        self.assertEqual(findings, {})

    def test_server_imports_against_the_accepted_package_surface(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))
        try:
            try:
                module = importlib.import_module(
                    "control_plane_kit_servers_cpk_server.server"
                )
            except ImportError as error:
                self.fail(f"cpk-server cannot import accepted packages: {error}")
        finally:
            sys.path.remove(str(PRODUCT_SRC))

        self.assertTrue(callable(module._operations_application))
        self.assertTrue(callable(module._cloudflare_ingress_interpreter))

    def test_one_operations_service_map_has_only_current_keywords(self) -> None:
        tree = ast.parse(
            SERVER_SOURCE.read_text(encoding="utf-8"), filename=str(SERVER_SOURCE)
        )
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "cpk_server_services"
        ]

        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg for keyword in calls[0].keywords}
        self.assertNotIn("gateway_key_rotations", keywords)
        self.assertNotIn("ingress_reservation_releases", keywords)
        self.assertIn("gateway_probes", keywords)
        self.assertIn("delegation_signing_keys", keywords)


if __name__ == "__main__":
    unittest.main()
