from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts" / "cpk_server_source_live_abort.py"
CONTROLLER_PATH = ROOT / "scripts" / "cpk_server_secret_provider_source_live.py"
SMOKE_PATH = (
    ROOT / "scripts" / "cpk_server_cloudflare_secret_custody_source_live_smoke.sh"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "cpk_server_source_live_abort_test",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("source-live abort module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def _controller_module():
    name = "cpk_server_source_live_abort_controller_test"
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


class SourceLiveAbortCompensationTests(unittest.TestCase):
    def test_each_committed_phase_checkpoints_before_fault_injection(self) -> None:
        module = _module()
        phases = (
            "public-on-committed",
            "public-off-committed",
            "public-on-again-committed",
            "final-teardown-committed",
        )
        controller_source = CONTROLLER_PATH.read_text(encoding="utf-8")
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "checkpoint.json"
                checkpoint = module.SourceLiveCheckpoint(
                    workspace_id="workspace-a",
                    phase=phase,
                    current_graph_id="graph-a",
                    desired_graph_id="graph-b",
                )

                with self.assertRaisesRegex(
                    module.SourceLiveAbortError,
                    f"fault injected after phase {phase}",
                ):
                    module.record_checkpoint(
                        path,
                        checkpoint,
                        fail_after_phase=phase,
                    )

                self.assertEqual(module.read_checkpoint(path), checkpoint)
                rendered = path.read_text(encoding="utf-8")
                self.assertNotIn("token", rendered.lower())
                self.assertNotIn("credential", rendered.lower())
                self.assertIn(f'phase="{phase}"', controller_source)

    def test_authoritative_cleanup_prevents_emergency_dispatch(self) -> None:
        module = _module()
        calls: list[str] = []

        report = module.compensate_abort(
            authoritative_cleanup=lambda: calls.append("cpk-server"),
            verify_authoritative_absence=lambda: calls.append("verify"),
            verify_emergency_absence=lambda: calls.append("unexpected-verify"),
            resources=(_resource(module),),
            emergency_compensators={
                "cloudflare": lambda _resource: calls.append("emergency") or (),
            },
        )

        self.assertEqual(calls, ["cpk-server", "verify"])
        self.assertTrue(report.authoritative)
        self.assertFalse(report.emergency_attempted)

    def test_failed_authoritative_cleanup_uses_exact_provider_dispatch_but_stays_failed(
        self,
    ) -> None:
        module = _module()
        calls: list[object] = []
        verification_attempts = 0

        def authoritative() -> None:
            calls.append("cpk-server")
            raise RuntimeError("bounded failure")

        def emergency(resource: object) -> tuple[str, ...]:
            calls.append(resource.bounded_descriptor())
            return ()

        def verify_authoritative() -> None:
            nonlocal verification_attempts
            verification_attempts += 1
            raise RuntimeError("still present")

        def verify_emergency() -> None:
            calls.append("absent")

        report = module.compensate_abort(
            authoritative_cleanup=authoritative,
            verify_authoritative_absence=verify_authoritative,
            verify_emergency_absence=verify_emergency,
            resources=(_resource(module),),
            emergency_compensators={"cloudflare": emergency},
        )

        self.assertEqual(calls[0], "cpk-server")
        self.assertEqual(
            calls[1]["public_provider_coordinates"]["tunnel_id"],
            "tunnel-exact",
        )
        self.assertEqual(
            calls[1]["public_provider_coordinates"]["dns_record_id"],
            "dns-exact",
        )
        self.assertEqual(calls[2], "absent")
        self.assertFalse(report.authoritative)
        self.assertTrue(report.emergency_attempted)

    def test_lost_authoritative_response_with_proven_absence_does_not_fall_back(
        self,
    ) -> None:
        module = _module()
        calls: list[str] = []

        def authoritative() -> None:
            calls.append("cpk-server")
            raise RuntimeError("response was lost after commit")

        report = module.compensate_abort(
            authoritative_cleanup=authoritative,
            verify_authoritative_absence=lambda: calls.append("verified-absent"),
            verify_emergency_absence=lambda: calls.append("unexpected-verify"),
            resources=(_resource(module),),
            emergency_compensators={
                "future-provider": lambda _resource: calls.append("emergency") or (),
            },
        )

        self.assertEqual(calls, ["cpk-server", "verified-absent"])
        self.assertTrue(report.authoritative)
        self.assertFalse(report.emergency_attempted)

    def test_unknown_provider_and_failed_stages_remain_bounded_uncertainty(self) -> None:
        module = _module()
        resource = _resource(module, provider_kind="future-provider")

        with self.assertRaises(module.SourceLiveAbortError) as raised:
            module.compensate_abort(
                authoritative_cleanup=lambda: (_ for _ in ()).throw(
                    RuntimeError("provider-token-value")
                ),
                verify_authoritative_absence=lambda: (_ for _ in ()).throw(
                    RuntimeError("tunnel-token-value")
                ),
                verify_emergency_absence=lambda: (_ for _ in ()).throw(
                    RuntimeError("tunnel-token-value")
                ),
                resources=(resource,),
                emergency_compensators={},
            )

        self.assertEqual(
            str(raised.exception),
            "source-live exact cleanup is uncertain: "
            "provider:future-provider,absence-verification",
        )
        self.assertNotIn("provider-token-value", repr(raised.exception))
        self.assertNotIn("tunnel-token-value", repr(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_controller_cleanup_drives_empty_graph_through_cpk_server_first(
        self,
    ) -> None:
        with _controller_module() as controller:
            workflow = RecordingWorkflow(controller, fail_transition=False)
            resource = _resource(controller)
            checkpoint = controller.SourceLiveCheckpoint(
                workspace_id="workspace-a",
                phase="public-on-committed",
                current_graph_id="graph-public",
                desired_graph_id="graph-public",
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "CPK_SOURCE_LIVE_STATE_FILE": "/state/checkpoint.json",
                        "CPK_HOSTED_ACTIVITY_WORKSPACE_ID": "workspace-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(resource,),
                ),
                patch.object(controller, "_workflow", return_value=workflow),
                patch.object(controller, "_disconnect_runtime_networks") as disconnect,
                patch.object(
                    controller,
                    "_assert_owned_cloudflare_resources_removed",
                ) as authoritative_verify,
                patch.object(
                    controller,
                    "_assert_abort_resources_physically_absent",
                ) as emergency_verify,
                patch.object(
                    controller,
                    "_emergency_compensate_cloudflare",
                ) as emergency,
            ):
                status = controller._run_cloudflare_abort_cleanup(
                    base_url="http://cpk-server:8080",
                    server_container="cpk-server",
                    operations_database_url="postgresql://operations",
                    provider_token_file=Path("/provider-token"),
                    bootstrap_dir=Path("/bootstrap"),
                )

            self.assertEqual(status, 0)
            self.assertEqual(workflow.transition_graph_names, ["workspace-a"])
            self.assertEqual(
                workflow.transition_expected_desired_ids,
                ["graph-public"],
            )
            disconnect.assert_called_once_with(
                "cpk-server",
                workspace_id="workspace-a",
            )
            authoritative_verify.assert_called_once()
            emergency_verify.assert_not_called()
            emergency.assert_not_called()

    def test_controller_fallback_is_exact_provider_dispatched_and_nonzero(self) -> None:
        with _controller_module() as controller:
            workflow = RecordingWorkflow(controller, fail_transition=True)
            resource = _resource(controller)
            checkpoint = controller.SourceLiveCheckpoint(
                workspace_id="workspace-a",
                phase="public-on-committed",
                current_graph_id="graph-public",
                desired_graph_id="graph-public",
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "CPK_SOURCE_LIVE_STATE_FILE": "/state/checkpoint.json",
                        "CPK_HOSTED_ACTIVITY_WORKSPACE_ID": "workspace-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(resource,),
                ),
                patch.object(controller, "_workflow", return_value=workflow),
                patch.object(controller, "_disconnect_runtime_networks"),
                patch.object(
                    controller,
                    "_assert_owned_cloudflare_resources_removed",
                    side_effect=RuntimeError("still active"),
                ),
                patch.object(
                    controller,
                    "_assert_abort_resources_physically_absent",
                ) as physical_verify,
                patch.object(
                    controller,
                    "_emergency_compensate_cloudflare",
                    return_value=(),
                ) as emergency,
            ):
                status = controller._run_cloudflare_abort_cleanup(
                    base_url="http://cpk-server:8080",
                    server_container="cpk-server",
                    operations_database_url="postgresql://operations",
                    provider_token_file=Path("/provider-token"),
                    bootstrap_dir=Path("/bootstrap"),
                )

            self.assertEqual(status, 2)
            emergency.assert_called_once()
            self.assertIs(emergency.call_args.args[0], resource)
            physical_verify.assert_called_once_with(
                (resource,),
                api_token_file=Path("/bootstrap/cloudflare-api-token"),
            )

    def test_cloudflare_emergency_compensator_uses_exact_reverse_order(self) -> None:
        with _controller_module() as controller, tempfile.TemporaryDirectory() as directory:
            calls: list[tuple[str, str]] = []
            api_token_file = Path(directory) / "api-token"
            api_token_file.write_text("test-only-api-token", encoding="utf-8")

            class Client:
                def delete_dns_record(self, record_id: str) -> None:
                    calls.append(("dns", record_id))

                def delete_tunnel(self, tunnel_id: str) -> None:
                    calls.append(("tunnel", tunnel_id))

            def revoke(**arguments: object) -> None:
                calls.append(("custody", str(arguments["version_id"])))

            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENJ92_CLOUDFLARE_ACCOUNT_ID": "account-exact",
                        "OPENJ92_CLOUDFLARE_ZONE": "openj92.dev",
                    },
                    clear=False,
                ),
                patch.object(
                    controller,
                    "_provider_revoke_exact_version",
                    side_effect=revoke,
                ),
                patch(
                    "control_plane_kit_interpreters.cloudflare.CloudflareApiClient",
                    return_value=Client(),
                ),
            ):
                failed = controller._emergency_compensate_cloudflare(
                    _resource(controller),
                    workspace_id="workspace-a",
                    provider_token_file=Path("/provider-token"),
                    api_token_file=api_token_file,
                )

            self.assertEqual(failed, ())
            self.assertEqual(
                calls,
                [
                    ("custody", "version-exact"),
                    ("dns", "dns-exact"),
                    ("tunnel", "tunnel-exact"),
                ],
            )

    def test_shell_keeps_fixtures_alive_until_abort_cleanup_finishes(self) -> None:
        smoke = SMOKE_PATH.read_text(encoding="utf-8")

        finish = smoke[smoke.index("finish() {") : smoke.index("trap finish EXIT")]
        self.assertLess(
            finish.index("run_controller abort-cleanup"),
            finish.index("cleanup\n"),
        )
        self.assertIn("CONTROLLER_STATUS=$?", smoke)
        self.assertIn("CPK_SECRET_PROVIDER_SOURCE_LIVE_MODE", smoke)
        self.assertIn("CPK_SOURCE_LIVE_STATE_FILE", smoke)
        self.assertNotIn("api.cloudflare.com", smoke)

    def test_abort_orchestrator_is_provider_neutral(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("cloudflare", source.lower())
        self.assertNotIn("tunnel_id", source)
        self.assertNotIn("dns_record_id", source)

        descriptor = _resource(_module()).bounded_descriptor()
        self.assertNotIn("secret_reference", descriptor)


class RecordingWorkflow:
    def __init__(self, controller, *, fail_transition: bool) -> None:
        self.controller = controller
        self.fail_transition = fail_transition
        self.transition_graph_names: list[str] = []
        self.transition_expected_desired_ids: list[str] = []

    def wait_ready(self) -> None:
        return None

    def read_current_graph_id(self) -> str:
        return "graph-public"

    def read_workspace(self) -> dict[str, object]:
        return {"workspace": {"desired_graph_id": "graph-public"}}

    def run_approved_transition(self, **arguments: object):
        graph = arguments["graph"]
        self.transition_graph_names.append(graph.name)
        self.transition_expected_desired_ids.append(
            str(arguments["expected_desired_graph_id"])
        )
        if self.fail_transition:
            raise RuntimeError("authoritative cleanup failed")
        return self.controller.PreparedRun(
            run_id="run-cleanup",
            plan_id="plan-cleanup",
            current_graph_id="graph-empty",
            desired_graph_id="graph-empty",
        )


def _resource(module, *, provider_kind: str = "cloudflare"):
    return module.ExactOwnedIngressResource(
        provider_kind=provider_kind,
        ingress_id="gateway-a",
        epoch=1,
        public_provider_coordinates={
            "tunnel_id": "tunnel-exact",
            "dns_record_id": "dns-exact",
            "hostname": "cpk-gateway-a.openj92.dev",
            "zone_id": "zone-exact",
        },
        secret_reference="secret://generated/ingress/token-a",
        provider_version_id="version-exact",
        provider_version_number=1,
    )


if __name__ == "__main__":
    unittest.main()
