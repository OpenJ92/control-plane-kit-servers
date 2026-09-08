import ast
import importlib
import json
from pathlib import Path
import sys
import tomllib
import unittest
from unittest.mock import patch

from control_plane_kit_core.operations import (
    ControlPlaneServiceRole,
    operator_command_http_routes,
    operator_read_http_routes,
)
from control_plane_kit_operations.cpk_server import cpk_server_services
from control_plane_kit_operations.saved_deployment_preparation import SavedDeploymentPreparationService


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
SERVER_SOURCE = (
    PRODUCT_SRC / "control_plane_kit_servers_cpk_server" / "server.py"
)
CPK_COMMIT = "f12f735ed8e349117775f7e6839b0b312c86c30e"
INTERPRETERS_COMMIT = "d31637404c3c3a03fec9fe8bff0c3c0d25143085"
PUBLIC_DEPLOYMENT_COMMAND_ROUTES = frozenset(
    {
        "command.deployment.prepare",
        "command.approval.decide",
        "command.deployment.admit",
        "command.run.claim",
        "command.run.start",
        "command.deployment.execute",
        "command.graph.advance-current",
    }
)
PUBLIC_DEPLOYMENT_READ_ROUTES = frozenset(
    {
        "read.current-graph",
        "read.desired-graph",
        "read.plan-detail",
        "read.approval-detail",
        "read.plan-runs",
        "read.run-events",
    }
)
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

    def test_public_deployment_prepare_is_installed_and_configured(self) -> None:
        command_routes = {
            route.route_id: route for route in operator_command_http_routes()
        }
        read_routes = {
            route.route_id: route for route in operator_read_http_routes()
        }
        self.assertEqual(
            PUBLIC_DEPLOYMENT_COMMAND_ROUTES - command_routes.keys(),
            set(),
        )
        self.assertEqual(
            PUBLIC_DEPLOYMENT_READ_ROUTES - read_routes.keys(),
            set(),
        )

        sys.path.insert(0, str(PRODUCT_SRC))
        try:
            from control_plane_kit_servers_cpk_server import (
                create_cpk_server_composition,
            )

            composition = create_cpk_server_composition()
        finally:
            sys.path.remove(str(PRODUCT_SRC))

        route = composition.http_api.route("command.deployment.prepare")
        binding = next(
            item
            for item in composition.handoff.command_parity.commands
            if item.http_route_id == route.route_id
        )
        self.assertEqual(
            (
                route.path_template,
                route.service_role,
                binding.operation_id,
                binding.mcp_tool_name,
                binding.service_role,
            ),
            (
                "/workspaces/{workspace_id}/deployments/prepare",
                ControlPlaneServiceRole.PLANNING,
                "deployment.prepare",
                "prepare_deployment",
                ControlPlaneServiceRole.PLANNING,
            ),
        )

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
        self.assertEqual(
            {"planning", "approval", "operations", "desired_graphs"} - keywords,
            set(),
        )

        planning = object()
        approval = object()
        operations = object()
        desired_graphs = object()
        deployment_program = object()
        unit_of_work_factory = lambda: None
        with patch(
            "control_plane_kit_operations.cpk_server.DeploymentProgram",
            return_value=deployment_program,
        ) as constructor:
            services = cpk_server_services(
                unit_of_work_factory=unit_of_work_factory,
                planning=planning,
                approval=approval,
                admission=object(),
                lifecycle=object(),
                execution=object(),
                operations=operations,
                desired_graphs=desired_graphs,
            )

        saved_preparations = constructor.call_args.kwargs["saved_preparations"]
        self.assertIsInstance(saved_preparations, SavedDeploymentPreparationService)
        self.assertIs(saved_preparations._unit_of_work_factory, unit_of_work_factory)
        self.assertIs(saved_preparations._operations, operations)
        constructor.assert_called_once_with(
            operations,
            desired_graphs,
            planning,
            approval,
            saved_preparations=saved_preparations,
        )
        self.assertIs(
            services[ControlPlaneServiceRole.PLANNING]._deployment_program,
            deployment_program,
        )


    def test_bootstrap_installs_real_catalogue_service_on_public_command_routes(self) -> None:
        from control_plane_kit_core.identity import PrincipalKind, WorkspaceGrant
        from control_plane_kit_core.policies import PolicyScope
        from control_plane_kit_operations.cpk_server import CpkServerApplicationError
        from control_plane_kit_operations.desired_topology_drafts import DesiredTopologyDraftCommandService

        sys.path.insert(0, str(PRODUCT_SRC))
        self.addCleanup(sys.path.remove, str(PRODUCT_SRC))
        module = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        from control_plane_kit_servers_cpk_server.boundary import CpkServerServiceRequest
        config = module.CpkServerBootstrapConfiguration.from_environment({
            "CPK_SERVER_MODE": "execution-capable", "CPK_CONTROL_AUTH_CONFIGURED": "true",
            "CPK_RUNTIME_INTERPRETERS": "none", "CPK_PORT": "8080",
            **{name: "postgresql://cpk:cpk@db/cpk" for name in (
                "CPK_WORKPLACE_DATABASE_URL", "CPK_ACTIVITY_HISTORY_DATABASE_URL",
                "CPK_OBSERVER_STATE_DATABASE_URL", "CPK_GRAPH_TOPOLOGY_DATABASE_URL")}})
        principal = module.static_development_principal(
            subject_id="operator-a", kind=PrincipalKind.OPERATOR,
            workspace_grants=(WorkspaceGrant("workspace-a", (PolicyScope.INSTANCE_WORKSPACE_EDIT,)),))
        with patch.object(module, "_install_operations_schema", return_value=None), patch.object(
            module.psycopg, "connect", side_effect=AssertionError("unexpected database use")
        ) as connect:
            application = module._operations_application(config)
            for surface in ("http", "mcp"):
                for command in ("create", "revise", "select"):
                    with self.subTest(surface=surface, command=command):
                        request = CpkServerServiceRequest(
                            surface, "command.desired-topology-draft." + command,
                            ControlPlaneServiceRole.PLANNING,
                            {"workspace_id": "workspace-a", "draft_id": "draft-a"}, {}, principal)
                        with self.assertRaises(CpkServerApplicationError) as caught:
                            application.handle(request)
                        self.assertEqual(caught.exception.status, 400)
            connect.assert_not_called()
        planning = application.services[ControlPlaneServiceRole.PLANNING]
        drafts = planning._desired_topology_drafts
        self.assertIsInstance(drafts, DesiredTopologyDraftCommandService)
        self.assertIs(drafts._uow, planning._desired_graphs._unit_of_work_factory)
        self.assertIs(drafts._clock, module._clock)
        self.assertIs(drafts._id, module._id)


if __name__ == "__main__":
    unittest.main()
