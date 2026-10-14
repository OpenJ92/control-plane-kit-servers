"""Generated custody composition through the real private fixture provider."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from control_plane_kit_core.secrets import (
    SecretCustodyGrant, SecretDenied, SecretProviderEndpointReference, SecretReference,
    SecretResolutionGrant, SecretResolved, SecretUseIntent,
)


def custody_grant():
    return SecretCustodyGrant(custody_id="scust_" + "a" * 64, workspace_id="image-provider-test",
        provider_registration_id="sprov_" + "b" * 64,
        endpoint_reference=SecretProviderEndpointReference("generated-secrets"),
        credential_reference=SecretReference("secret://bootstrap/generated-secrets/client-token"),
        reference=SecretReference("secret://generated/ingress/fixture-token"),
        intent=SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, actor_subject="image-provider-test",
        correlation_id="image-custody-test", custody_fingerprint="c" * 64,
        run_id="run-test", activity_id="activity-test", effect_id="effect-test")


class DockerImageProviderTests(unittest.TestCase):
    def test_generated_route_writes_resolves_and_revokes_through_existing_provider(self):
        from docker_image_update_provider import SigningProviderProcess, SyntheticIngressAllocation
        grant = custody_grant()
        resolution = SecretResolutionGrant(authorization_id="suse_" + "d" * 64,
            workspace_id=grant.workspace_id, reference_registration_id="sref_" + "e" * 64,
            provider_registration_id=grant.provider_registration_id, endpoint_reference=grant.endpoint_reference,
            credential_reference=grant.credential_reference, reference=grant.reference, intent=grant.intent,
            actor_subject=grant.actor_subject, correlation_id="image-resolve-test", intent_fingerprint="f" * 64,
            run_id=grant.run_id, activity_id=grant.activity_id, effect_id=grant.effect_id)
        with TemporaryDirectory() as root:
            with SigningProviderProcess(Path(root) / "provider", grant.workspace_id,
                    "postgresql://fixture:fixture@127.0.0.1/fixture") as provider:
                ingress = SyntheticIngressAllocation(provider.composition.secret_custodian, grant.workspace_id)
                allocation = ingress.create(SimpleNamespace(hostname="cpk-1912.example.invalid"),
                    authority=None, allocation_name="fixture-allocation", origin_service_url="http://gateway:8000",
                    secret_resolution_grant=None, secret_custody_grant=grant)
                self.assertTrue(allocation.secret_custody_receipt.matches(grant))
                self.assertNotEqual(allocation.secret_custody_receipt.version_id, "synthetic-version")
                resolved = provider.composition.authorized_resolver.resolve(resolution)
                self.assertIsInstance(resolved, SecretResolved)
                self.assertTrue(resolved.value.reveal())
                self.assertEqual(resolved.reference, grant.reference)
                with self.assertRaises(RuntimeError):
                    ingress.teardown(authority=None, resources=allocation,
                        secret_resolution_grant=None,
                        secret_custody_grant=replace(grant, provider_registration_id="sprov_" + "f" * 64))
                self.assertIsInstance(provider.composition.authorized_resolver.resolve(resolution), SecretResolved)
                self.assertEqual(ingress.allocations["fixture-allocation"], allocation)
                ingress.teardown(authority=None, resources=allocation,
                    secret_resolution_grant=None, secret_custody_grant=grant)
                self.assertIsInstance(provider.composition.authorized_resolver.resolve(resolution), SecretDenied)
                self.assertFalse(ingress.allocations)

    def test_custody_failure_or_foreign_grant_does_not_admit_allocation(self):
        from docker_image_update_provider import SyntheticIngressAllocation
        grant = custody_grant()
        custodian = Mock()
        custodian.store.side_effect = RuntimeError("fixture custody unavailable")
        ingress = SyntheticIngressAllocation(custodian, grant.workspace_id)
        arguments = dict(authority=None, allocation_name="fixture-allocation",
            origin_service_url="http://gateway:8000", secret_resolution_grant=None)
        target = SimpleNamespace(hostname="cpk-1912.example.invalid")
        with self.assertRaisesRegex(RuntimeError, "fixture custody unavailable"):
            ingress.create(target, **arguments, secret_custody_grant=grant)
        self.assertFalse(ingress.allocations)
        self.assertFalse(ingress.calls)
        custodian.store.assert_called_once()
        custodian.reset_mock()
        with self.assertRaises(RuntimeError):
            ingress.create(target, **arguments,
                secret_custody_grant=replace(grant, workspace_id="foreign-workspace"))
        custodian.store.assert_not_called()
        self.assertFalse(ingress.allocations)
