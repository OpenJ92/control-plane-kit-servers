from __future__ import annotations

from contextlib import contextmanager
import ast
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
    name = "cpk_server_ephemeral_source_live_controller_test"
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


class EphemeralSourceLiveLifecycleTests(unittest.TestCase):
    def test_public_gateway_graph_selects_ephemeral_lifecycle(self) -> None:
        with _controller_module() as controller:
            graph = controller._public_gateway_ingress_graph(
                controller._product_document(ROOT, "cpk_local_gateway"),
                controller._product_document(ROOT, "hello_server"),
                controller._product_document(ROOT, "cloudflared_connector"),
                workspace_id="workspace-ephemeral",
                authority_ref=controller.RuntimeAuthorityReference(
                    controller.LOCAL_DOCKER_AUTHORITY_REF
                ),
                public_hostname="cpk-sec1203-test-gateway.openj92.dev",
                lifecycle=controller.PublicIngressLifecycle.EPHEMERAL,
            )

            self.assertEqual(len(graph.public_ingresses), 1)
            self.assertIs(
                graph.public_ingresses[0].lifecycle,
                controller.PublicIngressLifecycle.EPHEMERAL,
            )
            source = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
            custody_calls = [
                node
                for node in ast.walk(source)
                if isinstance(node, ast.FunctionDef)
                and node.name == "_run_cloudflare_tunnel_custody"
            ]
            self.assertEqual(len(custody_calls), 1)
            custody_text = ast.unparse(custody_calls[0])
            self.assertTrue(
                "PublicIngressLifecycle.EPHEMERAL" in custody_text,
                "custody graph must select ephemeral ingress",
            )
            self.assertFalse(
                "PublicIngressLifecycle.RETAINED" in custody_text,
                "custody graph must not retain public ingress",
            )

    def test_two_ephemeral_epochs_have_distinct_complete_identities(self) -> None:
        with _controller_module() as controller:
            evidence = (
                (1, "removed", "tunnel-a", "dns-a", "version-a"),
                (2, "active", "tunnel-b", "dns-b", "version-b"),
            )
            with patch.object(
                controller,
                "_owned_cloudflare_epoch_evidence",
                return_value=evidence,
            ):
                controller._assert_owned_cloudflare_epoch_states(
                    "postgresql://operations",
                    workspace_id="workspace-ephemeral",
                    expected_statuses=("removed", "active"),
                )

            for column, label in ((2, "tunnel"), (3, "DNS"), (4, "token version")):
                duplicate = list(evidence)
                row = list(duplicate[1])
                row[column] = duplicate[0][column]
                duplicate[1] = tuple(row)
                with self.subTest(label=label), patch.object(
                    controller,
                    "_owned_cloudflare_epoch_evidence",
                    return_value=tuple(duplicate),
                ), self.assertRaisesRegex(RuntimeError, label):
                    controller._assert_owned_cloudflare_epoch_states(
                        "postgresql://operations",
                        workspace_id="workspace-ephemeral",
                        expected_statuses=("removed", "active"),
                    )

    def test_ephemeral_workflow_checkpoints_before_postcondition_assertions(self) -> None:
        function = next(
            node
            for node in ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_run_cloudflare_tunnel_custody"
        )
        checkpoints: dict[str, int] = {}
        transitions: dict[str, int] = {}
        assertions: dict[str, int] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if _call_name(node.value) == "run_approved_transition":
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        transitions[target.id] = node.lineno
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) == "_checkpoint_cloudflare_phase":
                phase = _keyword_string(node, "phase")
                if phase is not None:
                    checkpoints[phase] = node.lineno
            if _call_name(node) == "_assert_public_overlay_transition_evidence":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
                    assertions[node.args[1].id] = node.lineno

        expected = {
            "public_on": "public-on-committed",
            "public_off": "public-off-committed",
            "public_on_again": "public-on-again-committed",
            "removed": "final-teardown-committed",
        }
        self.assertEqual(set(checkpoints), {"prepared", *expected.values()})
        self.assertLess(checkpoints["prepared"], transitions["public_on"])
        for result, phase in expected.items():
            with self.subTest(result=result):
                self.assertLess(transitions[result], checkpoints[phase])
                self.assertLess(checkpoints[phase], assertions[result])

    def test_retained_reservation_surface_is_absent_but_failed_effect_fallback_remains(
        self,
    ) -> None:
        controller = CONTROLLER_PATH.read_text(encoding="utf-8")
        hosted = HOSTED_ACTIVITY_PATH.read_text(encoding="utf-8")
        active = controller + "\n" + hosted
        retired = (
            "_assert_retained_public_ingress_read",
            "_read_retained_public_ingress",
            "_release_retained_public_ingress",
            "run_approved_public_ingress_reservation_release",
            "plan_public_ingress_reservation_release",
            "public-ingress-reservations",
            "final-release-committed",
        )
        for token in retired:
            with self.subTest(token=token):
                self.assertFalse(token in active, token)
        for accepted in (
            "ExactFailedDockerNodeEffect",
            "_load_exact_failed_connector_effect",
            "_emergency_compensate_cloudflare",
            "_stop_remove_exact_failed_connector",
        ):
            with self.subTest(accepted=accepted):
                self.assertTrue(accepted in controller, accepted)

    def test_protected_inventory_and_shell_cleanup_remain_bounded(self) -> None:
        with _controller_module() as controller:
            before = controller.CloudflareInventorySnapshot(8, "a" * 64, 4, "b" * 64)
            same = controller.CloudflareInventorySnapshot(8, "a" * 64, 4, "b" * 64)
            changed = controller.CloudflareInventorySnapshot(9, "c" * 64, 4, "b" * 64)
            controller._require_protected_cloudflare_inventory_unchanged(before, same)
            with self.assertRaisesRegex(RuntimeError, "protected Cloudflare inventory"):
                controller._require_protected_cloudflare_inventory_unchanged(
                    before, changed
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

        smoke = SMOKE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("docker system prune", smoke)
        self.assertIn("host_inventory()", smoke)
        self.assertIn("assert_host_inventory_unchanged()", smoke)
        self.assertIn('host_inventory "$HOST_INVENTORY_BEFORE"', smoke)
        self.assertLess(
            smoke.index('host_inventory "$HOST_INVENTORY_BEFORE"'),
            smoke.index('docker network create "$NETWORK"'),
        )

def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _keyword_string(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if (
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and type(keyword.value.value) is str
        ):
            return keyword.value.value
    return None


if __name__ == "__main__":
    unittest.main()
