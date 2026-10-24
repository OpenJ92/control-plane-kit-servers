"""S1 process-port ordering/reporting; doubles are not physical-install proof."""
from types import SimpleNamespace
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import AsyncMock

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.configuration_instances import ConfigurationInstanceRef, ConfigurationInstanceSelection
from control_plane_kit_core.configuration_installation import configuration_installation_receipt_for_result
from control_plane_kit_core.configuration_invocation import configuration_invocation_correlation_for_request
from control_plane_kit_core.operations.run_identity import RunId
from control_plane_kit_core.operations.lifecycle import ActivityEventKind, FailureCategory
from control_plane_kit_core.planning import (
    ActivityId, NodeTarget, ReconcileNode, StartNode, ActivityPlan, PlannedActivity, DEFAULT_ACTIVITY_PLAN_CODEC,
)
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity,
    ProductReference, ProductRuntimeContract,
)
from control_plane_kit_core.runtime_effects import (
    EffectResultKind, RuntimeEffectKind, RuntimeEffectRequest, RuntimeEffectSource, RuntimeProductMaterial,
)
from control_plane_kit_core.types import RuntimeKind


NAME = "palette-example"


def request(operation, color="amber"):
    artifact = ConfigurationArtifact("palette-data", "/private/palette/colors.json",
        ConfigurationMediaType.JSON, '{"colors":["' + color + '"]}')
    product = ContainerServerProduct(ProductIdentity("test", "palette", 1),
        OciImageReference("example.invalid", "palette", "sha256:" + "d" * 64),
        ProductRuntimeContract(configuration_artifacts=(artifact,)))
    material = RuntimeProductMaterial(NAME, "docker",
        ProductReference.from_document(ProductDescriptorCodec().encode_document(product)), product)
    ref = ConfigurationInstanceRef("allocation-" + color, "workspace-a", "docker", NAME,
        artifact.artifact_id, artifact.target_path, artifact.media_type, artifact.file_mode,
        artifact.content_digest)
    return RuntimeEffectRequest("event-" + color, RuntimeEffectKind.CONFIGURATION_ACTIVITY_V1,
        RuntimeKind.DOCKER, RuntimeEffectSource("workspace-a", "request-a", RunId("run-a"),
            "plan-a", "base-a", "desired-a", "event-" + color), ActivityId("install-palette"),
        operation(NodeTarget(NAME)), products=(material,),
        configuration_instances=ConfigurationInstanceSelection((ref,)))


class ProcessPort:
    """Only the test-owned process boundary, never Operations durable state."""
    def __init__(self, fault=None):
        self.fault = fault
        self.replacement_started = set()
        self.calls = []
        self.observed_installed = []
        self.identities = {NAME: "b" * 64}  # Actual current epoch after a same-config restart.

    def install(self, name, material):
        self.calls.append(("install", name, material))
        self.observed_installed.append(dict(self.compute.installed))
        self.identities[name] = "c" * 64
        return self.identities[name]

    def replace(self, name, material):
        self.calls.append(("replace", name, material))
        self.observed_installed.append(dict(self.compute.installed))
        if self.fault == "stage":
            raise OSError("test-private-diagnostic")
        self.replacement_started.add(name)
        if self.fault == "launch":
            raise OSError("test-private-diagnostic")
        prior = self.identities[name]
        self.identities[name] = "c" * 64
        return prior, self.identities[name]


