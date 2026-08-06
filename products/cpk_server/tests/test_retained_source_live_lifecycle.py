from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER_PATH = ROOT / "scripts" / "cpk_server_secret_provider_source_live.py"
HOSTED_ACTIVITY_PATH = ROOT / "scripts" / "cpk_server_hosted_activity.py"
SMOKE_PATH = (
    ROOT / "scripts" / "cpk_server_cloudflare_secret_custody_source_live_smoke.sh"
)


@contextmanager
def _controller_module():
    name = "cpk_server_retained_source_live_controller_test"
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, CONTROLLER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("source-live controller could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(ROOT / "scripts"))
        sys.modules.pop(name, None)


@contextmanager
def _hosted_activity_module():
    name = "cpk_server_retained_hosted_activity_test"
    spec = importlib.util.spec_from_file_location(name, HOSTED_ACTIVITY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("hosted activity controller could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


class RetainedSourceLiveLifecycleTests(unittest.TestCase):
    def test_gateway_rotation_public_graph_selects_retained_hostname(self) -> None:
        with _controller_module() as controller:
            graph = controller._gateway_rotation_public_graph(
                controller._product_document(ROOT, "cpk_local_gateway"),
                controller._product_document(ROOT, "hello_server"),
                controller._product_document(ROOT, "postgres_server"),
                controller._product_document(ROOT, "cloudflared_connector"),
                workspace_id="workspace-retained",
                public_hostname="cpk-rot1404-test-gateway.openj92.dev",
            )

            self.assertEqual(len(graph.public_ingresses), 1)
            self.assertIs(
                graph.public_ingresses[0].lifecycle,
                controller.PublicIngressLifecycle.RETAINED,
            )

    def test_retained_readback_requires_http_mcp_parity_and_redaction(self) -> None:
        with _controller_module() as controller:
            item = _retained_item()
            workflow = MagicMock()
            workflow.read_public_ingress_resources.return_value = {
                "workspace_id": "workspace-retained",
                "items": [item],
            }
            workflow.read_public_ingress_resources_mcp.return_value = {
                "workspace_id": "workspace-retained",
                "items": [item],
            }

            controller._assert_retained_public_ingress_read(
                workflow,
                reservation_status="reserved",
                realization_statuses=("removed",),
            )

            workflow.read_public_ingress_resources.assert_called_once_with()
            workflow.read_public_ingress_resources_mcp.assert_called_once_with()

            workflow.read_public_ingress_resources_mcp.return_value = {
                "workspace_id": "workspace-retained",
                "items": [{**item, "version": 4}],
            }
            with self.assertRaisesRegex(RuntimeError, "HTTP/MCP.*changed"):
                controller._assert_retained_public_ingress_read(
                    workflow,
                    reservation_status="reserved",
                    realization_statuses=("removed",),
                )

    def test_canonical_mcp_retained_read_uses_shared_route(self) -> None:
        with _hosted_activity_module() as hosted:
            workflow = hosted.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-retained",
                worker_id="worker-a",
                server_container="server-a",
            )
            with patch.object(
                hosted,
                "_mcp_read",
                return_value={"workspace_id": "workspace-retained", "items": []},
            ) as read:
                result = workflow.read_public_ingress_resources_mcp()

            self.assertEqual(result["items"], [])
            read.assert_called_once_with(
                "http://cpk-server:8080",
                "list_public_ingress_resources",
                {"workspace_id": "workspace-retained"},
            )

    def test_release_runs_http_then_mcp_replay_and_never_advances_graph(self) -> None:
        with _hosted_activity_module() as hosted:
            workflow = hosted.HostedWorkflow(
                "http://cpk-server:8080",
                workspace_id="workspace-retained",
                worker_id="worker-a",
                server_container="server-a",
            )
            workflow.start_session = MagicMock(return_value="session-release")
            workflow.read_workspace = MagicMock(
                return_value={
                    "workspace": {
                        "current_graph_id": "graph-empty",
                        "desired_graph_id": "graph-empty",
                        "current_realized_projection_id": "projection-empty",
                        "desired_realized_projection_id": "projection-empty",
                        "desired_graph_revision": 7,
                    }
                }
            )
            workflow.request_approval = MagicMock(
                return_value={
                    "request_id": "approval-release",
                    "required_scope": "plan:approve-destructive",
                }
            )
            workflow.assert_approval_visible = MagicMock()
            workflow.approve = MagicMock()
            workflow.admit = MagicMock(return_value="request-release")
            workflow.claim = MagicMock(return_value="run-release")
            workflow.start_run = MagicMock()
            workflow.execute_to_completion = MagicMock()
            workflow.read_current_graph_id = MagicMock(return_value="graph-empty")
            workflow.advance_current_graph = MagicMock(
                side_effect=AssertionError("release must not fabricate graph advancement")
            )
            plan = {
                "plan_id": "plan-release",
                "session_id": "session-release",
                "base_graph_id": "graph-empty",
                "desired_graph_id": "graph-empty",
                "base_realized_projection_id": "projection-empty",
                "desired_realized_projection_id": "projection-empty",
                "desired_graph_revision": 7,
                "ready_for_execution": True,
                "activity_count": 1,
                "replayed": False,
            }
            replay = {**plan, "replayed": True}
            calls: list[str] = []

            def http(_base, method, path, payload=None, **_kwargs):
                calls.append(f"http:{method}:{path}")
                self.assertEqual(payload["expected_reservation_version"], 3)
                return plan

            def mcp(_base, name, arguments, **_kwargs):
                calls.append(f"mcp:{name}")
                self.assertEqual(arguments["reservation_id"], "reservation-1")
                return replay

            with (
                patch.object(hosted, "_http", side_effect=http),
                patch.object(hosted, "_mcp_tool", side_effect=mcp),
            ):
                result = workflow.run_approved_public_ingress_reservation_release(
                    title="Final retained ingress release",
                    reservation=_retained_item(),
                )

            self.assertEqual(
                calls,
                [
                    "http:POST:/workspaces/workspace-retained/"
                    "public-ingress-reservations/reservation-1/release-plan",
                    "mcp:plan_public_ingress_reservation_release",
                ],
            )
            self.assertEqual(result.plan_id, "plan-release")
            self.assertEqual(result.run_id, "run-release")
            workflow.execute_to_completion.assert_called_once_with(
                "run-release",
                sync_runtime_networks=False,
            )
            workflow.advance_current_graph.assert_not_called()

    def test_retained_epochs_share_dns_but_not_tunnel_or_token_identity(self) -> None:
        with _controller_module() as controller:
            evidence = (
                (1, "removed", "tunnel-a", "dns-stable", "version-a"),
                (2, "active", "tunnel-b", "dns-stable", "version-b"),
            )
            with patch.object(
                controller,
                "_owned_cloudflare_epoch_evidence",
                return_value=evidence,
            ):
                controller._assert_owned_cloudflare_epoch_states(
                    "postgresql://operations",
                    workspace_id="workspace-retained",
                    expected_statuses=("removed", "active"),
                    retained_reservation=True,
                )

            with patch.object(
                controller,
                "_owned_cloudflare_epoch_evidence",
                return_value=(
                    evidence[0],
                    (2, "active", "tunnel-b", "dns-other", "version-b"),
                ),
            ), self.assertRaisesRegex(RuntimeError, "DNS reservation"):
                controller._assert_owned_cloudflare_epoch_states(
                    "postgresql://operations",
                    workspace_id="workspace-retained",
                    expected_statuses=("removed", "active"),
                    retained_reservation=True,
                )

    def test_protected_inventory_uses_only_bounded_counts_and_digests(self) -> None:
        with _controller_module() as controller:
            before = controller.CloudflareInventorySnapshot(
                dns_record_count=8,
                dns_record_digest="a" * 64,
                active_tunnel_count=4,
                active_tunnel_digest="b" * 64,
            )
            same = controller.CloudflareInventorySnapshot(
                dns_record_count=8,
                dns_record_digest="a" * 64,
                active_tunnel_count=4,
                active_tunnel_digest="b" * 64,
            )
            changed = controller.CloudflareInventorySnapshot(
                dns_record_count=9,
                dns_record_digest="c" * 64,
                active_tunnel_count=4,
                active_tunnel_digest="b" * 64,
            )

            controller._require_protected_cloudflare_inventory_unchanged(before, same)
            with self.assertRaisesRegex(RuntimeError, "protected Cloudflare inventory"):
                controller._require_protected_cloudflare_inventory_unchanged(
                    before,
                    changed,
                )
            self.assertEqual(
                set(before.descriptor()),
                {
                    "dns_record_count",
                    "dns_record_digest",
                    "active_tunnel_count",
                    "active_tunnel_digest",
                },
            )
            self.assertNotIn("record", repr(before).lower().replace("dns_record", ""))

    def test_shell_preserves_full_host_inventory_across_exact_cleanup(self) -> None:
        smoke = SMOKE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("python3", smoke)
        self.assertIn("host_inventory()", smoke)
        self.assertIn("assert_host_inventory_unchanged()", smoke)
        self.assertIn('host_inventory "$HOST_INVENTORY_BEFORE"', smoke)
        self.assertIn("assert_host_inventory_unchanged", smoke)
        self.assertLess(
            smoke.index('host_inventory "$HOST_INVENTORY_BEFORE"'),
            smoke.index('docker network create "$NETWORK"'),
        )
        self.assertLess(
            smoke.rindex("cleanup\n"),
            smoke.rindex("assert_host_inventory_unchanged"),
        )


def _retained_item() -> dict[str, object]:
    return {
        "reservation_id": "reservation-1",
        "ingress_id": "gateway-public",
        "authority_ref": "openj92-cloudflare",
        "hostname": "cpk-rot1404-test-gateway.openj92.dev",
        "lifecycle": "retained",
        "status": "reserved",
        "version": 3,
        "created_at": "2026-08-05T10:00:00Z",
        "observed_at": "2026-08-05T10:02:00Z",
        "realizations": [
            {
                "epoch": 1,
                "status": "removed",
                "runtime_id": "docker",
                "created_at": "2026-08-05T10:00:00Z",
                "observed_at": "2026-08-05T10:01:00Z",
                "removed_at": "2026-08-05T10:02:00Z",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
