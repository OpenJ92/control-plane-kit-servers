from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path
import unittest

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.operations.lifecycle import (
    ActivityEventKind, ActivityRunStatus, ExecutionRequestStatus,
)
from control_plane_kit_core.planning import (
    ActivityId, ActivityPlan, NodeTarget, PlannedActivity, StartNode,
)
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductInstanceConfiguration, instantiate_product,
)
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference,
    NamedPublicIngress,
    PublicIngressTarget,
)
from control_plane_kit_core.runtime_authority import (
    RuntimeAuthorityAccessDelivery,
    RuntimeAuthorityAccessDeliveryKind,
    RuntimeAuthorityReference,
)
from control_plane_kit_core.secrets import (
    SecretFileDelivery,
    SecretProviderEndpointReference,
    SecretReference,
)
from control_plane_kit_core.topology import DeploymentGraph, GraphDescriptorCodec, compile_topology
from control_plane_kit_operations.coordinator import ActivityRealizationContext
from control_plane_kit_operations.execution_leases import ExecutionLeaseFence
from control_plane_kit_operations.lifecycle import ExecutionWorkerAuthority
from control_plane_kit_operations.products import InlineDescriptorSource, RegisteredProduct
from control_plane_kit_operations.records import (
    ActivityEventRecord, ActivityPlanRecord, ActivityPlanStatus, ActivityRunRecord,
    AdmittedRun, ClaimIdentity, ExecutionIdempotency, ExecutionRequestIdentity,
    ExecutionRequestRecord, GraphVersionRecord, RealizedGraphProjectionRecord,
    RetryIdentity,
)
from control_plane_kit_operations.runtime_effects import runtime_effect_request_for_context


ROOT = Path(__file__).resolve().parents[3]


