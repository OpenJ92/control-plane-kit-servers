"""Shared authentication composition; no runtime/provider effects."""
from dataclasses import replace
import importlib
import json
import unittest
import tempfile
from pathlib import Path

from control_plane_kit_core.identity import IdentityContractError
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretReference, SecretUseIntent
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology
from control_plane_kit_operations.cpk_server import CpkServerApplicationError, _ROUTE_AUTHORIZATION_POLICIES
import test_docker_installation as installation_fixture
from test_root_bootstrap import installation_input, DRIVER


class InstallationControlAuthTests(unittest.TestCase):
    def api(self):
        api = importlib.import_module("control_plane_kit_servers_cpk_server.installation")
        for name in ("SingleOperatorControlAuth", "MultiPrincipalControlAuth", "ControlAuthCodec"):
            self.assertTrue(hasattr(api, name), f"missing shared auth value {name}")
        return api

    def value(self, api):
        return installation_fixture.DockerInstallationTests().installation(api)

    def graph(self, api, value):
        return compile_topology(api.compose_docker_cpk_installation(value))

    def test_default_and_closed_auth_codec(self):
        api = self.api()
        codec = api.ControlAuthCodec()
        single = api.SingleOperatorControlAuth()
        self.assertEqual(self.value(api).control_auth, single)
        self.assertEqual(codec.decode({"kind": "single-operator"}), single)
        multi = api.MultiPrincipalControlAuth(SecretReference("secret://parent/principals"))
        for value in (single, multi):
            self.assertEqual(codec.decode(codec.encode(value)), value)
        for bad in ({}, {"kind": "unknown"}, {"kind": "single-operator", "extra": 1},
                    {"kind": "multi-principal"}, {"kind": "multi-principal", "principals_document": "bad"},
                    {"kind": "multi-principal", "principals_document": "secret://parent/doc", "extra": 1}):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                codec.decode(bad)
        with self.assertRaises(TypeError):
            api.MultiPrincipalControlAuth("secret://parent/doc")
        with self.assertRaises(TypeError):
            replace(self.value(api), control_auth={})
        with self.assertRaises(ValueError):
            value = self.value(api)
            replace(value, control_auth=api.MultiPrincipalControlAuth(value.control_credential))

    def test_multi_graph_is_reference_only_and_setup_bearer_is_not_graph_identity(self):
        api = self.api()
        original = self.value(api)
        self.assertEqual(self.graph(api, original), self.graph(api, replace(
            original, control_auth=api.SingleOperatorControlAuth())))
        value = replace(original, control_auth=api.MultiPrincipalControlAuth(
            SecretReference("secret://parent/principals")))
        graph = self.graph(api, value)
        cpk = graph.node(value.cpk_node_id)
        environment = cpk.non_secret_environment()
        self.assertNotIn("CPK_CONTROL_AUTH_STATIC_CREDENTIAL", environment)
        self.assertNotIn("CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON", environment)
        auth = [item for item in cpk.secret_deliveries if isinstance(item, SecretEnvironmentDelivery)
                and item.environment_name.startswith("CPK_CONTROL_AUTH")]
        self.assertEqual(len(auth), 1)
        self.assertEqual(auth[0].environment_name, "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON")
        self.assertEqual(auth[0].reference, value.control_auth.principals_document)
        self.assertEqual(self.graph(api, replace(value, control_credential=SecretReference("secret://parent/other"))), graph)
        changed = replace(value, control_auth=api.MultiPrincipalControlAuth(SecretReference("secret://parent/other-doc")))
        self.assertNotEqual(self.graph(api, changed), graph)
        encoded = json.dumps(GraphDescriptorCodec().encode(graph))
        self.assertNotIn("operator-private-token", encoded)
        self.assertNotIn("worker-private-token", encoded)

    def test_root_decode_keeps_setup_bearer_required(self):
        api = self.api()
        bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        document = installation_input()
        legacy = bootstrap.plan_root_bootstrap(document, driver_image_id=DRIVER)
        document["installation"]["control_auth"] = {"kind": "single-operator"}
        self.assertEqual(bootstrap.plan_root_bootstrap(document, driver_image_id=DRIVER)["graph"], legacy["graph"])
        document["installation"]["control_auth"] = api.ControlAuthCodec().encode(
            api.MultiPrincipalControlAuth(SecretReference("secret://bootstrap/root-a/principals")))
        plan = bootstrap.plan_root_bootstrap(document, driver_image_id=DRIVER)
        self.assertIn("secret://bootstrap/root-a/principals", plan["required_material"])
        self.assertIn(document["installation"]["references"]["control_credential"], plan["required_material"])

    def test_composed_auth_uses_real_principal_kind_and_workspace_gate(self):
        api = self.api()
        server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        value = replace(self.value(api), control_auth=api.MultiPrincipalControlAuth(
            SecretReference("secret://parent/principals")))
        node = self.graph(api, value).node(value.cpk_node_id)
        environment = {k: v for k, v in node.non_secret_environment().items() if k.startswith("CPK_CONTROL_AUTH")}
        environment.update({"CPK_SERVER_MODE": "execution-capable", "CPK_CONTROL_AUTH_CONFIGURED": "true",
                            "CPK_PORT": "8080", "CPK_RUNTIME_INTERPRETERS": "none"})
        for key in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY"):
            environment[f"CPK_{key}_DATABASE_URL"] = "postgres://user:pass@db/cpk"
        environment["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = json.dumps([
            {"credential": "operator-private-token", "subject_id": "operator", "kind": "operator",
             "workspace_grants": {"child-workspace": ["execution:operate"]}},
            {"credential": "worker-private-token", "subject_id": "worker", "kind": "worker",
             "workspace_grants": {"child-workspace": ["execution:operate"]}}])
        config = server.CpkServerBootstrapConfiguration.from_environment(environment)
        verifier = server._credential_verifier(config)
        operator = verifier.authenticate(b"operator-private-token")
        worker = verifier.authenticate(b"worker-private-token")
        with self.assertRaises(CpkServerApplicationError):
            _ROUTE_AUTHORIZATION_POLICIES["command.run.claim"].authorize(operator.command_context("child-workspace"))
        _ROUTE_AUTHORIZATION_POLICIES["command.run.claim"].authorize(worker.command_context("child-workspace"))
        with self.assertRaises(IdentityContractError):
            worker.command_context("other-workspace")
        with self.assertRaises(CpkServerApplicationError):
            _ROUTE_AUTHORIZATION_POLICIES["command.approval.decide"].authorize(worker.command_context("child-workspace"))
        self.assertNotIn("worker-private-token", repr(config))

    def test_inherited_single_inputs_removed_and_secret_leftovers_rejected(self):
        api = self.api()
        value = replace(self.value(api), control_auth=api.MultiPrincipalControlAuth(
            SecretReference("secret://parent/principals")))
        product = value.cpk_product.product
        legacy = ("CPK_CONTROL_AUTH_STATIC_CREDENTIAL", "CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON")
        with self.assertRaisesRegex(ValueError, "secret-shaped"):
            PublicStaticEnvironmentBinding(legacy[0], "legacy")
        contract = replace(product.runtime_contract, public_environment=(
            *product.runtime_contract.public_environment,
            PublicStaticEnvironmentBinding(legacy[1], "legacy")))
        selected = ProductDescriptorCodec().encode_document(replace(product, runtime_contract=contract))
        node = self.graph(api, replace(value, cpk_product=selected)).node(value.cpk_node_id)
        for name in legacy:
            self.assertNotIn(name, node.non_secret_environment())
        dirty = replace(contract, secret_deliveries=(SecretEnvironmentDelivery(
            legacy[0], SecretReference("secret://parent/unexpected"), SecretUseIntent.APPLICATION_CONTROL_TOKEN),))
        selected = ProductDescriptorCodec().encode_document(replace(product, runtime_contract=dirty))
        with self.assertRaisesRegex(ValueError, "installation requires the base product secret delivery contract"):
            self.graph(api, replace(value, cpk_product=selected))

    def test_missing_setup_bearer_fails_material_admission(self):
        api = self.api()
        bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        document = installation_input()
        document["installation"]["control_auth"] = api.ControlAuthCodec().encode(
            api.MultiPrincipalControlAuth(SecretReference("secret://bootstrap/root-a/principals")))
        plan = bootstrap.plan_root_bootstrap(document, driver_image_id=DRIVER)
        bearer = document["installation"]["references"]["control_credential"]
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index.json"
            files = {}
            for position, ref in enumerate(plan["required_material"]):
                material = Path(directory) / f"material-{position}"
                material.write_text("synthetic-material")
                material.chmod(0o400)
                files[ref] = material.name
            index.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
            index.chmod(0o600)
            self.assertEqual(runtime._material(plan, index), {ref: "synthetic-material" for ref in files})
            del files[bearer]
            index.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
            with self.assertRaises(bootstrap.RootBootstrapError):
                runtime._material(plan, index)
