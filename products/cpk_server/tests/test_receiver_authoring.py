"""#238 complete receiver graph authoring and exact local preparation laws."""

from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import re
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
            GatewayHealthRelayConfiguration,
            GatewayHealthTargetBinding,
            gateway_health_relay_configuration_artifact,
        )
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
        gateway_declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                gateway_target.provider_socket_name,
                (),
                health_reads=(core.NodeHealthReadKind.READINESS,),
            ),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
        )
        hello_declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                x_target.provider_socket_name,
                (),
                health_reads=(
                    core.NodeHealthReadKind.LIVENESS,
                    core.NodeHealthReadKind.READINESS,
                ),
            ),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
        )
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
            GatewayHealthRelayConfiguration(
                gateway_target,
                (
                    GatewayHealthTargetBinding(
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

        def receiver(binding_target, artifact):
            return {
                "binding": {
                    "workspace_id": "workspace-a",
                    "graph_id": "graph-a",
                    "realized_projection_id": "projection-a",
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
            "current_graph_id": "graph-a",
            "current_realized_projection_id": "projection-a",
            "desired_graph_id": None,
            "desired_realized_projection_id": None,
            "desired_graph_revision": 0,
        }
        context = {
            "profile": "receiver-authoring-context.v1",
            "workspace_id": "workspace-a",
            "expectation": expectation,
            "current": {
                "graph_id": "graph-a",
                "realized_projection_id": "projection-a",
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
        from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
            decode_gateway_health_relay_configuration,
        )

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
                            "hello-x",
                            api.ReceiverScope("hello-x", "internal"),
                            "http://hello-x:8000",
                        ),
                        api.GatewayHealthTargetIntent(
                            "hello-y", y_scope, "http://hello-y:8000"
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
        route = decode_gateway_health_relay_configuration(
            route_artifact.content.encode("utf-8")
        )
        routed_y = next(item for item in route.targets if item.target_id == "hello-y")
        self.assertEqual(routed_y.target, y_configuration.target)
        self.assertEqual(route.gateway_target, fixture["gateway_target"])
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

    def test_gateway_route_omission_preserves_bytes_and_explicit_empty_replaces(self):
        api = self.api()
        fixture = self.fixture()
        from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
            decode_gateway_health_relay_configuration,
        )

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
            decode_gateway_health_relay_configuration(
                empty_route.content.encode("utf-8")
            ).targets,
            (),
        )
        self.assertNotEqual(empty_route.content_digest, preserved_route.content_digest)

    def test_fresh_gateway_and_ambiguous_or_unresolved_scopes_refuse(self):
        api = self.api()
        fixture = self.fixture()
        gateway_scope = api.ReceiverScope("gateway", "control")
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


if __name__ == "__main__":
    unittest.main()