class ProcessMaterialTests(unittest.TestCase):
    def compute(self, fault=None):
        from live_unlisted_receiver import ProcessCompute
        port = ProcessPort(fault)
        compute = ProcessCompute(port)
        port.compute = compute
        return compute, port

    def test_start_records_material_only_after_process_installation(self):
        compute, port = self.compute()
        selected = request(StartNode)
        result = compute.execute_with_authority(selected, SimpleNamespace(authority_ref=None))
        self.assertEqual(port.observed_installed, [{}])
        self.assertEqual(result.kind, EffectResultKind.SUCCEEDED)
        self.assertEqual(compute.installed[NAME], selected.products[0])
        self.assertEqual(compute.identities[NAME], port.identities[NAME])

    def replacement(self, fault=None):
        compute, port = self.compute(fault)
        prior = request(StartNode).products[0]
        compute.installed[NAME] = prior
        compute.identities[NAME] = "a" * 64  # Deliberately stale pre-health-restart observation.
        selected = request(ReconcileNode, "teal")
        result = compute.execute_with_authority(selected, SimpleNamespace(authority_ref=None))
        return compute, port, prior, selected, result

    def test_replacement_receipt_uses_observed_processes_after_effect(self):
        compute, port, prior, selected, result = self.replacement()
        self.assertEqual(port.calls, [("replace", NAME, selected.products[0])])
        self.assertEqual(port.observed_installed, [{NAME: prior}])
        self.assertEqual(result.kind, EffectResultKind.SUCCEEDED)
        receipt = configuration_installation_receipt_for_result(
            configuration_invocation_correlation_for_request(selected), result)
        self.assertEqual(receipt.prior_realization_fingerprint, "b" * 64)
        self.assertEqual(receipt.current_realization_fingerprint, port.identities[NAME])
        self.assertEqual(compute.installed[NAME], selected.products[0])
        self.assertEqual(compute.identities[NAME], port.identities[NAME])

    def test_pre_stop_failure_does_not_publish_installation(self):
        self.check_failure("stage", EffectResultKind.FAILED)

    def test_post_stop_failure_remains_uncertain_without_success_receipt(self):
        self.check_failure("launch", EffectResultKind.UNCERTAIN)

    def check_failure(self, fault, kind):
        compute, port, prior, selected, result = self.replacement(fault)
        self.assertEqual(result.kind, kind)
        self.assertEqual(port.calls, [("replace", NAME, selected.products[0])])
        self.assertEqual(compute.installed[NAME], prior)
        self.assertEqual(compute.identities[NAME], "a" * 64)
        self.assertEqual(compute.configuration_refs, {})
        self.assertNotIn("configuration_installation_receipt", result.evidence)
        self.assertNotIn("test-private-diagnostic", repr(result))


