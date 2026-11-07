"""Actual bridge/connector qualification on an explicitly selected source cohort.

Pure source selection only: no admitted request, permission row or provider call.
The existing owning runner selects the immutable newer cohort for these tests.
"""
from dataclasses import replace
from datetime import datetime, timezone
import importlib
from pathlib import Path
import unittest
from unittest.mock import Mock

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.topology import validate_graph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_core.verification import HttpCheck, VerificationContract, VerificationPolicy
from control_plane_kit_core.http_verification_samples import http_verification_check_digest
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleReceiverConfiguration, HttpVerificationSampleReceiverConfigurationCodec,
    HttpVerificationSampleVerifierConfiguration, HttpVerificationSampleCheckBinding,
    HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT,
)
from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from control_plane_kit_operations.products import RegisteredProduct, InlineDescriptorSource
from control_plane_kit_interpreters.docker import DockerRuntimeInterpreter, DockerSdkClient
from control_plane_kit_interpreters.docker.connector_connection import (
    DockerConnectorConnectionQualifier, ConnectorConnectionQualification,
)
from control_plane_kit_interpreters.docker.sdk import ConnectorConnectionProfile
from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleTrust
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    gateway_http_sample_trust_artifact, gateway_http_sample_source_runtime_contract,
)
from control_plane_kit_servers_cpk_server.http_sample_composition import (
    gateway_http_sample_binding, compose_http_sample_runtime,
)
from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBridge
from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
from control_plane_kit_servers_cpk_server.managed_health_placement import (
    DockerRuntimeClientBinding, DockerRuntimeClientSelector,
)
from managed_native_material import NativeMaterial


