"""Fixture ownership/correlation/transport laws; no daemon, database or network."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
import control_plane_kit_core as core
from control_plane_kit_core.planning import StartRuntime, RuntimeTarget, ActivityId, ReconcileNode, NodeTarget
from control_plane_kit_core.runtime_effects import (
    RuntimeEffectResult, RuntimeEffectRequest, RuntimeEffectSource, RuntimeEffectKind, RuntimeProductMaterial,
)
from control_plane_kit_core.operations.run_identity import RunId
from control_plane_kit_core.operations.recovery import (
    EffectAttemptIdentity, EffectAttemptFence, EffectAttemptState, EffectAttemptStatus,
)
from control_plane_kit_core.runtime_effect_observation import (
    runtime_effect_intent_for_request, runtime_effect_intent_fingerprint, runtime_effect_result_fingerprint,
)
from control_plane_kit_operations.effect_attempts import effect_attempt_state_fingerprint
from control_plane_kit_core.configuration_instances import ConfigurationInstanceRef, ConfigurationInstanceSelection
from control_plane_kit_core.configuration_invocation import (
    configuration_invocation_correlation_for_request, configuration_invocation_selection_fingerprint,
)
from control_plane_kit_core.configuration_installation import (
    ConfigurationInstallationReceipt, ConfigurationInstallationDisposition,
)
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker.configuration import (
    _container_incarnation_fingerprint, configuration_volume_name,
)
from control_plane_kit_core.topology import validate_graph
from control_plane_kit_operations.runtime_authorities import LocalDockerSocketAuthority, RegisteredRuntimeAuthority
from control_plane_kit_operations.products import InlineDescriptorSource, RegisteredProduct
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_servers_cpk_server.client import ClientProfile, TopologyClient

from docker_image_update_material import DockerImageMaterial
from docker_image_update_placement import OwnedControllerPlacement, SyntheticConnectorConnection, PREFIX
from docker_image_update_ports import (
    AttachedPublicTransport, CompletedRuntimeCall, FixtureBoundaryFailure,
    InstalledGatewaySocketTransport, RecordedDockerRuntime, SyntheticIngressAddressResolver,
    require_committed_call, require_replacement_receipt, failed_apply_evidence, emit_failed_apply_evidence,
)
from test_topology_client import ScriptedTransport, DeterministicIds


def completed():
    request = RuntimeEffectRequest("effect-a", RuntimeEffectKind.REALIZE_ACTIVITY, RuntimeKind.DOCKER,
        RuntimeEffectSource("workspace-a", "request-a", RunId("run-a"), "plan-a", "base-a", "desired-a", "effect-a"),
        ActivityId("completed-activity"), StartRuntime(RuntimeTarget("docker")),
        authority_ref=RuntimeAuthorityReference("local-docker"))
    return CompletedRuntimeCall(request, RuntimeEffectResult.succeeded("effect-a"))


def events(record=None, *, generation=1, worker="worker-a"):
    record = record or completed()
    state = EffectAttemptState(EffectAttemptIdentity(record.request.source.run_id,
        record.request.activity_id.value, 1),
        runtime_effect_intent_fingerprint(runtime_effect_intent_for_request(record.request)),
        EffectAttemptFence(worker, generation), EffectAttemptStatus.STARTED)
    succeeded = replace(state, status=EffectAttemptStatus.SUCCEEDED,
        outcome_fingerprint=runtime_effect_result_fingerprint(record.result))
    return [{"event_id": identity, "run_id": "run-a", "ordinal": ordinal,
        "activity_id": "completed-activity", "event_type": kind, "failure": None,
        "payload": {"effect_attempt": {"attempt": 1,
            "state_fingerprint": effect_attempt_state_fingerprint(value)}}}
        for identity, ordinal, kind, value in (("effect-a", 3, "step_started", state),
            ("success-a", 4, "step_succeeded", succeeded))]


def replacement_record():
    document = DockerImageMaterial("workspace-a").successor
    refs = tuple(ConfigurationInstanceRef("allocation-" + str(index), "workspace-a", "docker", "api",
        value.artifact_id, value.target_path, value.media_type, value.file_mode, value.content_digest)
        for index, value in enumerate(document.product.runtime_contract.configuration_artifacts))
    request = replace(completed().request, kind=RuntimeEffectKind.CONFIGURATION_ACTIVITY_V1,
        operation=ReconcileNode(NodeTarget("api")), configuration_instances=ConfigurationInstanceSelection(refs),
        products=(RuntimeProductMaterial("api", "docker", ProductReference.from_document(document), document.product),))
    context = configuration_invocation_correlation_for_request(request)
    receipt = ConfigurationInstallationReceipt(context.request_fingerprint,
        configuration_invocation_selection_fingerprint(context.selection), ConfigurationInstallationDisposition.REPLACED,
        _container_incarnation_fingerprint("a" * 64), _container_incarnation_fingerprint("b" * 64))
    return CompletedRuntimeCall(request, RuntimeEffectResult.succeeded("effect-a",
        evidence={"configuration_installation_receipt": receipt.descriptor()}))


class DockerImageBoundaryTests(unittest.TestCase):
    def test_failure_evidence_retains_bounded_public_classifications_not_payloads(self):
        result = SimpleNamespace(run_id="run-a", plan_id="plan-a", status="attention-required",
            execution="failed", advancement="not-attempted")
        transport = Mock(failure="PRIVATE-FIXTURE-ERROR")
        event_rows = [{"run_id": "run-a", "event_id": f"event-{index}", "activity_id": "activity-a",
            "ordinal": index, "event_type": "step_failed", "payload": {"token": "PRIVATE-PAYLOAD"},
            "failure": {"category": "terminal", "code": "runtime.effect-failed",
                "message": "PRIVATE-MESSAGE", "details": {"key": "PRIVATE-DETAIL",
                    "effect_outcome": {"runtime_failure_code": "docker.container-start-failed",
                        "private": "PRIVATE-EFFECT-DETAIL"}}}}
            for index in range(40)]
        transport.call.side_effect = [
            {"items": event_rows, "next_cursor": None},
            {"items": [{"run_id": "run-a", "plan_id": "plan-a", "status": "failed",
                "metadata": {"secret": "PRIVATE-METADATA"}}], "next_cursor": None}]
        evidence = failed_apply_evidence(transport, "workspace-a", result)
        self.assertEqual(evidence["docker_image_apply_failure"], "observed")
        self.assertTrue(evidence["fixture_boundary_failed"])
        self.assertTrue(evidence["events_truncated"])
        self.assertEqual(len(evidence["events"]), 32)
        self.assertEqual(evidence["events"][-1]["ordinal"], 39)
        self.assertEqual(evidence["events"][-1]["failure_code"], "runtime.effect-failed")
        self.assertEqual(evidence["events"][-1]["runtime_failure_code"], "docker.container-start-failed")
        self.assertEqual(evidence["run_status"], "failed")
        self.assertNotIn("PRIVATE", json.dumps(evidence))
        self.assertLessEqual(len(json.dumps(evidence).encode()), 32768)
        self.assertEqual([call.args[0] for call in transport.call.call_args_list],
            ["read.run-events", "read.plan-runs"])
        for call in transport.call.call_args_list:
            self.assertEqual(call.kwargs["credential_role"], "operator")
            self.assertEqual(call.kwargs["path_parameters"]["workspace_id"], "workspace-a")

    def test_evidence_read_failure_does_not_raise_or_replace_primary_result(self):
        result = SimpleNamespace(run_id="run-a", plan_id="plan-a", status="attention-required",
            execution="failed", advancement="not-attempted")
        original = dict(vars(result))
        transport = Mock(failure=None)
        transport.call.side_effect = RuntimeError("PRIVATE-READ-ERROR")
        evidence = failed_apply_evidence(transport, "workspace-a", result)
        self.assertEqual(evidence["docker_image_apply_failure"], "evidence-unavailable")
        self.assertEqual(evidence["execution"], "failed")
        self.assertEqual(vars(result), original)
        self.assertNotIn("PRIVATE", json.dumps(evidence))
        transport.call.reset_mock()
        missing = failed_apply_evidence(transport, "workspace-a", None)
        self.assertTrue(missing["client_exception"])
        transport.call.assert_not_called()

    def test_partial_failure_evidence_remains_bounded_when_run_read_fails(self):
        result = SimpleNamespace(run_id="run-a", plan_id="plan-a", status="attention-required",
            execution="failed", advancement="not-attempted")
        transport = Mock(failure=None)
        page = {"items": [{"run_id": "run-a", "event_id": "event-a", "activity_id": "activity-a",
            "ordinal": 1, "event_type": "step_failed"}], "next_cursor": None}
        transport.call.side_effect = [page, RuntimeError("PRIVATE-READ-ERROR")]
        evidence = failed_apply_evidence(transport, "workspace-a", result)
        self.assertEqual(evidence["docker_image_apply_failure"], "evidence-unavailable")
        self.assertEqual(evidence["events"][0]["event_id"], "event-a")
        self.assertNotIn("PRIVATE", json.dumps(evidence))
        transport.call.side_effect = [page, RuntimeError("PRIVATE-READ-ERROR")]
        with patch("docker_image_update_ports.json.dumps", return_value="x" * 32769):
            bounded = failed_apply_evidence(transport, "workspace-a", result)
        self.assertEqual(bounded, {"docker_image_apply_failure": "evidence-unavailable"})

    def test_failure_evidence_output_failure_does_not_replace_primary_result(self):
        result = SimpleNamespace(run_id="run-a", plan_id="plan-a", status="attention-required",
            execution="failed", advancement="not-attempted")
        original = dict(vars(result))
        transport = Mock(failure=None)
        transport.call.side_effect = RuntimeError("PRIVATE-READ-ERROR")
        with patch("builtins.print", side_effect=OSError("PRIVATE-OUTPUT-ERROR")) as output:
            emit_failed_apply_evidence(transport, "workspace-a", result)
            emit_failed_apply_evidence(transport, "workspace-a", None)
        self.assertEqual(output.call_count, 2)
        self.assertEqual(vars(result), original)
        with patch("docker_image_update_ports.json.dumps", side_effect=ValueError("PRIVATE-SERIALIZATION")):
            emit_failed_apply_evidence(transport, "workspace-a", result)

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
        require_committed_call(completed(), response, arguments, events(), "worker-a")
        for changed in ([], events()[:1], [{**row, "run_id": "foreign"} for row in events()],
                [events()[0], {**events()[1], "event_type": "step_uncertain"}],
                [*events(), {**events()[0], "event_id": "retry", "ordinal": 5}],
                events(generation=2), events(worker="foreign-worker")):
            with self.subTest(events=changed), self.assertRaises(FixtureBoundaryFailure):
                require_committed_call(completed(), response, arguments, changed, "worker-a")
        for changed in ({**response, "coordinator_status": "uncertain"},
                {**response, "run_id": "foreign"}, {**response, "effects_attempted": 0}):
            with self.subTest(response=changed), self.assertRaises(FixtureBoundaryFailure):
                require_committed_call(completed(), changed, arguments, events(), "worker-a")

    def test_replacement_receipt_binds_provider_ids_and_committed_result(self):
        record = replacement_record()
        require_replacement_receipt(record, "a" * 64, "b" * 64)
        for prior, current in (("c" * 64, "b" * 64), ("a" * 64, "c" * 64)):
            with self.assertRaises(FixtureBoundaryFailure):
                require_replacement_receipt(record, prior, current)
        arguments = {"path_parameters": {"workspace_id": "workspace-a", "run_id": "run-a"},
            "payload": {"max_effects": 1, "claim_generation": 1}}
        response = {"run_id": "run-a", "run_status": "succeeded", "effects_attempted": 1,
            "coordinator_status": "completed"}
        require_committed_call(record, response, arguments, events(record), "worker-a")
        changed = replace(record, result=replace(record.result, evidence={}))
        with self.assertRaises(FixtureBoundaryFailure):
            require_committed_call(changed, response, arguments, events(record), "worker-a")

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
        transport = AttachedPublicTransport(inner, recorder, placement, "worker-a")
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
    def request(self, *, port=None, host="cpk-1912.example.invalid:443", sni="cpk-1912.example.invalid"):
        body = {"profile": "cpk-gateway-health-relay-request.v2", "target_id": "api",
            "attempt_id": "attempt-a", "request": {"kind": "readiness"}, "workload_credential": "signed-workload"}
        authority = "8.8.8.8" if port is None else f"8.8.8.8:{port}"
        return httpx.Request("POST", f"https://{authority}/cpk/health/readiness",
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
        for port in (None, 443):
            original = self.request(port=port)
            response = await transport.handle_async_request(original)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(str(requests[-1].url), "http://172.20.0.7:8000/cpk/health/readiness")
            self.assertEqual(requests[-1].content, original.content)
            self.assertEqual(requests[-1].headers["authorization"], original.headers["authorization"])
            self.assertNotIn("sni_hostname", requests[-1].extensions)
            await transport.aclose()
        for request in (self.request(host="foreign.invalid:443"), self.request(sni="foreign.invalid"), self.request(port=8443),
                httpx.Request("POST", "https://1.1.1.1/cpk/health/readiness")):
            with self.assertRaises(FixtureBoundaryFailure):
                await transport.handle_async_request(request)
        self.assertEqual(len(requests), 2)
        self.assertEqual(endpoint.call_count, 2)


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

    def test_same_workspace_unrecorded_resource_prevents_all_disposal(self):
        from docker_image_update_placement import dispose_fixture
        unknown = Mock(id="c" * 64)
        unknown.labels = {PREFIX + "workspace": "workspace-a", PREFIX + "runtime": "docker",
            PREFIX + "node": "api", PREFIX + "kind": "container"}
        self.engine.containers.list.return_value = [unknown]
        self.engine.networks.list.return_value = []
        self.engine.volumes.list.return_value = []
        with self.assertRaises(FixtureBoundaryFailure):
            dispose_fixture(self.placement)
        unknown.remove.assert_not_called()
        self.network.disconnect.assert_not_called()
        self.network.remove.assert_not_called()

    def test_recorded_container_with_changed_labels_is_preserved_even_outside_discovery(self):
        from docker_image_update_placement import dispose_fixture
        container = Mock(id="c" * 64)
        container.labels = {PREFIX + "workspace": "foreign"}
        self.placement.record["containers"][container.id] = {"node": "api", "image_role": "hello_a"}
        self.engine.containers.get.return_value = container
        for manager in (self.engine.containers, self.engine.networks, self.engine.volumes):
            manager.list.return_value = []
        with self.assertRaises(FixtureBoundaryFailure):
            dispose_fixture(self.placement)
        self.engine.containers.get.assert_called_once_with(container.id)
        container.remove.assert_not_called()

    def test_configuration_references_are_persisted_before_runtime_dispatch(self):
        request = replacement_record().request
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ownership.json"
            placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
                "daemon-a", record_path=path, run="fixture-run")
            runtime = Mock()
            def execute(actual):
                self.assertIs(actual, request)
                recorded = json.loads(path.read_text())
                self.assertEqual(recorded["intents"][0]["effect_id"], request.effect_id)
                self.assertEqual(set(recorded["volumes"]),
                    {configuration_volume_name(ref) for ref in request.configuration_instances.instances})
                raise FixtureBoundaryFailure("simulated provider stop")
            runtime.execute.side_effect = execute
            with self.assertRaises(FixtureBoundaryFailure):
                RecordedDockerRuntime(runtime, resources=placement).execute(request)
            runtime.execute.assert_called_once_with(request)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class NativeFixtureSelectionTests(unittest.TestCase):
    def test_every_native_operation_resolves_to_the_exact_fixture_tuple(self):
        material = DockerImageMaterial("workspace-a")
        placement = SimpleNamespace(workspace="workspace-a")
        observer = SyntheticConnectorConnection(placement, SimpleNamespace(allocations={}), material)
        authority = RegisteredRuntimeAuthority("registration", "workspace-a",
            RuntimeAuthorityReference("local-docker"), RuntimeKind.DOCKER,
            LocalDockerSocketAuthority(), "operator", "2026-10-13T00:00:00Z")
        products = tuple(RegisteredProduct("product-" + name, "workspace-a",
            ProductReference.from_document(document), document, InlineDescriptorSource(),
            "operator", "2026-10-13T00:00:00Z") for name, document in material.documents.items())
        def select(graph):
            retained = {"gateway", "connector"}
            current = replace(graph, nodes={key: value for key, value in graph.nodes.items() if key in retained},
                runtimes={key: replace(value, children=tuple(node for node in value.children if node in retained))
                    for key, value in graph.runtimes.items()})
            plan = core.compile_graph_activity_plan(validate_graph(current), validate_graph(graph))
            return observer.select(plan=plan, current=current, desired=graph,
                registered_products=products, runtime_authorities=(authority,))
        self.assertTrue(select(material.a))
        foreign = replace(material.a, public_ingresses=(replace(material.a.public_ingresses[0],
            hostname="foreign.example.invalid"),))
        self.assertIsNone(select(foreign))
