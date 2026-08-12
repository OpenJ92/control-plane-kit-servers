from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "scripts" / "cpk_server_secret_provider_source_live.py"
HOSTED = ROOT / "scripts" / "cpk_server_hosted_activity.py"
SOURCE_LIVE_SMOKE = (
    ROOT / "scripts" / "cpk_server_secret_provider_source_live_smoke.sh"
)
CUSTODY_SMOKE = (
    ROOT / "scripts" / "cpk_server_cloudflare_secret_custody_source_live_smoke.sh"
)
PUBLISHED_GATE = ROOT / "scripts" / "cpk_server_gateway_published_live_smoke.sh"


def _python_strings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _python_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    names.update(
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    )
    return names


def _verifier_scenario_function(tree: ast.Module) -> ast.FunctionDef:
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    main = functions["main"]
    for branch in ast.walk(main):
        if not isinstance(branch, ast.If):
            continue
        strings = {
            node.value
            for node in ast.walk(branch.test)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        if "gateway-verifier-projection" not in strings:
            continue
        calls = [
            node.func.id
            for statement in branch.body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        candidates = [name for name in calls if name in functions]
        if len(candidates) != 1:
            raise AssertionError(
                "gateway verifier scenario must call one local controller"
            )
        return functions[candidates[0]]
    raise AssertionError("gateway verifier scenario is unavailable")


class GatewaySourceLiveRetirementTests(unittest.TestCase):
    def test_retired_selectors_and_controller_program_are_absent(self) -> None:
        controller_strings = _python_strings(CONTROLLER)
        controller_names = _python_names(CONTROLLER)
        source_live_smoke = SOURCE_LIVE_SMOKE.read_text(encoding="utf-8")
        custody_smoke = CUSTODY_SMOKE.read_text(encoding="utf-8")

        for selector in (
            "gateway-capability-denials",
            "gateway-key-rotation",
            "gateway-key-rotation-overlay",
        ):
            with self.subTest(selector=selector, owner="controller"):
                self.assertFalse(selector in controller_strings, selector)
            for owner, source in (
                ("source-live-smoke", source_live_smoke),
                ("custody-smoke", custody_smoke),
            ):
                with self.subTest(selector=selector, owner=owner):
                    self.assertIsNone(
                        re.search(
                            rf"(?:^|[|=\s]){re.escape(selector)}"
                            rf"(?:[)|\s]|$)",
                            source,
                            flags=re.MULTILINE,
                        )
                    )

        for name in (
            "GatewayRotationSourceLiveScope",
            "_run_gateway_key_rotation_program",
            "_run_gateway_rotation_public_overlay_lifecycle",
            "_finalize_gateway_rotation_source_live",
            "_rotation_from_response",
            "_advance_rotation_until",
            "_poll_rotation_until_drain_deadline",
            "_replay_rotation_command",
            "_assert_rotation_transition_history",
            "_gateway_rotation_public_graph",
        ):
            with self.subTest(name=name):
                self.assertFalse(name in controller_names, name)

    def test_retired_hosted_facade_and_route_spellings_are_absent(self) -> None:
        names = _python_names(HOSTED)
        strings = _python_strings(HOSTED)
        for name in (
            "request_gateway_key_rotation",
            "request_gateway_key_rotation_approval",
            "decide_gateway_key_rotation_mcp",
            "advance_gateway_key_rotation_http",
            "advance_gateway_key_rotation_mcp",
            "read_gateway_key_rotation_detail",
            "read_gateway_key_rotation_transitions_mcp",
        ):
            with self.subTest(name=name):
                self.assertFalse(name in names, name)
        for spelling in (
            "command.gateway-key-rotation.decide",
            "command.gateway-key-rotation.advance",
            "read.gateway-key-rotation.transitions",
        ):
            with self.subTest(spelling=spelling):
                self.assertFalse(spelling in strings, spelling)
        self.assertFalse(
            any("gateway-key-rotations" in value for value in strings),
            "retired HTTP gateway-key-rotation routes remain",
        )

    def test_verifier_scenario_runs_successes_then_live_denial_matrix(self) -> None:
        tree = ast.parse(
            CONTROLLER.read_text(encoding="utf-8"),
            filename=str(CONTROLLER),
        )
        function = _verifier_scenario_function(tree)
        calls = [
            (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id,
             node.lineno)
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        ]
        line_by_name = {name: line for name, line in calls}
        denial_line = line_by_name.get("_assert_live_gateway_denial_matrix")
        self.assertIsNotNone(denial_line)
        if denial_line is None:
            return
        self.assertLess(
            line_by_name["request_gateway_probe_http"],
            denial_line,
        )
        self.assertLess(
            line_by_name["request_gateway_probe_mcp"],
            denial_line,
        )
        returns = [node.lineno for node in ast.walk(function) if isinstance(node, ast.Return)]
        self.assertTrue(returns)
        self.assertLess(denial_line, min(returns))

    def test_published_gate_selects_current_verifier_acceptance(self) -> None:
        wrapper = PUBLISHED_GATE.read_text(encoding="utf-8")
        for fact in (
            "coordinates/server-products.json",
            "product_source_commit cpk-local-gateway",
            "require_digest",
            "CPK_SOURCE_LIVE_GATEWAY_IMAGE",
            "CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT",
            "CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO=gateway-verifier-projection",
            "cpk_server_secret_provider_source_live_smoke.sh",
            "docker_residue_audit.sh",
        ):
            with self.subTest(fact=fact):
                self.assertTrue(fact in wrapper, fact)
        self.assertFalse("gateway-key-rotation-overlay" in wrapper)
        self.assertFalse(
            "cpk_server_cloudflare_secret_custody_source_live_smoke.sh" in wrapper
        )

    def test_cloudflare_custody_shell_keeps_current_cleanup_only(self) -> None:
        smoke = CUSTODY_SMOKE.read_text(encoding="utf-8")
        for fact in (
            "cloudflare-tunnel-custody",
            "cleanup_workspace_resources",
            "assert_host_inventory_unchanged",
            "source-live controller failed; attempting cpk-server-first abort cleanup",
            '"action": "secret.write"',
            '"action": "secret.resolve"',
            '"action": "secret.revoke"',
            "CPK_SECRETS_CREDENTIALS_FILE",
        ):
            with self.subTest(fact=fact):
                self.assertTrue(fact in smoke, fact)
        self.assertFalse("gateway-key-rotation-overlay" in smoke)
        self.assertFalse("delegation-key:rotate" in smoke)


if __name__ == "__main__":
    unittest.main()
