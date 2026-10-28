"""Production semantic registrations; no permission-history or provider simulation."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker import DockerRuntimeEffectObserver, DockerRuntimeInterpreter
from control_plane_kit_interpreters.invocations import InvocationPortError
from control_plane_kit_operations.coordinator import ManagedHealthAdapterRegistration
from control_plane_kit_operations.ingress_authorities import IngressAuthorityProviderKind
from control_plane_kit_operations.ingress_realization import IngressProviderRegistration
from control_plane_kit_operations.managed_runtime_assignments import (
    ManagedRuntimeCapability, ManagedRuntimeCapabilityPolicy,
)
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from control_plane_kit_operations.workspace_permissions import WorkspaceAdministrationPolicy
from managed_native_material import NativeMaterial
from test_secret_provider_bootstrap import _provider_environment


class DynamicEffectCompositionTests(unittest.TestCase):
    def configuration(self):
        from control_plane_kit_interpreters.docker import DockerUnixSocketClientConfig
        from control_plane_kit_servers_cpk_server import server
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerRuntimeCapabilityBinding, DockerRuntimeClientSelector,
        )
        from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
        from control_plane_kit_servers_cpk_server.operations_application import WorkspaceAuthorityConfiguration
        world = NativeMaterial()
        administrator = PrincipalIdentity("issuer-a", "administrator-a", PrincipalKind.OPERATOR)
        capability = ManagedRuntimeCapability("installed-management-a")
        policy = ManagedRuntimeCapabilityPolicy("installation-a", (capability,))
        authority = WorkspaceAuthorityConfiguration(
            WorkspaceAdministrationPolicy(policy.installation_id, (administrator,), (administrator,)), policy)
        selector = DockerRuntimeClientSelector((), capability_policy=policy,
            capability_bindings=(DockerRuntimeCapabilityBinding(capability,
                DockerUnixSocketClientConfig("/var/run/synthetic-never-opened.sock", 5.0)),),
            unit_of_work_factory=Mock(side_effect=AssertionError("composition must not read assignments")))
        native = DockerManagedNativeConnection(selector, world.document, Mock())
        health = ManagedHealthBootstrap((world.authored.documents["gateway"],), selector, native=native)
        environment = {**_provider_environment(Path("/synthetic/provider.token")),
            "CPK_INGRESS_INTERPRETERS": "cloudflare"}
        config = replace(server.CpkServerBootstrapConfiguration.from_environment(environment),
            workspace_authority=authority, managed_health=health)
        return config, selector

    def test_dynamic_production_registers_distinct_actual_adapters_and_requires_ports(self):
        from control_plane_kit_servers_cpk_server import server
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBridge
        config, selector = self.configuration()
        for metadata in (None, object()):
            with self.subTest(exact_versions=metadata is not None), \
                    patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
                provider = server._SecretProviderComposition(authorized_resolver=Mock(),
                    secret_custodian=Mock(), metadata_reader=metadata)
                ports = server._operations_effect_ports(config, provider)
                runtime = ports.runtime_interpreters[RuntimeKind.DOCKER]
                observer = ports.runtime_observer
                self.assertIs(type(runtime), RuntimeAdapterRegistration)
                self.assertIs(type(runtime.adapter), DockerRuntimeInterpreter)
                self.assertEqual(runtime.invocation_profile, "cpk.semantic-invocations.v1")
                self.assertTrue(runtime.ordinary_verification_invocations)
                self.assertEqual(runtime.exact_version_execute, metadata is not None)
                self.assertEqual(runtime.exact_version_execute_with_authority, metadata is not None)
                self.assertFalse(runtime.exact_version_observe)
                self.assertIs(type(observer), RuntimeAdapterRegistration)
                self.assertIs(type(observer.adapter), DockerRuntimeEffectObserver)
                self.assertIsNot(runtime.adapter, observer.adapter)
                self.assertEqual(observer.invocation_profile, "cpk.semantic-invocations.v1")
                self.assertTrue(observer.original_runtime_observation_invocations)
                self.assertFalse(observer.exact_version_observe)
                self.assertFalse(observer.exact_version_execute)
                self.assertIs(type(ports.managed_health), ManagedHealthAdapterRegistration)
                self.assertIs(type(ports.managed_health.adapter), ManagedHealthBridge)
                self.assertEqual(ports.managed_health.invocation_profile, "cpk.semantic-invocations.v1")
                self.assertTrue(ports.managed_health.adapter.reader.require_invocations)
                ingress = ports.ingress_interpreters[IngressAuthorityProviderKind.CLOUDFLARE]
                self.assertIs(type(ingress), IngressProviderRegistration)
                self.assertEqual(ingress.invocation_profile, "cpk.ingress-invocations.v1")
                for port in (None, object()):
                    with self.assertRaises(InvocationPortError):
                        runtime.adapter.execute(object(), invocations=port)
                    with self.assertRaises(InvocationPortError):
                        runtime.adapter.execute_with_authority(object(), authority=object(), invocations=port)
                    with self.assertRaises(InvocationPortError):
                        observer.adapter.observe(object(), object(), invocations=port)
                provider.authorized_resolver.assert_not_called()
                self.assertEqual(provider.authorized_resolver.mock_calls, [])
                self.assertEqual(provider.secret_custodian.mock_calls, [])
                constructor.assert_not_called()
                ambient.assert_not_called()
                selector.unit_of_work_factory.assert_not_called()

    def test_static_production_does_not_acquire_dynamic_profile_claims(self):
        from control_plane_kit_servers_cpk_server import server
        config, _ = self.configuration()
        config = replace(config, workspace_authority=None, managed_health=None)
        provider = server._SecretProviderComposition(authorized_resolver=Mock(), secret_custodian=Mock())
        with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
            ports = server._operations_effect_ports(config, provider)
            self.assertIs(type(ports.runtime_interpreters[RuntimeKind.DOCKER]), DockerRuntimeInterpreter)
            self.assertFalse(ports.runtime_interpreters[RuntimeKind.DOCKER].require_invocations)
            self.assertIs(type(ports.runtime_observer), DockerRuntimeEffectObserver)
            self.assertFalse(ports.runtime_observer.require_invocations)
            self.assertNotIsInstance(ports.ingress_interpreters[IngressAuthorityProviderKind.CLOUDFLARE],
                IngressProviderRegistration)
            self.assertIsNone(ports.managed_health)
            constructor.assert_not_called()
            ambient.assert_not_called()

    def test_actual_ingress_wrapper_preserves_control_port_before_secret_or_provider_work(self):
        from control_plane_kit_servers_cpk_server import server
        from control_plane_kit_core.public_ingress import (
            IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget,
        )
        from control_plane_kit_core.secrets import (
            SecretCustodyGrant, SecretProviderEndpointReference, SecretReference,
            SecretResolutionGrant, SecretUseIntent,
        )
        from control_plane_kit_operations.ingress_authorities import CloudflareZoneIngressAuthority
        config, _ = self.configuration()
        provider = server._SecretProviderComposition(authorized_resolver=Mock(), secret_custodian=Mock())
        # Bounded translation values at the public adapter seam; no owner record
        # or admitted execution is fabricated by this unit test.
        api_reference = SecretReference("secret://fixture/cloudflare/api")
        prefix = SecretReference("secret://fixture/generated")
        authority = CloudflareZoneIngressAuthority("account-a", "zone-a", "example.invalid",
            api_reference, "gateway.example.invalid", "provider-a", prefix)
        ingress = NamedPublicIngress("ingress-a", IngressAuthorityReference("zone-a"),
            PublicIngressTarget("gateway", "control"), "connector", "gateway.example.invalid")
        resources = SimpleNamespace(tunnel_id="tunnel-a", dns_record_id="dns-a",
            tunnel_name="allocation-a", hostname=ingress.hostname)
        common = dict(workspace_id="workspace-a", provider_registration_id="provider-a",
            endpoint_reference=SecretProviderEndpointReference("fixture"),
            credential_reference=SecretReference("secret://bootstrap/provider"), actor_subject="operator-a",
            correlation_id="correlation-a", run_id="run-a", activity_id="activity-a", effect_id="effect-a")
        resolution = SecretResolutionGrant(authorization_id="suse_" + "a" * 64,
            reference_registration_id="reference-a", reference=api_reference,
            intent=SecretUseIntent.CLOUDFLARE_API_TOKEN, intent_fingerprint="b" * 64, **common)
        custody = SecretCustodyGrant(custody_id="scust_" + "c" * 64,
            reference=SecretReference(prefix.reference_id + "/token"),
            intent=SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, custody_fingerprint="d" * 64, **common)

        class ControlStop(RuntimeError):
            pass

        denied = ControlStop("synthetic denial")
        port = SimpleNamespace(control_error=ControlStop, admit=Mock(side_effect=denied),
            record_outcome=Mock(), record_result=Mock())
        adapter = server._cloudflare_ingress_interpreter(config, provider)
        # Registration belongs to _operations_effect_ports; this helper returns
        # the actual nominal translation wrapper for direct adapter evidence.
        for operation in ("create", "teardown"):
            def call(invocations):
                arguments = dict(authority=authority, secret_resolution_grant=resolution,
                    secret_custody_grant=custody, invocations=invocations)
                if operation == "create":
                    return adapter.create(ingress, allocation_name="allocation-a",
                        origin_service_url="http://gateway:8000", **arguments)
                return adapter.teardown(resources=resources, **arguments)
            with self.subTest(operation=operation), \
                    patch("control_plane_kit_interpreters.cloudflare.client.HttpxCloudflareTransport.request") as request:
                for unavailable in (None, object()):
                    with self.assertRaises(InvocationPortError):
                        call(unavailable)
                with self.assertRaises(ControlStop) as caught:
                    call(port)
                self.assertIs(caught.exception, denied)
                port.admit.assert_called_once_with("secret-resolution",
                    authorization_id=resolution.authorization_id)
                port.admit.reset_mock()
                port.record_outcome.assert_not_called()
                port.record_result.assert_not_called()
                request.assert_not_called()
                self.assertEqual(provider.authorized_resolver.mock_calls, [])
                self.assertEqual(provider.secret_custodian.mock_calls, [])
