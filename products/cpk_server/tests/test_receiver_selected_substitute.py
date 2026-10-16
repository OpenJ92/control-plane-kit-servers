"""Existing connector substitute only; no real provider or recipient claim."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.operations.run_identity import RunId
from control_plane_kit_core.planning import ActivityId, NodeTarget, StartNode, ReconcileNode, RemoveNodeResource
from control_plane_kit_core.products import (
    ContainerServerProduct, ProductIdentity, OciImageReference, ProductRuntimeContract, ProductDescriptorCodec, ProductReference,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.runtime_effects import (
    RuntimeEffectRequest, RuntimeEffectSource, RuntimeEffectKind, RuntimeProductMaterial, EffectResultKind,
)
from control_plane_kit_core.runtime_effect_observation import runtime_effect_intent_for_request, runtime_effect_intent_fingerprint
from control_plane_kit_core.secret_installation import secret_material_selection_fingerprint, secret_installation_receipt_for_result
from control_plane_kit_core.secret_selections import SecretVersionSelection
from control_plane_kit_core.secret_version_grants import SecretVersionResolutionGrant
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretDenied, SecretFileDelivery, SecretFileMode, SecretFilePathBinding
from control_plane_kit_core.types import RuntimeKind


def request(custody, *, version="synthetic-version", node="connector", operation=StartNode, delivery=None):
    selection = SecretVersionSelection(custody.reference, custody.intent, version)
    delivery = delivery or SecretFileDelivery("/run/secrets/cloudflare-tunnel-token", custody.reference,
        custody.intent, SecretFileMode.OWNER_READ_ONLY, SecretFilePathBinding("TUNNEL_TOKEN_FILE"))
    product = ContainerServerProduct(ProductIdentity("fixture", "connector", 1),
        OciImageReference("example.invalid", "connector", "sha256:" + "a" * 64),
        ProductRuntimeContract(secret_deliveries=(delivery,)))
    material = RuntimeProductMaterial(node, "docker", ProductReference.from_document(
        ProductDescriptorCodec().encode_document(product)), product, secret_selections=(selection,))
    effect = "effect-start" if operation is StartNode else "effect-reconcile"
    value = RuntimeEffectRequest(effect, RuntimeEffectKind.REALIZE_ACTIVITY, RuntimeKind.DOCKER,
        RuntimeEffectSource(custody.workspace_id, "request-a", RunId("run-a"), "plan-a", "base-a", "desired-a", effect),
        ActivityId(effect), operation(NodeTarget(node)), products=(material,), authority_ref=RuntimeAuthorityReference("local-docker"))
    grant = SecretVersionResolutionGrant(authorization_id="suse_" + "d" * 64, workspace_id=custody.workspace_id,
        reference_registration_id="sref_" + "e" * 64, provider_registration_id=custody.provider_registration_id,
        endpoint_reference=custody.endpoint_reference, credential_reference=custody.credential_reference,
        selection=selection, actor_subject="fixture-worker", correlation_id="fixture-resolve", intent_fingerprint="f" * 64,
        operation_id=value.source.request_id, run_id=value.source.run_id.value, activity_id=value.activity_id.value,
        effect_id=effect, request_fingerprint=runtime_effect_intent_fingerprint(runtime_effect_intent_for_request(value)),
        selection_fingerprint=secret_material_selection_fingerprint(value))
    return replace(value, secret_resolution_grants=(grant,))


class SelectedSubstituteTests(unittest.TestCase):
    def fixture(self):
        from receiver_acceptance_ports import ComputeSubstitute, IngressSubstitute
        from test_docker_image_update_provider import custody_grant
        compute = ComputeSubstitute()
        ingress = IngressSubstitute(compute)
        custody = custody_grant()
        allocation = ingress.create(SimpleNamespace(hostname="fixture.invalid"), authority=None,
            allocation_name="fixture", origin_service_url="http://fixture.invalid", secret_resolution_grant=None,
            secret_custody_grant=custody)
        authority = SimpleNamespace(authority_ref=RuntimeAuthorityReference("local-docker"))
        return compute, ingress, custody, allocation, authority

    def test_exact_resolution_recipient_receipts_and_allocation_lifetime(self):
        from receiver_acceptance_ports import synthetic_runtime_registration
        from control_plane_kit_operations.ingress_authorities import require_cloudflared_tunnel_token_delivery
        compute, ingress, custody, allocation, authority = self.fixture()
        registration = synthetic_runtime_registration(compute)
        self.assertIs(registration.adapter, compute)
        self.assertTrue(registration.exact_version_execute_with_authority)
        self.assertFalse(registration.exact_version_execute or registration.exact_version_observe)
        prior = None
        for operation, disposition in ((StartNode, "created"), (ReconcileNode, "replaced")):
            selected = request(custody, operation=operation)
            delivery = require_cloudflared_tunnel_token_delivery(selected.products[0].product.runtime_contract.secret_deliveries)
            result = compute.execute_with_authority(selected, authority)
            self.assertIs(result.kind, EffectResultKind.SUCCEEDED)
            receipt = secret_installation_receipt_for_result(selected, result)
            self.assertEqual(receipt.disposition.value, disposition)
            self.assertEqual(receipt.prior_realization_fingerprint, prior)
            self.assertEqual(receipt.current_realization_fingerprint, compute.identities["connector"])
            value = ingress.resolve(selected.secret_resolution_grants[0]).value.reveal()
            incarnation, environment, files = compute._recipient_material["connector"]
            self.assertEqual(incarnation, compute.identities["connector"])
            self.assertEqual(environment, {"TUNNEL_TOKEN_FILE": delivery.target_path})
            content, mode, binding = files[delivery.target_path]
            self.assertTrue(content == value, "private synthetic recipient differs")
            self.assertEqual((mode, binding), (SecretFileMode.OWNER_READ_ONLY, "TUNNEL_TOKEN_FILE"))
            self.assertNotIn(value, json.dumps(result.descriptor()))
            self.assertEqual(result.evidence["secret_recipient_boundary"], "synthetic-in-memory")
            prior = compute.identities["connector"]
        compute.execute_with_authority(replace(selected, operation=RemoveNodeResource(NodeTarget("connector")),
            secret_resolution_grants=()), authority)
        ingress.teardown(authority=None, resources=allocation, secret_resolution_grant=None, secret_custody_grant=custody)
        self.assertFalse(compute._recipient_material or ingress._private_material or ingress.allocations)
        self.assertIsInstance(ingress.resolve(selected.secret_resolution_grants[0]), SecretDenied)

    def test_unavailable_exact_material_refuses_before_simulated_installation(self):
        for fault in ("version", "provider", "missing", "grant"):
            with self.subTest(fault=fault):
                compute, ingress, custody, allocation, authority = self.fixture()
                selected = request(custody, version="foreign-version" if fault == "version" else "synthetic-version")
                if fault == "provider":
                    selected = replace(selected, secret_resolution_grants=(replace(selected.secret_resolution_grants[0],
                        provider_registration_id="foreign-provider"),))
                if fault == "missing":
                    ingress.teardown(authority=None, resources=allocation, secret_resolution_grant=None, secret_custody_grant=custody)
                if fault == "grant":
                    selected = replace(selected, secret_resolution_grants=())
                result = compute.execute_with_authority(selected, authority)
                self.assertIs(result.kind, EffectResultKind.FAILED)
                self.assertFalse(compute.installed or compute.identities or compute._recipient_material or compute.configuration_refs)
                self.assertNotIn("secret_installation_receipt", result.evidence)

    def test_named_process_selected_material_refuses_before_process_effects(self):
        from live_unlisted_receiver import ProcessCompute, EXAMPLES
        unused, ingress, custody, allocation, authority = self.fixture()
        processes = Mock()
        compute = ProcessCompute(processes)
        compute.selected_resolver = ingress
        for operation in (StartNode, ReconcileNode):
            with patch.object(ingress, "resolve", wraps=ingress.resolve) as resolve:
                result = compute.execute_with_authority(request(custody, node=EXAMPLES[0][0], operation=operation), authority)
                self.assertIs(result.kind, EffectResultKind.UNSUPPORTED)
                self.assertFalse(compute.calls or compute.installed or compute.identities)
                resolve.assert_not_called()
        self.assertFalse(processes.mock_calls)

    def test_recipient_mismatch_has_no_receipt_and_other_node_refuses(self):
        class LostRecipient(dict):
            def __setitem__(self, key, value):
                super().__setitem__(key, ("foreign-incarnation", {}))
        compute, ingress, custody, allocation, authority = self.fixture()
        with patch.object(ingress, "resolve", wraps=ingress.resolve) as resolve:
            refused = compute.execute_with_authority(request(custody, node="other"), authority)
            self.assertIs(refused.kind, EffectResultKind.UNSUPPORTED)
            resolve.assert_not_called()
        self.assertFalse(compute.installed or compute.identities)
        unsupported = SecretEnvironmentDelivery("TUNNEL_TOKEN", custody.reference, custody.intent)
        result = compute.execute_with_authority(request(custody, delivery=unsupported), authority)
        self.assertIs(result.kind, EffectResultKind.UNSUPPORTED)
        self.assertFalse(compute.installed or compute.identities)
        compute._recipient_material = LostRecipient()
        result = compute.execute_with_authority(request(custody), authority)
        self.assertIs(result.kind, EffectResultKind.UNCERTAIN)
        self.assertNotIn("secret_installation_receipt", result.evidence)
        self.assertNotIn("secret_resolution_receipt", result.evidence)
