"""S1 process-port ordering/reporting; doubles are not physical-install proof."""
from types import SimpleNamespace
import unittest

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.configuration_instances import ConfigurationInstanceRef, ConfigurationInstanceSelection
from control_plane_kit_core.configuration_installation import configuration_installation_receipt_for_result
from control_plane_kit_core.configuration_invocation import configuration_invocation_correlation_for_request
from control_plane_kit_core.operations.run_identity import RunId
from control_plane_kit_core.planning import ActivityId, NodeTarget, ReconcileNode, StartNode
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