class DockerInstallationTests(unittest.TestCase):
    def api(self):
        name = "control_plane_kit_servers_cpk_server.installation"
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise
            self.fail("shared Docker CPK installation composition is not implemented")

    def installation(self, api, identity="child-a"):
        def document(product, filename="product.cpk.json"):
            return ProductDescriptorCodec().decode_document(
                (ROOT / "products" / product / filename).read_bytes()
            )

        return api.DockerCpkInstallation(
            installation_id=identity,
            workspace_id="parent-workspace",
            runtime_authority=RuntimeAuthorityReference("parent-docker"),
            runtime_access=RuntimeAuthorityAccessDelivery(
                RuntimeAuthorityReference("parent-docker"),
                RuntimeAuthorityAccessDeliveryKind.LOCAL_DOCKER_SOCKET_MOUNT,
            ),
            cpk_product=document("cpk_server", "product.docker-cloudflare.cpk.json"),
            postgres_product=document("postgres_server"),
            secrets_product=document("secrets_server"),
            control_credential=SecretReference(f"secret://parent/{identity}/control"),
            postgres_password=SecretReference(f"secret://parent/{identity}/postgres"),
            custody_root_key=SecretReference(f"secret://parent/{identity}/custody"),
            provider_credentials_document=SecretReference(
                f"secret://parent/{identity}/provider-credentials"
            ),
            provider_client_credential=SecretReference(
                f"secret://parent/{identity}/provider-client"
            ),
            workspace_grants=(
                WorkspaceGrant("child-workspace", (PolicyScope.INSTANCE_WORKSPACE_READ,)),
            ),
            provider_endpoint_ref=SecretProviderEndpointReference("child-provider"),
            provider_bootstrap_credential_ref=SecretReference(
                "secret://child/provider-bootstrap"
            ),
            ingress=NamedPublicIngress(
                ingress_id=f"{identity}-public",
                authority_ref=IngressAuthorityReference("parent-cloudflare"),
                target=PublicIngressTarget(f"{identity}-cpk", "http-api"),
                connector_node_id=f"{identity}-connector",
                hostname=f"{identity}.example.test",
            ),
            connector_product=document("cloudflared_connector"),
        )

    def test_named_installation_composes_real_products_and_reference_deliveries(self):
        api = self.api()
        desired = self.installation(api)
        topology = api.compose_docker_cpk_installation(desired)
        graph = compile_topology(topology)
        self.assertEqual(set(graph.nodes), {
            "child-a-cpk", "child-a-postgres", "child-a-secrets", "child-a-connector",
        })
        self.assertEqual({
            (edge.provider_role, edge.provider_socket, edge.consumer_role,
             edge.requirement_socket) for edge in graph.edges.values()
        }, {
            ("child-a-postgres", "postgres", "child-a-cpk", requirement)
            for requirement in ("workplace-store", "activity-history-store",
                                "observer-state-store", "graph-topology-store")
        })
        self.assertEqual(topology.root.authority_ref, desired.runtime_authority)
        self.assertEqual(topology.public_ingresses, (desired.ingress,))
        blocks = {child.block_id: child for child in topology.root.children
                  if hasattr(child, "block_id")}
        for role, selected in (("cpk", desired.cpk_product),
                               ("postgres", desired.postgres_product),
                               ("secrets", desired.secrets_product)):
            product = blocks[f"child-a-{role}"].implementation.document.product
            self.assertEqual(product.image, selected.product.image)
            self.assertNotEqual(product.identity, selected.product.identity)
            self.assertEqual(product.runtime_contract.retained_data_mounts,
                             selected.product.runtime_contract.retained_data_mounts)
            self.assertEqual(product.runtime_contract.lifecycle,
                             selected.product.runtime_contract.lifecycle)
        cpk = graph.node("child-a-cpk")
        environment = cpk.non_secret_environment()
        self.assertEqual(json.loads(environment["CPK_MATERIAL_PROVIDER_ROUTES_JSON"]),
                         {"child-provider": "http://child-a-secrets:8081"})
        files = json.loads(environment["CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON"])
        (client_delivery,) = tuple(value for value in cpk.secret_deliveries
                                   if isinstance(value, SecretFileDelivery))
        self.assertEqual(files, {desired.provider_bootstrap_credential_ref.reference_id:
                                 client_delivery.target_path})
        self.assertEqual(client_delivery.reference, desired.provider_client_credential)
        self.assertEqual(json.loads(environment["CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON"]),
                         {"child-workspace": ["instance:workspace:read"]})
        self.assertNotIn("CPK_CONTROL_AUTH_STATIC_CREDENTIAL", environment)
        cpk_secrets = {value.environment_name: value.reference
                       for value in cpk.secret_deliveries
                       if hasattr(value, "environment_name")}
        self.assertEqual(cpk_secrets["CPK_CONTROL_AUTH_STATIC_CREDENTIAL"],
                         desired.control_credential)
        self.assertEqual(cpk_secrets["PGPASSWORD"], desired.postgres_password)
        custody = graph.node("child-a-secrets").secret_deliveries
        self.assertEqual({value.intent.value: value.reference for value in custody}, {
            "secrets.custody-root-key": desired.custody_root_key,
            "secrets.provider-credentials-document": desired.provider_credentials_document,
        })
        self.assertTrue(all(isinstance(value, SecretFileDelivery)
                            and value.file_mode.value == "0400" for value in custody))
        self.assertEqual({value.path_binding.environment_name for value in custody},
                         {"CPK_SECRETS_MASTER_KEY_FILE", "CPK_SECRETS_CREDENTIALS_FILE"})
        postgres = graph.node("child-a-postgres")
        self.assertEqual(postgres.secret_deliveries[0].reference, desired.postgres_password)
        self.assertEqual(postgres.block_spec.verification.checks[0].authentication.password_reference,
                         desired.postgres_password)

    def test_composed_secrets_files_reach_runtime_material_once(self):
        api = self.api()
        desired = self.installation(api)
        composed = api.compose_docker_cpk_installation(desired)
        blocks = tuple(child for child in composed.root.children
                       if hasattr(child, "block_id"))
        secrets = next(child for child in blocks
                       if child.block_id == desired.secrets_node_id)
        documents = tuple(child.implementation.document for child in blocks)
        product = secrets.implementation.document.product
        defaults = ProductInstanceConfiguration.from_contract(product.runtime_contract)

        for substituted in (False, True):
            with self.subTest(substituted=substituted):
                configuration = defaults
                topology = composed
                if substituted:
                    configuration = replace(defaults, secret_deliveries=tuple(
                        replace(value, reference=SecretReference(
                            "secret://configured/child-a/" + value.target_path.rsplit("/", 1)[1],
                        )) for value in reversed(defaults.secret_deliveries)
                    ))
                    selected = instantiate_product(
                        product, desired.secrets_node_id, configuration,
                    )
                    self.assertEqual(selected.implementation.document.content,
                                     secrets.implementation.document.content)
                    topology = replace(composed, root=replace(
                        composed.root, children=tuple(
                            selected if child is secrets else child
                            for child in composed.root.children
                        ),
                    ))
                graph = compile_topology(topology)
                context = _runtime_context(
                    graph, documents, desired.workspace_id, desired.secrets_node_id,
                )

                request = runtime_effect_request_for_context(context)

                self.assertEqual(len(request.products), 1)
                material = request.products[0]
                self.assertEqual(material.node_id, desired.secrets_node_id)
                self.assertEqual(material.product.runtime_contract.secret_deliveries,
                                 configuration.secret_deliveries)

    def test_only_cpk_instance_declares_runtime_access(self):
        api = self.api()
        for identity in ("child-a", "second-controller"):
            with self.subTest(installation=identity):
                desired = self.installation(api, identity)
                topology = api.compose_docker_cpk_installation(desired)
                graph = compile_topology(topology)
                blocks = {child.block_id: child for child in topology.root.children
                          if hasattr(child, "block_id")}
                self.assertEqual(len(blocks), 4)
                for node_id, block in blocks.items():
                    expected = (desired.runtime_access,) if node_id == desired.cpk_node_id else ()
                    self.assertEqual(block.implementation.configuration.runtime_authority_deliveries,
                                     expected, node_id)
                    self.assertEqual(graph.node(node_id).runtime_authority_deliveries, expected, node_id)
                self.assertEqual(graph.node(desired.cpk_node_id).runtime_authority_deliveries[0].authority_ref,
                                 topology.root.authority_ref)

    def test_permission_roundtrip_and_removal_preserve_product_identity(self):
        api = self.api()
        desired = self.installation(api)
        topology = api.compose_docker_cpk_installation(desired)
        graph = compile_topology(topology)
        codec = GraphDescriptorCodec()
        decoded = codec.decode(codec.encode(graph))
        self.assertEqual(decoded.node(desired.cpk_node_id).runtime_authority_deliveries,
                         (desired.runtime_access,))
        blocks = tuple(child for child in topology.root.children if hasattr(child, "block_id"))
        cpk = next(child for child in blocks if child.block_id == desired.cpk_node_id)
        empty = replace(cpk, implementation=replace(cpk.implementation,
            configuration=replace(cpk.implementation.configuration, runtime_authority_deliveries=())))
        without = replace(topology, root=replace(topology.root,
            children=tuple(empty if child is cpk else child for child in topology.root.children)))
        empty_graph = compile_topology(without)
        self.assertNotEqual(codec.encode(empty_graph), codec.encode(graph))
        self.assertEqual(empty.implementation.document, cpk.implementation.document)
        self.assertEqual(empty_graph.node(desired.cpk_node_id).metadata,
                         graph.node(desired.cpk_node_id).metadata)
        self.assertTrue(all(node.runtime_authority_deliveries == ()
                            for node in codec.decode(codec.encode(empty_graph)).nodes.values()))
        self.assertNotIn("runtime_authority_deliveries", json.dumps(codec.encode(empty_graph)))

    def test_runtime_access_must_match_enclosing_authority(self):
        api = self.api()
        desired = self.installation(api)
        with self.assertRaises(ValueError):
            api.compose_docker_cpk_installation(replace(desired,
                runtime_access=replace(desired.runtime_access,
                    authority_ref=RuntimeAuthorityReference("other-docker"))))

    def test_stable_identity_codec_roundtrip_and_external_ingress_boundary(self):
        api = self.api()
        desired = self.installation(api)
        graph = compile_topology(api.compose_docker_cpk_installation(desired))
        self.assertEqual(graph, compile_topology(api.compose_docker_cpk_installation(desired)))
        codec = GraphDescriptorCodec()
        self.assertEqual(codec.decode(codec.encode(graph)), graph)
        second = self.installation(api, "child-b")
        second_graph = compile_topology(api.compose_docker_cpk_installation(second))
        self.assertTrue(set(graph.nodes).isdisjoint(second_graph.nodes))
        same_contract = replace(desired, installation_id="child-b", ingress=second.ingress)
        reused = compile_topology(api.compose_docker_cpk_installation(same_contract))
        self.assertEqual(graph.node("child-a-secrets").metadata["product_identity"],
                         reused.node("child-b-secrets").metadata["product_identity"])
        changed = replace(desired, postgres_password=SecretReference("secret://parent/changed/postgres"))
        changed_graph = compile_topology(api.compose_docker_cpk_installation(changed))
        self.assertNotEqual(graph.node("child-a-postgres").metadata["product_identity"],
                            changed_graph.node("child-a-postgres").metadata["product_identity"])
        external = replace(desired, ingress=api.ExternalInstallationIngress(
            "https://root.example.test"), connector_product=None)
        root = api.compose_docker_cpk_installation(external)
        self.assertEqual(root.public_ingresses, ())
        self.assertEqual(set(compile_topology(root).nodes),
                         {"child-a-cpk", "child-a-postgres", "child-a-secrets"})
        self.assertEqual(external.runtime_access, desired.runtime_access)
        with self.assertRaises(FrozenInstanceError):
            desired.installation_id = "changed"

    def test_rejects_incomplete_or_contradictory_installation_inputs(self):
        api = self.api()
        desired = self.installation(api)
        for changes in (
            {"control_credential": "raw-credential-is-not-a-reference"},
            {"workspace_grants": ()},
            {"workspace_grants": (WorkspaceGrant("*", (PolicyScope.PLAN_EXECUTE,)),)},
            {"connector_product": None},
            {"ingress": replace(desired.ingress, target=PublicIngressTarget("other", "http-api"))},
            {"postgres_product": desired.secrets_product},
            {"installation_id": "../not-a-docker-alias"},
        ):
            with self.subTest(fields=tuple(changes)), self.assertRaises((TypeError, ValueError)):
                api.compose_docker_cpk_installation(replace(desired, **changes))


