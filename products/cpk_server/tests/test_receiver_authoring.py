"""#238 complete receiver graph authoring and exact local preparation laws."""

from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
AUTHORING_MODULE = "control_plane_kit_servers_cpk_server.client.authoring"


class ReceiverAuthoringTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec(AUTHORING_MODULE),
            "#238 receiver authoring module is missing",
        )
        return importlib.import_module(AUTHORING_MODULE)

    def preparation_inputs(self):
        """Real public material with no graph, product instance or accepted receiver."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import control_plane_kit_core as core
        api = self.api()
        public = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"),
                (), health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        context = {
            "profile": "receiver-authoring-context.v1", "workspace_id": "workspace-a",
            "expectation": {"current_graph_id": None, "current_realized_projection_id": None,
                "desired_graph_id": None, "desired_realized_projection_id": None,
                "desired_graph_revision": 0},
            "current": {"graph_id": None, "realized_projection_id": None, "receivers": []},
            "desired": None, "pending_draft": None,
        }
        verifiers = {"workload_verifier_configuration": {"verifiers": [
            {"purpose": purpose.value, "issuer": "issuer-a",
             "public_keys": [{"key_id": "public-a",
                "algorithm": core.DelegationKeyAlgorithm.ED25519.value, "public_key_pem": public}]}
            for purpose in (core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
        ]}}
        return api, core, dict(workspace_id="workspace-a", runtime_id="runtime-a",
            scope=api.ReceiverScope("connector-a", "control"), receiver_id="a" * 32,
            declaration=declaration, context=context, verifier_configuration=verifiers)

    def preparation_entrypoint(self, api):
        # This assertion preserves collection and distinguishes interface absence
        # from downstream semantic laws that have not yet executed.
        prepare = getattr(api, "prepare_receiver_configuration", None)
        self.assertTrue(callable(prepare), "fresh receiver preparation interface is unavailable")
        return prepare

    def test_prepare_genuine_receiver_configuration_before_any_graph_or_instance(self):
        api, core, inputs = self.preparation_inputs()
        prepare = self.preparation_entrypoint(api)
        configured = prepare(**inputs)
        self.assertIs(type(configured), core.ReceiverNodeControlConfiguration)
        codec = core.ReceiverNodeControlConfigurationCodec()
        self.assertEqual(codec.decode_bytes(codec.encode_bytes(configured)), configured)
        self.assertEqual((configured.target.workspace_id.value, configured.target.runtime_id.value,
            configured.target.node_id.value, configured.target.provider_socket_name.value,
            configured.target.receiver_id), ("workspace-a", "runtime-a", "connector-a", "control", "a" * 32))
        self.assertEqual(configured.declaration, inputs["declaration"])
        self.assertEqual({item.purpose for item in configured.verifiers}, {
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ})
        self.assertEqual({key.public_key_pem for item in configured.verifiers for key in item.public_keys},
            {inputs["verifier_configuration"]["workload_verifier_configuration"]["verifiers"][0]
             ["public_keys"][0]["public_key_pem"]})
        from control_plane_kit_servers_cloudflared_connector import managed
        artifact = managed.control_configuration_artifact(configured)
        self.assertEqual(codec.decode_bytes(artifact.content.encode()), configured)
        public_api = importlib.import_module("control_plane_kit_servers_cpk_server.client")
        self.assertIs(public_api.prepare_receiver_configuration, prepare)

    def test_prepare_uses_owner_coordinate_grammars(self):
        api, core, inputs = self.preparation_inputs()
        prepare = self.preparation_entrypoint(api)
        surface = replace(inputs["declaration"].surface,
            provider_socket_name=core.NodeControlGraphReference(
                core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "API.Socket"))
        configured = prepare(**{**inputs, "runtime_id": "2Runtime",
            "scope": api.ReceiverScope("2Node", "API.Socket"),
            "declaration": replace(inputs["declaration"], surface=surface)})
        self.assertEqual((configured.target.runtime_id.value, configured.target.node_id.value,
                          configured.target.provider_socket_name.value), ("2Runtime", "2Node", "API.Socket"))

    def test_prepare_refuses_invalid_material_current_scope_and_pending_context(self):
        api, core, inputs = self.preparation_inputs()
        prepare = self.preparation_entrypoint(api)
        cases = [
            {"workspace_id": "foreign"}, {"workspace_id": "bad workspace"},
            {"runtime_id": "bad runtime"}, {"runtime_id": 123},
            {"scope": "connector-a"}, {"declaration": object()},
            {"scope": api.ReceiverScope("connector-a", "different")},
            *({"receiver_id": identity} for identity in ("", "a" * 31, "a" * 33, "A" * 32, "z" * 32, 1)),
            {"context": None}, {"verifier_configuration": None},
        ]
        for path, value in (
            (("profile",), "foreign.v1"), (("workspace_id",), "foreign"),
            (("current", "graph_id"), "unexpected-graph"),
            (("current", "realized_projection_id"), "unexpected-projection"),
            (("pending_draft",), {}), (("pending_draft",), {"draft_id": "draft-a", "revision": 1}),
        ):
            context = json.loads(json.dumps(inputs["context"]))
            target = context
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            cases.append({"context": context})
        current = self.fixture()
        from control_plane_kit_servers_hello_server.configuration import hello_control_declaration
        cases.append({"context": current["context"], "scope": api.ReceiverScope("hello-x", "internal"),
                      "declaration": hello_control_declaration()})
        for mutate in (
            lambda families:families.pop(),
            lambda families:families[0].update(purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL.value),
            lambda families:families[0].update(public_keys=[]),
            lambda families:families[0]["public_keys"][0].update(public_key_pem="PRIVATE-CONFIG-CANARY"),
            lambda families:families.append(dict(families[0])),
        ):
            verifiers = json.loads(json.dumps(inputs["verifier_configuration"]))
            mutate(verifiers["workload_verifier_configuration"]["verifiers"])
            cases.append({"verifier_configuration": verifiers})
        for index, changes in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(api.ReceiverAuthoringError) as caught:
                prepare(**{**inputs, **changes})
            self.assertEqual(str(caught.exception), "receiver graph could not be authored")
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)
            self.assertEqual(vars(caught.exception), {})

    def test_two_prepared_instances_preserve_one_original_catalogue_identity(self):
        api, core, inputs = self.preparation_inputs()
        prepare = self.preparation_entrypoint(api)
        from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
        from control_plane_kit_core.products import (
            ProductCatalog, ProductInstanceConfiguration, ProductInstantiationError,
            instantiate_catalog_product,
        )
        from control_plane_kit_core.topology import compile_topology
        from control_plane_kit_servers_cloudflared_connector import managed
        from health_receiver_join_fixtures import document
        factory = getattr(managed, "declared_runtime_contract", None)
        self.assertTrue(callable(factory), "required contract factory is unavailable")
        # Existing never-executed source descriptor fixture; no published native
        # descriptor is relabeled and no built/deployed image is claimed.
        selected = document("prepared-connectors", factory())
        catalog = ProductCatalog.from_documents((selected,))
        original = selected.content
        contract = selected.product.runtime_contract
        blocks, configurations = [], []
        for node_id, identity in (("connector-a", "a" * 32), ("connector-b", "b" * 32)):
            configured = prepare(**{**inputs, "scope": api.ReceiverScope(node_id, "control"),
                                   "receiver_id": identity})
            configurations.append(configured)
            artifact = managed.control_configuration_artifact(configured)
            blocks.append(instantiate_catalog_product(
                catalog, selected.product.identity, role_id=node_id,
                configuration=ProductInstanceConfiguration(
                    public_environment=contract.public_environment,
                    configuration_artifacts=(artifact,), secret_deliveries=())))
        graph = compile_topology(DeploymentTopology("prepared-connectors",
            DockerRuntime(runtime_id="runtime-a", children=tuple(blocks))))
        codec = core.ReceiverNodeControlConfigurationCodec()
        artifacts = []
        for node_id, configured in zip(("connector-a", "connector-b"), configurations):
            node = graph.node(node_id)
            artifact, = node.configuration_artifacts
            artifacts.append(artifact)
            self.assertEqual(codec.decode_bytes(artifact.content.encode()), configured)
            self.assertEqual(node.metadata["product_identity"], selected.product.identity.key)
            self.assertEqual(node.metadata["product_descriptor_digest"], selected.content_digest)
            self.assertEqual(node.metadata["oci_image"], selected.product.image.execution_reference)
            self.assertEqual(node.secret_deliveries, ())
        self.assertNotEqual(artifacts[0].content, artifacts[1].content)
        self.assertEqual(catalog.lookup(selected.product.identity).content, original)
        example_path = ROOT / "products/cpk_server/examples/prepared_receiver_configuration.py"
        spec = importlib.util.spec_from_file_location("prepared_receiver_example", example_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        example = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(example)
        self.assertEqual(example.two_instances(
            catalog=catalog, identity=selected.product.identity,
            workspace_id=inputs["workspace_id"], runtime_id=inputs["runtime_id"],
            context=inputs["context"], verifier_configuration=inputs["verifier_configuration"],
            first_receiver_id="a" * 32, second_receiver_id="b" * 32), graph)
        with self.assertRaises(ProductInstantiationError):
            instantiate_catalog_product(catalog, selected.product.identity, role_id="missing",
                configuration=ProductInstanceConfiguration(public_environment=contract.public_environment))

    def refresh_fixture(self):
        api = self.api()
        self.assertIn("verifier_refreshes", api.AuthoredDesiredGraph.__dataclass_fields__,
            "explicit current-receiver verifier refresh intent is missing")
        fixture = self.fixture()
        selected = json.loads(json.dumps(fixture["verifiers"]))
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        overlap = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        for family in selected["workload_verifier_configuration"]["verifiers"]:
            family["public_keys"].append({**family["public_keys"][0],
                "key_id": "public-overlap", "public_key_pem": overlap})
        return api, fixture, selected, api.ReceiverScope("hello-x", "internal")

    def declaration_fixture(self):
        api, fixture = self.api(), self.fixture()
        from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
        core = fixture["core"]
        scope = api.ReceiverScope("hello-x", "internal")
        gateway = api.ReceiverScope("gateway", "control")
        current = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(fixture["graph_a"]))
        fixture["graph_a"] = current
        node = current.node("hello-x")
        surface, = node.block_spec.control_surfaces
        desired = current.update_node(replace(node, block_spec=replace(node.block_spec,
            control_surfaces=(replace(surface, health_reads=(core.NodeHealthReadKind.READINESS,)),))))
        routes = api.GatewayHealthRoutes(gateway, (
            api.GatewayHealthTargetIntent("gateway-self", gateway, "http://gateway:8000"),
            api.GatewayHealthTargetIntent("hello-x", scope, "http://hello-x:8000"),
        ))
        return api, fixture, scope, desired, routes

    def test_declaration_update_changes_only_declaration_and_explicit_route(self):
        api, fixture, scope, desired, routes = self.declaration_fixture()
        core = fixture["core"]
        authored = api.author_receiver_graph(desired, workspace_id="workspace-a",
            context=fixture["context"], verifier_configuration=None,
            declaration_updates=(scope,), gateway_health_replacements=(routes,),
            receiver_identity_factory=lambda: self.fail("identity regenerated"))
        before = fixture["x_wrapper"]
        after, = authored.node("hello-x").configuration_artifacts
        codec = core.ReceiverNodeControlConfigurationCodec()
        old, new = (codec.decode_bytes(item.content.encode()) for item in (before, after))
        self.assertEqual((new.target, new.verifiers), (old.target, old.verifiers))
        self.assertEqual(new.declaration.surface.health_reads, (core.NodeHealthReadKind.READINESS,))
        self.assertNotEqual(new.declaration, old.declaration)
        expected_bytes = codec.encode_bytes(replace(old, declaration=new.declaration))
        self.assertEqual(after.content.encode(), expected_bytes)
        self.assertEqual(after.source_digest, after.content_digest)
        self.assertEqual(after.source_digest, hashlib.sha256(expected_bytes).hexdigest())
        self.assertNotEqual(after.source_digest, before.source_digest)
        self.assertEqual(replace(after, content=before.content, source_digest=before.source_digest), before)
        old_routes = core.ReceiverManagementRoutesCodec().decode_bytes(fixture["routes"].content.encode())
        route_artifact, = (item for item in authored.node("gateway").configuration_artifacts
            if item.artifact_id == fixture["routes"].artifact_id)
        new_routes = core.ReceiverManagementRoutesCodec().decode_bytes(route_artifact.content.encode())
        self.assertEqual(new_routes.gateway_target, old_routes.gateway_target)
        expected = replace(old_routes, targets=tuple(replace(item, declaration=new.declaration)
            if item.target == old.target else item for item in old_routes.targets))
        self.assertEqual(new_routes, expected)
        self.assertEqual(authored.node("gateway").configuration_artifacts,
            tuple(route_artifact if item == fixture["routes"] else item
                for item in desired.node("gateway").configuration_artifacts))
        # Omission retains the strict path; a changed desired surface is not intent.
        with self.assertRaises(api.ReceiverAuthoringError):
            api.author_receiver_graph(desired, workspace_id="workspace-a",
                context=fixture["context"], verifier_configuration=None,
                gateway_health_replacements=(routes,))

    def test_declaration_noop_preserves_exact_bytes_without_route_or_key_read(self):
        api, fixture, scope, _, _ = self.declaration_fixture()
        before = replace(fixture["x_wrapper"],
            content=json.dumps(json.loads(fixture["x_wrapper"].content), indent=3) + "\n",
            source_digest="f" * 64)
        graph = fixture["graph_a"].update_node(replace(fixture["graph_a"].node("hello-x"),
            configuration_artifacts=(before,)))
        row = fixture["context"]["current"]["receivers"][1]
        row["configuration_artifact"] = before.descriptor()
        row["binding"]["selected_configuration_digest"] = before.content_digest
        authored = api.author_receiver_graph(graph, workspace_id="workspace-a",
            context=fixture["context"], verifier_configuration=None, declaration_updates=(scope,))
        self.assertEqual(authored, graph)
        self.assertEqual(authored.node("hello-x").configuration_artifacts[0].descriptor(), before.descriptor())

    def test_declaration_update_refuses_missing_routes_and_conflicting_scopes(self):
        api, fixture, scope, desired, routes = self.declaration_fixture()
        for replacements in ((), (replace(routes, targets=()),),
                (replace(routes, targets=routes.targets[:1]),),
                (replace(routes, targets=routes.targets[1:]),)):
            with self.subTest(routes=replacements), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(desired, workspace_id="workspace-a",
                    context=fixture["context"], verifier_configuration=None,
                    declaration_updates=(scope,), gateway_health_replacements=replacements)
        for updates, other in (
            ((scope, scope), {}), ((api.ReceiverScope("missing", "internal"),), {}),
            ((routes.gateway_scope,), {}), ((scope,), {"verifier_refreshes": (scope,)}),
            ((scope,), {"introductions": (api.ReceiverIntroduction(scope, "new", "/etc/new.json"),)}),
            ((scope,), {"pending": api.PendingReceiverContinuation("draft-a", 1, (scope,))}),
        ):
            with self.subTest(updates=updates, other=other), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(desired, workspace_id="workspace-a",
                    context=fixture["context"], verifier_configuration=None,
                    declaration_updates=updates, gateway_health_replacements=(routes,), **other)
        for other in ({"declaration_updates": (scope, scope)},
                {"declaration_updates": ("hello-x",)},
                {"declaration_updates": (scope,), "verifier_refreshes": (scope,)},
                {"declaration_updates": (scope,), "pending": api.PendingReceiverContinuation("draft-a", 1, (scope,))}):
            with self.subTest(other=other), self.assertRaises(ValueError):
                api.AuthoredDesiredGraph(self.root / "graph.json", **other)

    def test_declaration_update_validates_current_binding_and_health_only_boundary(self):
        api, fixture, scope, desired, routes = self.declaration_fixture()
        core = fixture["core"]
        desired_declaration = core.WorkloadNodeControlSurfaceDeclaration(
            desired.node("hello-x").block_spec.control_surfaces[0],
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        for field, value in (("workspace_id", "foreign"), ("runtime_id", "foreign"),
                ("receiver_id", "f" * 32), ("declaration_identity", desired_declaration.identity().value),
                ("selected_configuration_digest", "0" * 64)):
            context = json.loads(json.dumps(fixture["context"]))
            context["current"]["receivers"][1]["binding"][field] = value
            with self.subTest(field=field), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(desired, workspace_id="workspace-a", context=context,
                    verifier_configuration=None, declaration_updates=(scope,), gateway_health_replacements=(routes,))
        node = desired.node("hello-x")
        surface, = node.block_spec.control_surfaces
        variable_surface = fixture["graph_variable"].node("hello-y").block_spec.control_surfaces[0]
        for changed in (replace(surface, health_reads=(core.NodeHealthReadKind.LIVENESS,)),
                replace(surface, variables=variable_surface.variables)):
            graph = desired.update_node(replace(node,
                block_spec=replace(node.block_spec, control_surfaces=(changed,))))
            with self.subTest(changed=changed), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(graph, workspace_id="workspace-a", context=fixture["context"],
                    verifier_configuration=None, declaration_updates=(scope,), gateway_health_replacements=(routes,))

    def test_declaration_cli_selects_intent_and_refuses_duplicates(self):
        api, _, scope, _, _ = self.declaration_fixture()
        from control_plane_kit_servers_cpk_server.client import cli, ClientInputError
        arguments = cli._parser().parse_args(["--profile", "local", "plan", "graph.json",
            "--update-receiver-declaration", "hello-x", "internal"])
        self.assertTrue(cli._has_authoring_arguments(arguments))
        self.assertEqual(cli._authored_plan_input(arguments).declaration_updates, (scope,))
        arguments.update_receiver_declaration.append(("hello-x", "internal"))
        with self.assertRaises(ClientInputError):
            cli._authored_plan_input(arguments)

    def test_declaration_client_journals_coupled_bytes_and_retries_without_reauthoring(self):
        api, fixture, scope, desired, routes = self.declaration_fixture()
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_servers_cpk_server.client import TopologyClient, JournalError
        from test_topology_client import DeterministicIds
        codec = GraphDescriptorCodec()
        source = self.root / "declaration.json"
        source.write_text(json.dumps(codec.encode(desired)), encoding="utf-8")
        source_bytes = source.read_bytes()
        transport = self.authoring_transport(fixture)
        no_identity = lambda: self.fail("declaration update allocated an identity")
        client = TopologyClient(self.client_profile(), transport=transport,
            identity_factory=DeterministicIds(), receiver_identity_factory=no_identity)
        operation_ref = "00000000-0000-4000-8000-000000000001"
        def before_prepare(payload):
            journal = client.journal.read(operation_ref)
            artifact = client.journal.root / journal["preparation"]["name"]
            self.assertEqual(json.loads(artifact.read_bytes()), payload["desired_graph"])
            self.assertEqual(os.stat(artifact).st_mode & 0o777, 0o600)
            material = codec.decode(payload["desired_graph"])
            for node in ("hello-x", "gateway"):
                self.assertNotEqual(material.node(node).configuration_artifacts,
                    fixture["graph_a"].node(node).configuration_artifacts)
        transport.before_prepare = before_prepare
        result = client.plan(api.AuthoredDesiredGraph(source, declaration_updates=(scope,),
            gateway_health_replacements=(routes,)))
        self.assertEqual(result.status, "attention-required")
        first, = [call for call in transport.calls if call["route_id"] == "command.deployment.prepare"]
        self.assertFalse(any(call["route_id"] == "read.workload-verifier-configuration" for call in transport.calls))
        journal = client.journal.read(result.operation_ref)
        artifact = client.journal.root / journal["preparation"]["name"]
        prepared_bytes = artifact.read_bytes()
        restarted = TopologyClient(self.client_profile(), transport=transport, receiver_identity_factory=no_identity)
        source.write_text("{}", encoding="utf-8")
        self.assertEqual(restarted.resume_prepare(result.operation_ref).status, "attention-required")
        source.write_bytes(source_bytes)
        artifact.write_bytes(b"{}")
        with self.assertRaises(JournalError):
            restarted.resume_prepare(result.operation_ref)
        self.assertEqual(sum(call["route_id"] == "command.deployment.prepare" for call in transport.calls), 1)
        artifact.write_bytes(prepared_bytes)
        fixture["context"]["current"]["receivers"] = []
        self.assertEqual(restarted.resume_prepare(result.operation_ref).status, "planned")
        self.assertEqual([call for call in transport.calls if call["route_id"] == "command.deployment.prepare"],
            [first, first])
        self.assertEqual(sum(call["route_id"] == "read.receiver-authoring-context" for call in transport.calls), 1)
        self.assertEqual(artifact.read_bytes(), prepared_bytes)

    def test_refresh_changes_only_selected_current_wrapper(self):
        api, fixture, selected, scope = self.refresh_fixture()
        core = fixture["core"]
        from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
        from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
        application = ConfigurationArtifact("application", "/etc/app/settings.json",
            ConfigurationMediaType.JSON, '{"revision":1}')
        graph = fixture["graph_a"]
        graph = graph.update_node(replace(graph.node("hello-x"),
            configuration_artifacts=(fixture["x_wrapper"], application)))
        graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(graph))
        authored = api.author_receiver_graph(graph, workspace_id="workspace-a",
            context=fixture["context"], verifier_configuration=selected,
            verifier_refreshes=(scope,), receiver_identity_factory=lambda: self.fail("identity regenerated"))
        before = fixture["x_wrapper"]
        after, = [item for item in authored.node("hello-x").configuration_artifacts
            if item.artifact_id == before.artifact_id]
        codec = core.ReceiverNodeControlConfigurationCodec()
        old, new = (codec.decode_bytes(item.content.encode()) for item in (before, after))
        self.assertEqual((new.target, new.declaration), (old.target, old.declaration))
        self.assertNotEqual(new.verifiers, old.verifiers)
        self.assertTrue(all({key.key_id for key in family.public_keys} ==
            {"public-a", "public-overlap"} for family in new.verifiers))
        self.assertEqual(replace(after, content=before.content, source_digest=before.source_digest), before)
        restored = authored.update_node(replace(authored.node("hello-x"),
            configuration_artifacts=graph.node("hello-x").configuration_artifacts))
        self.assertEqual(restored, graph)
        ordinary = api.author_receiver_graph(graph, workspace_id="workspace-a",
            context=fixture["context"], verifier_configuration=selected)
        self.assertEqual(ordinary, graph)

    def test_refresh_equal_families_preserve_noncanonical_bytes_and_source_digest(self):
        api, fixture, _, scope = self.refresh_fixture()
        from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
        original = fixture["x_wrapper"]
        content = json.dumps(json.loads(original.content), indent=3) + "\n"
        artifact = replace(original, content=content, source_digest="f" * 64)
        graph = fixture["graph_a"].update_node(replace(fixture["graph_a"].node("hello-x"),
            configuration_artifacts=(artifact,)))
        graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(graph))
        row = fixture["context"]["current"]["receivers"][1]
        row["configuration_artifact"] = artifact.descriptor()
        row["binding"]["selected_configuration_digest"] = artifact.content_digest
        # The owner response may order families differently from the installed bytes.
        fixture["verifiers"]["workload_verifier_configuration"]["verifiers"].reverse()
        authored = api.author_receiver_graph(graph, workspace_id="workspace-a",
            context=fixture["context"], verifier_configuration=fixture["verifiers"],
            verifier_refreshes=(scope,), receiver_identity_factory=lambda: self.fail("identity regenerated"))
        actual, = authored.node("hello-x").configuration_artifacts
        self.assertEqual(actual.descriptor(), artifact.descriptor())
        self.assertEqual(actual.content, content)
        self.assertEqual(authored, graph)

    def test_refresh_refuses_noncurrent_duplicate_and_conflicting_scopes(self):
        api, fixture, selected, scope = self.refresh_fixture()
        with self.assertRaises(ValueError):
            api.AuthoredDesiredGraph(self.root / "graph.json", verifier_refreshes=(scope, scope))
        with self.assertRaises(ValueError):
            api.AuthoredDesiredGraph(self.root / "graph.json", verifier_refreshes=("hello-x",))
        for scopes, introductions, pending in (
            ((api.ReceiverScope("missing", "internal"),), (), None),
            ((scope, scope), (), None),
            ((scope,), (api.ReceiverIntroduction(scope, "new", "/etc/new.json"),), None),
            ((scope,), (), api.PendingReceiverContinuation("draft-a", 1, (scope,))),
        ):
            with self.subTest(scopes=scopes, pending=bool(pending)):
                with self.assertRaises(api.ReceiverAuthoringError):
                    api.author_receiver_graph(fixture["graph_a"], workspace_id="workspace-a",
                        context=fixture["context"], verifier_configuration=selected,
                        verifier_refreshes=scopes, introductions=introductions, pending=pending,
                        receiver_identity_factory=lambda: self.fail("identity regenerated"))
        # A valid pending-only receiver is still not a current refresh target.
        row = fixture["context"]["current"]["receivers"].pop()
        row["lifecycle"] = "pending"
        fixture["context"]["pending_draft"] = {"draft_id": "draft-a", "head_revision": 1,
            "graph_id": "graph-current", "realized_projection_id": "projection-current",
            "receivers": [row]}
        with self.assertRaises(api.ReceiverAuthoringError):
            api.author_receiver_graph(fixture["graph_a"], workspace_id="workspace-a",
                context=fixture["context"], verifier_configuration=selected,
                verifier_refreshes=(scope,))

    def test_refresh_refuses_foreign_current_binding_and_invalid_families(self):
        api, fixture, selected, scope = self.refresh_fixture()
        mutations = (
            ("workspace_id", "foreign"), ("runtime_id", "foreign"),
            ("declaration_identity", "f" * 64), ("selected_configuration_digest", "0" * 64),
        )
        for field, value in mutations:
            context = json.loads(json.dumps(fixture["context"]))
            context["current"]["receivers"][1]["binding"][field] = value
            with self.subTest(field=field), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(fixture["graph_a"], workspace_id="workspace-a",
                    context=context, verifier_configuration=selected, verifier_refreshes=(scope,))
        for material in (None, {"workload_verifier_configuration": {"verifiers": []}},
                {"workload_verifier_configuration": {"verifiers":
                    selected["workload_verifier_configuration"]["verifiers"][:1]}}):
            with self.subTest(material=bool(material)), self.assertRaises(api.ReceiverAuthoringError):
                api.author_receiver_graph(fixture["graph_a"], workspace_id="workspace-a",
                    context=fixture["context"], verifier_configuration=material,
                    verifier_refreshes=(scope,))

    def test_client_refresh_journals_exact_bytes_and_restarts_without_reselection(self):
        api, fixture, selected, scope = self.refresh_fixture()
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_servers_cpk_server.client import TopologyClient, JournalError
        from test_topology_client import DeterministicIds
        codec = GraphDescriptorCodec()
        source = self.root / "refresh.json"
        source.write_text(json.dumps(codec.encode(fixture["graph_a"])), encoding="utf-8")
        original = source.read_bytes()
        fixture["verifiers"] = selected
        transport = self.authoring_transport(fixture)
        no_identity = lambda: self.fail("refresh allocated receiver identity")
        client = TopologyClient(self.client_profile(), transport=transport,
            identity_factory=DeterministicIds(), receiver_identity_factory=no_identity)
        operation_ref = "00000000-0000-4000-8000-000000000001"
        def before_prepare(payload):
            journal = client.journal.read(operation_ref)
            artifact = client.journal.root / journal["preparation"]["name"]
            self.assertEqual(json.loads(artifact.read_bytes()), payload["desired_graph"])
            self.assertEqual(os.stat(artifact).st_mode & 0o777, 0o600)
        transport.before_prepare = before_prepare
        result = client.plan(api.AuthoredDesiredGraph(source, verifier_refreshes=(scope,)))
        self.assertEqual(result.status, "attention-required")
        first, = [call for call in transport.calls if call["route_id"] == "command.deployment.prepare"]
        prepared = codec.decode(first["payload"]["desired_graph"])
        self.assertNotEqual(prepared.node("hello-x").configuration_artifacts,
            fixture["graph_a"].node("hello-x").configuration_artifacts)
        verifier_read, = [call for call in transport.calls
            if call["route_id"] == "read.workload-verifier-configuration"]
        self.assertEqual(verifier_read["credential_role"], "operator")
        self.assertEqual(set(verifier_read["path_parameters"]["purposes"].split(",")),
            {fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ.value,
             fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ.value})
        journal = client.journal.read(result.operation_ref)
        artifact = client.journal.root / journal["preparation"]["name"]
        saved_bytes = artifact.read_bytes()
        restarted = TopologyClient(self.client_profile(), transport=transport,
            receiver_identity_factory=no_identity)
        artifact.write_bytes(b"{}")
        with self.assertRaises(JournalError):
            restarted.resume_prepare(result.operation_ref)
        self.assertEqual(sum(call["route_id"] == "command.deployment.prepare" for call in transport.calls), 1)
        artifact.write_bytes(saved_bytes)
        fixture["verifiers"] = {"workload_verifier_configuration": {"verifiers": []}}
        resumed = restarted.resume_prepare(result.operation_ref)
        self.assertEqual(resumed.status, "planned")
        prepares = [call for call in transport.calls if call["route_id"] == "command.deployment.prepare"]
        self.assertEqual(prepares, [first, first])
        for route in ("read.receiver-authoring-context", "read.workload-verifier-configuration"):
            self.assertEqual(sum(call["route_id"] == route for call in transport.calls), 1)
        self.assertEqual(artifact.read_bytes(), saved_bytes)
        self.assertEqual(source.read_bytes(), original)

    def test_refresh_cli_selects_explicit_scopes_and_refuses_duplicates(self):
        api, _, _, scope = self.refresh_fixture()
        from control_plane_kit_servers_cpk_server.client import cli, ClientInputError
        arguments = cli._parser().parse_args(["--profile", "local", "plan", "graph.json",
            "--refresh-receiver-verifiers", "hello-x", "internal"])
        selected = cli._authored_plan_input(arguments)
        self.assertEqual(selected.verifier_refreshes, (scope,))
        self.assertEqual(selected.introductions, ())
        arguments.refresh_receiver_verifiers.append(("hello-x", "internal"))
        with self.assertRaises(ClientInputError):
            cli._authored_plan_input(arguments)

    def test_mixed_refresh_and_introduction_select_union_then_each_declaration(self):
        api, fixture, selected, scope = self.refresh_fixture()
        core = fixture["core"]
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_servers_cpk_server.client import TopologyClient
        codec = GraphDescriptorCodec()
        source = self.root / "mixed.json"
        source.write_text(json.dumps(codec.encode(fixture["graph_variable"])), encoding="utf-8")
        fixture["verifiers"] = selected
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        identities = []
        client = TopologyClient(self.client_profile(), transport=transport,
            receiver_identity_factory=lambda: identities.append("c" * 32) or "c" * 32)
        client.plan(api.AuthoredDesiredGraph(source, verifier_refreshes=(scope,),
            introductions=(api.ReceiverIntroduction(api.ReceiverScope("hello-y", "internal"),
                "hello-control", "/etc/cpk/hello/control.json"),)))
        read, = [call for call in transport.calls
            if call["route_id"] == "read.workload-verifier-configuration"]
        purpose = core.DelegationKeyPurpose
        surface, health, control = (purpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            purpose.WORKLOAD_NODE_HEALTH_READ, purpose.WORKLOAD_NODE_CONTROL)
        self.assertEqual(set(read["path_parameters"]["purposes"].split(",")),
            {surface.value, health.value, control.value})
        self.assertEqual(read["credential_role"], "operator")
        prepare, = [call for call in transport.calls if call["route_id"] == "command.deployment.prepare"]
        authored = codec.decode(prepare["payload"]["desired_graph"])
        for name, expected in (("hello-x", {surface, health}), ("hello-y", {surface, control})):
            artifact, = authored.node(name).configuration_artifacts
            configured = core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())
            self.assertEqual({family.purpose for family in configured.verifiers}, expected)
        self.assertEqual(identities, ["c" * 32])
        # This scripted client test asserts authoring, not mixed deployment eligibility.

    def test_profile_import_does_not_require_receiver_authoring_dependencies(self):
        script = """