class StartDiagnosticTests(unittest.TestCase):
    def test_failure_reader_consumes_public_history_page_items(self):
        from receiver_acceptance_operations import PublicOperationsDriver
        event = {"event_type": ActivityEventKind.STEP_UNSUPPORTED.value, "activity_id": "start-connector",
            "failure": {"category": FailureCategory.OPERATOR_REVIEW.value,
                "code": "runtime.effect-unsupported", "details": {"effect_outcome": {"kind": "unsupported"}}}}
        plan = {"payload": DEFAULT_ACTIVITY_PLAN_CODEC.encode(ActivityPlan((
            PlannedActivity(ActivityId("start-connector"), StartNode(NodeTarget("connector"))),)))}
        reader = AsyncMock(return_value={"items": [event], "pages": 1, "next_cursor": None})
        driver = SimpleNamespace(workspace_id="workspace-a", _history_page=reader)
        output = StringIO()
        with redirect_stdout(output):
            asyncio.run(PublicOperationsDriver._emit_execution_failure(driver, "run-a", plan))
        reader.assert_awaited_once_with("read.run-events", path={"workspace_id": "workspace-a", "run_id": "run-a"})
        actual = json.loads(output.getvalue())
        self.assertEqual(actual["receiver_execution_failure"], "observed")
        self.assertEqual(actual["failures"][0]["event_type"], ActivityEventKind.STEP_UNSUPPORTED.value)
        self.assertIsNone(actual["failures"][0]["runtime_failure_code"])
        self.assertEqual(actual["failures"][0]["failure_category"], "operator_review")
        self.assertEqual(actual["failures"][0]["activity_id"], "start-connector")
        self.assertEqual(actual["failures"][0]["operation"], "start-node")
        self.assertEqual(actual["failures"][0]["node_id"], "connector")
        reader.side_effect = RuntimeError("PRIVATE-READ-FAILURE")
        output = StringIO()
        with redirect_stdout(output):
            asyncio.run(PublicOperationsDriver._emit_execution_failure(driver, "run-a", plan))
        self.assertEqual(json.loads(output.getvalue()), {"receiver_execution_failure": "evidence-unavailable"})

    def test_public_failure_diagnostic_keeps_only_bounded_classifications(self):
        from receiver_acceptance_operations import execution_failure_codes
        event = {"event_type": "step_failed", "payload": {"secret": "PRIVATE-PAYLOAD"},
            "failure": {"category": "terminal", "code": "runtime.effect-failed", "message": "PRIVATE-MESSAGE",
                "details": {"secret": "PRIVATE-DETAIL", "effect_outcome": {
                    "runtime_failure_code": "runtime.secret-version-unsupported", "token": "PRIVATE-TOKEN"}}}}
        result = execution_failure_codes([event] * 40)
        self.assertTrue(result["events_truncated"])
        self.assertEqual(len(result["failures"]), 32)
        self.assertEqual(result["failures"][0], {"event_type": "step_failed", "failure_category": "terminal",
            "activity_id": None, "operation": None, "node_id": None,
            "failure_code": "runtime.effect-failed", "runtime_failure_code": "runtime.secret-version-unsupported"})
        self.assertNotIn("PRIVATE", json.dumps(result))
        for kind in ActivityEventKind:
            event["event_type"] = kind.value
            self.assertEqual(execution_failure_codes([event])["failures"][0]["event_type"], kind.value)
        for category in FailureCategory:
            event["failure"]["category"] = category.value
            self.assertEqual(execution_failure_codes([event])["failures"][0]["failure_category"], category.value)
        for kind, category, code in ((ActivityEventKind.STEP_UNSUPPORTED, FailureCategory.OPERATOR_REVIEW,
                "runtime.effect-unsupported"), (ActivityEventKind.STEP_UNCERTAIN, FailureCategory.UNCERTAIN,
                "runtime.effect-uncertain")):
            observed = execution_failure_codes([{"event_type": kind.value,
                "failure": {"category": category.value, "code": code, "details": {"effect_outcome": {}}}}])
            self.assertIsNone(observed["failures"][0]["runtime_failure_code"])
            self.assertEqual(observed["failures"][0]["failure_code"], code)
        event["failure"]["code"] = "PRIVATE/" + "x" * 200
        self.assertIsNone(execution_failure_codes([event])["failures"][0]["failure_code"])

    def test_host_diagnostic_preserves_suppressed_owner_context_with_bounds(self):
        from unlisted_controller_host import DiagnosticApplicationBoundary
        from control_plane_kit_operations.cpk_server import _prepare_deployment, CpkServerApplicationError
        output = StringIO()
        diagnostic = SimpleNamespace(diagnostic_count=0)
        try:
            _prepare_deployment(None, SimpleNamespace(payload={"desired_graph": {"PRIVATE": "VALUE"}},
                path_parameters={}), None)
        except CpkServerApplicationError as error:
            self.assertTrue(error.__suppress_context__)
            with redirect_stdout(output):
                DiagnosticApplicationBoundary._diagnose(diagnostic, error, "command.deployment.prepare")
        result = json.loads(output.getvalue())
        self.assertEqual(result["exception_chain"][0]["kind"], "CpkServerApplicationError")
        self.assertEqual(result["exception_chain"][1]["kind"], "MalformedGraphDescriptor")
        self.assertTrue(result["exception_chain"][1]["frames"])
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertFalse(result["chain_truncated"])
        errors = [ValueError("PRIVATE-MESSAGE") for _ in range(10)]
        for left, right in zip(errors, errors[1:]):
            left.__context__ = right
        output = StringIO()
        with redirect_stdout(output):
            DiagnosticApplicationBoundary._diagnose(diagnostic, errors[0], "command.deployment.prepare")
            errors[0].__context__ = errors[0]
            DiagnosticApplicationBoundary._diagnose(diagnostic, errors[0], "command.deployment.prepare")
            for _ in range(10):
                DiagnosticApplicationBoundary._diagnose(diagnostic, errors[0], "command.deployment.prepare")
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(rows), 7)
        self.assertEqual(len(rows[0]["exception_chain"]), 8)
        self.assertEqual(len(rows[1]["exception_chain"]), 1)
        self.assertTrue(all(row["chain_truncated"] for row in rows))
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_observer_preserves_exact_command_result_and_original_error(self):
        from receiver_acceptance_operations import ObservedEffectStart
        command, result, seen = object(), object(), []
        service = SimpleNamespace(execute=lambda value: seen.append(value) or result,
            execute_health=lambda value: seen.append(value) or result)
        observed = ObservedEffectStart(service, lambda error: self.fail("unexpected observation"))
        self.assertIs(observed.execute(command), result)
        self.assertIs(observed.execute_health(command), result)
        self.assertEqual(seen, [command, command])
        failure = ValueError("private-failure-text")
        def fail(value):
            self.assertIs(value, command)
            raise failure
        def broken_diagnostic(error):
            self.assertIs(error, failure)
            raise RuntimeError("private-observer-text")
        service.execute = fail
        observed = ObservedEffectStart(service, broken_diagnostic)
        with self.assertRaises(ValueError) as raised:
            observed.execute(command)
        self.assertIs(raised.exception, failure)

    def test_diagnostic_bounds_output_and_omits_exception_values(self):
        from live_unlisted_receiver import StartFailureDiagnostic
        diagnostic = StartFailureDiagnostic()
        output = StringIO()
        with redirect_stdout(output):
            for _ in range(6):
                try:
                    raise ValueError("private-failure-text")
                except ValueError as error:
                    diagnostic(error)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertNotIn("private-failure-text", output.getvalue())
        for line in lines:
            chain = json.loads(line)["unlisted_start_failure"]
            self.assertEqual(chain, [{"kind": "ValueError", "frames": []}])
