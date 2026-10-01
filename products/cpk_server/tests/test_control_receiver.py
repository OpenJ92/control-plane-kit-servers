"""CPK receiving values, startup admission and actual installed authority laws."""
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductRuntimeContractCodec, ProductDescriptorCodec
from fastapi.testclient import TestClient
from cpk_http_host_fixtures import fixture, token, verifier_family
from test_http_mcp_boundaries import DeterministicVerifier, RecordingService
from control_plane_kit_core.operations import ControlPlaneServiceRole

PRODUCT = Path(__file__).resolve().parents[1]


class CpkControlReceiverTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(PRODUCT / "src"))
        self.config = importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        self.fixture = fixture()
        self.control = self.fixture.config
        self.artifact = self.config.cpk_control_configuration_artifact(self.control)
        self.bootstrap = self.server.CpkServerBootstrapConfiguration.from_environment({
            "CPK_SERVER_MODE":"execution-capable", "CPK_PORT":"8080", "CPK_RUNTIME_INTERPRETERS":"none",
            **{f"CPK_{store}_DATABASE_URL":"postgres://fixture:fixture@database.invalid/db"
               for store in ("WORKPLACE","ACTIVITY_HISTORY","OBSERVER_STATE","GRAPH_TOPOLOGY")},
        })
        self.services = {role:RecordingService(role.value) for role in ControlPlaneServiceRole}
        self.verifier = DeterministicVerifier()

    def tearDown(self):
        sys.path.remove(str(PRODUCT / "src"))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith("control_plane_kit_servers_cpk_server."):
                sys.modules.pop(name,None)

    def rejected(self, action):
        with self.assertRaises(self.config.CpkControlConfigurationError) as caught:
            action()
        self.assertEqual(str(caught.exception),"CPK control configuration is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception),{})

    def app(self, control=None):
        with patch.object(self.server,"_operations_application",return_value=SimpleNamespace(services=self.services)):
            return self.server.create_app(self.bootstrap,self.verifier,control=self.control if control is None else control,clock=lambda:150)

    def test_real_receiving_artifact_and_all_three_complete_source_contracts(self):
        self.assertEqual(self.config.decode_cpk_control_configuration(self.artifact.content.encode()),self.control)
        self.assertEqual(ConfigurationArtifact.from_descriptor(self.artifact.descriptor()),self.artifact)
        self.assertEqual(self.artifact.target_path,"/etc/cpk/cpk-server/control.json")
        self.assertEqual(self.artifact.file_mode.value,"0444")
        bootstrap_contract=json.loads((PRODUCT/"bootstrap.contract.json").read_text())
        receiving=bootstrap_contract["configuration_files"][0]
        self.assertTrue(receiving["required"])
        self.assertEqual(receiving["path"],self.artifact.target_path)
        self.assertEqual(receiving["maximum_bytes"],65536)
        variants = self.config.CpkSourceVariant
        for variant,filename in ((variants.CPK,"product.cpk.json"),(variants.DOCKER,"product.docker.cpk.json"),(variants.DOCKER_CLOUDFLARE,"product.docker-cloudflare.cpk.json")):
            with self.subTest(variant=variant):
                old = ProductDescriptorCodec().decode_document((PRODUCT / filename).read_bytes()).product.runtime_contract
                actual = self.config.cpk_source_runtime_contract(variant,self.artifact)
                self.assertEqual(ProductRuntimeContractCodec().decode(actual.descriptor()),actual)
                for field in ("sockets","provider_ports","secret_deliveries","retained_data_mounts","verification","lifecycle"):
                    self.assertEqual(getattr(actual,field),getattr(old,field))
                self.assertEqual(set(actual.public_environment), {*old.public_environment,
                    PublicStaticEnvironmentBinding("CPK_WRAPPER_CONFIGURATION_FILE", self.artifact.target_path)})
                self.assertEqual(len(actual.public_environment), len(old.public_environment) + 1)
                self.assertEqual(actual.configuration_artifacts,(self.artifact,))
                self.assertEqual(actual.control_surfaces,(self.control.declaration.surface,))
                self.assertEqual(set(actual.capabilities),set(old.capabilities)|{CapabilityName.NODE_CONTROLLABLE})
                self.assertEqual(old.control_surfaces,())
        self.rejected(lambda:self.config.cpk_source_runtime_contract("cpk-server",self.artifact))
        self.rejected(lambda:self.config.cpk_source_runtime_contract(variants.CPK,None))
        self.assertIs(type(self.control), core.ReceiverNodeControlConfiguration)
        self.assertNotIn("public_key", repr(self.control))
        self.assertNotIn("PRIVATE KEY", self.artifact.content)

    def test_closed_configuration_fixed_errors_and_wrong_authority_types(self):
        original = json.loads(self.artifact.content)
        cases = [b"",b"\xff",b"{"+b" "*65536,self.artifact.content.replace('"profile":','"profile":"duplicate", "profile":',1).encode()]
        health = next(value for value in original["verifiers"]
                      if value["purpose"] == core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ.value)
        def health_families(**changes):
            return [{**value, **changes} if value["purpose"] == health["purpose"] else dict(value)
                    for value in original["verifiers"]]
        for field,value in (("extra",True),("runtime_id",""),("profile","unknown"),
            ("target",{**original["target"],"provider_socket_name":"mcp"}),
            ("target",{**original["target"],"runtime_id":""}),
            ("verifiers", []),
            ("verifiers",health_families(purpose="wrong")),
            ("verifiers",health_families(issuer="secret\nissuer")),
            ("verifiers",health_families(public_keys=health["public_keys"]*17)),
            ("verifiers",health_families(public_keys=[{**health["public_keys"][0],"public_key_pem":"private malformed material"}]))):
            cases.append(json.dumps({**original,field:value}).encode())
        cases.append(json.dumps({**original, "verifiers":[{**value, "public_keys":[]}
            if value["purpose"] == core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ.value
            else dict(value) for value in original["verifiers"]]}).encode())
        for raw in cases:
            with self.subTest(size=len(raw)):
                self.rejected(lambda:self.config.decode_cpk_control_configuration(raw))
        with self.assertRaises(ValueError):
            replace(self.control, verifiers=(verifier_family(self.control,
                core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ),))
        self.rejected(lambda:self.config.cpk_control_configuration_artifact(replace(self.control,declaration=replace(
            self.control.declaration,surface=replace(self.control.declaration.surface,
                health_reads=(core.NodeHealthReadKind.READINESS,))))))
        malformed = {**original, "target": {**original["target"], "receiver_id":"wrong"}}
        self.rejected(lambda:self.config.decode_cpk_control_configuration(json.dumps(malformed).encode()))
        with self.assertRaises(ValueError):
            replace(self.control.target, runtime_id=core.NodeControlGraphReference(
                core.NodeControlGraphReferenceRole.NODE, "wrong"))
        self.rejected(lambda:self.config.cpk_control_configuration_artifact(None))
        with patch.object(core.ReceiverNodeControlConfigurationCodec,"decode_bytes",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.config.decode_cpk_control_configuration(self.artifact.content.encode())

    def test_fixed_opened_file_bound_symlink_directory_fifo_and_missing(self):
        raw = self.artifact.content.encode()
        with TemporaryDirectory() as directory:
            path = Path(directory)/"control.json"
            with patch.dict(os.environ, {"CPK_WRAPPER_CONFIGURATION_FILE":str(path)}):
                self.rejected(self.config.read_cpk_control_configuration)
                path.write_bytes(raw+b" "*(65536-len(raw)))
                path.chmod(0o444)
                self.assertEqual(self.config.read_cpk_control_configuration(),self.control)
                path.chmod(0o644)
                self.rejected(self.config.read_cpk_control_configuration)
                with path.open("ab") as stream:
                    stream.write(b" ")
                path.chmod(0o444)
                self.rejected(self.config.read_cpk_control_configuration)
                path.unlink()
                target=Path(directory)/"target"; target.write_bytes(raw)
                target.chmod(0o444)
                path.symlink_to(target)
                self.rejected(self.config.read_cpk_control_configuration)
                path.unlink(); path.mkdir()
                self.rejected(self.config.read_cpk_control_configuration)
                path.rmdir(); os.mkfifo(path)
                self.rejected(self.config.read_cpk_control_configuration)

    def test_required_config_and_actual_sdk_collision_precede_schema_effects(self):
        with patch.object(self.server,"_operations_application") as operations:
            with self.assertRaises(TypeError):
                self.server.create_app(self.bootstrap,self.verifier)
            self.rejected(lambda:self.server.create_app(self.bootstrap,self.verifier,control=None))
            original=self.server.install_operator_http_routes
            def collision(app,contract,endpoint):
                original(app,contract,endpoint)
                app.add_api_route("/{path:path}",endpoint,methods=["GET"])
            with patch.object(self.server,"install_operator_http_routes",side_effect=collision):
                with self.assertRaisesRegex(ValueError,"collides"):
                    self.server.create_app(self.bootstrap,self.verifier,control=self.control,clock=lambda:150)
            operations.assert_not_called()

    def test_sdk_install_completes_before_schema_and_schema_failure_returns_no_app(self):
        captured=[]
        original=self.server.install_cpk_wrapper
        def install(app,**kwargs):
            original(app,**kwargs)
            captured.append(app)
        def fail_schema(config):
            self.assertEqual(len(captured),1)
            self.assertTrue(any(route.path.startswith("/__control/") for route in captured[0].routes))
            raise RuntimeError("test schema failure")
        with patch.object(self.server,"install_cpk_wrapper",side_effect=install), patch.object(self.server,"_operations_application",side_effect=fail_schema) as operations:
            with self.assertRaisesRegex(RuntimeError,"test schema failure"):
                self.server.create_app(self.bootstrap,self.verifier,control=self.control,clock=lambda:150)
            operations.assert_called_once_with(self.bootstrap)

    def test_real_protected_health_and_separate_instance_authorities_do_no_operator_work(self):
        second=fixture("second")
        with TestClient(self.app()) as first, TestClient(self.app(second.config)) as other:
            static=first.get("/__control/capabilities",headers={"Authorization":"Bearer "+token(self.fixture,static=True)})
            self.assertEqual(static.status_code,200)
            self.assertEqual(static.json()["declaration"],self.control.declaration.descriptor())
            live=first.get("/__control/health/liveness",headers={"Authorization":"Bearer "+token(self.fixture)})
            self.assertEqual(live.status_code,200)
            request=core.ReceiverHealthReadRequest(self.control.target,self.fixture.authority,core.NodeHealthReadKind.LIVENESS,self.control.declaration.identity(),"health-request")
            result=core.ReceiverHealthReadResultCodec(request,self.control.declaration).decode(live.json())
            self.assertIs(result.outcome,core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(live.headers["cache-control"],"no-store")
            for client,credential in ((first,None),(first,"valid-token"),(first,token(self.fixture,static=True)),(other,token(self.fixture))):
                headers={} if credential is None else {"Authorization":"Bearer "+credential}
                self.assertNotEqual(client.get("/__control/health/liveness",headers=headers).status_code,200)
            self.assertNotEqual(first.get("/__control/health/readiness",headers={"Authorization":"Bearer "+token(self.fixture,kind=core.NodeHealthReadKind.READINESS)}).status_code,200)
            self.assertEqual(other.get("/__control/health/liveness",headers={"Authorization":"Bearer "+token(second)}).status_code,200)
            self.assertEqual(first.get("/health/ready").json()["stores"],"configured")
        self.assertEqual(self.verifier.credentials,[])
        self.assertEqual([r for s in self.services.values() for r in s.requests],[])

    def test_main_rejects_missing_control_before_listener_and_config_import_is_pure(self):
        with patch.object(self.server.CpkServerBootstrapConfiguration,"from_environment",return_value=self.bootstrap), patch.object(self.server,"_credential_verifier",return_value=self.verifier), patch.object(self.server,"read_cpk_control_configuration",side_effect=self.config.CpkControlConfigurationError("CPK control configuration is invalid")), patch.object(self.server,"_operations_application") as operations, patch.object(self.server.uvicorn,"run") as listen:
            self.assertEqual(self.server.main(),2)
            operations.assert_not_called(); listen.assert_not_called()
        result=subprocess.run([sys.executable,"-I","-B","-c",
            "import sys; sys.path.insert(0,sys.argv[1]); import control_plane_kit_servers_cpk_server.control_configuration; assert 'fastapi' not in sys.modules; assert 'control_plane_kit_servers_cpk_server.server' not in sys.modules",str(PRODUCT/"src")],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_same_installed_receiver_accepts_two_contexts_and_refuses_foreign_scope(self):
        with TestClient(self.app()) as client:
            for authority in (self.fixture.authority, core.NodeControlAuthorityContext("revision-b", "projection-b")):
                request = core.ReceiverHealthReadRequest(self.control.target, authority,
                    core.NodeHealthReadKind.LIVENESS, self.control.declaration.identity(), "health-request")
                response = client.get("/__control/health/liveness", headers={"Authorization":"Bearer " +
                    token(self.fixture, request_changes={"authority_context":authority})})
                self.assertEqual(response.status_code, 200)
                actual = core.ReceiverHealthReadResultCodec(request, self.control.declaration).decode(response.json())
                self.assertIs(actual.outcome, core.NodeHealthReadOutcome.HEALTHY)
            for name in ("workspace_id", "runtime_id", "node_id", "provider_socket_name", "receiver_id"):
                value = "f"*32 if name == "receiver_id" else replace(getattr(self.control.target, name), value="foreign")
                credential = token(self.fixture, request_changes={"target":replace(self.control.target, **{name:value})})
                with self.subTest(name=name):
                    response = client.get("/__control/health/liveness", headers={"Authorization":"Bearer " + credential})
                    self.assertNotEqual(response.status_code, 200)
        self.assertEqual(self.verifier.credentials, [])
        self.assertEqual([request for service in self.services.values() for request in service.requests], [])