def _runtime_context(graph, documents, workspace_id, node_id):
    """Supply public pinned inputs to translation without executing an effect."""
    activity = PlannedActivity(ActivityId("start-secrets"), StartNode(NodeTarget(node_id)))
    plan = ActivityPlan((activity,))
    timestamp = "2026-09-12T08:00:00Z"

    def projection(identity, value, version):
        return RealizedGraphProjectionRecord.identity_for_authored(
            authored_record=GraphVersionRecord.from_graph(
                graph_id=identity, workspace_id=workspace_id, version=version,
                graph=value, created_by="operator", created_at=timestamp,
            ),
        )

    return ActivityRealizationContext(
        activity=activity,
        request=ExecutionRequestRecord(
            ExecutionRequestIdentity("request", workspace_id, "session", "plan"),
            ExecutionRequestStatus.CLAIMED, "operator", timestamp,
            "approval-request", "approval-decision",
            ExecutionIdempotency("execute", "fingerprint"),
            ClaimIdentity("worker", 1, timestamp, "2026-09-12T09:00:00Z"),
        ),
        run=ActivityRunRecord(
            "run", "plan", AdmittedRun("request"), RetryIdentity(1),
            ActivityRunStatus.RUNNING, timestamp, started_at=timestamp,
        ),
        plan_record=ActivityPlanRecord(
            "plan", "session", "base", "desired", ActivityPlanStatus.PLANNED,
            timestamp, plan,
        ),
        base_graph=projection("base", DeploymentGraph(graph.name), 1),
        desired_graph=projection("desired", graph, 2),
        registered_products=tuple(RegisteredProduct.from_document(
            workspace_id=workspace_id, descriptor_document=document,
            source=InlineDescriptorSource(), imported_by="operator", imported_at=timestamp,
        ) for document in documents),
        authority=ExecutionWorkerAuthority("worker", (PolicyScope.EXECUTION_OPERATE,)),
        fence=ExecutionLeaseFence("worker", 1),
        intent_event=ActivityEventRecord(
            "intent", "run", 1, ActivityEventKind.STEP_STARTED, timestamp,
            activity_id=activity.activity_id.value,
        ),
    )


if __name__ == "__main__":
    unittest.main()