import sys

from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
assert "control_plane_kit_servers_cpk_server.client.authoring" not in sys.modules
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PRODUCT_SRC)
        result = subprocess.run(
            [sys.executable, "-c", script],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def fixture(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import control_plane_kit_core as core
        from control_plane_kit_core.algebra import BlockSockets, BlockSpec, ProviderSocket
        from control_plane_kit_core.capabilities import CapabilityName
        from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
        from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
        from control_plane_kit_core.topology import DeploymentGraph, Node, RuntimeRecord
        from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
        from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
        from control_plane_kit_core.wrapper_configuration import (
            NodeControlVerificationConfiguration,
            WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT,
        )
        from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
            gateway_health_relay_configuration_artifact,
        )
        from control_plane_kit_servers_cpk_local_gateway.control_configuration import gateway_control_declaration
        from control_plane_kit_servers_hello_server.configuration import hello_control_declaration
        from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
            GatewayHealthTransitConfiguration,
            gateway_health_transit_configuration_artifact,
        )

        roles = core.NodeControlGraphReferenceRole

        def ref(role, value):
            return core.NodeControlGraphReference(role, value)

        workspace = ref(roles.WORKSPACE, "workspace-a")
        runtime = ref(roles.RUNTIME, "runtime-a")

        def target(node, socket, receiver):
            return core.NodeControlReceiverTarget(
                workspace,
                runtime,
                ref(roles.NODE, node),
                ref(roles.PROVIDER_SOCKET, socket),
                receiver,
            )

        gateway_target = target("gateway", "control", "a" * 32)
        x_target = target("hello-x", "internal", "b" * 32)
        gateway_declaration = gateway_control_declaration()
        hello_declaration = hello_control_declaration()
        private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey(
            "public-a",
            core.DelegationKeyAlgorithm.ED25519,
            private.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii"),
        )

        def verifiers(declaration):
            purposes = [core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ]
            if declaration.surface.variables:
                purposes.append(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL)
            if declaration.surface.health_reads:
                purposes.append(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
            return tuple(
                NodeControlVerificationConfiguration(purpose, "issuer-a", (public,))
                for purpose in purposes
            )

        def wrapper_artifact(identity, path, configured):
            content = core.ReceiverNodeControlConfigurationCodec().encode_bytes(configured)
            return ConfigurationArtifact(
                identity, path, ConfigurationMediaType.JSON, content.decode("utf-8")
            )

        gateway_wrapper = wrapper_artifact(
            "gateway-control",
            "/etc/cpk/gateway/control.json",
            core.ReceiverNodeControlConfiguration(
                gateway_target, gateway_declaration, verifiers(gateway_declaration)
            ),
        )
        x_wrapper = wrapper_artifact(
            "hello-control",
            "/etc/cpk/hello/control.json",
            core.ReceiverNodeControlConfiguration(
                x_target, hello_declaration, verifiers(hello_declaration)
            ),
        )
        trust = gateway_health_transit_configuration_artifact(
            GatewayHealthTransitConfiguration(
                gateway_target,
                "gateway-issuer",
                core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
                (public,),
            )
        )
        routes = gateway_health_relay_configuration_artifact(
            core.ReceiverManagementRoutes(
                gateway_target,
                (
                    core.ReceiverManagementRouteBinding(
                        "gateway-self", gateway_target, gateway_declaration,
                        "http://gateway:8000",
                    ),
                    core.ReceiverManagementRouteBinding(
                        "hello-x",
                        x_target,
                        hello_declaration,
                        "http://hello-x:8000",
                    ),
                ),
            )
        )

        def node(node_id, declaration, artifacts, path, *, gateway=False):
            socket = declaration.surface.provider_socket_name.value
            spec = BlockSpec(
                node_id,
                capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
                control_surfaces=(declaration.surface,),
                gateway_transit=(
                    core.GatewayTransitDeclaration(
                        socket, core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2
                    )
                    if gateway
                    else None
                ),
            )
            environment = tuple(
                PublicStaticEnvironmentBinding(
                    WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, artifact.target_path
                )
                for artifact in artifacts
                if artifact.artifact_id in {"gateway-control", "hello-control"}
            )
            return Node(
                node_id,
                BlockFamily.APPLICATION,
                spec,
                "container-server",
                "runtime-a",
                BlockSockets(providers=(ProviderSocket(socket, Protocol.HTTP),)),
                endpoints={socket: Endpoint(LiteralAddress(path), Protocol.HTTP)},
                public_environment=environment,
                configuration_artifacts=artifacts,
            )

        gateway = node(
            "gateway",
            gateway_declaration,
            (trust, routes, gateway_wrapper),
            "http://gateway:8000",
            gateway=True,
        )
        hello_x = node(
            "hello-x",
            hello_declaration,
            (x_wrapper,),
            "http://hello-x:8000",
        )
        hello_y = node(
            "hello-y",
            replace(
                hello_declaration,
                surface=replace(
                    hello_declaration.surface,
                    provider_socket_name=ref(roles.PROVIDER_SOCKET, "internal"),
                ),
            ),
            (),
            "http://hello-y:8000",
        )
        variable = core.ControlPlaneVariableDescriptor(
            ref(roles.VARIABLE, "mode"),
            core.ControlPlaneVariableKind.SCALAR,
            core.ControlPlaneStateCodec.SCALAR_V1,
            (
                core.ControlPlaneVariableOperationContract(
                    core.NodeControlOperation.READ_STATE,
                    None,
                    core.ControlPlaneResultCodec.STATE_V1,
                ),
                core.ControlPlaneVariableOperationContract(
                    core.NodeControlOperation.APPLY_COMMAND,
                    core.ControlPlaneCommandCodec.REPLACE_SCALAR_V1,
                    core.ControlPlaneResultCodec.TRANSITION_V1,
                ),
            ),
        )
        variable_declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                ref(roles.PROVIDER_SOCKET, "internal"),
                (variable,),
            ),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V1,
        )
        hello_variable = node(
            "hello-y",
            variable_declaration,
            (),
            "http://hello-y:8000",
        )
        graph_a = DeploymentGraph(
            "receiver-authoring",
            nodes={"gateway": gateway, "hello-x": hello_x},
            runtimes={
                "runtime-a": RuntimeRecord(
                    "runtime-a", RuntimeKind.DOCKER, ("gateway", "hello-x")
                )
            },
        )
        graph_b = replace(
            graph_a,
            nodes={**graph_a.nodes, "hello-y": hello_y},
            runtimes={
                "runtime-a": replace(
                    graph_a.runtimes["runtime-a"],
                    children=("gateway", "hello-x", "hello-y"),
                )
            },
        )
        graph_variable = replace(
            graph_b,
            nodes={**graph_b.nodes, "hello-y": hello_variable},
        )

        def receiver(binding_target, artifact):
            return {
                "binding": {
                    "workspace_id": "workspace-a",
                    "graph_id": "graph-current",
                    "realized_projection_id": "projection-current",
                    "runtime_id": binding_target.runtime_id.value,
                    "node_id": binding_target.node_id.value,
                    "provider_socket_name": binding_target.provider_socket_name.value,
                    "receiver_id": binding_target.receiver_id,
                    "selected_configuration_digest": artifact.content_digest,
                    "declaration_identity": (
                        gateway_declaration
                        if binding_target == gateway_target
                        else hello_declaration
                    ).identity().value,
                },
                "configuration_artifact": artifact.descriptor(),
                "origin": {
                    "introducing_graph_id": "graph-a",
                    "introducing_realized_projection_id": "projection-a",
                    "introducing_action_id": "action-a",
                    "introducing_session_id": "session-a",
                    "introducing_draft_id": None,
                    "first_accepted_action_id": "action-a",
                    "first_accepted_session_id": "session-a",
                },
                "lifecycle": "current",
            }

        expectation = {
            "current_graph_id": "graph-current",
            "current_realized_projection_id": "projection-current",
            "desired_graph_id": None,
            "desired_realized_projection_id": None,
            "desired_graph_revision": 0,
        }
        context = {
            "profile": "receiver-authoring-context.v1",
            "workspace_id": "workspace-a",
            "expectation": expectation,
            "current": {
                "graph_id": "graph-current",
                "realized_projection_id": "projection-current",
                "receivers": [
                    receiver(gateway_target, gateway_wrapper),
                    receiver(x_target, x_wrapper),
                ],
            },
            "desired": None,
            "pending_draft": None,
        }
        verifier_configuration = {
            "workload_verifier_configuration": {
                "verifiers": [
                    {
                        "purpose": purpose.value,
                        "issuer": "issuer-a",
                        "public_keys": [
                            {
                                "key_id": public.key_id,
                                "algorithm": public.algorithm.value,
                                "public_key_pem": public.public_key_pem,
                            }
                        ],
                    }
                    for purpose in (
                        core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL,
                        core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                        core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
                    )
                ]
            }
        }
        return {
            "core": core,
            "graph_a": graph_a,
            "graph_b": graph_b,
            "graph_variable": graph_variable,
            "context": context,
            "verifiers": verifier_configuration,
            "gateway_target": gateway_target,
            "x_target": x_target,
            "gateway_wrapper": gateway_wrapper,
            "x_wrapper": x_wrapper,
            "trust": trust,
            "routes": routes,
        }

    def test_default_fresh_identity_is_shared_by_wrapper_and_complete_gateway_route(self):
        api = self.api()
        fixture = self.fixture()
        from control_plane_kit_core.receiver_configuration import (
            ReceiverNodeControlConfigurationCodec,
            select_receiver_node_control_configuration_artifact,
        )
        from control_plane_kit_core.receiver_management_routes import ReceiverManagementRoutesCodec

        y_scope = api.ReceiverScope("hello-y", "internal")
        authored = api.author_receiver_graph(
            fixture["graph_b"],
            workspace_id="workspace-a",
            context=fixture["context"],
            verifier_configuration=fixture["verifiers"],
            introductions=(
                api.ReceiverIntroduction(
                    y_scope, "hello-control", "/etc/cpk/hello/control.json"
                ),
            ),
            gateway_health_replacements=(
                api.GatewayHealthRoutes(
                    api.ReceiverScope("gateway", "control"),
                    (
                        api.GatewayHealthTargetIntent(
                            "gateway-self", api.ReceiverScope("gateway", "control"),
                            fixture["graph_b"].node("gateway").endpoint("control").url,
                        ),
                        api.GatewayHealthTargetIntent(
                            "hello-x",
                            api.ReceiverScope("hello-x", "internal"),
                            fixture["graph_b"].node("hello-x").endpoint("internal").url,
                        ),
                        api.GatewayHealthTargetIntent(
                            "hello-y", y_scope, fixture["graph_b"].node("hello-y").endpoint("internal").url
                        ),
                    ),
                ),
            ),
        )

        y_node = authored.node("hello-y")
        y_artifact = select_receiver_node_control_configuration_artifact(
            artifacts=y_node.configuration_artifacts,
            environment=y_node.public_environment + y_node.socket_environment,
            control_surfaces=y_node.block_spec.control_surfaces,
        )
        y_configuration = ReceiverNodeControlConfigurationCodec().decode_bytes(
            y_artifact.content.encode("utf-8")
        )
        self.assertRegex(y_configuration.target.receiver_id, r"[0-9a-f]{32}")
        route_artifact = next(
            artifact
            for artifact in authored.node("gateway").configuration_artifacts
            if artifact.artifact_id == "gateway-health-targets"
        )
        route = ReceiverManagementRoutesCodec().decode_bytes(
            route_artifact.content.encode("utf-8")
        )
        routed_y = next(item for item in route.targets if item.target_id == "hello-y")
        self.assertEqual(routed_y.target, y_configuration.target)
        self.assertEqual(route.gateway_target, fixture["gateway_target"])
        self.assertEqual({item.target_id for item in route.targets},
                         {"gateway-self", "hello-x", "hello-y"})
        previous = ReceiverManagementRoutesCodec().decode_bytes(fixture["routes"].content.encode())
        self.assertEqual(tuple(item for item in route.targets if item.target_id != "hello-y"), previous.targets)
        self.assertEqual(
            next(
                item for item in authored.node("hello-x").configuration_artifacts
                if item.artifact_id == "hello-control"
            ),
            fixture["x_wrapper"],
        )
        self.assertEqual(
            next(
                item for item in authored.node("gateway").configuration_artifacts
                if item.artifact_id == "gateway-health-transit"
            ),
            fixture["trust"],
        )

    def test_complete_registered_same_product_routes_preserve_self_and_x(self):
        self.assert_complete_registered_routes(distinct_product=False)

    def test_distinct_registered_products_use_common_receiver_routes_without_registry(self):
        self.assert_complete_registered_routes(distinct_product=True)

    def assert_complete_registered_routes(self, *, distinct_product):
        """Pure source-product composition; no deployed-image or saga claim."""
        import control_plane_kit_core as core
        from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
        from control_plane_kit_core.products import (
            ContainerServerProduct, OciImageReference, ProductDescriptorCodec,
            ProductIdentity, ProductInstanceConfiguration, instantiate_product,
        )
        from control_plane_kit_core.topology import compile_topology
        from control_plane_kit_core.planning import PlanGraphSide
        from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
        from control_plane_kit_operations.products import RegisteredProduct, InlineDescriptorSource
        from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection
        from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_source_runtime_contract
        from control_plane_kit_servers_hello_server.configuration import hello_source_runtime_contract
        from control_plane_kit_servers_secrets_server.configuration import (
            secrets_control_configuration_artifact, secrets_source_runtime_contract,
        )
        from control_plane_kit_secrets.control import secrets_control_declaration
        from control_plane_kit_servers_cpk_server.health_receiver_adapters import (
            select_gateway_self_health_binding, select_own_health_configuration,
        )

        api, fixture = self.api(), self.fixture()
        wrapper_codec = core.ReceiverNodeControlConfigurationCodec()
        route_codec = core.ReceiverManagementRoutesCodec()

        def registered(name, contract):
            # A distinct never-executed descriptor records this source contract;
            # no historical published image is associated with new behavior.
            codec = ProductDescriptorCodec()
            document = codec.encode_document(ContainerServerProduct(
                ProductIdentity("receiver-test", name, 1),
                OciImageReference("example.invalid", "never-executed/" + name, "sha256:" + "b" * 64),
                contract,
            ))
            return RegisteredProduct.from_document(workspace_id="workspace-a",
                descriptor_document=codec.decode_document(document.content),
                source=InlineDescriptorSource(), imported_by="fixture",
                imported_at="2026-10-10T00:00:00Z")

        gateway = registered("gateway", gateway_health_source_runtime_contract(
            fixture["trust"], fixture["routes"], fixture["gateway_wrapper"]))
        hello = registered("hello", hello_source_runtime_contract(fixture["x_wrapper"]))
        y_name, y_socket, y_port = ("secrets-y", "control", 8081) if distinct_product else ("hello-y", "internal", 8000)
        y_product = hello
        y_artifact = fixture["x_wrapper"]
        if distinct_product:
            configured = wrapper_codec.decode_bytes(fixture["x_wrapper"].content.encode())
            y_target = replace(configured.target,
                node_id=replace(configured.target.node_id, value=y_name),
                provider_socket_name=replace(configured.target.provider_socket_name, value=y_socket))
            y_artifact = secrets_control_configuration_artifact(replace(configured,
                target=y_target, declaration=secrets_control_declaration()))
            y_product = registered("secrets", secrets_source_runtime_contract(y_artifact))
            self.assertNotEqual(hello.reference, y_product.reference)

        def block(record, name):
            product = record.descriptor_document.product
            return instantiate_product(product, name, ProductInstanceConfiguration.from_contract(product.runtime_contract))

        blocks = (block(gateway, "gateway"), block(hello, "hello-x"))
        graph_a = compile_topology(DeploymentTopology("registered-receivers",
            DockerRuntime(runtime_id="runtime-a", children=blocks)))
        graph_b = compile_topology(DeploymentTopology("registered-receivers",
            DockerRuntime(runtime_id="runtime-a", children=(*blocks, block(y_product, y_name)))))
        # Y is an unconfigured desired receiver. Authoring owns the explicit
        # fresh wrapper installation; this does not assert running state.
        y_node = graph_b.node(y_name)
        graph_b = graph_b.update_node(replace(y_node,
            configuration_artifacts=tuple(item for item in y_node.configuration_artifacts
                if item.artifact_id != y_artifact.artifact_id),
            public_environment=tuple(item for item in y_node.public_environment
                if item.name != WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT)))

        scopes = (("gateway-self", "gateway", "control", 8000), ("hello-x", "hello-x", "internal", 8000))
        def routes(graph, members):
            intents = []
            for identity, name, socket, port in members:
                node = graph.node(name)
                self.assertEqual(node.runtime_id, "runtime-a")
                # Actual Core product materialization is the endpoint owner.
                self.assertEqual(node.endpoint(socket).url, f"http://{name}:{port}")
                intents.append(api.GatewayHealthTargetIntent(identity, api.ReceiverScope(name, socket), node.endpoint(socket).url))
            return (api.GatewayHealthRoutes(api.ReceiverScope("gateway", "control"), tuple(intents)),)

        authored = {}
        for letter, graph, members in (("a", graph_a, scopes),
                ("b", graph_b, (*scopes, (y_name, y_name, y_socket, y_port))),
                ("c", graph_a, scopes)):
            authored[letter] = api.author_receiver_graph(graph, workspace_id="workspace-a",
                context=fixture["context"], verifier_configuration=fixture["verifiers"],
                introductions=((api.ReceiverIntroduction(api.ReceiverScope(y_name, y_socket),
                    y_artifact.artifact_id, y_artifact.target_path),) if letter == "b" else ()),
                gateway_health_replacements=routes(graph, members),
                receiver_identity_factory=lambda:"c" * 32)

        documents = {}
        for letter, graph in authored.items():
            artifacts = {item.artifact_id:item for item in graph.node("gateway").configuration_artifacts}
            documents[letter] = route_codec.decode_bytes(artifacts["gateway-health-targets"].content.encode())
            def selection(identity):
                return HealthReceiverSelection("workspace-a", "graph-" + letter, "projection-" + letter,
                    PlanGraphSide.DESIRED_GRAPH, "gateway", "runtime-a", "control",
                    gateway.reference, gateway.descriptor_document, artifacts[identity])
            selected = select_gateway_self_health_binding(transit=selection("gateway-health-transit"),
                targets=selection("gateway-health-targets"), control=selection("gateway-control"))
            self.assertEqual(selected.target, fixture["gateway_target"])
            self.assertEqual(selected.origin, graph.node("gateway").endpoint("control").url)
        self.assertEqual(documents["a"], documents["c"])
        self.assertEqual({item.target_id for item in documents["a"].targets}, {"gateway-self", "hello-x"})
        self.assertEqual({item.target_id for item in documents["b"].targets}, {"gateway-self", "hello-x", y_name})
        self.assertEqual(tuple(item for item in documents["b"].targets if item.target_id != y_name), documents["a"].targets)
        y_route = next(item for item in documents["b"].targets if item.target_id == y_name)
        y_control = next(item for item in authored["b"].node(y_name).configuration_artifacts if item.artifact_id == y_artifact.artifact_id)
        selected_y = select_own_health_configuration(HealthReceiverSelection(
            "workspace-a", "graph-b", "projection-b", PlanGraphSide.DESIRED_GRAPH,
            y_name, "runtime-a", y_socket, y_product.reference, y_product.descriptor_document, y_control))
        self.assertEqual(y_route.target, selected_y.target)
        self.assertEqual(y_route.declaration, selected_y.declaration)
        self.assertEqual(y_route.origin, authored["b"].node(y_name).endpoint(y_socket).url)

    def test_variable_receiver_requests_and_installs_control_verifier(self):
        api = self.api()
        fixture = self.fixture()
        from control_plane_kit_core.receiver_configuration import (
            ReceiverNodeControlConfigurationCodec,
            select_receiver_node_control_configuration_artifact,
        )
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from test_topology_client import DeterministicIds
        from control_plane_kit_servers_cpk_server.client import TopologyClient

        path = self.root / "variable.json"
        path.write_text(
            json.dumps(GraphDescriptorCodec().encode(fixture["graph_variable"])),
            encoding="utf-8",
        )
        desired = api.AuthoredDesiredGraph(
            path,
            introductions=(
                api.ReceiverIntroduction(
                    api.ReceiverScope("hello-y", "internal"),
                    "hello-control",
                    "/etc/cpk/hello/control.json",
                ),
            ),
        )
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        client = TopologyClient(
            self.client_profile(),
            transport=transport,
            identity_factory=DeterministicIds(),
            receiver_identity_factory=lambda: "c" * 32,
        )
        client.plan(desired)

        verifier_call = next(
            call
            for call in transport.calls
            if call["route_id"] == "read.workload-verifier-configuration"
        )
        self.assertEqual(
            set(verifier_call["path_parameters"]["purposes"].split(",")),
            {
                fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_CONTROL.value,
                fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ.value,
            },
        )
        prepare = next(
            call
            for call in transport.calls
            if call["route_id"] == "command.deployment.prepare"
        )
        authored = GraphDescriptorCodec().decode(prepare["payload"]["desired_graph"])
        node = authored.node("hello-y")
        artifact = select_receiver_node_control_configuration_artifact(
            artifacts=node.configuration_artifacts,
            environment=node.public_environment + node.socket_environment,
            control_surfaces=node.block_spec.control_surfaces,
        )
        configured = ReceiverNodeControlConfigurationCodec().decode_bytes(
            artifact.content.encode("utf-8")
        )
        self.assertEqual(
            {verifier.purpose for verifier in configured.verifiers},
            {
                fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_CONTROL,
                fixture["core"].DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            },
        )

    def test_owner_coordinates_use_owner_grammars(self):
        api = self.api()
        scope = api.ReceiverScope("2Node", "API.Socket")
        continuation = api.PendingReceiverContinuation("Draft.UPPER-2", 1, (scope,))
        self.assertEqual(scope.node_id, "2Node")
        self.assertEqual(continuation.draft_id, "Draft.UPPER-2")
        with self.assertRaises(ValueError):
            api.GatewayHealthTargetIntent("UPPER", scope, "http://target:8000")

    def test_gateway_route_omission_preserves_bytes_and_explicit_empty_replaces(self):
        api = self.api()
        fixture = self.fixture()
        from control_plane_kit_core.receiver_management_routes import ReceiverManagementRoutesCodec

        preserved = api.author_receiver_graph(
            fixture["graph_a"],
            workspace_id="workspace-a",
            context=fixture["context"],
            verifier_configuration=None,
        )
        preserved_route = next(
            item
            for item in preserved.node("gateway").configuration_artifacts
            if item.artifact_id == "gateway-health-targets"
        )
        self.assertEqual(preserved_route, fixture["routes"])

        emptied = api.author_receiver_graph(
            fixture["graph_a"],
            workspace_id="workspace-a",
            context=fixture["context"],
            verifier_configuration=None,
            gateway_health_replacements=(
                api.GatewayHealthRoutes(
                    api.ReceiverScope("gateway", "control"), ()
                ),
            ),
        )
        empty_route = next(
            item
            for item in emptied.node("gateway").configuration_artifacts
            if item.artifact_id == "gateway-health-targets"
        )
        self.assertEqual(
            ReceiverManagementRoutesCodec().decode_bytes(
                empty_route.content.encode("utf-8")
            ).targets,
            (),
        )
        self.assertNotEqual(empty_route.content_digest, preserved_route.content_digest)

    def test_fresh_gateway_and_ambiguous_or_unresolved_scopes_refuse(self):
        api = self.api()
        fixture = self.fixture()
        gateway_scope = api.ReceiverScope("gateway", "control")
        without_current_gateway = {
            **fixture["context"],
            "current": {
                **fixture["context"]["current"],
                "receivers": fixture["context"]["current"]["receivers"][1:],
            },
        }
        with self.assertRaises(api.ReceiverAuthoringError):
            api.author_receiver_graph(
                fixture["graph_a"],
                workspace_id="workspace-a",
                context=without_current_gateway,
                verifier_configuration=fixture["verifiers"],
                introductions=(
                    api.ReceiverIntroduction(
                        gateway_scope,
                        "fresh-gateway-control",
                        "/etc/cpk/gateway/fresh-control.json",
                    ),
                ),
            )
        partial_x = replace(
            fixture["graph_a"].node("hello-x"), configuration_artifacts=()
        )
        with self.assertRaises(api.ReceiverAuthoringError):
            api.author_receiver_graph(
                fixture["graph_a"].update_node(partial_x),
                workspace_id="workspace-a",
                context=fixture["context"],
                verifier_configuration=None,
            )
        cases = (
            dict(
                introductions=(
                    api.ReceiverIntroduction(
                        gateway_scope,
                        "gateway-control",
                        "/etc/cpk/gateway/control.json",
                    ),
                )
            ),
            dict(
                introductions=(
                    api.ReceiverIntroduction(
                        api.ReceiverScope("hello-x", "internal"),
                        "hello-control",
                        "/etc/cpk/hello/control.json",
                    ),
                )
            ),
            dict(
                gateway_health_replacements=(
                    api.GatewayHealthRoutes(
                        gateway_scope,
                        (
                            api.GatewayHealthTargetIntent(
                                "missing",
                                api.ReceiverScope("missing", "internal"),
                                "http://missing:8000",
                            ),
                        ),
                    ),
                )
            ),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(api.ReceiverAuthoringError) as caught:
                    api.author_receiver_graph(
                        fixture["graph_a"],
                        workspace_id="workspace-a",
                        context=fixture["context"],
                        verifier_configuration=fixture["verifiers"],
                        **arguments,
                    )
                self.assertEqual(str(caught.exception), "receiver graph could not be authored")
                self.assertEqual(vars(caught.exception), {})

    def test_exact_pending_scope_installs_owner_artifact_without_key_reselection(self):
        api = self.api()
        fixture = self.fixture()
        core = fixture["core"]
        from control_plane_kit_core.configuration import (
            ConfigurationArtifact,
            ConfigurationMediaType,
        )
        from control_plane_kit_core.receiver_configuration import (
            ReceiverNodeControlConfiguration,
            ReceiverNodeControlConfigurationCodec,
        )

        y_scope = api.ReceiverScope("hello-y", "internal")
        roles = core.NodeControlGraphReferenceRole
        y_target = core.NodeControlReceiverTarget(
            core.NodeControlGraphReference(roles.WORKSPACE, "workspace-a"),
            core.NodeControlGraphReference(roles.RUNTIME, "runtime-a"),
            core.NodeControlGraphReference(roles.NODE, "hello-y"),
            core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "internal"),
            "e" * 32,
        )
        declaration = core.WorkloadNodeControlSurfaceDeclaration(
            fixture["graph_b"].node("hello-y").block_spec.control_surfaces[0],
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
        )
        x_configuration = ReceiverNodeControlConfigurationCodec().decode_bytes(
            fixture["x_wrapper"].content.encode("utf-8")
        )
        configured = ReceiverNodeControlConfiguration(
            y_target, declaration, x_configuration.verifiers
        )
        artifact = ConfigurationArtifact(
            "hello-control",
            "/etc/cpk/hello/control.json",
            ConfigurationMediaType.JSON,
            ReceiverNodeControlConfigurationCodec()
            .encode_bytes(configured)
            .decode("utf-8"),
        )
        pending_receiver = {
            "binding": {
                "workspace_id": "workspace-a",
                "graph_id": "graph-pending",
                "realized_projection_id": None,
                "runtime_id": "runtime-a",
                "node_id": "hello-y",
                "provider_socket_name": "internal",
                "receiver_id": "e" * 32,
                "selected_configuration_digest": artifact.content_digest,
                "declaration_identity": declaration.identity().value,
            },
            "configuration_artifact": artifact.descriptor(),
            "origin": {
                "introducing_graph_id": "graph-pending",
                "introducing_realized_projection_id": None,
                "introducing_action_id": "action-pending",
                "introducing_session_id": "session-pending",
                "introducing_draft_id": "draft-a",
                "first_accepted_action_id": None,
                "first_accepted_session_id": None,
            },
            "lifecycle": "pending",
        }
        context = {
            **fixture["context"],
            "pending_draft": {
                "draft_id": "draft-a",
                "head_revision": 7,
                "graph_id": "graph-pending",
                "realized_projection_id": None,
                "receivers": [pending_receiver],
            },
        }
        authored = api.author_receiver_graph(
            fixture["graph_b"],
            workspace_id="workspace-a",
            context=context,
            verifier_configuration=None,
            pending=api.PendingReceiverContinuation("draft-a", 7, (y_scope,)),
        )
        self.assertIn(artifact, authored.node("hello-y").configuration_artifacts)
        with self.assertRaises(api.ReceiverAuthoringError):
            api.author_receiver_graph(
                fixture["graph_b"],
                workspace_id="workspace-a",
                context=context,
                verifier_configuration=None,
                pending=api.PendingReceiverContinuation("draft-a", 8, (y_scope,)),
            )

    def test_cli_builds_closed_groups_and_rejects_unattached_targets(self):
        self.api()
        from control_plane_kit_servers_cpk_server.client import cli
        from control_plane_kit_servers_cpk_server.client import ClientInputError

        arguments = cli._parser().parse_args(
            [
                "--profile",
                "local",
                "plan",
                str(self.root / "desired.json"),
                "--introduce-receiver",
                "hello-y",
                "internal",
                "hello-control",
                "/etc/cpk/hello/control.json",
                "--replace-gateway-health-routes",
                "gateway",
                "control",
                "--gateway-health-target",
                "gateway",
                "control",
                "hello-y",
                "hello-y",
                "internal",
                "http://hello-y:8000",
            ]
        )
        selected = cli._authored_plan_input(arguments)
        self.assertEqual(len(selected.introductions), 1)
        self.assertEqual(len(selected.gateway_health_replacements), 1)
        self.assertEqual(len(selected.gateway_health_replacements[0].targets), 1)

        arguments.replace_gateway_health_routes = []
        with self.assertRaises(ClientInputError):
            cli._authored_plan_input(arguments)

    def authored_input(self, api, fixture, name="desired.json"):
        from control_plane_kit_core.topology import GraphDescriptorCodec

        path = self.root / name
        path.write_text(
            json.dumps(GraphDescriptorCodec().encode(fixture["graph_b"])),
            encoding="utf-8",
        )
        y_scope = api.ReceiverScope("hello-y", "internal")
        return api.AuthoredDesiredGraph(
            path,
            introductions=(
                api.ReceiverIntroduction(
                    y_scope, "hello-control", "/etc/cpk/hello/control.json"
                ),
            ),
            gateway_health_replacements=(
                api.GatewayHealthRoutes(
                    api.ReceiverScope("gateway", "control"),
                    (
                        api.GatewayHealthTargetIntent(
                            "gateway-self", api.ReceiverScope("gateway", "control"),
                            fixture["graph_b"].node("gateway").endpoint("control").url,
                        ),
                        api.GatewayHealthTargetIntent(
                            "hello-x",
                            api.ReceiverScope("hello-x", "internal"),
                            fixture["graph_b"].node("hello-x").endpoint("internal").url,
                        ),
                        api.GatewayHealthTargetIntent(
                            "hello-y", y_scope, fixture["graph_b"].node("hello-y").endpoint("internal").url
                        ),
                    ),
                ),
            ),
        )

    def client_profile(self, state="state"):
        from control_plane_kit_servers_cpk_server.client import ClientProfile

        credentials = {
            role: self.root / f"{role}.token"
            for role in ("operator", "approver", "worker")
        }
        return ClientProfile(
            "https://cpk.example", "workspace-a", credentials, self.root / state
        )

    def authoring_transport(self, fixture, *, lose_prepare_once=True):
        from test_topology_client import ScriptedTransport
        from control_plane_kit_operations.read_services.models import FocusedDetailReadModel

        class AuthoringTransport(ScriptedTransport):
            def call(inner, route_id, *, path_parameters, payload, credential_role):
                if route_id == "read.receiver-authoring-context":
                    inner.calls.append(
                        {
                            "route_id": route_id,
                            "path_parameters": dict(path_parameters),
                            "payload": dict(payload),
                            "credential_role": credential_role,
                        }
                    )
                    return fixture["context"]
                if route_id == "read.workload-verifier-configuration":
                    inner.calls.append(
                        {
                            "route_id": route_id,
                            "path_parameters": dict(path_parameters),
                            "payload": dict(payload),
                            "credential_role": credential_role,
                        }
                    )
                    if hasattr(inner, "verifier_response"):
                        return inner.verifier_response
                    return FocusedDetailReadModel(
                        workspace_id="workspace-a",
                        kind="workload-verifier-configuration",
                        payload=fixture["verifiers"],
                    ).descriptor()
                if route_id == "command.deployment.prepare" and hasattr(
                    inner, "before_prepare"
                ):
                    inner.before_prepare(payload)
                return super().call(
                    route_id,
                    path_parameters=path_parameters,
                    payload=payload,
                    credential_role=credential_role,
                )

        return AuthoringTransport(lose_prepare_once=lose_prepare_once)

    def test_client_accepts_flat_owner_verifier_descriptor(self):
        api = self.api()
        fixture = self.fixture()
        desired = self.authored_input(api, fixture)
        original = desired.path.read_bytes()
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        from control_plane_kit_servers_cpk_server.client import TopologyClient

        generated = []
        client = TopologyClient(self.client_profile(), transport=transport,
            receiver_identity_factory=lambda: generated.append(True) or "c" * 32)
        result = client.plan(desired)
        self.assertEqual(result.status, "planned")
        self.assertEqual(generated, [True])
        self.assertEqual(desired.path.read_bytes(), original)
        self.assertEqual(sum(call["route_id"] == "command.deployment.prepare"
            for call in transport.calls), 1)

    def test_invalid_verifier_response_field_refuses_before_identity_or_prepare(self):
        api = self.api()
        fixture = self.fixture()
        desired = self.authored_input(api, fixture)
        envelope = {"workspace_id": "workspace-a", "kind": "workload-verifier-configuration"}
        invalid = (
            envelope,
            {**envelope, "workload_verifier_configuration": None},
            {**envelope, "workload_verifier_configuration": []},
            {**envelope, "workload_verifier_configuration": "invalid"},
            {**envelope, "payload": fixture["verifiers"]},
        )
        from control_plane_kit_servers_cpk_server.client import ClientInputError, TopologyClient

        for number, response in enumerate(invalid):
            with self.subTest(response=number):
                transport = self.authoring_transport(fixture, lose_prepare_once=False)
                transport.verifier_response = response
                generated = []
                client = TopologyClient(self.client_profile(state=f"invalid-{number}"),
                    transport=transport,
                    receiver_identity_factory=lambda: generated.append(True) or "c" * 32)
                with self.assertRaises(ClientInputError):
                    client.plan(desired)
                self.assertEqual(generated, [])
                self.assertNotIn("command.deployment.prepare",
                    [call["route_id"] for call in transport.calls])

    def test_retained_only_client_authoring_needs_no_verifier_read_or_identity(self):
        api = self.api()
        fixture = self.fixture()
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_servers_cpk_server.client import TopologyClient

        codec = GraphDescriptorCodec()
        from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
        application = ConfigurationArtifact("palette-data", "/etc/app/colors.json",
            ConfigurationMediaType.JSON, '{"colors":["teal","coral"]}')
        nodes = dict(fixture["graph_a"].nodes)
        nodes["hello-x"] = replace(nodes["hello-x"],
            configuration_artifacts=(*nodes["hello-x"].configuration_artifacts, application))
        desired = replace(fixture["graph_a"], nodes=nodes)
        source = self.root / "retained.json"
        source.write_text(json.dumps(codec.encode(desired)), encoding="utf-8")
        original = source.read_bytes()
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        generated = []
        client = TopologyClient(self.client_profile(), transport=transport,
            receiver_identity_factory=lambda: generated.append(True) or "c" * 32)
        result = client.plan(api.AuthoredDesiredGraph(source))
        self.assertEqual(result.status, "planned")
        self.assertEqual(generated, [])
        self.assertNotIn("read.workload-verifier-configuration",
            [call["route_id"] for call in transport.calls])
        preparation, = (call for call in transport.calls
            if call["route_id"] == "command.deployment.prepare")
        prepared = codec.decode(preparation["payload"]["desired_graph"])
        for name in ("gateway", "hello-x"):
            self.assertEqual(
                {item.artifact_id: item for item in prepared.node(name).configuration_artifacts},
                {item.artifact_id: item for item in desired.node(name).configuration_artifacts})
        self.assertEqual(source.read_bytes(), original)

    def test_client_persists_before_send_and_restart_replays_exact_authored_graph(self):
        api = self.api()
        fixture = self.fixture()
        desired = self.authored_input(api, fixture)
        transport = self.authoring_transport(fixture)
        from test_topology_client import DeterministicIds
        from control_plane_kit_servers_cpk_server.client import TopologyClient
        from control_plane_kit_servers_cpk_server.client.journal import (
            PREPARATION_JOURNAL_SCHEMA,
        )

        receiver_calls = []
        client = TopologyClient(
            self.client_profile(),
            transport=transport,
            identity_factory=DeterministicIds(),
            receiver_identity_factory=lambda: receiver_calls.append("generated") or "c" * 32,
        )
        operation_ref = "00000000-0000-4000-8000-000000000001"

        def verify_persisted_before_dispatch(payload):
            journal = client.journal.read(operation_ref)
            preparation = journal["preparation"]
            artifact = client.journal.root / preparation["name"]
            self.assertEqual(journal["schema"], PREPARATION_JOURNAL_SCHEMA)
            self.assertEqual(
                journal["pending_request"]["route_id"],
                "command.deployment.prepare",
            )
            self.assertEqual(
                json.loads(artifact.read_text(encoding="utf-8")),
                payload["desired_graph"],
            )

        transport.before_prepare = verify_persisted_before_dispatch
        unresolved = client.plan(desired)
        journal = client.journal.read(unresolved.operation_ref)
        preparation = journal["preparation"]
        artifact = client.journal.root / preparation["name"]
        first_prepare = next(
            call
            for call in transport.calls
            if call["route_id"] == "command.deployment.prepare"
        )

        self.assertEqual(unresolved.status, "attention-required")
        self.assertEqual(journal["schema"], PREPARATION_JOURNAL_SCHEMA)
        self.assertEqual(receiver_calls, ["generated"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(os.stat(artifact).st_mode & 0o777, 0o600)
        self.assertEqual(
            json.loads(artifact.read_text(encoding="utf-8")),
            first_prepare["payload"]["desired_graph"],
        )

        def regenerated():
            raise AssertionError("restart must not regenerate identities")

        restarted = TopologyClient(
            self.client_profile(),
            transport=transport,
            identity_factory=regenerated,
            receiver_identity_factory=regenerated,
        )
        resumed = restarted.resume_prepare(unresolved.operation_ref)
        prepare_calls = [
            call
            for call in transport.calls
            if call["route_id"] == "command.deployment.prepare"
        ]
        self.assertEqual(resumed.status, "planned")
        self.assertEqual(prepare_calls, [first_prepare, first_prepare])
        self.assertEqual(
            [call["route_id"] for call in transport.calls].count(
                "read.receiver-authoring-context"
            ),
            1,
        )
        self.assertEqual(
            [call["route_id"] for call in transport.calls].count(
                "read.workload-verifier-configuration"
            ),
            1,
        )

    def test_context_expectation_mismatch_refuses_before_keys_identity_or_dispatch(self):
        api = self.api()
        fixture = self.fixture()
        desired = self.authored_input(api, fixture)
        fixture["context"]["expectation"] = {
            **fixture["context"]["expectation"],
            "desired_graph_revision": 9,
        }
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        from test_topology_client import DeterministicIds
        from control_plane_kit_servers_cpk_server.client import ClientInputError, TopologyClient

        generated = []
        client = TopologyClient(
            self.client_profile(),
            transport=transport,
            identity_factory=DeterministicIds(),
            receiver_identity_factory=lambda: generated.append(True) or "c" * 32,
        )
        with self.assertRaises(ClientInputError):
            client.plan(desired)
        self.assertEqual(generated, [])
        self.assertNotIn(
            "read.workload-verifier-configuration",
            [call["route_id"] for call in transport.calls],
        )
        self.assertNotIn(
            "command.deployment.prepare",
            [call["route_id"] for call in transport.calls],
        )

    def test_preparation_persistence_failure_never_dispatches(self):
        api = self.api()
        fixture = self.fixture()
        desired = self.authored_input(api, fixture)
        transport = self.authoring_transport(fixture, lose_prepare_once=False)
        from test_topology_client import DeterministicIds
        from control_plane_kit_servers_cpk_server.client import (
            JournalError,
            JournalStore,
            TopologyClient,
        )

        class FailingPreparationStore(JournalStore):
            def create_preparation(self, operation_ref, raw):
                raise JournalError("prepared graph could not be persisted")

        client = TopologyClient(
            self.client_profile(),
            transport=transport,
            journal=FailingPreparationStore(self.root / "failed-state"),
            identity_factory=DeterministicIds(),
            receiver_identity_factory=lambda: "c" * 32,
        )
        with self.assertRaises(JournalError):
            client.plan(desired)
        self.assertNotIn(
            "command.deployment.prepare",
            [call["route_id"] for call in transport.calls],
        )

    def test_retry_refuses_source_drift_and_missing_or_corrupt_preparation(self):
        api = self.api()
        fixture = self.fixture()
        from test_topology_client import DeterministicIds
        from control_plane_kit_servers_cpk_server.client import JournalError, TopologyClient

        for damage in ("source", "missing", "corrupt"):
            with self.subTest(damage=damage):
                desired = self.authored_input(api, fixture, f"{damage}.json")
                transport = self.authoring_transport(fixture)
                client = TopologyClient(
                    self.client_profile(state=f"state-{damage}"),
                    transport=transport,
                    identity_factory=DeterministicIds(),
                    receiver_identity_factory=lambda: "d" * 32,
                )
                unresolved = client.plan(desired)
                journal = client.journal.read(unresolved.operation_ref)
                artifact = client.journal.root / journal["preparation"]["name"]
                if damage == "source":
                    desired.path.write_text("{}", encoding="utf-8")
                    refused = client.resume_prepare(unresolved.operation_ref)
                    self.assertEqual(refused.status, "attention-required")
                elif damage == "missing":
                    artifact.unlink()
                    with self.assertRaises(JournalError):
                        client.resume_prepare(unresolved.operation_ref)
                else:
                    artifact.write_bytes(b"{}")
                    with self.assertRaises(JournalError):
                        client.resume_prepare(unresolved.operation_ref)
                self.assertEqual(
                    [
                        call
                        for call in transport.calls
                        if call["route_id"] == "command.deployment.prepare"
                    ][0:1],
                    [
                        call
                        for call in transport.calls
                        if call["route_id"] == "command.deployment.prepare"
                    ],
                )


if __name__ == "__main__":
    unittest.main()
