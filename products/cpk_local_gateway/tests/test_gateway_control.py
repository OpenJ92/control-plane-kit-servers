"""#182 product laws: real SDK local truth, selected files and complete contract."""
import asyncio
import builtins
from contextlib import redirect_stderr
from dataclasses import replace
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
import control_plane_kit_core as core
from control_plane_kit_core.products import ProductRuntimeContractCodec
from control_plane_kit_core.planning import (
    compile_graph_activity_plan, resolve_management_observation, ObserveManagementBootstrap,
    ManagementBootstrapStage, StartNode, ObserveNodeHealth, AllocatePublicIngress,
)
from gateway_control_fixtures import fixture, credential, topology, CONTROL_PATH

PACKAGE = "control_plane_kit_servers_cpk_local_gateway"


class GatewayControlMigrationTests(unittest.TestCase):
    def test_configuration_admits_only_common_receiver_profile(self):
        api = importlib.import_module(PACKAGE + ".control_configuration")
        # Freeze the old wire independently of the migrating product factory.
        # Both real public-key families and the exact declaration are lawful.
        declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(core.NodeControlGraphReference(
                core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"), (),
                health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        families = []
        for name in ("surface", "health"):
            public = Ed25519PrivateKey.generate().public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
            families.append({"issuer": name + "-issuer", "public_keys": [{
                "key_id": name + "-key", "algorithm": "ed25519", "public_key_pem": public}]})
        old = {"profile": "cpk-gateway-control-configuration.v1", "target": {
            "workspace_id": "workspace-a", "graph_revision": "revision-a",
            "node_id": "gateway-a", "provider_socket_name": "control"},
            "runtime_id": "runtime-a", "declaration": declaration.descriptor(),
            "surface_read": families[0], "health_read": families[1]}
        raw = json.dumps(old, sort_keys=True, separators=(",", ":")).encode()
        # Only actual decoding is inside the assertion. The old production
        # decoder accepts this complete document, yielding meaningful red.
        with self.assertRaises(api.GatewayControlConfigurationError) as caught:
            api.decode_gateway_control_configuration(raw)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

        # Successor half of this same profile-admission contract: no positive
        # red credit until the accepted Core/SDK and real receiving source run.
        target = {"workspace_id": "workspace-a", "runtime_id": "runtime-a",
            "node_id": "gateway-a", "provider_socket_name": "control", "receiver_id": "a" * 32}
        common = {"profile": "workload-node-control-configuration.v2", "target": target,
            "declaration": declaration.descriptor(), "verifiers": [
                {"purpose": purpose, **family} for purpose, family in zip((
                    "workload-node-control-surface-read", "workload-node-health-read"), families, strict=True)]}
        admitted = api.decode_gateway_control_configuration(json.dumps(common).encode())
        self.assertIs(type(admitted), core.ReceiverNodeControlConfiguration)
        self.assertEqual(admitted.target.descriptor(), target)
        self.assertEqual(admitted.declaration, declaration)
        self.assertEqual(tuple(family.issuer for family in admitted.verifiers),
                         ("surface-issuer", "health-issuer"))


class GatewayControlTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(PACKAGE + ".control_configuration"),
            "#182 gateway own control configuration is missing")
        self.api = importlib.import_module(PACKAGE + ".control_configuration")
        self.server = importlib.import_module(PACKAGE + ".server")
        self.value = fixture(self.api)

    def app(self, value=None):
        value = self.value if value is None else value
        return self.server.create_app(health_relay=value.relay,
            control_configuration=value.config, clock=lambda:value.world.now)

    def health(self, client, value=None, kind=core.NodeHealthReadKind.READINESS):
        value = self.value if value is None else value
        request, token = credential(value, kind=kind)
        response = client.get("/__control/health/" + kind.value, headers={"Authorization":"Bearer " + token})
        self.assertEqual(response.status_code, 200)
        return core.ReceiverHealthReadResultCodec(request, value.config.declaration).decode(response.json())

    def test_actual_sdk_surface_and_both_own_health_callbacks(self):
        self.assertIs(type(self.value.config), core.ReceiverNodeControlConfiguration)
        with TestClient(self.app()) as client:
            _, token = credential(self.value, static=True)
            response = client.get("/__control/capabilities", headers={"Authorization":"Bearer " + token})
            self.assertEqual(response.status_code, 200)
            for kind in core.NodeHealthReadKind:
                self.assertIs(self.health(client, kind=kind).outcome, core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(client.get("/health/ready").json(), {"status":"ready"})
            self.assertEqual(client.post("/cpk/probes", json={}).status_code, 404)
        self.assertEqual(self.value.outbound.requests, [])

    def test_sdk_admission_precedes_protected_callback(self):
        control = importlib.import_module(PACKAGE + ".control")
        original = control.GatewayLocalHealth.readiness
        with patch.object(control.GatewayLocalHealth, "readiness", autospec=True,
                          side_effect=original) as callback:
            with TestClient(self.app()) as client:
                config = self.value.config
                tokens = [None, credential(self.value, static=True)[1],
                    credential(self.value, expires=120)[1],
                    credential(self.value, private=Ed25519PrivateKey.generate())[1],
                    credential(self.value, request_changes={"target":replace(config.target,
                        runtime_id=replace(config.target.runtime_id, value="other"))})[1],
                    credential(self.value, request_changes={"target":replace(config.target, receiver_id="f" * 32)})[1],
                    credential(self.value, request_changes={"target":replace(config.target,
                        node_id=replace(config.target.node_id, value="other"))})[1]]
                for token in tokens:
                    response = client.get("/__control/health/readiness", headers={} if token is None else
                        {"Authorization":"Bearer " + token})
                    self.assertIn(response.status_code, (401, 403))
                    self.assertNotIn("public_key", response.text)
                callback.assert_not_called()
                self.assertIs(self.health(client).outcome, core.NodeHealthReadOutcome.HEALTHY)
                self.assertEqual(callback.call_count, 1)
        self.assertEqual(self.value.outbound.requests, [])

    def test_readiness_tracks_serving_lifespan_and_exceptional_shutdown(self):
        app = self.app()
        self.assertIs(app.state.gateway_local_health.readiness(), core.NodeHealthReadOutcome.UNHEALTHY)
        with TestClient(app) as client:
            self.assertEqual(client.get("/health/ready").status_code, 200)
            self.assertIs(self.health(client).outcome, core.NodeHealthReadOutcome.HEALTHY)
        self.assertIs(app.state.gateway_local_health.readiness(), core.NodeHealthReadOutcome.UNHEALTHY)
        async def exceptional_lifespan():
            # Deliver the exception into the actual async lifespan context;
            # an exception in a TestClient body does not establish that path.
            async with app.router.lifespan_context(app):
                self.assertIs(app.state.gateway_local_health.readiness(), core.NodeHealthReadOutcome.HEALTHY)
                raise RuntimeError("synthetic shutdown")
        with self.assertRaisesRegex(RuntimeError, "synthetic shutdown"):
            asyncio.run(exceptional_lifespan())
        self.assertIs(app.state.gateway_local_health.readiness(), core.NodeHealthReadOutcome.UNHEALTHY)
        with TestClient(self.server.create_app(health_relay=self.value.relay)) as client:
            response = client.get("/health/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status":"not-ready"})
            self.assertEqual(client.get("/health/live").status_code, 200)

    def test_downstream_failure_is_reported_without_breaking_own_readiness(self):
        w = self.value.world
        with TestClient(self.app()) as client:
            self.assertIs(self.health(client).outcome, core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(self.value.outbound.requests, [])
            signed, _ = w.pair()
            response = client.post("/cpk/health/readiness", json=w.envelope(), headers={"Authorization":"Bearer " + signed})
            self.assertEqual(response.status_code, 502)
            self.assertEqual(len(self.value.outbound.requests), 1)
            self.assertIs(self.health(client).outcome, core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(client.get("/health/ready").status_code, 200)
            self.assertEqual(len(self.value.outbound.requests), 1)

    def test_complete_source_contract_compiles_real_fresh_bootstrap_order(self):
        factory = importlib.import_module(PACKAGE + ".health_relay_configuration").gateway_health_source_runtime_contract
        contract = factory(*self.value.artifacts)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(contract.control_surfaces, (self.api.gateway_control_declaration().surface,))
        self.assertEqual(set(contract.configuration_artifacts), set(self.value.artifacts))
        self.assertEqual(contract.verification.checks, ())
        self.assertEqual(contract.gateway_transit.provider_socket_name, "control")
        current, desired = topology(self.value, contract)
        current.require_valid()
        desired.require_valid()
        gateway = desired.graph.nodes[self.value.world.transit.gateway.value]
        self.assertEqual(gateway.block_spec.verification, contract.verification)
        self.assertEqual(gateway.block_spec.control_surfaces, contract.control_surfaces)
        self.assertEqual(gateway.configuration_artifacts, contract.configuration_artifacts)
        self.assertIsNone(gateway.block_spec.health_path)
        plan = compile_graph_activity_plan(current, desired)
        self.assertTrue(plan.ready_for_execution)
        stages = {item.operation.stage:item for item in plan.activities if type(item.operation) is ObserveManagementBootstrap}
        self.assertNotIn(ManagementBootstrapStage.GATEWAY_LOCAL_READY, stages)
        ready = stages[ManagementBootstrapStage.GATEWAY_INGRESS_READY]
        resolved = resolve_management_observation(ready.operation, current, desired, expected_operation=ready.operation)
        self.assertEqual(resolved.gateway_readiness_socket, "control")
        self.assertEqual(resolved.gateway_node.block_spec.control_surfaces, contract.control_surfaces)
        connector = next(item for item in plan.activities if type(item.operation) is StartNode and item.operation.target.node_id == "connector")
        gateway_start = next(item for item in plan.activities if type(item.operation) is StartNode
            and item.operation.target.node_id == gateway.node_id)
        allocation = next(item for item in plan.activities if type(item.operation) is AllocatePublicIngress)
        self.assertIn(gateway_start.activity_id, {item.predecessor for item in allocation.dependencies})
        self.assertIn(allocation.activity_id, {item.predecessor for item in connector.dependencies})
        connected = stages[ManagementBootstrapStage.CONNECTOR_CONNECTED]
        path = stages[ManagementBootstrapStage.AUTHENTICATED_MANAGEMENT_PATH]
        for observation in (connected, path):
            self.assertTrue({connector.activity_id, allocation.activity_id}.issubset(
                {item.predecessor for item in observation.dependencies}))
        self.assertNotIn(connected.activity_id, {item.predecessor for item in path.dependencies})
        self.assertNotIn(path.activity_id, {item.predecessor for item in connected.dependencies})
        self.assertIn(path.activity_id, {item.predecessor for item in ready.dependencies})
        workload = next(item for item in plan.activities if type(item.operation) is ObserveNodeHealth)
        self.assertTrue({ready.activity_id, connected.activity_id}.issubset(
            {item.predecessor for item in workload.dependencies}))

    def test_control_artifact_is_closed_bounded_and_identity_checked(self):
        artifact = self.value.artifacts[2]
        self.assertEqual((artifact.artifact_id, artifact.target_path), ("gateway-control", CONTROL_PATH))
        self.assertEqual(artifact.file_mode.value, "0444")
        self.assertEqual(self.api.decode_gateway_control_configuration(artifact.content.encode()), self.value.config)
        good = artifact.content.encode()
        for raw in (b"x" * 65537, b"{}", b'{"profile":"duplicate",' + good[1:],
                    good.replace(b'"runtime-a"', b'NaN'), b"["*100 + b"]"*100):
            with self.subTest(raw=raw[:15]), self.assertRaises(self.api.GatewayControlConfigurationError):
                self.api.decode_gateway_control_configuration(raw)
        for changed in (replace(self.value.config.target, runtime_id=replace(self.value.config.target.runtime_id, value="other")),
                replace(self.value.config.target, node_id=replace(self.value.config.target.node_id, value="other")),
                replace(self.value.config.target, receiver_id="f" * 32)):
            value = replace(self.value.config, target=changed)
            with self.assertRaises(ValueError):
                self.server.create_app(health_relay=self.value.relay, control_configuration=value)
        self.assertNotIn("public_key", repr(self.value.config))

    def test_actual_main_consumes_selected_control_keys_and_refuses_bad_files(self):
        value = self.value
        other = fixture(self.api)
        selected = replace(value.config, verifiers=tuple(
            next(item for item in other.config.verifiers if item.purpose is family.purpose)
            if family.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ else family
            for family in value.config.verifiers))
        files = {item.target_path:item.content.encode() for item in value.artifacts}
        files[CONTROL_PATH] = self.api.gateway_control_configuration_artifact(selected).content.encode()
        with tempfile.TemporaryDirectory() as directory:
            actual_open = builtins.open
            actual_os_open = os.open
            def redirected(path, *args, **kwargs):
                return actual_open(Path(directory)/Path(path).name if str(path) in files else path, *args, **kwargs)
            def redirected_os_open(path, *args, **kwargs):
                return actual_os_open(Path(directory)/Path(path).name if str(path) in files else path, *args, **kwargs)
            for path, raw in files.items():
                (Path(directory)/Path(path).name).write_bytes(raw)
                (Path(directory)/Path(path).name).chmod(0o444)
            # Redirect fixed public file locations only. Real main/decoders/SDK run.
            with patch("builtins.open", redirected), patch.object(os, "open", redirected_os_open), \
                    patch.dict("os.environ", {"CPK_WRAPPER_CONFIGURATION_FILE":CONTROL_PATH}, clear=True), \
                    patch.object(self.server.uvicorn, "run") as serve:
                self.assertEqual(self.server.main(), 0)
            serve.assert_called_once()
            self.assertEqual(serve.call_args.kwargs["port"], 8000)
            with TestClient(serve.call_args.args[0]) as client:
                now = int(time.time())
                selected_fixture = fixture(self.api, value.world)
                selected_fixture.config = selected
                selected_fixture.world = other.world
                wrong = credential(value, issued=now, expires=now+100)[1]
                correct = credential(selected_fixture, issued=now, expires=now+100)[1]
                self.assertIn(client.get("/__control/health/readiness", headers={"Authorization":"Bearer "+wrong}).status_code, (401,403))
                self.assertEqual(client.get("/__control/health/readiness", headers={"Authorization":"Bearer "+correct}).status_code, 200)
            for raw in (None, b"private-marker", b"x"*65537):
                path = Path(directory)/"control.json"
                if raw is None:
                    path.unlink()
                else:
                    if path.exists():
                        path.chmod(0o644)
                    path.write_bytes(raw)
                    path.chmod(0o444)
                output = io.StringIO()
                with patch("builtins.open", redirected), patch.object(os, "open", redirected_os_open), \
                        patch.dict("os.environ", {"CPK_WRAPPER_CONFIGURATION_FILE":CONTROL_PATH}, clear=True), \
                        patch.object(self.server.uvicorn, "run") as serve, redirect_stderr(output):
                    self.assertEqual(self.server.main(), 2)
                serve.assert_not_called()
                self.assertNotIn("private-marker", output.getvalue())
