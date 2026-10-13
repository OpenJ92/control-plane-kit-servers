"""Fixture ownership/correlation/transport laws; no daemon, database or network."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import httpx
from control_plane_kit_core.planning import StartRuntime, RuntimeTarget
from control_plane_kit_core.runtime_effects import RuntimeEffectResult
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_servers_cpk_server.client import ClientProfile, TopologyClient

from docker_image_update_material import DockerImageMaterial
from docker_image_update_placement import OwnedControllerPlacement, PREFIX
from docker_image_update_ports import (
    AttachedPublicTransport, CompletedRuntimeCall, FixtureBoundaryFailure,
    InstalledGatewaySocketTransport, RecordedDockerRuntime, SyntheticIngressAddressResolver,
    require_committed_call,
)
from test_topology_client import ScriptedTransport, DeterministicIds


def completed():
    request = SimpleNamespace(source=SimpleNamespace(workspace_id="workspace-a",
        run_id=SimpleNamespace(value="run-a"), intent_event_id="effect-a"),
        effect_id="effect-a", activity_id=SimpleNamespace(value="completed-activity"),
        operation=StartRuntime(RuntimeTarget("docker")))
    return CompletedRuntimeCall(request, RuntimeEffectResult.succeeded("effect-a"))


def events():
    return [{"event_id": identity, "run_id": "run-a", "ordinal": ordinal,
        "activity_id": "completed-activity", "event_type": kind, "failure": None}
        for identity, ordinal, kind in (("effect-a", 3, "step_started"),
            ("success-a", 4, "step_succeeded"))]


class DockerImageBoundaryTests(unittest.TestCase):
    def test_material_uses_current_receivers_and_contract_equal_image_successor(self):
        material = DockerImageMaterial("image-test")
        old, new = material.documents["api"].product, material.successor.product
        self.assertEqual(old.runtime_contract, new.runtime_contract)
        self.assertNotEqual(old.image, new.image)
        self.assertEqual(old.image.repository, new.image.repository)
        self.assertEqual(set(material.a.nodes), {"gateway", "api", "api-y", "connector"})
        self.assertEqual(material.a.node("api").sockets.providers[0].name, "internal")
        self.assertNotEqual(material.configurations["api"].target, material.configurations["api-y"].target)
        self.assertEqual(material.configurations["api"].target.workspace_id.value, "image-test")

    def test_recorder_returns_the_actual_result_and_calls_the_real_port_once(self):
        inner = Mock()
        result = RuntimeEffectResult.succeeded("effect-a")
        inner.execute_with_authority.return_value = result
        recorder = RecordedDockerRuntime(inner)
        request, authority = object(), object()
        self.assertIs(recorder.execute_with_authority(request, authority), result)
        inner.execute_with_authority.assert_called_once_with(request, authority)
        self.assertIs(recorder.completed[0].request, request)
        self.assertIs(recorder.completed[0].result, result)

    def test_public_success_is_correlated_to_original_event_not_next_activity(self):
        arguments = {"path_parameters": {"workspace_id": "workspace-a", "run_id": "run-a"},
            "payload": {"max_effects": 1, "claim_generation": 1}}
        response = {"run_id": "run-a", "run_status": "running", "effects_attempted": 1,
            "coordinator_status": "progressed", "activity_id": "next-not-completed"}
        require_committed_call(completed(), response, arguments, events())
        for changed in ([], events()[:1], [{**row, "run_id": "foreign"} for row in events()],
                [events()[0], {**events()[1], "event_type": "step_uncertain"}],
                [*events(), {**events()[0], "event_id": "retry", "ordinal": 5}]):
            with self.subTest(events=changed), self.assertRaises(FixtureBoundaryFailure):
                require_committed_call(completed(), response, arguments, changed)
        for changed in ({**response, "coordinator_status": "uncertain"},
                {**response, "run_id": "foreign"}, {**response, "effects_attempted": 0}):
            with self.subTest(response=changed), self.assertRaises(FixtureBoundaryFailure):
                require_committed_call(completed(), changed, arguments, events())

    def test_hook_failure_journals_original_success_and_never_sends_next_mutation(self):
        recorder = SimpleNamespace(completed=[])
        class Transport(ScriptedTransport):
            def call(inner, route, **arguments):
                if route == "read.run-events":
                    return {"items": events(), "next_cursor": None}
                response = super().call(route, **arguments)
                if route == "command.deployment.execute":
                    recorder.completed.append(completed())
                return response
        inner = Transport(progress_once=True)
        placement = Mock()
        placement.completed.side_effect = FixtureBoundaryFailure("attachment failed")
        transport = AttachedPublicTransport(inner, recorder, placement)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = ClientProfile("https://fixture.example", "workspace-a",
                {role: root / (role + ".token") for role in ("operator", "approver", "worker")},
                root / "state")
            client = TopologyClient(profile, transport=transport, identity_factory=DeterministicIds())
            desired = root / "desired.json"
            desired.write_text(json.dumps({"workspace_id": "workspace-a", "nodes": {}, "edges": []}))
            planned = client.plan(desired)
            with self.assertRaises(FixtureBoundaryFailure):
                client.apply(planned.operation_ref, execute_plan=planned.plan_id, approve_plan=planned.plan_id)
            journal = client.journal.read(planned.operation_ref)
            successes = [row for row in journal["request_history"]
                if row["route_id"] == "command.deployment.execute"]
            self.assertEqual(len(successes), 1)
            self.assertEqual(successes[0]["response"], transport.responses[0])
            self.assertEqual(sum(row["route_id"] == "command.deployment.execute" for row in inner.calls), 1)
            self.assertEqual(transport.unsent, ["command.deployment.execute"])
            placement.completed.assert_called_once()


class DockerImageTransportTests(unittest.IsolatedAsyncioTestCase):
    def request(self, *, host="cpk-1912.example.invalid:443", sni="cpk-1912.example.invalid"):
        body = {"profile": "cpk-gateway-health-relay-request.v2", "target_id": "api",
            "attempt_id": "attempt-a", "request": {"kind": "readiness"}, "workload_credential": "signed-workload"}
        return httpx.Request("POST", "https://8.8.8.8/cpk/health/readiness",
            headers={"Host": host, "Authorization": "Bearer signed-transit"},
            json=body, extensions={"sni_hostname": sni})

    async def test_synthetic_dns_is_exact_and_never_resolves_another_host(self):
        resolver = SyntheticIngressAddressResolver("cpk-1912.example.invalid")
        self.assertEqual(await resolver.resolve("cpk-1912.example.invalid"), ("8.8.8.8",))
        with self.assertRaises(FixtureBoundaryFailure):
            await resolver.resolve("another.invalid")

    async def test_only_validated_original_host_sni_target_reaches_fresh_socket(self):
        requests = []
        async def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"actual_socket_fixture": True})
        endpoint = Mock(return_value="http://172.20.0.7:8000")
        def target(identity, request):
            if identity != "api":
                raise FixtureBoundaryFailure("target differs")
            return request
        transport = InstalledGatewaySocketTransport("cpk-1912.example.invalid", target, endpoint,
            transport_factory=lambda: httpx.MockTransport(handler))
        original = self.request()
        response = await transport.handle_async_request(original)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(requests[0].url), "http://172.20.0.7:8000/cpk/health/readiness")
        self.assertEqual(requests[0].content, original.content)
        self.assertEqual(requests[0].headers["authorization"], original.headers["authorization"])
        self.assertNotIn("sni_hostname", requests[0].extensions)
        await transport.aclose()
        for request in (self.request(host="foreign.invalid:443"), self.request(sni="foreign.invalid"),
                httpx.Request("POST", "https://1.1.1.1/cpk/health/readiness")):
            with self.assertRaises(FixtureBoundaryFailure):
                await transport.handle_async_request(request)
        self.assertEqual(len(requests), 1)
        endpoint.assert_called_once()


class OwnedAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.sdk = Mock(), Mock()
        self.engine.info.return_value = {"ID": "daemon-a"}
        self.network = Mock()
        self.network.id = "a" * 64
        self.network.attrs = {"Labels": {PREFIX + "workspace": "workspace-a",
            PREFIX + "runtime": "docker", PREFIX + "kind": "runtime-network"}}
        self.engine.networks.get.return_value = self.network
        self.sdk.inspect_network.return_value = SimpleNamespace(network_id=self.network.id)
        self.controller = SimpleNamespace(container_id="b" * 64, running=True, network_attachments=())
        self.sdk.inspect_container.return_value = self.controller
        def connect(identity):
            self.assertEqual(identity, self.controller.container_id)
            self.controller.network_attachments = (SimpleNamespace(network_id=self.network.id),)
        self.network.connect.side_effect = connect
        self.placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64, "daemon-a")
        self.record = completed()
        self.record.request.authority_ref = RuntimeAuthorityReference("local-docker")
        self.record = replace(self.record, result=RuntimeEffectResult.succeeded("effect-a",
            evidence={"runtime_id": "docker", "network": "returned-provider-name"}))

    def test_returned_name_resolves_to_verified_id_and_repeated_attachment_is_noop(self):
        self.placement.completed(self.record)
        self.placement.completed(self.record)
        self.engine.networks.get.assert_called_with("returned-provider-name")
        self.assertEqual(self.placement.network_id, self.network.id)
        self.network.connect.assert_called_once_with(self.controller.container_id)

    def test_foreign_network_or_unrecorded_membership_never_attaches(self):
        self.network.attrs["Labels"][PREFIX + "workspace"] = "foreign"
        with self.assertRaises(FixtureBoundaryFailure):
            self.placement.completed(self.record)
        self.network.connect.assert_not_called()
        self.network.attrs["Labels"][PREFIX + "workspace"] = "workspace-a"
        self.controller.network_attachments = (SimpleNamespace(network_id=self.network.id),)
        with self.assertRaises(FixtureBoundaryFailure):
            self.placement.completed(self.record)
        self.network.connect.assert_not_called()
