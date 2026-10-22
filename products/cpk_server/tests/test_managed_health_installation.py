"""Explicit installation artifact laws; delivery effects stay with their owners."""
import copy
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationFileMode,
    ConfigurationMediaType, MAX_CONFIGURATION_BYTES,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.lifecycle import ResourceLifecycle
from control_plane_kit_core.products import ProductDescriptorCodec, ProductDescriptorError, RetainedDataMount
from control_plane_kit_core.secrets import (
    SecretEnvironmentDelivery, SecretFileDelivery, SecretFilePathBinding, SecretReference, SecretUseIntent,
)
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from managed_native_material import NativeMaterial
import test_docker_installation as installation_fixture
import test_managed_health_configuration as process_fixture
from test_root_bootstrap import installation_input, DRIVER
from test_secret_provider_bootstrap import _provider_environment


ARTIFACT_ID = "cpk-managed-health"
CONFIGURATION_PATH = "/etc/cpk/cpk-server/managed-health.json"
ERROR = "managed health installation configuration is invalid"
PACKAGE = "control_plane_kit_servers_cpk_server"


class ManagedHealthInstallationTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module(PACKAGE + ".managed_health_configuration")
        self.assertTrue(callable(getattr(self.api, "managed_health_configuration_artifact", None)),
            "managed health installation artifact interface is missing")
        self.installation = importlib.import_module(PACKAGE + ".installation")
        self.bootstrap = importlib.import_module(PACKAGE + ".bootstrap")
        self.world = NativeMaterial()
        self.codec = ProductDescriptorCodec()

    def raw(self, *, socket_path="/var/run/docker.sock"):
        return json.dumps({"schema": "cpk-server.managed-health.v1",
            "docker": {"socket_path": socket_path, "request_timeout": 5.0},
            "scopes": [{"workspace_id": "workspace-a", "runtime_id": "docker",
                "authority_ref": self.world.authority.authority_ref.reference_id}],
            "gateway_documents": [self.world.authored.documents["gateway"].content.decode()],
            "native_product_document": self.world.document.content.decode()}).encode()

    def artifact(self, raw=None):
        return self.api.managed_health_configuration_artifact(self.raw() if raw is None else raw)

    def value(self):
        # Reuse only the existing pure input constructor, not its assertions.
        return installation_fixture.DockerInstallationTests().installation(self.installation)

    def compose(self, value):
        return compile_topology(self.installation.compose_docker_cpk_installation(value))

    def root_input(self, artifact=None):
        value = installation_input()
        value["installation"]["managed_health_configuration"] = (
            self.artifact() if artifact is None else artifact).descriptor()
        return value

    def plan(self, value):
        return self.bootstrap.plan_root_bootstrap(value, driver_image_id=DRIVER)

    def selected(self, value, **changes):
        product = value.cpk_product.product
        return self.codec.encode_document(replace(product,
            runtime_contract=replace(product.runtime_contract, **changes)))

    def assert_delivery_refused(self, callback):
        with self.assertRaises(ValueError) as raised:
            callback()
        self.assertEqual(str(raised.exception), ERROR)
        self.assertIsNone(raised.exception.__context__)

    def test_constructor_preserves_outer_bytes_and_fixed_public_profile_without_effects(self):
        raw = b" \n" + self.raw() + b"\t\n"
        with patch("docker.DockerClient") as docker, patch("builtins.open") as files, \
                patch("os.open") as descriptors, patch("socket.getaddrinfo") as network:
            artifact = self.artifact(raw)
        for effect in (docker, files, descriptors, network):
            effect.assert_not_called()
        self.assertEqual(self.api.MANAGED_HEALTH_ARTIFACT_ID, ARTIFACT_ID)
        self.assertEqual(self.api.MANAGED_HEALTH_CONFIGURATION_PATH, CONFIGURATION_PATH)
        self.assertIs(type(artifact), ConfigurationArtifact)
        self.assertEqual((artifact.artifact_id, artifact.target_path, artifact.media_type, artifact.file_mode),
            (ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY))
        self.assertEqual(artifact.content.encode(), raw)
        self.assertEqual(artifact.content_digest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(artifact.source_digest, artifact.content_digest)
        self.assertEqual(self.api.decode_managed_health_process_configuration(raw).native_product_document,
            self.world.document)
        self.assertNotIn(artifact.content, repr(artifact))

    def test_constructor_rejects_invalid_schema_and_respects_artifact_not_reader_bound(self):
        for raw in (b"", b"private invalid input", "not bytes", b"{}"):
            self.assert_delivery_refused(lambda: self.artifact(raw))
        raw = self.raw()
        bounded = raw + b" " * (MAX_CONFIGURATION_BYTES - len(raw))
        self.assertEqual(len(self.artifact(bounded).content.encode()), MAX_CONFIGURATION_BYTES)
        # The existing standalone parser admits more than topology delivery.
        self.api.decode_managed_health_process_configuration(bounded + b" ")
        self.assert_delivery_refused(lambda: self.artifact(bounded + b" "))

    def test_typed_artifact_is_revalidated_and_wrong_delivery_slot_is_refused(self):
        value, artifact = self.value(), self.artifact()
        cases = [replace(artifact, artifact_id="other"), replace(artifact, target_path="/etc/cpk/other.json"),
            replace(artifact, media_type=ConfigurationMediaType.TEXT),
            replace(artifact, file_mode=ConfigurationFileMode.OWNER_READ_ONLY),
            replace(artifact, content="{}", source_digest=None)]
        for field, content in (("content_digest", "0" * 64), ("source_digest", "private invalid provenance")):
            malformed = copy.copy(artifact)
            # Simulate an untrusted typed value without failing its constructor
            # before the installation validator under test can inspect it.
            object.__setattr__(malformed, field, content)
            cases.append(malformed)
        for candidate in (*cases, {}, "not an artifact"):
            with self.subTest(kind=type(candidate).__name__):
                self.assert_delivery_refused(lambda: self.compose(replace(value,
                    managed_health_configuration=candidate)))

    def test_distinct_source_digest_is_preserved_as_metadata_through_root_projection(self):
        artifact = replace(self.artifact(), source_digest="a" * 64)
        self.assertNotEqual(artifact.source_digest, artifact.content_digest)
        document = self.root_input(artifact)
        plan = self.plan(document)
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        entry = next(item for item in cpk["configuration_files"] if item["artifact"]["artifact_id"] == ARTIFACT_ID)
        self.assertEqual(entry["artifact"], artifact.descriptor())
        self.assertEqual(entry["sha256"], artifact.content_digest)
        graph = GraphDescriptorCodec().decode(plan["graph"])
        delivered = next(item for item in graph.node(plan["cpk_node_id"]).configuration_artifacts
            if item.artifact_id == ARTIFACT_ID)
        self.assertEqual(delivered.source_digest, artifact.source_digest)
        self.assertEqual(delivered.content, artifact.content)

    def test_disabled_default_keeps_existing_graph_and_root_plan(self):
        value = self.value()
        self.assertIsNone(value.managed_health_configuration)
        self.assertEqual(self.compose(value), self.compose(replace(value, managed_health_configuration=None)))
        plan = self.plan(installation_input())
        self.assertEqual(plan, self.plan(copy.deepcopy(installation_input())))
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        self.assertNotIn("CPK_MANAGED_HEALTH", cpk["environment"])
        self.assertNotIn("CPK_MANAGED_HEALTH_CONFIGURATION_FILE", cpk["environment"])
        self.assertFalse(any(item["artifact"]["artifact_id"] == ARTIFACT_ID for item in cpk["configuration_files"]))

    def test_disabled_root_planning_in_clean_process_does_not_import_docker_or_new_mode(self):
        # This subprocess is a single import-isolation assertion inside the
        # unchanged owning Docker suite, never an alternate runner/host check.
        script = """
import json, sys
from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
plan_root_bootstrap(json.loads(sys.stdin.read()), driver_image_id="sha256:" + "a" * 64)
assert "control_plane_kit_interpreters.docker" not in sys.modules
assert "control_plane_kit_servers_cpk_server.managed_health_configuration" not in sys.modules
"""
        result = subprocess.run([sys.executable, "-c", script], input=json.dumps(installation_input()),
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_enabled_composition_changes_only_cpk_contract_and_preserves_existing_inputs(self):
        value = self.value()
        unrelated = ConfigurationArtifact("unrelated", "/etc/cpk/unrelated.json", ConfigurationMediaType.JSON, "{}")
        original = value.cpk_product.product.runtime_contract
        value = replace(value, cpk_product=self.selected(value,
            configuration_artifacts=(*original.configuration_artifacts, unrelated)))
        before = self.compose(value)
        artifact = self.artifact()
        enabled = replace(value, managed_health_configuration=artifact)
        after = self.compose(enabled)
        before_cpk, after_cpk = before.node(value.cpk_node_id), after.node(value.cpk_node_id)
        self.assertEqual(set(after.nodes), set(before.nodes))
        for node_id in before.nodes:
            if node_id != value.cpk_node_id:
                self.assertEqual(after.node(node_id), before.node(node_id))
        self.assertEqual(after_cpk.secret_deliveries, before_cpk.secret_deliveries)
        self.assertEqual(after_cpk.runtime_authority_deliveries, (value.runtime_access,))
        self.assertEqual(after_cpk.configuration_artifacts,
            tuple(sorted((*before_cpk.configuration_artifacts, artifact))))
        environment = after_cpk.non_secret_environment()
        self.assertEqual(environment["CPK_MANAGED_HEALTH"], "docker-unix-v1")
        self.assertEqual(environment["CPK_MANAGED_HEALTH_CONFIGURATION_FILE"], CONFIGURATION_PATH)
        self.assertEqual({key: item for key, item in environment.items() if key not in
            ("CPK_MANAGED_HEALTH", "CPK_MANAGED_HEALTH_CONFIGURATION_FILE")}, before_cpk.non_secret_environment())
        self.assertNotEqual(after_cpk.metadata["product_identity"], before_cpk.metadata["product_identity"])
        topology = self.installation.compose_docker_cpk_installation(enabled)
        cpk = next(child for child in topology.root.children if getattr(child, "block_id", None) == value.cpk_node_id)
        self.assertEqual(cpk.implementation.document.product.image, value.cpk_product.product.image)
        self.assertEqual(self.compose(enabled), after)

    def test_explicit_managed_scope_is_not_inferred_and_socket_matches_actual_delivery(self):
        value, artifact = self.value(), self.artifact()
        self.assertNotEqual(value.workspace_id, "workspace-a")
        self.compose(replace(value, managed_health_configuration=artifact))
        observed = self.api.decode_managed_health_process_configuration(artifact.content.encode())
        binding, = observed.provider_clients.bindings
        self.assertEqual((binding.workspace_id, binding.runtime_id), ("workspace-a", "docker"))
        self.assertNotEqual(binding.authority_ref, value.runtime_authority)
        other = self.artifact(self.raw(socket_path="/var/run/other.sock"))
        self.assert_delivery_refused(lambda: self.compose(replace(value, managed_health_configuration=other)))

    def test_reserved_public_environment_is_refused_even_when_identical(self):
        value, artifact = self.value(), self.artifact()
        for name, content in (("CPK_MANAGED_HEALTH", "docker-unix-v1"),
                ("CPK_MANAGED_HEALTH", "disabled"),
                ("CPK_MANAGED_HEALTH_CONFIGURATION_FILE", CONFIGURATION_PATH),
                ("CPK_MANAGED_HEALTH_CONFIGURATION_FILE", "/etc/cpk/other.json")):
            contract = value.cpk_product.product.runtime_contract
            selected = self.selected(value, public_environment=(*contract.public_environment,
                PublicStaticEnvironmentBinding(name, content)))
            self.assert_delivery_refused(lambda: self.compose(replace(value, cpk_product=selected,
                managed_health_configuration=artifact)))

    def test_reserved_artifact_or_requirement_id_or_path_is_refused_even_when_identical(self):
        value, artifact = self.value(), self.artifact()
        contract = value.cpk_product.product.runtime_contract
        for candidate in (artifact, replace(artifact, target_path="/etc/cpk/different.json"),
                replace(artifact, artifact_id="different")):
            for requirement in (False, True):
                changes = {"configuration_artifacts": (*contract.configuration_artifacts, candidate)}
                if requirement:
                    slot = ConfigurationArtifactRequirement(candidate.artifact_id, candidate.target_path,
                        candidate.media_type, candidate.file_mode)
                    changes = {"configuration_requirements": (*contract.configuration_requirements, slot)}
                selected = self.selected(value, **changes)
                self.assert_delivery_refused(lambda: self.compose(replace(value, cpk_product=selected,
                    managed_health_configuration=artifact)))

    def test_existing_base_contract_rejects_extra_secret_deliveries_and_retained_mounts(self):
        value, artifact = self.value(), self.artifact()
        contract = value.cpk_product.product.runtime_contract
        reference = SecretReference("secret://fixture/unexpected")
        extra = (SecretEnvironmentDelivery("CPK_MANAGED_HEALTH", reference, SecretUseIntent.APPLICATION_CONTROL_TOKEN),
            SecretFileDelivery("/run/secrets/unexpected", reference, SecretUseIntent.APPLICATION_CONTROL_TOKEN,
                path_binding=SecretFilePathBinding("CPK_MANAGED_HEALTH_CONFIGURATION_FILE")))
        cases = [(self.selected(value, secret_deliveries=(*contract.secret_deliveries, delivery)),
            "installation requires the base product secret delivery contract") for delivery in extra]
        selected = self.selected(value, retained_data_mounts=(RetainedDataMount("extra", "/var/lib/extra"),),
            lifecycle=ResourceLifecycle.owned_with_retained_data("extra"))
        cases.append((selected, "installation product retained mounts do not match its process contract"))
        for selected, error in cases:
            for option in (None, artifact):
                with self.assertRaisesRegex(ValueError, "^" + error + "$" ):
                    self.compose(replace(value, cpk_product=selected, managed_health_configuration=option))

    def test_closed_root_field_rejects_null_malformed_descriptor_and_digest_drift(self):
        descriptor = self.artifact().descriptor()
        cases = [None, {}, "private invalid input", {**descriptor, "unexpected": "private"},
            {key: item for key, item in descriptor.items() if key != "source_digest"},
            {**descriptor, "content_digest": "0" * 64}, {**descriptor, "source_digest": "private invalid digest"}]
        for candidate in cases:
            document = installation_input()
            document["installation"]["managed_health_configuration"] = candidate
            with patch("docker.DockerClient") as docker, patch("os.open") as files:
                with self.assertRaises(self.bootstrap.RootBootstrapError) as raised:
                    self.plan(document)
            docker.assert_not_called()
            files.assert_not_called()
            self.assertNotIn("private", str(raised.exception))

    def test_projection_preserves_original_bytes_and_complete_plan_roundtrip(self):
        raw = b" \n" + self.raw() + b"\t"
        artifact = self.artifact(raw)
        document = self.root_input(artifact)
        self.assertEqual(self.bootstrap.decode_document(self.bootstrap.canonical(document)), document)
        plan = self.plan(document)
        self.assertEqual(self.bootstrap.decode_document(self.bootstrap.canonical(plan)), plan)
        self.assertEqual(self.plan(copy.deepcopy(document)), plan)
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        entry = next(item for item in cpk["configuration_files"] if item["artifact"]["artifact_id"] == ARTIFACT_ID)
        self.assertEqual(entry["target"], CONFIGURATION_PATH)
        self.assertEqual(entry["artifact"], artifact.descriptor())
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(cpk["local_docker_access"]["socket"], "/var/run/docker.sock")
        successor = self.plan(self.root_input(self.artifact(raw + b" ")))
        self.assertNotEqual(plan["digest"], successor["digest"])
        original_graph, next_graph = (GraphDescriptorCodec().decode(value["graph"]) for value in (plan, successor))
        self.assertNotEqual(original_graph.node(plan["cpk_node_id"]).metadata["product_identity"],
            next_graph.node(successor["cpk_node_id"]).metadata["product_identity"])
        self.assertEqual(self.api.decode_managed_health_process_configuration(raw).native_product_document,
            self.api.decode_managed_health_process_configuration(raw + b" ").native_product_document)

    def test_core_product_document_bound_remains_distinct_from_artifact_bound(self):
        raw = self.raw()
        artifact = self.artifact(raw + b" " * (MAX_CONFIGURATION_BYTES - len(raw)))
        value = replace(self.value(), managed_health_configuration=artifact)
        # The valid artifact's payload plus product envelope exceeds Core's
        # separate whole-product document bound. Do not mistake it for root size.
        with self.assertRaises(ProductDescriptorError):
            self.compose(value)

    def test_aggregate_root_plan_bound_refuses_after_individual_products_fit(self):
        raw = self.raw()
        artifact = self.artifact(raw + b" " * (100_000 - len(raw)))
        document = self.root_input(artifact)
        selected = {}
        for role in ("postgres", "secrets"):
            original = self.codec.decode_document(document["installation"]["products"][role])
            filler = ConfigurationArtifact("envelope-" + role, "/etc/cpk/envelope-" + role + ".json",
                ConfigurationMediaType.JSON, json.dumps({"padding": "x" * 180_000}))
            product = replace(original.product, runtime_contract=replace(original.product.runtime_contract,
                configuration_artifacts=(*original.product.runtime_contract.configuration_artifacts, filler)))
            selected[role] = self.codec.encode_document(product)
            self.assertLess(len(selected[role].content), 262_144)
            document["installation"]["products"][role] = json.loads(selected[role].content)
        # Actual composed products still fit their owner bound; this is not a
        # generic assertion accepting an earlier Core document-size failure.
        desired = replace(self.value(), postgres_product=selected["postgres"],
            secrets_product=selected["secrets"], managed_health_configuration=artifact)
        topology = self.installation.compose_docker_cpk_installation(desired)
        for child in topology.root.children:
            if hasattr(child, "implementation"):
                self.assertLess(len(child.implementation.document.content), 262_144)
        self.compose(desired)
        self.bootstrap.decode_document(self.bootstrap.canonical(document))
        with self.assertRaisesRegex(self.bootstrap.RootBootstrapError, "^bootstrap document exceeds its bound$"):
            self.plan(document)

    def test_actual_projected_file_is_consumed_by_normal_process_and_factory(self):
        self.assert_projected_file_consumed(self.artifact())

    def test_required_gateway_declaration_reaches_normal_enabled_factory(self):
        document = self.world.authored.documents["gateway"]
        contract = document.product.runtime_contract
        declaration = self.codec.encode_document(replace(document.product,
            runtime_contract=replace(contract, configuration_artifacts=(),
                configuration_requirements=tuple(ConfigurationArtifactRequirement(
                    value.artifact_id, value.target_path, value.media_type, value.file_mode)
                    for value in contract.configuration_artifacts))))
        raw = json.loads(self.raw())
        raw["gateway_documents"] = [declaration.content.decode()]
        self.assertEqual(declaration.product.runtime_contract.configuration_artifacts, ())
        self.assert_projected_file_consumed(self.artifact(json.dumps(raw).encode()))

    def assert_projected_file_consumed(self, artifact):
        plan = self.plan(self.root_input(artifact))
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        entry = next(item for item in cpk["configuration_files"] if item["artifact"]["artifact_id"] == ARTIFACT_ID)
        server = importlib.import_module(PACKAGE + ".server")
        with tempfile.TemporaryDirectory() as directory:
            materialized = Path(directory) / "projected.json"
            materialized.write_bytes(entry["artifact"]["content"].encode())
            environment = {**_provider_environment(Path(directory) / "unread.token"),
                **cpk["environment"], "CPK_CONTROL_AUTH_STATIC_CREDENTIAL": "fixture-control-credential"}
            opened = []
            actual_open = os.open
            def read_projected(path, flags, *args, **kwargs):
                opened.append(path)
                if path != entry["target"]:
                    raise OSError("unplanned fixture file read")
                return actual_open(materialized, flags, *args, **kwargs)
            with patch.object(os, "open", side_effect=read_projected), patch("docker.DockerClient") as docker:
                config = server.CpkServerBootstrapConfiguration.from_environment(environment)
                helper = process_fixture.ManagedHealthConfigurationTests()
                helper.server = server
                provider = server._secret_provider_composition(config)
                factory = helper.compose(config, provider=provider)
            self.assertEqual(opened, [entry["target"]])
            docker.assert_not_called()
        process = config.managed_health_process
        self.assertEqual(process.native_product_document, self.world.document)
        registration = factory.ports.runtime_interpreters[RuntimeKind.DOCKER]
        self.assertIs(type(registration), RuntimeAdapterRegistration)
        self.assertTrue(registration.exact_version_execute)
        self.assertTrue(registration.exact_version_execute_with_authority)
        self.assertFalse(registration.exact_version_observe)
        self.assertIs(registration.adapter.local_client_config, process.local_client_config)
        self.assertIs(factory.ports.secret_metadata_reader, provider.metadata_reader)
        self.assertEqual(set(factory.ports.ingress_interpreters),
            {server.IngressAuthorityProviderKind.CLOUDFLARE})
        self.assertIs(factory.ports.runtime_observer.local_client_config, process.local_client_config)
        self.assertIs(factory.ports.managed_health.provider_clients, process.provider_clients)
        self.assertIsNotNone(factory.ports.managed_health.native.clock().utcoffset())
        self.assertIsInstance(factory.clock(), str)
