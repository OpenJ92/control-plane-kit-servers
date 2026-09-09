from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.runtime_authority import (
    RuntimeAuthorityAccessDeliveryCodec, RuntimeAuthorityReference,
)
from control_plane_kit_core.secrets import (
    SecretEnvironmentDelivery, SecretFileDelivery,
    SecretProviderEndpointReference, SecretReference,
)
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology


ROOT = Path(__file__).resolve().parents[3]
DRIVER = "sha256:" + "a" * 64


def installation_input():
    def product(directory, filename="product.cpk.json"):
        return json.loads((ROOT / "products" / directory / filename).read_text())

    return {
        "schema": "cpk.root-bootstrap.input.v1",
        "installation": {
            "installation_id": "root-a", "workspace_id": "root-workspace",
            "runtime_authority": "external-root-docker",
            "runtime_access": {
                "authority_ref": {"reference_id": "root-docker-access"},
                "delivery_kind": "local-docker-socket-mount",
                "secret_references": [],
            },
            "products": {
                "cpk": product("cpk_server", "product.docker-cloudflare.cpk.json"),
                "postgres": product("postgres_server"),
                "secrets": product("secrets_server"),
            },
            "references": {
                "control_credential": "secret://bootstrap/root-a/control",
                "postgres_password": "secret://bootstrap/root-a/postgres",
                "custody_root_key": "secret://bootstrap/root-a/custody",
                "provider_credentials_document": "secret://bootstrap/root-a/grants",
                "provider_client_credential": "secret://bootstrap/root-a/client",
                "provider_bootstrap_credential_ref": "secret://control-plane-kit/bootstrap/client",
            },
            "workspace_grants": [{"workspace_id": "root-workspace", "scopes": [
                "hub:instance:create", "instance:workspace:read", "instance:workspace:edit",
                "runtime-authority:register", "runtime-authority:read",
                "runtime-authority-delivery:register", "runtime-authority-delivery:read",
                "secret-provider:register", "secret-provider:read",
            ]}],
            "provider_endpoint_ref": "root-provider",
            "external_endpoint": "https://root.example.test",
        },
        "host_binding": {"address": "127.0.0.1", "port": 18080},
        "setup": {
            "workspace_name": "Root workspace",
            "provider": {
                "provider_id": "control-plane-kit",
                "allowed_reference_prefixes": ["secret://control-plane-kit/root-workspace"],
                "allowed_intents": ["postgres.password", "application.control-token"],
            },
            "secret_references": [],
            "image_pull_authorities": [],
            "ingress_authorities": [],
        },
    }


class RootBootstrapTests(unittest.TestCase):
    def api(self):
        name = "control_plane_kit_servers_cpk_server.bootstrap"
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise
            self.fail("root bootstrap public interface is not implemented")

    def test_saved_plan_preserves_graph_and_refuses_projection_or_driver_drift(self):
        api = self.api()
        document = installation_input()
        plan = api.plan_root_bootstrap(document, driver_image_id=DRIVER)
        self.assertEqual(plan, api.plan_root_bootstrap(document, driver_image_id=DRIVER))
        from control_plane_kit_servers_cpk_server.installation import (
            DockerCpkInstallation, ExternalInstallationIngress, compose_docker_cpk_installation,
        )
        value = document["installation"]
        products = {name: ProductDescriptorCodec().decode_document(content)
                    for name, content in value["products"].items()}
        expected = DockerCpkInstallation(
            installation_id=value["installation_id"], workspace_id=value["workspace_id"],
            runtime_authority=RuntimeAuthorityReference(value["runtime_authority"]),
            runtime_access=RuntimeAuthorityAccessDeliveryCodec().decode(value["runtime_access"]),
            cpk_product=products["cpk"], postgres_product=products["postgres"],
            secrets_product=products["secrets"],
            workspace_grants=tuple(WorkspaceGrant(grant["workspace_id"],
                tuple(PolicyScope(scope) for scope in grant["scopes"]))
                for grant in value["workspace_grants"]),
            provider_endpoint_ref=SecretProviderEndpointReference(value["provider_endpoint_ref"]),
            ingress=ExternalInstallationIngress(value["external_endpoint"]), connector_product=None,
            **{name: SecretReference(reference) for name, reference in value["references"].items()},
        )
        topology = compose_docker_cpk_installation(expected)
        graph = compile_topology(topology)
        self.assertEqual(plan["graph"], GraphDescriptorCodec().encode(graph))
        self.assertEqual(plan["driver_image_id"], DRIVER)
        self.assertEqual(plan["resources"]["network"]["name"], topology.root.network_name)
        self.assertEqual(set(plan["required_material"]), {
            delivery.reference.reference_id for node in graph.nodes.values()
            for delivery in node.secret_deliveries
            if isinstance(delivery, (SecretEnvironmentDelivery, SecretFileDelivery))
        })
        self.assertEqual(plan["external_endpoint"], "https://root.example.test")
        self.assertNotIn("credential_value", json.dumps(plan))
        altered = copy.deepcopy(plan)
        altered["resources"]["network"]["name"] = "unrelated-network"
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for candidate, driver, reason in (
                (altered, DRIVER, "plan"), (plan, "sha256:" + "b" * 64, "driver"),
            ):
                with self.subTest(driver=driver, changed=candidate is altered):
                    with self.assertRaises(api.RootBootstrapError) as caught:
                        api.apply_root_bootstrap(
                            candidate, expected_digest=plan["digest"], driver_image_id=driver,
                            index_path=state / "absent.json", state_directory=state)
                    self.assertIn(reason, str(caught.exception).lower())
            self.assertFalse((state / "receipt.json").exists())

    def test_permissive_material_is_refused_before_acquisition_and_redacted(self):
        api = self.api()
        plan = api.plan_root_bootstrap(installation_input(), driver_image_id=DRIVER)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            secret = "must-not-appear-in-bootstrap-output"
            for position, reference in enumerate(plan["required_material"]):
                path = root / f"material-{position}"
                path.write_text(secret)
                path.chmod(0o400)
                files[reference] = path.name
            next(iter(root.iterdir())).chmod(0o644)
            index = root / "index.json"
            index.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
            index.chmod(0o400)
            state = root / "state"
            with self.assertRaises(api.RootBootstrapError) as caught:
                api.apply_root_bootstrap(plan, expected_digest=plan["digest"],
                    driver_image_id=DRIVER, index_path=index, state_directory=state)
            self.assertIn("material", str(caught.exception).lower())
            self.assertNotIn(secret, str(caught.exception))
            self.assertFalse((state / "receipt.json").exists())

    def test_uncertain_receipt_holds_without_redispatch_or_rewriting_history(self):
        api = self.api()
        plan = api.plan_root_bootstrap(installation_input(), driver_image_id=DRIVER)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            receipt = state / "receipt.json"
            receipt.write_text(json.dumps({
                "schema": "cpk.root-bootstrap.receipt.v1", "plan_digest": plan["digest"],
                "driver_image_id": DRIVER, "phase": "acquiring",
                "pending": "create-network", "resources": {}, "observations": {},
            }))
            receipt.chmod(0o600)
            before = receipt.read_bytes()
            observed = api.inspect_root_bootstrap(state_directory=state)
            self.assertEqual(observed["status"], "hold")
            self.assertEqual(observed["pending"], "create-network")
            with self.assertRaises(api.RootBootstrapHold):
                api.apply_root_bootstrap(plan, expected_digest=plan["digest"],
                    driver_image_id=DRIVER, index_path=state / "absent.json", state_directory=state)
            self.assertEqual(receipt.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
