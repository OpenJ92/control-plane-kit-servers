from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "scripts" / "cpk_server_hosted_activity.py"
PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
-----END PUBLIC KEY-----
"""


@contextmanager
def _controller_module():
    name = "cpk_server_hosted_gateway_delegation_test"
    spec = importlib.util.spec_from_file_location(name, CONTROLLER)
    if spec is None or spec.loader is None:
        raise RuntimeError("hosted activity controller could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


class HostedGatewayDelegationBootstrapTests(unittest.TestCase):
    def test_desired_graph_command_uses_authoritative_workspace_pointer(self) -> None:
        with _controller_module() as module:
            calls: list[tuple[str, str, dict[str, object]]] = []

            def fake_http(
                _base_url: str,
                method: str,
                path: str,
                payload: dict[str, object] | None = None,
                **_kwargs: object,
            ) -> dict[str, object]:
                calls.append(("http", f"{method} {path}", payload or {}))
                return {
                    "desired_graph_id": "graph-next",
                    "desired_realized_projection_id": "projection-next",
                    "desired_graph_revision": 8,
                }

            def fake_mcp_read(
                _base_url: str,
                name: str,
                arguments: dict[str, object],
            ) -> dict[str, object]:
                calls.append(("mcp-read", name, arguments))
                return {
                    "workspace": {
                        "workspace_id": "workspace-a",
                        "desired_graph_id": "graph-stable",
                        "desired_realized_projection_id": "projection-rotation-b",
                        "desired_graph_revision": 7,
                    }
                }

            workflow = module.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-a",
                worker_id="worker-a",
                server_container="cpk-server",
            )
            with (
                patch.object(module, "_http", side_effect=fake_http),
                patch.object(module, "_mcp_read", side_effect=fake_mcp_read),
            ):
                result = workflow.set_desired_graph(
                    session_id="session-a",
                    graph=module.DeploymentGraph("workspace-a"),
                    title="teardown",
                    expected_desired_graph_id="graph-stable",
                )

            self.assertEqual(result, "graph-next")
            self.assertEqual(
                [value[:2] for value in calls],
                [
                    ("mcp-read", "read.workspace"),
                    (
                        "http",
                        "POST /workspaces/workspace-a/graphs/desired",
                    ),
                ],
            )
            payload = calls[1][2]
            self.assertEqual(payload["expected_desired_graph_id"], "graph-stable")
            self.assertEqual(
                payload["expected_desired_realized_projection_id"],
                "projection-rotation-b",
            )
            self.assertEqual(payload["expected_desired_graph_revision"], 7)

    def test_desired_graph_command_rejects_stale_graph_before_write(self) -> None:
        with _controller_module() as module:
            workflow = module.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-a",
                worker_id="worker-a",
                server_container="cpk-server",
            )
            with (
                patch.object(
                    module,
                    "_mcp_read",
                    return_value={
                        "workspace": {
                            "workspace_id": "workspace-a",
                            "desired_graph_id": "graph-newer",
                            "desired_realized_projection_id": "projection-newer",
                            "desired_graph_revision": 9,
                        }
                    },
                ),
                patch.object(module, "_http") as command,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "desired graph changed before authoring",
                ):
                    workflow.set_desired_graph(
                        session_id="session-a",
                        graph=module.DeploymentGraph("workspace-a"),
                        title="teardown",
                        expected_desired_graph_id="graph-older",
                    )

            command.assert_not_called()

    def test_initial_desired_graph_command_uses_unassigned_pointer(self) -> None:
        with _controller_module() as module:
            payloads: list[dict[str, object]] = []

            def fake_http(
                _base_url: str,
                _method: str,
                _path: str,
                payload: dict[str, object] | None = None,
                **_kwargs: object,
            ) -> dict[str, object]:
                payloads.append(payload or {})
                return {
                    "desired_graph_id": "graph-first",
                    "desired_realized_projection_id": "projection-first",
                    "desired_graph_revision": 1,
                }

            workflow = module.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-a",
                worker_id="worker-a",
                server_container="cpk-server",
            )
            with (
                patch.object(
                    module,
                    "_mcp_read",
                    return_value={
                        "workspace": {
                            "workspace_id": "workspace-a",
                            "desired_graph_id": None,
                            "desired_realized_projection_id": None,
                            "desired_graph_revision": 0,
                        }
                    },
                ),
                patch.object(module, "_http", side_effect=fake_http),
            ):
                workflow.set_desired_graph(
                    session_id="session-a",
                    graph=module.DeploymentGraph("workspace-a"),
                    title="initial",
                    expected_desired_graph_id=None,
                )

            self.assertIsNone(payloads[0]["expected_desired_graph_id"])
            self.assertIsNone(
                payloads[0]["expected_desired_realized_projection_id"]
            )
            self.assertEqual(payloads[0]["expected_desired_graph_revision"], 0)

    def test_admission_uses_public_http_and_mcp_surfaces_then_reads_exact_key(self) -> None:
        with _controller_module() as module:
            calls: list[tuple[str, str, dict[str, object]]] = []
            fingerprint = sha256(PUBLIC_KEY.encode("ascii")).hexdigest()
            active = {
                "workspace_id": "workspace-a",
                "purpose": "gateway-probe",
                "issuer": "cpk-source-live",
                "key_id": "source-live-gateway-key",
                "algorithm": "ed25519",
                "fingerprint_sha256": fingerprint,
                "private_key_reference": (
                    "secret://control-plane-kit/gateway/source-live-signing-key"
                ),
                "status": "active",
            }

            def fake_http(
                _base_url: str,
                method: str,
                path: str,
                payload: dict[str, object] | None = None,
                **_kwargs: object,
            ) -> dict[str, object]:
                calls.append(("http", f"{method} {path}", payload or {}))
                if path.endswith("/secret-providers"):
                    return {"registration_id": "sprov_source_live"}
                if path.endswith("/secret-references"):
                    return {"registration_id": "sref_gateway_key"}
                if path.endswith("/delegation-keys"):
                    return {**active, "status": "verify-only"}
                raise AssertionError(f"unexpected HTTP path: {path}")

            def fake_mcp_tool(
                _base_url: str,
                name: str,
                arguments: dict[str, object],
                **_kwargs: object,
            ) -> dict[str, object]:
                calls.append(("mcp-tool", name, arguments))
                return active

            def fake_mcp_read(
                _base_url: str,
                name: str,
                arguments: dict[str, object],
            ) -> dict[str, object]:
                calls.append(("mcp-read", name, arguments))
                return {"items": [active]}

            workflow = module.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-a",
                worker_id="worker-a",
                server_container="cpk-server",
            )
            with (
                patch.object(module, "_http", side_effect=fake_http),
                patch.object(module, "_mcp_tool", side_effect=fake_mcp_tool),
                patch.object(module, "_mcp_read", side_effect=fake_mcp_read),
            ):
                result = workflow.admit_gateway_delegation_key(
                    provider_id="control-plane-kit",
                    provider_display_name="Ephemeral hosted acceptance custody",
                    provider_endpoint_reference="source-live-secrets",
                    provider_credential_reference=(
                        "secret://bootstrap/provider/client-token"
                    ),
                    private_key_reference=(
                        "secret://control-plane-kit/gateway/"
                        "source-live-signing-key"
                    ),
                    issuer="cpk-source-live",
                    key_id="source-live-gateway-key",
                    public_key_pem=PUBLIC_KEY,
                    admitted_at="2026-08-04T10:00:00Z",
                    activated_at="2026-08-04T10:00:01Z",
                    metadata={"acceptance": "ephemeral-hosted-source-live"},
                )

            self.assertEqual(result, active)
            self.assertEqual(
                [value[:2] for value in calls],
                [
                    (
                        "http",
                        "POST /workspaces/workspace-a/secret-providers",
                    ),
                    (
                        "http",
                        "POST /workspaces/workspace-a/secret-references",
                    ),
                    (
                        "http",
                        "POST /workspaces/workspace-a/delegation-keys",
                    ),
                    ("mcp-tool", "command.delegation-key.activate"),
                    ("mcp-read", "read.delegation-keys"),
                ],
            )
            provider_payload = calls[0][2]
            self.assertEqual(
                provider_payload["provider_kind"],
                "control-plane-kit-secrets",
            )
            self.assertEqual(
                provider_payload["allowed_intents"],
                ["gateway.probe-signing-key"],
            )
            self.assertEqual(
                calls[1][2]["provider_registration_id"],
                "sprov_source_live",
            )
            self.assertEqual(calls[2][2]["public_key_pem"], PUBLIC_KEY)
            self.assertNotIn("actor_scopes", calls[2][2])
            self.assertEqual(calls[3][2]["workspace_id"], "workspace-a")

    def test_source_live_bootstrap_uses_real_provider_and_restart_replay(self) -> None:
        controller = (
            ROOT / "scripts" / "cpk_server_secret_provider_source_live.py"
        ).read_text(encoding="utf-8")
        smoke = (
            ROOT / "scripts" / "cpk_server_secret_provider_source_live_smoke.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('== "gateway-delegation-bootstrap"', controller)
        self.assertIn("workflow.admit_gateway_delegation_key(**arguments)", controller)
        self.assertEqual(controller.count("_restart_provider(provider_container)"), 2)
        self.assertIn("ready_policy=_verification_policy", controller)
        self.assertIn("gateway-delegation-bootstrap-write", controller)
        self.assertIn('"provider_kind": "control-plane-kit-secrets"', CONTROLLER.read_text())
        self.assertIn('"workspace-gateway-key-bootstrap"', smoke)
        self.assertIn("CPK_PRODUCT_MATERIAL_RESOLVER=provider", smoke)
        self.assertNotIn("CPK_PRODUCT_MATERIAL_RESOLVER=local-development", smoke)


if __name__ == "__main__":
    unittest.main()
