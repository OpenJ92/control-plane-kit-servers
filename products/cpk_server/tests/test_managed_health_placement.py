"""Servers selects explicit resources; Interpreter owns the provider projection."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkNetworkAttachment, DockerSdkResourceInspection
from control_plane_kit_operations.runtime_authorities import (
    LocalDockerSocketAuthority, RegisteredRuntimeAuthority, RegisteredRuntimeAuthorityStatus,
)


class ManagedHealthPlacementTests(unittest.TestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerControllerPlacement, DockerGatewayBinding, DockerGatewayEndpointReader, DockerRuntimeClientBinding,
        )
        self.authority = RegisteredRuntimeAuthority("registration", "workspace-a",
            RuntimeAuthorityReference("local-docker"), RuntimeKind.DOCKER,
            LocalDockerSocketAuthority(), "operator", "2026-10-13T00:00:00Z")
        self.client = Mock()
        self.sdk = DockerSdkClient(client=Mock(), connect_on_init=False)
        self.sdk.inspect_network = self.client.inspect_network
        self.sdk.inspect_container = self.client.inspect_container
        self.sdk.close = self.client.close
        self.provider = DockerRuntimeClientBinding("workspace-a", "docker", self.authority.authority_ref, self.sdk)
        self.placement = DockerControllerPlacement(self.provider, "c" * 64)
        self.binding = DockerGatewayBinding("workspace-a", "docker", self.authority.authority_ref,
            "gateway", "a" * 64, "b" * 64)
        self.bindings = Mock(return_value=self.binding)
        self.reader = DockerGatewayEndpointReader((self.placement,), self.bindings)
        self.network = DockerSdkResourceInspection("opaque-network", False, None, {}, network_id="a" * 64)
        self.gateway = DockerSdkResourceInspection("opaque-gateway", True, None, {},
            container_id="b" * 64, network_attachments=(DockerSdkNetworkAttachment("a" * 64, "172.20.0.7"),))
        self.controller = DockerSdkResourceInspection("opaque-controller", True, None, {},
            container_id="c" * 64, network_attachments=(DockerSdkNetworkAttachment("a" * 64, "172.20.0.8"),))
        self.client.inspect_network.return_value = self.network
        self.client.inspect_container.side_effect = lambda identity: {
            "b" * 64: self.gateway, "c" * 64: self.controller}[identity]

    def read(self):
        return self.reader.read(provider_binding=self.provider,
            workspace_id="workspace-a", runtime_id="docker", authority=self.authority,
            gateway_node_id="gateway", socket_name="readiness", port=8123, graph_id="graph-original")

    def test_selection_is_pure_and_rejects_wrong_workspace_or_authority(self):
        self.assertIs(self.reader.select(provider_binding=self.provider, workspace_id="workspace-a", runtime_id="docker",
            authority=self.authority), self.placement)
        for authority in (replace(self.authority, workspace_id="workspace-b"),
                replace(self.authority, authority_ref=RuntimeAuthorityReference("different")),
                replace(self.authority, status=RegisteredRuntimeAuthorityStatus.REVOKED)):
            self.assertIsNone(self.reader.select(provider_binding=self.provider,
                workspace_id="workspace-a", runtime_id="docker", authority=authority))
        self.client.assert_not_called()
        self.assertEqual(self.client.mock_calls, [])
        self.bindings.assert_not_called()

    def test_exact_identity_membership_supplies_only_numeric_selected_origin(self):
        selected = self.read()
        self.assertEqual(selected.endpoint.address.value, "http://172.20.0.7:8123")
        self.assertEqual((selected.endpoint.subject_id, selected.endpoint.socket_name, selected.endpoint.graph_id),
            ("gateway", "readiness", "graph-original"))
        self.assertEqual(selected.policy.runtime_private_authorities, frozenset({"http://172.20.0.7:8123"}))
        from control_plane_kit_interpreters.probes.security import authorize_probe_endpoint
        target = authorize_probe_endpoint(selected.endpoint, selected.policy)
        self.assertEqual(target.request_url("/__control/health/readiness"),
            "http://172.20.0.7:8123/__control/health/readiness")
        self.client.inspect_network.assert_called_once_with("a" * 64)
        self.assertEqual([call.args for call in self.client.inspect_container.call_args_list],
            [("c" * 64,), ("b" * 64,)])
        self.client.close.assert_not_called()  # Provisioner owns the explicitly injected client.

    def test_missing_empty_addressless_or_replaced_membership_refuses(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import GatewayPlacementUnavailable
        original = self.gateway
        variants = (replace(original, network_attachments=None), replace(original, network_attachments=()),
            replace(original, network_attachments=(DockerSdkNetworkAttachment("a" * 64, None),)),
            replace(original, network_attachments=(DockerSdkNetworkAttachment("d" * 64, "172.20.0.7"),)),
            replace(original, container_id="e" * 64), replace(original, running=False))
        for observed in variants:
            with self.subTest(observed=variants.index(observed)):
                self.gateway = observed
                with self.assertRaisesRegex(GatewayPlacementUnavailable, "gateway placement is unavailable"):
                    self.read()
        self.gateway = original
        self.client.inspect_network.return_value = replace(self.network, network_id="f" * 64)
        with self.assertRaises(GatewayPlacementUnavailable):
            self.read()
        self.client.close.assert_not_called()

    def test_binding_cannot_redirect_to_another_gateway_or_scope(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import GatewayPlacementUnavailable
        for binding in (None, replace(self.binding, workspace_id="workspace-b"),
                replace(self.binding, gateway_node_id="other"), replace(self.binding, runtime_id="other"),
                replace(self.binding, authority_ref=RuntimeAuthorityReference("other"))):
            with self.subTest(binding_missing=binding is None):
                self.bindings.return_value = binding
                with self.assertRaises(GatewayPlacementUnavailable):
                    self.read()
        self.assertEqual(self.client.mock_calls, [])

    def test_provider_payload_is_not_exposed_and_caller_client_is_not_closed(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import GatewayPlacementUnavailable
        self.client.inspect_network.side_effect = RuntimeError("sensitive-provider-response")
        with self.assertRaises(GatewayPlacementUnavailable) as failure:
            self.read()
        self.assertNotIn("sensitive-provider-response", str(failure.exception))
        self.assertIsNone(failure.exception.__cause__)
        self.assertIsNone(failure.exception.__context__)
        self.client.close.assert_not_called()
