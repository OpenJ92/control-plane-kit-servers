import ast
import asyncio
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_kit_core.identity import (
    AuthenticatedPrincipal,
    PrincipalIdentity,
    PrincipalKind,
)
from control_plane_kit_core.operations import (
    ControlPlaneServiceRole,
    CpkServerEntrypointHandoffContract,
    EntrypointCompositionPolicy,
    ProcessStatePolicy,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
SERVER_SOURCE = PRODUCT_SRC / "control_plane_kit_servers_cpk_server" / "server.py"


class ProcessCredentialVerifier:
    def __init__(self) -> None:
        self.credentials = []

    def authenticate(self, credential: bytes) -> AuthenticatedPrincipal:
        self.credentials.append(credential)
        if credential != b"valid-token":
            raise ValueError("credential rejected")
        return AuthenticatedPrincipal(
            PrincipalIdentity(
                issuer="https://identity.openj92.dev",
                subject_id="operator-jacob",
                kind=PrincipalKind.OPERATOR,
            )
        )


class ProcessRecordingService:
    def __init__(self) -> None:
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        values = {**request.path_parameters, **request.payload}
        limit = values.get("limit", 50)
        return {
            "schema": "cpk.test.run-events-page",
            "workspace_id": values["workspace_id"],
            "run_id": values["run_id"],
            "limit": limit,
            "items": [
                {
                    "event_id": f"event-{limit}",
                    "ordinal": 1,
                }
            ],
            "next_cursor": None,
        }


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

    def test_fastapi_run_event_limit_is_typed_and_matches_mcp_readback(self) -> None:
        app, reads, verifier = self._process_app()

        http_status, http_body = _asgi_json(
            app,
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query=b"limit=100",
            headers=((b"authorization", b"Bearer valid-token"),),
        )
        mcp_status, mcp_body = _asgi_json(
            app,
            method="POST",
            path="/mcp",
            headers=(
                (b"accept", b"application/json, text/event-stream"),
                (b"authorization", b"Bearer valid-token"),
                (b"content-type", b"application/json"),
                (b"mcp-method", b"resources/read"),
                (b"mcp-protocol-version", b"2025-06-18"),
            ),
            body=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "events-a",
                    "method": "resources/read",
                    "params": {
                        "name": "read.run-events",
                        "arguments": {
                            "workspace_id": "workspace-a",
                            "run_id": "run-a",
                            "limit": 100,
                        },
                    },
                }
            ).encode("utf-8"),
        )

        self.assertEqual((http_status, mcp_status), (200, 200))
        self.assertEqual(http_body, mcp_body["result"])
        self.assertEqual(
            [request.payload for request in reads.requests],
            [
                {"limit": 100},
                {
                    "workspace_id": "workspace-a",
                    "run_id": "run-a",
                    "limit": 100,
                },
            ],
        )
        self.assertEqual(reads.requests[0].route_id, "read.run-events")
        self.assertEqual(reads.requests[0].surface, "http")
        self.assertEqual(
            reads.requests[0].path_parameters,
            {"workspace_id": "workspace-a", "run_id": "run-a"},
        )
        self.assertEqual(verifier.credentials, [b"valid-token", b"valid-token"])

    def test_fastapi_run_event_query_defaults_and_rejects_invalid_before_dispatch(self) -> None:
        app, reads, _ = self._process_app()
        status, body = _asgi_json(
            app,
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            headers=((b"authorization", b"Bearer valid-token"),),
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["limit"], 50)
        self.assertEqual(reads.requests[0].payload, {})

        cases = (
            ("duplicate", b"limit=100&limit=1"),
            ("malformed-text", b"limit=one"),
            ("malformed-float", b"limit=1.0"),
            ("below-range", b"limit=0"),
            ("above-range", b"limit=101"),
            ("unknown", b"unexpected=value"),
        )
        for title, query in cases:
            with self.subTest(title=title):
                app, reads, _ = self._process_app()
                status, body = _asgi_json(
                    app,
                    method="GET",
                    path="/workspaces/workspace-a/runs/run-a/events",
                    query=query,
                    headers=((b"authorization", b"Bearer valid-token"),),
                )

                self.assertEqual(status, 400)
                self.assertEqual(
                    body,
                    {"error": {"message": "invalid query parameters", "status": 400}},
                )
                self.assertEqual(reads.requests, [])

    def test_fastapi_query_rejection_preserves_auth_precedence_and_redaction(self) -> None:
        app, reads, verifier = self._process_app()
        protected = b"provider_message=registry.example.com%2Fprivate%2Fsecret"

        status, body = _asgi_json(
            app,
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query=protected,
            headers=((b"authorization", b"Bearer invalid-token"),),
        )

        self.assertEqual(status, 401)
        self.assertEqual(
            body,
            {"error": {"message": "invalid credential", "status": 401}},
        )
        self.assertNotIn("registry.example.com", repr(body))
        self.assertNotIn("private", repr(body))
        self.assertNotIn("secret", repr(body))
        self.assertEqual(reads.requests, [])
        self.assertEqual(verifier.credentials, [b"invalid-token"])

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

    def test_server_composes_attempt_services_with_one_adapter_and_shared_fold(self) -> None:
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
            [adapter_name, fold_name],
        )

        coordinator = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and _call_name(node.func) == "ExecutionCoordinator"
        )
        keywords = {item.arg: item.value for item in coordinator.keywords}
        self.assertEqual(_name(keywords["adapter"]), adapter_name)
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

    def _process_app(self):
        import control_plane_kit_servers_cpk_server.server as server_module
        from control_plane_kit_servers_cpk_server import CpkServerProcessConfiguration

        reads = ProcessRecordingService()
        services = {
            role: (
                reads
                if role is ControlPlaneServiceRole.READS
                else ProcessRecordingService()
            )
            for role in ControlPlaneServiceRole
        }
        config = SimpleNamespace(
            process_configuration=lambda: CpkServerProcessConfiguration.execution_capable(
                authentication_required=True
            ),
            runtime_dispatcher="none",
            ingress_interpreters="none",
            product_material_resolver="none",
        )
        verifier = ProcessCredentialVerifier()
        with patch.object(
            server_module,
            "_operations_application",
            return_value=SimpleNamespace(services=services),
        ):
            app = server_module.create_app(config, verifier)
        return app, reads, verifier


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _name(node: ast.expr) -> str:
    return node.id if isinstance(node, ast.Name) else ""


def _asgi_json(
    app,
    *,
    method: str,
    path: str,
    headers: tuple[tuple[bytes, bytes], ...],
    query: bytes = b"",
    body: bytes = b"",
) -> tuple[int, dict[str, object]]:
    messages = []

    async def invoke() -> None:
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"spec_version": "2.3", "version": "3.0"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": query,
                "root_path": "",
                "headers": list(headers),
                "client": ("127.0.0.1", 12345),
                "server": ("cpk-server", 80),
            },
            receive,
            send,
        )

    asyncio.run(invoke())
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
