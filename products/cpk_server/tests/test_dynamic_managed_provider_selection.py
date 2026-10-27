"""Dynamic selector composition; Operations owns assignment decisions and history."""
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_interpreters.docker.sdk import DockerSdkClient, DockerUnixSocketClientConfig
from control_plane_kit_operations.managed_runtime_assignments import (
    ManagedRuntimeCapability, ManagedRuntimeCapabilityPolicy,
)
from control_plane_kit_operations.runtime_authorities import RegisteredRuntimeAuthorityStatus
from managed_native_material import NativeMaterial


class DynamicManagedProviderSelectionTests(unittest.TestCase):
    def configuration(self):
        from control_plane_kit_servers_cpk_server import managed_health_placement as placement
        binding_type = getattr(placement, "DockerRuntimeCapabilityBinding", None)
        self.assertTrue(callable(binding_type), "installed management capability binding is missing")
        capability = ManagedRuntimeCapability("installed-capability-a")
        config = DockerUnixSocketClientConfig("/var/run/synthetic-installed-capability.sock", 5.0)
        binding = binding_type(capability, config)
        policy = ManagedRuntimeCapabilityPolicy("installation-a", (capability,))
        return placement, binding, policy

    def test_current_lookup_failure_refuses_without_client_construction_or_static_fallback(self):
        placement, binding, policy = self.configuration()
        world = NativeMaterial()
        unavailable = Mock(side_effect=RuntimeError("synthetic private permission-store detail"))
        with patch.object(DockerSdkClient, "from_authority") as sdk, \
                patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
            selector = placement.DockerRuntimeClientSelector((), capability_policy=policy,
                capability_bindings=(binding,), unit_of_work_factory=unavailable)
            unavailable.assert_not_called()
            self.assertIsNone(selector.select(workspace_id="workspace-a", runtime_id="docker",
                authority=world.authority))
            unavailable.assert_called_once_with()
            for workspace, authority in (("other-workspace", world.authority),
                    ("workspace-a", replace(world.authority, status=RegisteredRuntimeAuthorityStatus.REVOKED))):
                self.assertIsNone(selector.select(workspace_id=workspace, runtime_id="docker", authority=authority))
            unavailable.assert_called_once_with()
            sdk.assert_not_called()
            constructor.assert_not_called()
            ambient.assert_not_called()
        self.assertNotIn(binding.local_client_config.socket_path, repr(selector))
        self.assertNotIn("synthetic private", repr(selector))

    def test_dynamic_catalog_is_exact_and_cannot_mix_static_scope_bindings(self):
        placement, binding, policy = self.configuration()
        world = NativeMaterial()
        static = placement.DockerRuntimePolicyBinding("workspace-a", "docker",
            world.authority.authority_ref, binding.local_client_config)
        other = replace(binding, capability=ManagedRuntimeCapability("unconfigured-capability"))
        uow = Mock()
        # An explicitly configured empty dynamic catalog is not static mode.
        placement.DockerRuntimeClientSelector((),
            capability_policy=ManagedRuntimeCapabilityPolicy("installation-a", ()),
            capability_bindings=(), unit_of_work_factory=uow)
        base = dict(capability_policy=policy, capability_bindings=(binding,), unit_of_work_factory=uow)
        for bindings, changes in (((static,), {}), ((), {"capability_bindings": ()}),
                ((), {"capability_bindings": (binding, binding)}), ((), {"capability_bindings": (other,)}),
                ((), {"unit_of_work_factory": None}), ((), {"capability_policy": None})):
            with self.subTest(changes=tuple(changes), static=bool(bindings)), self.assertRaises(ValueError) as caught:
                placement.DockerRuntimeClientSelector(bindings, **{**base, **changes})
            self.assertNotIn(binding.local_client_config.socket_path, str(caught.exception))
        uow.assert_not_called()