class LinkedHttpSampleQualificationTests(unittest.TestCase):
    def setUp(self):
        self.value = value = NativeMaterial(registered_participants=True)
        authored = value.authored
        configured = authored.configurations["api"]
        checks = tuple(HttpCheck(check_id=name, provider_socket="http", path="/health/" + name,
            policy=VerificationPolicy(timeout_seconds=1, interval_seconds=1, maximum_attempts=1))
            for name in ("ready", "live"))
        samples = HttpVerificationSampleReceiverConfiguration(configured.target,
            configured.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
                "cpk-server", (authored.public["workload"],)), tuple(
                    HttpVerificationSampleCheckBinding(check.check_id, http_verification_check_digest(check))
                    for check in checks))
        sample_artifact = ConfigurationArtifact("sample-checks", "/etc/cpk/api/samples.json", ConfigurationMediaType.JSON,
            HttpVerificationSampleReceiverConfigurationCodec().encode_canonical_bytes(samples).decode())
        contract = authored.documents["api"].product.runtime_contract
        contract = replace(contract, verification=VerificationContract(checks),
            configuration_artifacts=contract.configuration_artifacts + (sample_artifact,),
            public_environment=contract.public_environment + (PublicStaticEnvironmentBinding(
                HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT, sample_artifact.target_path),))
        api = authored.node("api", contract)
        api = replace(api, block_spec=replace(api.block_spec, verification=contract.verification),
            configuration_artifacts=value.desired.node("api").configuration_artifacts + (sample_artifact,))
        artifacts = {item.artifact_id: item for item in value.desired.node("gateway").configuration_artifacts}
        trust = gateway_http_sample_trust_artifact(GatewayHttpSampleTrust(
            authored.configurations["gateway"].target, "cpk-server", (authored.public["transit"],)))
        gateway = authored.node("gateway", gateway_http_sample_source_runtime_contract(
            artifacts["gateway-health-transit"], artifacts["gateway-health-targets"], artifacts["gateway-control"], trust))
        self.desired = replace(value.desired, nodes={**value.desired.nodes, "api": api, "gateway": gateway})
        self.pair = validate_graph(value.current), validate_graph(self.desired)
        for graph in self.pair:
            graph.require_valid()
        self.plan = core.compile_http_sample_bootstrap_activity_plan(*self.pair)
        self.assertTrue(self.plan.ready_for_execution)
        self.products = tuple(RegisteredProduct("product-" + name, "workspace-a",
            ProductReference.from_document(document), document, InlineDescriptorSource(),
            "operator", "2026-11-07T00:00:00Z") for name, document in authored.documents.items())
        self.support = HttpSampleExecutionSupport(gateway_http_sample_binding(authored.documents["gateway"]), "control")
        self.client = Mock()
        sdk = DockerSdkClient(client=self.client, connect_on_init=False)
        adapter = compose_http_sample_runtime(DockerRuntimeInterpreter(sdk, require_invocations=True),
            support=self.support, resolver=Mock(), public_resolver=Mock(), clock=lambda: 150)
        self.registration = RuntimeAdapterRegistration(adapter, invocation_profile="cpk.semantic-invocations.v1",
            ordinary_verification_invocations=True, http_sample_support=self.support)
        selector = DockerRuntimeClientSelector((DockerRuntimeClientBinding(
            "workspace-a", "docker", value.authority.authority_ref, sdk),))
        self.native = DockerManagedNativeConnection(selector, value.document,
            lambda: datetime.now(timezone.utc), http_sample_registration=self.registration)
        from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
        self.bridge = ManagedHealthBridge(object(), selector, None,
            health_receiver_decoders(gateway_documents=(authored.documents["gateway"],)), self.native,
            http_sample_registration=self.registration)

    def select(self, bridge=None, plan=None):
        return (bridge or self.bridge).select(plan=plan or self.plan, current=self.value.current, desired=self.desired,
            registered_products=self.products, runtime_authorities=(self.value.authority,))

    def test_source_import_provenance_is_the_explicit_immutable_cohort(self):
        for module, root in (("control_plane_kit_core", "/reviewed-http-sample/core/src"),
                             ("control_plane_kit_operations", "/reviewed-http-sample/operations/src"),
                             ("control_plane_kit_interpreters", "/reviewed-http-sample/interpreters/src")):
            self.assertTrue(Path(importlib.import_module(module).__file__).resolve().is_relative_to(root))

    def test_real_bridge_and_real_connector_qualifier_accept_same_exact_fresh_sample_plan(self):
        selected = self.select()
        self.assertIsNotNone(selected)
        connector = tuple(item for item in self.plan.activities if type(item.operation) is core.ObserveManagementBootstrap
            and item.operation.stage is core.ManagementBootstrapStage.CONNECTOR_CONNECTED)
        self.assertEqual(len(connector), 1)
        self.assertIn(connector[0].activity_id, selected)
        qualifier = DockerConnectorConnectionQualifier(self.value.reference,
            self.value.document.product.image.execution_reference, profile=ConnectorConnectionProfile.MANAGED_WRAPPER_V1,
            http_sample_executor=self.registration.adapter.http_sample_executor)
        self.assertIs(qualifier.qualify_shape(activity_id=connector[0].activity_id, plan=self.plan,
            current=self.pair[0], desired=self.pair[1], product_document=self.value.document,
            authority_ref=self.value.authority.authority_ref), ConnectorConnectionQualification.FRESH)
        self.assertEqual(self.client.mock_calls, [])

    def test_unselected_or_legacy_interpretation_retains_refusal(self):
        native = replace(self.native, http_sample_registration=None)
        self.assertIsNone(self.select(replace(self.bridge, native=native, http_sample_registration=None)))
        legacy = core.compile_graph_activity_plan(*self.pair)
        self.assertNotEqual(legacy, self.plan)
        self.assertIsNone(self.select(plan=legacy))
        self.assertEqual(self.client.mock_calls, [])

    def test_changed_actual_support_refuses_before_any_provider_io(self):
        self.registration.adapter.http_sample_support = object()
        self.assertIsNone(self.select())
        self.assertEqual(self.client.mock_calls, [])
