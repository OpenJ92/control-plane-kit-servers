import ast
import importlib
from pathlib import Path
import sys
import unittest

from control_plane_kit_core.operations import (
    ControlPlaneServiceRole,
    CpkServerEntrypointHandoffContract,
    EntrypointCompositionPolicy,
    ProcessStatePolicy,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
SERVER_SOURCE = PRODUCT_SRC / "control_plane_kit_servers_cpk_server" / "server.py"


class CpkServerProcessCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def test_product_local_law_cards_assign_813_owned_laws(self) -> None:
        import json

        cards = json.loads(
            (ROOT / "products" / "cpk_server" / "law-cards" / "extract-f-813.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(cards["schema"], "cpk-server.extract-f-law-cards")
        self.assertEqual(cards["issue"], "#813")
        self.assertEqual(
            [card["law"] for card in cards["law_cards"]],
            [
                "behavior.execution-mode-requires-auth-configuration",
                "behavior.execution-mutations-require-identity-replay-and-conflict",
                "behavior.observer-mutation-updates-observer-state",
                "behavior.replacing-targets-clears-stale-active-target",
            ],
        )
        self.assertTrue(
            all(card["owner"] == "control-plane-kit-servers/cpk_server" for card in cards["law_cards"])
        )

    def test_composition_root_consumes_core_handoff_and_one_program_boundary(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerProcessConfiguration,
            create_cpk_server_composition,
        )

        composition = create_cpk_server_composition(
            CpkServerProcessConfiguration.execution_capable(
                authentication_required=True
            )
        )

        self.assertIsInstance(composition.handoff, CpkServerEntrypointHandoffContract)
        self.assertEqual(
            composition.handoff.composition_policy,
            EntrypointCompositionPolicy.ONE_DEPLOYMENT_PROGRAM,
        )
        self.assertEqual(
            composition.handoff.state_policy,
            ProcessStatePolicy.PROCESS_GLOBALS_ARE_NOT_TRUTH,
        )
        self.assertIs(composition.program, composition.handoff.program)
        self.assertIs(composition.http_api, composition.handoff.http_api)
        self.assertIs(composition.mcp, composition.handoff.mcp)
        self.assertEqual(
            composition.service_binding(ControlPlaneServiceRole.PLANNING).service_name,
            "planning-service",
        )
        self.assertEqual(composition.command_identity_policy, "single-application-boundary")

    def test_execution_capable_composition_requires_auth_configuration(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerCompositionError,
            CpkServerProcessConfiguration,
            create_cpk_server_composition,
        )

        with self.assertRaisesRegex(CpkServerCompositionError, "requires authentication"):
            create_cpk_server_composition(
                CpkServerProcessConfiguration.execution_capable(
                    authentication_required=False
                )
            )

        local = create_cpk_server_composition(CpkServerProcessConfiguration.local_read_only())
        self.assertFalse(local.configuration.execution_enabled)

    def test_observer_and_target_mutation_is_process_state_not_graph_truth(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerProcessState

        state = CpkServerProcessState(targets=("blue", "green"), active_target="blue")
        observed = state.record_observer("obs-a", {"status": "ready"})
        switched = observed.switch_active_target("green")
        replaced = switched.replace_targets(("green", "purple"))
        cleared = switched.replace_targets(("purple",))

        self.assertEqual(state.observers, ())
        self.assertEqual(observed.observers[0].observer_id, "obs-a")
        self.assertEqual(switched.active_target, "green")
        self.assertEqual(replaced.active_target, "green")
        self.assertIsNone(cleared.active_target)
        self.assertEqual(cleared.graph_truth_policy, "process-state-never-owns-graph-truth")

    def test_unknown_targets_fail_closed(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerProcessState,
            UnknownTargetError,
        )

        state = CpkServerProcessState(targets=("blue",), active_target="blue")

        with self.assertRaisesRegex(UnknownTargetError, "unknown target"):
            state.switch_active_target("green")

    def test_root_catalogue_import_does_not_import_cpk_server_product(self) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        try:
            import control_plane_kit_servers

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
            self.assertNotIn("control_plane_kit_servers_cpk_server", sys.modules)
            self.assertNotIn("control_plane_kit_servers_hello_server", sys.modules)
            self.assertNotIn(
                "control_plane_kit_servers_http_active_router",
                sys.modules,
            )
            self.assertNotIn(
                "control_plane_kit_servers_cpk_local_gateway",
                sys.modules,
            )
            self.assertNotIn(
                "control_plane_kit_servers_http_multiplexer",
                sys.modules,
            )
        finally:
            sys.path.remove(str(ROOT / "src"))
            sys.modules.pop("control_plane_kit_servers", None)
            sys.modules.pop("control_plane_kit_servers.catalogue", None)

    def test_core_import_does_not_import_cpk_server_product(self) -> None:
        import control_plane_kit_core

        self.assertIsNotNone(control_plane_kit_core.CpkServerEntrypointHandoffContract)
        self.assertNotIn("control_plane_kit_servers_cpk_server", sys.modules)

    def test_hello_product_cannot_satisfy_cpk_server_laws(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("control_plane_kit_servers_hello")

    def test_server_composes_distinct_executor_and_observer_with_shared_fold(self) -> None:
        tree = ast.parse(SERVER_SOURCE.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_operations_application"
        )
        assignments = {
            node.targets[0].id: node.value
            for node in function.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
        }
        constructors = {
            name: value
            for name, value in assignments.items()
            if _call_name(value.func)
            in {
                "EffectAttemptFoldService",
                "EffectAttemptStartService",
                "EffectAttemptReconciliationService",
            }
        }

        self.assertEqual(
            {_call_name(call.func) for call in constructors.values()},
            {
                "EffectAttemptFoldService",
                "EffectAttemptStartService",
                "EffectAttemptReconciliationService",
            },
        )
        adapter_name = next(
            name
            for name, call in assignments.items()
            if _call_name(call.func) == "_activity_adapter"
        )
        observer_assignments = [
            (name, call)
            for name, call in assignments.items()
            if _call_name(call.func) == "_runtime_observer"
        ]
        self.assertEqual(
            len(observer_assignments),
            1,
            "cpk-server must compose one observer separately from execution",
        )
        if len(observer_assignments) != 1:
            return
        observer_name, observer_call = observer_assignments[0]
        self.assertNotEqual(adapter_name, observer_name)
        adapter_call = assignments[adapter_name]
        self.assertGreaterEqual(len(adapter_call.args), 4)
        self.assertEqual(len(observer_call.args), 1)
        if len(adapter_call.args) < 4 or len(observer_call.args) != 1:
            return
        self.assertEqual(_name(adapter_call.args[0]), "config")
        self.assertEqual(_name(observer_call.args[0]), _name(adapter_call.args[0]))
        adapter_provider = _name(adapter_call.args[3])
        observer_keywords = {
            item.arg: item.value for item in observer_call.keywords
        }
        self.assertEqual(set(observer_keywords), {"secret_provider"})
        self.assertEqual(
            _name(observer_keywords["secret_provider"]),
            adapter_provider,
        )
        provider_assignments = [
            name
            for name, call in assignments.items()
            if _call_name(call.func) == "_secret_provider_composition"
        ]
        self.assertEqual(provider_assignments, [adapter_provider])
        fold_name = next(
            name
            for name, call in constructors.items()
            if _call_name(call.func) == "EffectAttemptFoldService"
        )
        start_name = next(
            name
            for name, call in constructors.items()
            if _call_name(call.func) == "EffectAttemptStartService"
        )
        reconciliation = next(
            call
            for call in constructors.values()
            if _call_name(call.func) == "EffectAttemptReconciliationService"
        )
        self.assertEqual(
            [_name(argument) for argument in reconciliation.args[1:]],
            [observer_name, fold_name],
        )

        coordinator = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and _call_name(node.func) == "ExecutionCoordinator"
        )
        keywords = {item.arg: item.value for item in coordinator.keywords}
        self.assertEqual(_name(keywords["adapter"]), adapter_name)
        self.assertNotIn("observer", keywords)
        self.assertEqual(_name(keywords["start_service"]), start_name)
        self.assertEqual(_name(keywords["fold_service"]), fold_name)
        self.assertEqual(
            _name(keywords["reconciliation_service"]),
            next(
                name
                for name, call in constructors.items()
                if _call_name(call.func) == "EffectAttemptReconciliationService"
            ),
        )
        id_factories = {
            constructor: ast.dump(
                next(item.value for item in call.keywords if item.arg == "id_factory")
            )
            for constructor, call in (
                (_call_name(call.func), call)
                for call in constructors.values()
                if _call_name(call.func) in {"EffectAttemptFoldService", "EffectAttemptStartService"}
            )
        }
        lifecycle = assignments["lifecycle"]
        id_factories["RunLifecycleCommandService"] = ast.dump(
            next(item.value for item in lifecycle.keywords if item.arg == "id_factory")
        )
        id_factories["ExecutionCoordinator"] = ast.dump(keywords["id_factory"])
        self.assertEqual(
            set(id_factories),
            {
                "EffectAttemptFoldService",
                "EffectAttemptStartService",
                "ExecutionCoordinator",
                "RunLifecycleCommandService",
            },
        )
        self.assertEqual(len(set(id_factories.values())), 4)


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _name(node: ast.expr) -> str:
    return node.id if isinstance(node, ast.Name) else ""


if __name__ == "__main__":
    unittest.main()
