from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch


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
            "prepared",
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
            emergency_resources=(),
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
            emergency_resources=(_resource(module),),
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
            emergency_resources=(),
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
                emergency_resources=(resource,),
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
        self.assertIsNone(raised.exception.__context__)

    def test_only_exact_failed_unadvanced_resources_enter_emergency_dispatch(
        self,
    ) -> None:
        module = _module()
        accepted = _resource(module)
        unadvanced = _resource(module, source_run_id="run-unadvanced", epoch=2)
        calls: list[str] = []

        report = module.compensate_abort(
            authoritative_cleanup=lambda: (_ for _ in ()).throw(
                RuntimeError("graph cleanup did not see unadvanced effect")
            ),
            verify_authoritative_absence=lambda: (_ for _ in ()).throw(
                RuntimeError("unadvanced effect remains")
            ),
            verify_emergency_absence=lambda: calls.append("verified"),
            resources=(accepted, unadvanced),
            emergency_resources=(unadvanced,),
            emergency_compensators={
                "cloudflare": lambda resource: calls.append(resource.source_run_id)
                or (),
            },
        )

        self.assertEqual(calls, ["run-unadvanced", "verified"])
        self.assertFalse(report.authoritative)
        self.assertTrue(report.emergency_attempted)
        self.assertEqual(report.resource_count, 2)

    def test_uncertain_unadvanced_evidence_authorizes_no_destructive_call(self) -> None:
        module = _module()
        calls: list[str] = []

        with self.assertRaises(module.SourceLiveAbortError) as raised:
            module.compensate_abort(
                authoritative_cleanup=lambda: (_ for _ in ()).throw(
                    RuntimeError("candidate-provider-address")
                ),
                verify_authoritative_absence=lambda: (_ for _ in ()).throw(
                    RuntimeError("candidate-secret-reference")
                ),
                verify_emergency_absence=lambda: (_ for _ in ()).throw(
                    RuntimeError("candidate-token")
                ),
                resources=(_resource(module),),
                emergency_resources=(),
                emergency_compensators={
                    "cloudflare": lambda _resource: calls.append("mutated") or (),
                },
            )

        self.assertEqual(calls, [])
        rendered = str(raised.exception) + repr(raised.exception)
        for candidate in (
            "candidate-provider-address",
            "candidate-secret-reference",
            "candidate-token",
        ):
            self.assertNotIn(candidate, rendered)
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_abort_snapshot_is_candidate_free(self) -> None:
        with _controller_module() as controller:
            resource = _resource(controller)
            connector = _failed_connector_effect(controller)
            output = StringIO()
            with redirect_stdout(output):
                controller._print_bounded_abort_snapshot(
                    controller.SourceLiveCheckpoint(
                        "workspace-a",
                        "public-on-committed",
                        "graph-private",
                        "graph-public",
                    ),
                    (resource,),
                    failed_connector_effects={"run-failed": connector},
                    uncertain_connector_runs=set(),
                )

            rendered = output.getvalue()
            for candidate in (
                "tunnel-exact",
                "dns-exact",
                "cpk-gateway-a.openj92.dev",
                "secret://generated/ingress/token-a",
                "container-exact",
            ):
                self.assertNotIn(candidate, rendered)
            self.assertLessEqual(len(rendered), 512)

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
                        "CPK_SECRET_PROVIDER_CONTAINER": "provider-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(resource,),
                ),
                patch.object(
                    controller,
                    "_load_exact_connector_run_evidence",
                    return_value=_failed_connector_effect(controller),
                ),
                patch.object(controller, "_workflow", return_value=workflow),
                patch.object(controller, "_disconnect_runtime_networks") as disconnect,
                patch.object(
                    controller,
                    "_assert_owned_cloudflare_resources_removed",
                ) as authoritative_verify,
                patch.object(
                    controller,
                    "_assert_abort_generated_secret_versions_revoked",
                ) as custody_verify,
                patch.object(
                    controller,
                    "_assert_failed_connectors_absent",
                ) as connector_verify,
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
                    provider_container="provider-a",
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
            self.assertEqual(workflow.release_reservation_statuses, [])
            connector_verify.assert_called_once()
            custody_verify.assert_called_once_with(
                (resource,),
                provider_container="provider-a",
                workspace_id="workspace-a",
            )
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
                        "CPK_SECRET_PROVIDER_CONTAINER": "provider-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(resource,),
                ),
                patch.object(
                    controller,
                    "_load_exact_connector_run_evidence",
                    return_value=_failed_connector_effect(controller),
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
                    "_assert_abort_generated_secret_versions_revoked",
                ) as custody_verify,
                patch.object(
                    controller,
                    "_assert_failed_connectors_absent",
                ) as connector_verify,
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
                    provider_container="provider-a",
                    provider_token_file=Path("/provider-token"),
                    bootstrap_dir=Path("/bootstrap"),
                )

            self.assertEqual(status, 2)
            connector_verify.assert_called_once()
            emergency.assert_called_once()
            self.assertIs(emergency.call_args.args[0], resource)
            physical_verify.assert_called_once_with(
                (resource,),
                connector_resources=(resource,),
                api_token_file=Path("/bootstrap/cloudflare-api-token"),
                failed_connector_effects={
                    "run-failed": _failed_connector_effect(controller)
                },
                uncertain_connector_runs=set(),
            )
            self.assertEqual(
                custody_verify.call_args_list,
                [
                    call(
                        (resource,),
                        provider_container="provider-a",
                        workspace_id="workspace-a",
                    ),
                    call(
                        (resource,),
                        provider_container="provider-a",
                        workspace_id="workspace-a",
                    ),
                ],
            )

    def test_controller_fallback_receives_only_failed_unadvanced_resources(
        self,
    ) -> None:
        with _controller_module() as controller:
            workflow = RecordingWorkflow(controller, fail_transition=True)
            accepted = _resource(controller, source_run_id="run-accepted")
            unadvanced = _resource(
                controller,
                source_run_id="run-unadvanced",
                epoch=2,
            )
            checkpoint = controller.SourceLiveCheckpoint(
                workspace_id="workspace-a",
                phase="public-on-committed",
                current_graph_id="graph-public",
                desired_graph_id="graph-public",
            )

            def connector_effect(
                _database_url: str,
                *,
                workspace_id: str,
                source_run_id: str,
                connector_node_id: str,
                accepted_graph_id: str,
            ):
                del _database_url, workspace_id, connector_node_id, accepted_graph_id
                if source_run_id == "run-accepted":
                    return None
                return _failed_connector_effect(
                    controller,
                    run_id=source_run_id,
                    desired_graph_id="graph-unadvanced",
                )

            with (
                patch.dict(
                    os.environ,
                    {
                        "CPK_SOURCE_LIVE_STATE_FILE": "/state/checkpoint.json",
                        "CPK_HOSTED_ACTIVITY_WORKSPACE_ID": "workspace-a",
                        "CPK_SECRET_PROVIDER_CONTAINER": "provider-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(accepted, unadvanced),
                ),
                patch.object(
                    controller,
                    "_load_exact_connector_run_evidence",
                    side_effect=connector_effect,
                ),
                patch.object(controller, "_workflow", return_value=workflow),
                patch.object(controller, "_disconnect_runtime_networks"),
                patch.object(
                    controller,
                    "_assert_owned_cloudflare_resources_removed",
                    side_effect=RuntimeError("unadvanced effect remains"),
                ),
                patch.object(controller, "_assert_abort_generated_secret_versions_revoked"),
                patch.object(controller, "_assert_abort_resources_physically_absent"),
                patch.object(controller, "_assert_failed_connectors_absent"),
                patch.object(controller, "_assert_no_node_containers") as no_containers,
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
                    provider_container="provider-a",
                    provider_token_file=Path("/provider-token"),
                    bootstrap_dir=Path("/bootstrap"),
                )

            self.assertEqual(status, 2)
            emergency.assert_called_once()
            self.assertIs(emergency.call_args.args[0], unadvanced)
            self.assertEqual(
                no_containers.call_args_list,
                [
                    call("workspace-a", "cloudflared-gateway"),
                    call("workspace-a", "cloudflared-gateway"),
                ],
            )

    def test_post_teardown_abort_uses_historical_exact_ephemeral_evidence(
        self,
    ) -> None:
        with _controller_module() as controller:
            workflow = RecordingWorkflow(controller, fail_transition=False)
            resource = _resource(controller)
            checkpoint = controller.SourceLiveCheckpoint(
                workspace_id="workspace-a",
                phase="final-teardown-committed",
                current_graph_id="graph-empty",
                desired_graph_id="graph-empty",
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "CPK_SOURCE_LIVE_STATE_FILE": "/state/checkpoint.json",
                        "CPK_HOSTED_ACTIVITY_WORKSPACE_ID": "workspace-a",
                        "CPK_SECRET_PROVIDER_CONTAINER": "provider-a",
                    },
                    clear=False,
                ),
                patch.object(controller, "read_checkpoint", return_value=checkpoint),
                patch.object(
                    controller,
                    "_load_exact_owned_ingress_resources",
                    return_value=(),
                ),
                patch.object(
                    controller,
                    "_load_all_exact_owned_ingress_resources",
                    return_value=(resource,),
                ) as historical,
                patch.object(
                    controller,
                    "_load_exact_connector_run_evidence",
                ) as failed_connector,
                patch.object(controller, "_workflow", return_value=workflow),
                patch.object(controller, "_disconnect_runtime_networks"),
                patch.object(
                    controller,
                    "_assert_owned_cloudflare_resources_removed",
                ),
                patch.object(
                    controller,
                    "_assert_abort_generated_secret_versions_revoked",
                ),
                patch.object(controller, "_assert_failed_connectors_absent") as absent,
                patch.object(controller, "_emergency_compensate_cloudflare") as emergency,
            ):
                status = controller._run_cloudflare_abort_cleanup(
                    base_url="http://cpk-server:8080",
                    server_container="cpk-server",
                    operations_database_url="postgresql://operations",
                    provider_container="provider-a",
                    provider_token_file=Path("/provider-token"),
                    bootstrap_dir=Path("/bootstrap"),
                )

            self.assertEqual(status, 0)
            historical.assert_called_once()
            failed_connector.assert_not_called()
            self.assertEqual(workflow.release_reservation_statuses, [])
            absent.assert_called_once_with(
                (),
                failed_connector_effects={},
                uncertain_connector_runs=set(),
            )
            emergency.assert_not_called()

    def test_abort_custody_verification_requires_each_exact_version_revoked(self) -> None:
        with _controller_module() as controller:
            resource = _resource(controller)
            audit_rows = [
                {
                    "outcome": "revoked",
                    "version_id": resource.provider_version_id,
                }
            ]
            with patch.object(
                controller,
                "_provider_audit_rows",
                return_value=audit_rows,
            ) as audit:
                controller._assert_abort_generated_secret_versions_revoked(
                    (resource,),
                    provider_container="provider-a",
                    workspace_id="workspace-a",
                )
            audit.assert_called_once_with("provider-a", "workspace-a")

            with patch.object(
                controller,
                "_provider_audit_rows",
                return_value=[],
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "revocation evidence is incomplete",
                ):
                    controller._assert_abort_generated_secret_versions_revoked(
                        (resource,),
                        provider_container="provider-a",
                        workspace_id="workspace-a",
                    )

    def test_cloudflare_emergency_compensator_uses_exact_reverse_order(self) -> None:
        with _controller_module() as controller, tempfile.TemporaryDirectory() as directory:
            calls: list[tuple[str, str]] = []
            api_token_file = Path(directory) / "api-token"
            api_token_file.write_text("test-only-api-token", encoding="utf-8")

            class Client:
                def delete_dns_record(self, record_id: str) -> None:
                    calls.append(("dns", record_id))

                def delete_tunnel_connections(self, tunnel_id: str) -> None:
                    calls.append(("connections", tunnel_id))

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
                patch.object(
                    controller,
                    "_stop_remove_exact_failed_connector",
                    side_effect=lambda effect: calls.append(
                        ("connector", effect.container_name)
                    ),
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
                    failed_connector_effect=_failed_connector_effect(controller),
                )

            self.assertEqual(failed, ())
            self.assertEqual(
                calls,
                [
                    ("custody", "version-exact"),
                    ("connector", "container-exact"),
                    ("dns", "dns-exact"),
                    ("connections", "tunnel-exact"),
                    ("tunnel", "tunnel-exact"),
                ],
            )

    def test_failed_connector_effect_is_reconstructed_from_one_exact_success(
        self,
    ) -> None:
        with _controller_module() as controller:
            effect = controller._decode_exact_failed_connector_effect(
                expected_workspace_id="workspace-a",
                expected_run_id="run-failed",
                connector_node_id="cloudflared-gateway",
                rows=_failed_connector_rows(),
            )

            self.assertEqual(effect, _failed_connector_effect(controller))
            descriptor = effect.bounded_descriptor()
            self.assertNotIn("token", str(descriptor).lower())
            self.assertNotIn("secret", str(descriptor).lower())

    def test_connector_run_evidence_separates_accepted_graph_from_failed_effect(
        self,
    ) -> None:
        with _controller_module() as controller:
            failed = controller._decode_exact_connector_run_evidence(
                expected_workspace_id="workspace-a",
                expected_run_id="run-failed",
                connector_node_id="cloudflared-gateway",
                accepted_graph_id="graph-current",
                rows=_failed_connector_rows(),
            )
            self.assertEqual(failed, _failed_connector_effect(controller))

            row = _failed_connector_rows()[0]
            accepted_rows = (
                (
                    "run-accepted",
                    "succeeded",
                    row[2],
                    "plan-accepted",
                    "graph-current",
                    row[5],
                    row[6],
                ),
            )
            self.assertIsNone(
                controller._decode_exact_connector_run_evidence(
                    expected_workspace_id="workspace-a",
                    expected_run_id="run-accepted",
                    connector_node_id="cloudflared-gateway",
                    accepted_graph_id="graph-current",
                    rows=accepted_rows,
                )
            )

            for name, rows in {
                "wrong-graph": (
                    accepted_rows[0][:4]
                    + ("graph-other",)
                    + accepted_rows[0][5:],
                ),
                "in-progress": (
                    (accepted_rows[0][0], "running") + accepted_rows[0][2:],
                ),
            }.items():
                with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError,
                    "connector run evidence is uncertain",
                ):
                    controller._decode_exact_connector_run_evidence(
                        expected_workspace_id="workspace-a",
                        expected_run_id="run-accepted",
                        connector_node_id="cloudflared-gateway",
                        accepted_graph_id="graph-current",
                        rows=rows,
                    )

    def test_owned_ingress_rows_are_strict_and_duplicate_free(self) -> None:
        with _controller_module() as controller:
            row = (
                "cloudflare",
                "gateway-a",
                1,
                "tunnel-a",
                "dns-a",
                "cpk-gateway-a.openj92.dev",
                "zone-a",
                "run-a",
                "secret://generated/ingress/token-a",
                "version-a",
                1,
            )
            resources = controller._decode_exact_owned_ingress_resources((row,))
            self.assertEqual(resources[0].source_run_id, "run-a")

            for name, rows in {
                "null": (row[:3] + (None,) + row[4:],),
                "coerced-epoch": (row[:2] + ("1",) + row[3:],),
                "unknown-provider": (("other",) + row[1:],),
                "duplicate": (row, row),
            }.items():
                with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError,
                    "owned ingress evidence is uncertain",
                ):
                    controller._decode_exact_owned_ingress_resources(rows)

    def test_failed_connector_effect_rejects_missing_duplicate_or_contradictory_evidence(
        self,
    ) -> None:
        with _controller_module() as controller:
            valid = _failed_connector_rows()
            cases = {
                "missing": (valid[0][:-1] + (None,),),
                "duplicate": (valid[0], valid[0]),
                "wrong-workspace": (
                    valid[0][:2] + ("workspace-other",) + valid[0][3:],
                ),
                "non-failed-run": (
                    (valid[0][0], "succeeded") + valid[0][2:],
                ),
                "null-plan": (valid[0][:3] + (None,) + valid[0][4:],),
            }
            for name, rows in cases.items():
                with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError,
                    "failed connector evidence is uncertain",
                ):
                    controller._decode_exact_failed_connector_effect(
                        expected_workspace_id="workspace-a",
                        expected_run_id="run-failed",
                        connector_node_id="cloudflared-gateway",
                        rows=rows,
                    )

    def test_exact_failed_connector_requires_every_ownership_label_before_mutation(
        self,
    ) -> None:
        with _controller_module() as controller:
            effect = _failed_connector_effect(controller)
            expected_labels = effect.expected_labels()
            container = MagicMock()
            container.name = effect.container_name
            container.status = "running"
            container.attrs = {"Config": {"Labels": expected_labels}}
            client = MagicMock()
            client.containers.get.return_value = container

            with patch.object(controller.docker, "from_env", return_value=client):
                controller._stop_remove_exact_failed_connector(effect)

            client.containers.get.assert_called_once_with("container-exact")
            container.stop.assert_called_once_with(timeout=10)
            container.remove.assert_called_once_with()

            for label in expected_labels:
                with self.subTest(label=label):
                    mismatched = dict(expected_labels)
                    mismatched[label] = "other"
                    container.reset_mock()
                    container.attrs = {"Config": {"Labels": mismatched}}
                    with (
                        patch.object(controller.docker, "from_env", return_value=client),
                        self.assertRaisesRegex(RuntimeError, "ownership is uncertain"),
                    ):
                        controller._stop_remove_exact_failed_connector(effect)
                    container.stop.assert_not_called()
                    container.remove.assert_not_called()

    def test_cloudflare_cleanup_faults_remain_ordered_and_independently_attempted(
        self,
    ) -> None:
        with _controller_module() as controller, tempfile.TemporaryDirectory() as directory:
            calls: list[str] = []
            api_token_file = Path(directory) / "api-token"
            api_token_file.write_text("test-only-api-token", encoding="utf-8")

            class Client:
                def delete_dns_record(self, _record_id: str) -> None:
                    calls.append("dns")
                    raise RuntimeError("bounded")

                def delete_tunnel_connections(self, _tunnel_id: str) -> None:
                    calls.append("connections")
                    raise RuntimeError("bounded")

                def delete_tunnel(self, _tunnel_id: str) -> None:
                    calls.append("tunnel")
                    raise RuntimeError("bounded")

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
                    side_effect=lambda **_arguments: (
                        calls.append("custody"),
                        (_ for _ in ()).throw(RuntimeError("bounded")),
                    ),
                ),
                patch.object(
                    controller,
                    "_stop_remove_exact_failed_connector",
                    side_effect=lambda _effect: (
                        calls.append("connector"),
                        (_ for _ in ()).throw(RuntimeError("bounded")),
                    ),
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
                    failed_connector_effect=_failed_connector_effect(controller),
                )

            self.assertEqual(
                calls,
                ["custody", "connector", "dns", "connections", "tunnel"],
            )
            self.assertEqual(
                failed,
                ("custody", "connector", "dns", "connections", "tunnel"),
            )

    def test_missing_connector_evidence_preserves_later_exact_provider_attempts(
        self,
    ) -> None:
        with _controller_module() as controller, tempfile.TemporaryDirectory() as directory:
            calls: list[str] = []
            api_token_file = Path(directory) / "api-token"
            api_token_file.write_text("test-only-api-token", encoding="utf-8")

            class Client:
                def delete_dns_record(self, _record_id: str) -> None:
                    calls.append("dns")

                def delete_tunnel_connections(self, _tunnel_id: str) -> None:
                    calls.append("connections")

                def delete_tunnel(self, _tunnel_id: str) -> None:
                    calls.append("tunnel")

            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENJ92_CLOUDFLARE_ACCOUNT_ID": "account-exact",
                        "OPENJ92_CLOUDFLARE_ZONE": "openj92.dev",
                    },
                    clear=False,
                ),
                patch.object(controller, "_provider_revoke_exact_version"),
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
                    failed_connector_effect=None,
                )

            self.assertEqual(calls, ["dns", "connections", "tunnel"])
            self.assertEqual(failed, ("connector-evidence",))

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
        for scope in (
            "delegation-key:register",
            "delegation-key:read",
            "delegation-key:activate",
            "delegation-key:retire",
            "delegation-key:revoke",
            "delegation-key:use",
        ):
            self.assertIn(f'"{scope}"', smoke)
        for fixture in (
            '"$SERVER_CONTAINER"',
            '"$SECRETS_CONTAINER"',
            '"$POSTGRES_CONTAINER"',
        ):
            self.assertIn(f"docker rm -fv {fixture}", smoke)

    def test_abort_orchestrator_is_provider_neutral(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("cloudflare", source.lower())
        self.assertNotIn("tunnel_id", source)
        self.assertNotIn("dns_record_id", source)

        descriptor = _resource(_module()).bounded_descriptor()
        self.assertNotIn("secret_reference", descriptor)

    def test_owned_resource_carries_bounded_failed_source_run(self) -> None:
        module = _module()

        resource = module.ExactOwnedIngressResource(
            provider_kind="cloudflare",
            ingress_id="gateway-a",
            epoch=1,
            public_provider_coordinates={
                "tunnel_id": "tunnel-exact",
                "dns_record_id": "dns-exact",
                "hostname": "cpk-gateway-a.openj92.dev",
                "zone_id": "zone-exact",
            },
            source_run_id="run-failed",
            secret_reference="secret://generated/ingress/token-a",
            provider_version_id="version-exact",
            provider_version_number=1,
        )

        self.assertEqual(resource.source_run_id, "run-failed")
        self.assertEqual(
            resource.bounded_descriptor()["source_run_id"],
            "run-failed",
        )
        self.assertNotIn("secret_reference", resource.bounded_descriptor())


class RecordingWorkflow:
    def __init__(
        self,
        controller,
        *,
        fail_transition: bool,
    ) -> None:
        self.controller = controller
        self.fail_transition = fail_transition
        self.transition_graph_names: list[str] = []
        self.transition_expected_desired_ids: list[str] = []
        self.release_reservation_statuses: list[str] = []

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

    def read_public_ingress_resources(self) -> dict[str, object]:
        return {
            "workspace_id": "workspace-a",
            "items": [
                {
                    "reservation_id": "reservation-exact",
                    "ingress_id": "gateway-a",
                    "lifecycle": "retained",
                    "status": "reserved",
                    "version": 2,
                    "realizations": [{"epoch": 1, "status": "removed"}],
                }
            ],
        }

    def read_public_ingress_resources_mcp(self) -> dict[str, object]:
        return self.read_public_ingress_resources()

    def run_approved_public_ingress_reservation_release(
        self,
        *,
        title: str,
        reservation: dict[str, object],
    ):
        del title
        self.release_reservation_statuses.append(str(reservation["status"]))
        return self.controller.HostedReleaseResult(
            plan_id="plan-release",
            approval_id="approval-release",
            run_id="run-release",
            current_graph_id="graph-empty",
        )


def _resource(
    module,
    *,
    provider_kind: str = "cloudflare",
    source_run_id: str = "run-failed",
    epoch: int = 1,
):
    suffix = "" if epoch == 1 else f"-{epoch}"
    return module.ExactOwnedIngressResource(
        provider_kind=provider_kind,
        ingress_id="gateway-a",
        epoch=epoch,
        public_provider_coordinates={
            "tunnel_id": f"tunnel-exact{suffix}",
            "dns_record_id": f"dns-exact{suffix}",
            "hostname": "cpk-gateway-a.openj92.dev",
            "zone_id": "zone-exact",
        },
        source_run_id=source_run_id,
        secret_reference=f"secret://generated/ingress/token{suffix or '-a'}",
        provider_version_id=f"version-exact{suffix}",
        provider_version_number=epoch,
    )


def _failed_connector_effect(
    module,
    *,
    run_id: str = "run-failed",
    desired_graph_id: str = "graph-failed",
):
    return module.ExactFailedDockerNodeEffect(
        workspace_id="workspace-a",
        run_id=run_id,
        plan_id="plan-failed",
        desired_graph_id=desired_graph_id,
        activity_id="activity-start-connector",
        runtime_id="runtime-a",
        node_id="cloudflared-gateway",
        container_name="container-exact",
    )


def _failed_connector_rows():
    plan_payload = {
        "schema": "control-plane-kit.activity-plan",
        "version": 1,
        "activities": [
            {
                "activity_id": "activity-start-connector",
                "operation": {
                    "kind": "start-node",
                    "target": {
                        "kind": "node",
                        "node_id": "cloudflared-gateway",
                    },
                },
            }
        ],
    }
    event_payload = {
        "activity_id": "activity-start-connector",
        "evidence": {
            "action": "created",
            "node_id": "cloudflared-gateway",
            "runtime_id": "runtime-a",
            "container": "container-exact",
            "network": "network-exact",
            "image": "registry.example/image@sha256:bounded",
        },
        "failure": None,
        "recovery": None,
    }
    return (
        (
            "run-failed",
            "failed",
            "workspace-a",
            "plan-failed",
            "graph-failed",
            plan_payload,
            event_payload,
        ),
    )


if __name__ == "__main__":
    unittest.main()
