from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path
import unittest

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
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
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology


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
                RuntimeAuthorityReference("child-docker-access"),
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


if __name__ == "__main__":
    unittest.main()
