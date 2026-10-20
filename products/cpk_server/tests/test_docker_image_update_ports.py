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
from control_plane_kit_core.planning import StartRuntime, StartNode, RuntimeTarget, ActivityId, ReconcileNode, NodeTarget
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
from control_plane_kit_core.products import ProductReference, ProductDescriptorCodec
from control_plane_kit_core.secrets import SecretFileDelivery, SecretFilePathBinding, SecretReference, SecretUseIntent
from control_plane_kit_core.secret_selections import SecretVersionSelection, UnselectedSecretUse
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker.configuration import (
    _container_incarnation_fingerprint, configuration_volume_name,
)
from control_plane_kit_interpreters.docker.runtime import _secret_volume_name
from control_plane_kit_interpreters.docker.sdk import DockerSdkImageInspection
from control_plane_kit_core.topology import validate_graph
from control_plane_kit_operations.runtime_authorities import LocalDockerSocketAuthority, RegisteredRuntimeAuthority
from control_plane_kit_operations.products import InlineDescriptorSource, RegisteredProduct
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_servers_cpk_server.client import ClientProfile, TopologyClient
from control_plane_kit_servers_cpk_server.managed_health_placement import DockerGatewayBinding

from docker_image_update_material import DockerImageMaterial, IMAGES
from image_identity_test_material import qualified_images
from docker_image_update_selection import consumer_graph, application_content_graph
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


def replacement_record(node="api", *, prior_id="a" * 64, current_id="b" * 64):
    material = DockerImageMaterial("workspace-a")
    document = material.successor if node == "api" else material.documents[node]
    refs = tuple(ConfigurationInstanceRef("allocation-" + str(index), "workspace-a", "docker", node,
        value.artifact_id, value.target_path, value.media_type, value.file_mode, value.content_digest)
        for index, value in enumerate(document.product.runtime_contract.configuration_artifacts))
    request = replace(completed().request, kind=RuntimeEffectKind.CONFIGURATION_ACTIVITY_V1,
        operation=ReconcileNode(NodeTarget(node)), configuration_instances=ConfigurationInstanceSelection(refs),
        products=(RuntimeProductMaterial(node, "docker", ProductReference.from_document(document), document.product,
            secret_selections=tuple(SecretVersionSelection(delivery.reference, delivery.intent, "version-a")
                for delivery in document.product.runtime_contract.secret_deliveries)),))
    context = configuration_invocation_correlation_for_request(request)
    receipt = ConfigurationInstallationReceipt(context.request_fingerprint,
        configuration_invocation_selection_fingerprint(context.selection), ConfigurationInstallationDisposition.REPLACED,
        _container_incarnation_fingerprint(prior_id), _container_incarnation_fingerprint(current_id))
    return CompletedRuntimeCall(request, RuntimeEffectResult.succeeded("effect-a",
        evidence={"configuration_installation_receipt": receipt.descriptor()}))


def secret_file_request():
    original = DockerImageMaterial("workspace-a").documents["connector"].product
    delivery = SecretFileDelivery("/run/secrets/tunnel", SecretReference("secret://generated/ingress/fixture"),
        SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, path_binding=SecretFilePathBinding("TUNNEL_TOKEN_FILE"))
    document = ProductDescriptorCodec().encode_document(replace(original,
        runtime_contract=replace(original.runtime_contract, secret_deliveries=(delivery,))))
    return replace(completed().request, operation=StartNode(NodeTarget("connector")),
        products=(RuntimeProductMaterial("connector", "docker", ProductReference.from_document(document), document.product,
            secret_selections=(SecretVersionSelection(delivery.reference, delivery.intent, "version-a"),)),))


class DockerImageBoundaryTests(unittest.TestCase):
    def test_consumer_fixture_declares_initial_use_and_separates_image_and_content(self):
        material = DockerImageMaterial("workspace-a")
        introduced = material.a
        pending, = introduced.node("api").secret_selections
        self.assertIs(type(pending), UnselectedSecretUse)
        self.assertEqual(introduced.node("api").secret_deliveries,
            material.documents["api"].product.runtime_contract.secret_deliveries)
        self.assertIn("application-settings", {value.artifact_id
            for value in introduced.node("api").configuration_artifacts})
        selected = SecretVersionSelection(pending.reference, pending.intent, "version-a")
        introduced = introduced.update_node(replace(introduced.node("api"), secret_selections=(selected,)))
        successor = consumer_graph(introduced, material.successor)
        self.assertEqual(successor.node("api").secret_selections, (selected,))
        self.assertEqual(successor.node("api").secret_deliveries, introduced.node("api").secret_deliveries)
        self.assertNotEqual(successor.node("api").metadata, introduced.node("api").metadata)
        self.assertEqual(successor.node("api").configuration_artifacts,
            introduced.node("api").configuration_artifacts)
        self.assertEqual(successor.update_node(replace(successor.node("api"),
            metadata=introduced.node("api").metadata)), introduced)
        content = application_content_graph(successor)
        self.assertNotEqual(content.node("api").configuration_artifacts,
            successor.node("api").configuration_artifacts)
        self.assertEqual(content.update_node(replace(content.node("api"),
            configuration_artifacts=successor.node("api").configuration_artifacts)), successor)

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
            self.assertFalse(emit_failed_apply_evidence(transport, "workspace-a", result))
            self.assertFalse(emit_failed_apply_evidence(transport, "workspace-a", None))
        self.assertEqual(output.call_count, 2)
        self.assertEqual(vars(result), original)
        with patch("docker_image_update_ports.json.dumps", side_effect=ValueError("PRIVATE-SERIALIZATION")):
            self.assertFalse(emit_failed_apply_evidence(transport, "workspace-a", result))
        with patch("builtins.print"):
            self.assertTrue(emit_failed_apply_evidence(transport, "workspace-a", result))

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
        self.assertNotEqual(material.public["workload"].fingerprint_sha256,
            material.public["workload-overlap"].fingerprint_sha256)
        self.assertTrue(all(key.key_id != "health-workload-overlap"
            for configured in material.configurations.values()
            for family in configured.verifiers for key in family.public_keys))

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
        self.assert_post_response_failure_journaled(observer=False)

    def test_committed_observer_failure_preserves_response_and_blocks_next_mutation(self):
        self.assert_post_response_failure_journaled(observer=True)

    def assert_post_response_failure_journaled(self, *, observer):
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
        if not observer:
            placement.completed.side_effect = FixtureBoundaryFailure("attachment failed")
        transport = AttachedPublicTransport(inner, recorder, placement, "worker-a")
        observed = []
        if observer:
            def observe(record, response):
                self.assertIs(record, recorder.completed[0])
                self.assertIs(response, transport.responses[0])
                self.assertEqual(transport.committed[record.request.effect_id][1], response)
                placement.completed.assert_called_once_with(record)
                observed.append(record.request.effect_id)
                raise FixtureBoundaryFailure("observation failed")
            transport.committed_observer = observe
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
            self.assertEqual(observed, [recorder.completed[0].request.effect_id] if observer else [])


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
        self.assertEqual(transport.observations, [("api", "readiness", 200)] * 2)


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
        self.qualified_images = qualified_images()
        self.placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64, "daemon-a",
            qualified_images=self.qualified_images)
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

    def gateway_reconcile_transport(self, *, node="gateway", invalid=None):
        self.placement.network_id = self.network.id
        self.placement.nodes["gateway"] = "c" * 64
        self.placement.bindings["gateway"] = DockerGatewayBinding("workspace-a", "docker",
            RuntimeAuthorityReference("local-docker"), "gateway", self.network.id, "c" * 64)
        container = SimpleNamespace(id="d" * 64, labels={PREFIX + "workspace": "workspace-a",
            PREFIX + "runtime": "docker", PREFIX + "kind": "container", PREFIX + "node": "gateway"},
            attrs={"Image": IMAGES["gateway"]["image_id"], "Config": {"User": "gateway"}})
        self.engine.containers.get.return_value = container
        inspected = SimpleNamespace(container_id=container.id, running=True,
            network_attachments=(SimpleNamespace(network_id=self.network.id),))
        if invalid == "owner":
            container.labels[PREFIX + "workspace"] = "foreign"
        elif invalid == "image":
            container.attrs["Image"] = "sha256:" + "e" * 64
        elif invalid == "user":
            container.attrs["Config"]["User"] = "root"
        elif invalid == "network":
            inspected.network_attachments = ()
        elif invalid == "running":
            inspected.running = False
        self.sdk.inspect_container.return_value = inspected
        record = replacement_record(node, prior_id="c" * 64, current_id=container.id)
        record = replace(record, result=replace(record.result,
            evidence={**record.result.evidence, "runtime_id": "docker", "container": container.id}))
        recorder = SimpleNamespace(completed=[])
        response = {"run_id": "run-a", "run_status": "succeeded", "effects_attempted": 1,
            "coordinator_status": "completed"}
        dispatches = []
        class Transport:
            def call(inner, route, **arguments):
                if route == "read.run-events":
                    return {"items": events(record), "next_cursor": None}
                if route != "command.deployment.execute":
                    raise AssertionError("unexpected fixture request")
                dispatches.append(route)
                recorder.completed.append(record)
                return response
        transport = AttachedPublicTransport(Transport(), recorder, self.placement, "worker-a")
        return transport, response, container, dispatches

    def gateway_execute(self, transport):
        return transport.call("command.deployment.execute",
            path_parameters={"workspace_id": "workspace-a", "run_id": "run-a"},
            payload={"max_effects": 1, "claim_generation": 1})

    def test_committed_gateway_replacement_refreshes_exact_binding_without_attachment(self):
        transport, response, container, dispatches = self.gateway_reconcile_transport()
        observed = []
        transport.committed_observer = lambda record, response: observed.append(
            self.placement.bindings["gateway"].gateway_container_id)
        returned = self.gateway_execute(transport)
        transport.require_healthy()
        self.assertIs(returned, response)
        self.assertEqual(observed, [container.id])
        self.assertEqual(self.placement.nodes["gateway"], container.id)
        self.assertEqual(self.placement.bindings["gateway"].network_id, self.network.id)
        self.assertEqual(dispatches, ["command.deployment.execute"])
        self.network.connect.assert_not_called()
        self.network.disconnect.assert_not_called()
        self.engine.containers.create.assert_not_called()

    def test_invalid_gateway_observation_preserves_binding_response_and_blocks_next_dispatch(self):
        for invalid in ("owner", "image", "user", "network", "running"):
            with self.subTest(invalid=invalid):
                transport, response, _, dispatches = self.gateway_reconcile_transport(invalid=invalid)
                original_binding = self.placement.bindings["gateway"]
                self.assertIs(self.gateway_execute(transport), response)
                self.assertIs(self.placement.bindings["gateway"], original_binding)
                with self.assertRaises(FixtureBoundaryFailure):
                    self.gateway_execute(transport)
                self.assertEqual(dispatches, ["command.deployment.execute"])
                self.assertEqual(transport.unsent, ["command.deployment.execute"])
                self.network.connect.assert_not_called()
                self.network.disconnect.assert_not_called()
                self.engine.containers.create.assert_not_called()

    def test_non_gateway_reconcile_does_not_enter_default_gateway_observation(self):
        transport, response, _, _ = self.gateway_reconcile_transport(node="api", invalid="image")
        original_binding = self.placement.bindings["gateway"]
        self.assertIs(self.gateway_execute(transport), response)
        transport.require_healthy()
        self.assertIs(self.placement.bindings["gateway"], original_binding)
        self.engine.containers.get.assert_not_called()
        self.network.connect.assert_not_called()
        self.network.disconnect.assert_not_called()
        self.engine.containers.create.assert_not_called()

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
                "daemon-a", record_path=path, run="fixture-run", qualified_images=self.qualified_images)
            runtime = Mock()
            def execute(actual):
                self.assertIs(actual, request)
                recorded = json.loads(path.read_text())
                self.assertEqual(recorded["qualified_images"], self.qualified_images.descriptor())
                self.assertEqual(recorded["intents"][0]["effect_id"], request.effect_id)
                self.assertEqual(set(recorded["volumes"]),
                    {configuration_volume_name(ref) for ref in request.configuration_instances.instances})
                raise FixtureBoundaryFailure("simulated provider stop")
            runtime.execute.side_effect = execute
            with self.assertRaises(FixtureBoundaryFailure):
                RecordedDockerRuntime(runtime, resources=placement).execute(request)
            runtime.execute.assert_called_once_with(request)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_secret_volume_identity_is_persisted_before_runtime_dispatch(self):
        request = secret_file_request()
        delivery, = request.products[0].product.runtime_contract.secret_deliveries
        self.sdk.inspect_image.return_value = DockerSdkImageInspection("sha256:" + "a" * 64,
            (request.products[0].product.image.execution_reference,), "65535:65535")
        name = _secret_volume_name(request, "connector", delivery, owner_uid=65535)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ownership.json"
            placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
                "daemon-a", record_path=path, qualified_images=self.qualified_images)
            runtime = Mock()
            def execute(actual):
                self.assertIs(actual, request)
                recorded = json.loads(path.read_text())
                self.assertEqual(recorded["qualified_images"], self.qualified_images.descriptor())
                self.assertEqual(set(recorded["secret_volumes"]), {name})
                self.assertEqual(recorded["secret_volumes"][name][PREFIX + "secret.reference"],
                    delivery.reference.reference_id)
                self.assertEqual(len(recorded["secret_volumes"][name][PREFIX + "secret.identity"]), 64)
                self.assertFalse(recorded["volumes"])
                raise FixtureBoundaryFailure("simulated provider stop")
            runtime.execute.side_effect = execute
            with self.assertRaises(FixtureBoundaryFailure):
                RecordedDockerRuntime(runtime, resources=placement).execute(request)
            runtime.execute.assert_called_once_with(request)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_selected_volume_reuse_retains_original_labels_and_separates_version_and_uid(self):
        request = secret_file_request()
        self.sdk.inspect_image.return_value = DockerSdkImageInspection("sha256:" + "a" * 64,
            (request.products[0].product.image.execution_reference,), "65535:65535")
        self.placement.starting(request)
        original = dict(self.placement.record["secret_volumes"])
        self.placement.starting(replace(request, source=replace(request.source, plan_id="later-plan")))
        self.assertEqual(self.placement.record["secret_volumes"], original)
        material, = request.products
        selection, = material.secret_selections
        self.placement.starting(replace(request, products=(replace(material,
            secret_selections=(replace(selection, version_id="version-b"),)),)))
        self.sdk.inspect_image.return_value = DockerSdkImageInspection("sha256:" + "a" * 64,
            (material.product.image.execution_reference,), "10001")
        self.placement.starting(request)
        self.assertEqual(len(self.placement.record["secret_volumes"]), 3)
        self.assertEqual(len({row[PREFIX + "secret.identity"]
            for row in self.placement.record["secret_volumes"].values()}), 3)

    def test_secret_volume_cleanup_requires_prerecord_and_unchanged_ownership(self):
        from docker_image_update_placement import dispose_fixture
        request = secret_file_request()
        self.sdk.inspect_image.return_value = DockerSdkImageInspection("sha256:" + "a" * 64,
            (request.products[0].product.image.execution_reference,), "65535:65535")
        self.placement.starting(request)
        name, = self.placement.record["secret_volumes"]
        expected = self.placement.record["secret_volumes"][name]
        volume = Mock()
        volume.name = name
        volume.attrs = {"Labels": dict(expected)}
        self.engine.containers.list.return_value = []
        self.engine.networks.list.return_value = []
        self.engine.volumes.list.return_value = [volume]
        self.engine.volumes.get.return_value = volume
        self.sdk.inspect_volume.return_value = SimpleNamespace(name=name, labels=dict(expected))
        self.assertEqual(self.placement.cleanup_candidates()["volumes"], [volume])
        for key in ("workspace", "secret.target", "secret.reference", "volume.kind", "secret.identity"):
            with self.subTest(changed=key):
                volume.attrs["Labels"][PREFIX + key] = "foreign"
                with self.assertRaises(FixtureBoundaryFailure):
                    dispose_fixture(self.placement)
                volume.remove.assert_not_called()
                volume.attrs["Labels"] = dict(expected)
        self.placement.record["secret_volumes"].clear()
        with self.assertRaises(FixtureBoundaryFailure):
            dispose_fixture(self.placement)
        volume.remove.assert_not_called()

    def test_missing_or_wrong_daemon_proof_set_prevents_placement_effects(self):
        for supplied in (None, qualified_images(daemon_id="another-daemon")):
            with self.subTest(supplied=supplied), self.assertRaises(FixtureBoundaryFailure):
                OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
                    "daemon-a", qualified_images=supplied)
        self.network.connect.assert_not_called()
        self.network.disconnect.assert_not_called()
        self.engine.containers.create.assert_not_called()

    def test_manifest_execution_identity_is_recorded_before_runtime_dispatch(self):
        proof_set = qualified_images("manifest-valued")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ownership.json"
            placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
                "daemon-a", record_path=path, qualified_images=proof_set)
            request = replacement_record().request
            runtime = Mock()
            def execute(actual):
                stored = json.loads(path.read_text())
                self.assertEqual(stored["qualified_images"], proof_set.descriptor())
                for role, proof in proof_set.images.items():
                    self.assertEqual(stored["qualified_images"]["images"][role]["execution_id"],
                                     IMAGES[role]["reference"].split("@")[1])
                    self.assertEqual(stored["qualified_images"]["images"][role]["config_digest"],
                                     IMAGES[role]["image_id"])
                raise FixtureBoundaryFailure("simulated provider stop")
            runtime.execute.side_effect = execute
            with self.assertRaises(FixtureBoundaryFailure):
                RecordedDockerRuntime(runtime, resources=placement).execute(request)
            runtime.execute.assert_called_once_with(request)

    def test_proof_record_persistence_failure_prevents_runtime_dispatch(self):
        request = replacement_record().request
        runtime = Mock()
        with patch.object(self.placement, "persist", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                RecordedDockerRuntime(runtime, resources=self.placement).execute(request)
        runtime.execute.assert_not_called()
        self.network.connect.assert_not_called()
        self.network.disconnect.assert_not_called()

    def owned_identity_candidates(self):
        proofs = qualified_images("manifest-valued")
        placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
            "daemon-a", qualified_images=proofs)
        candidates = []
        for identity, node, role in (("c" * 64, "api", "hello_a"), ("d" * 64, "api-y", "hello_b")):
            container = Mock()
            container.id = identity
            container.labels = {PREFIX + "workspace": "workspace-a", PREFIX + "runtime": "docker",
                                PREFIX + "node": node, PREFIX + "kind": "container"}
            container.attrs = {"Image": proofs.images[role].execution_id,
                               "Config": {"User": IMAGES[role]["user"]}}
            placement.record["containers"][identity] = {"node": node, "image_role": role}
            candidates.append(container)
        self.engine.containers.list.return_value = candidates
        by_id = {container.id: container for container in candidates}
        self.engine.containers.get.side_effect = by_id.__getitem__
        self.engine.networks.list.return_value = []
        self.engine.volumes.list.return_value = []
        # An image lookup here would silently replace the original expectation.
        self.engine.images.get.side_effect = AssertionError("cleanup must not resolve image identity")
        self.sdk.inspect_image.side_effect = AssertionError("cleanup must not inspect replacement image")
        return placement, candidates

    def test_cleanup_uses_captured_manifest_execution_identity_without_resolving_again(self):
        placement, candidates = self.owned_identity_candidates()
        selected = placement.cleanup_candidates()
        self.assertEqual(selected["containers"], candidates)
        self.engine.images.get.assert_not_called()
        self.sdk.inspect_image.assert_not_called()

    def test_late_image_mismatch_prevents_all_removal_and_detachment(self):
        from docker_image_update_placement import dispose_fixture
        placement, candidates = self.owned_identity_candidates()
        candidates[-1].attrs["Image"] = IMAGES["hello_b"]["image_id"]
        with patch.object(placement, "detach") as detach:
            with self.assertRaises(FixtureBoundaryFailure):
                dispose_fixture(placement)
            detach.assert_not_called()
        for container in candidates:
            container.remove.assert_not_called()
        self.network.remove.assert_not_called()
        self.network.disconnect.assert_not_called()
        self.engine.volumes.get.assert_not_called()
        self.engine.images.get.assert_not_called()

    def test_missing_or_mutated_map_and_changed_daemon_preserve_every_candidate(self):
        from docker_image_update_placement import dispose_fixture
        for failure in ("missing-map", "changed-map", "changed-daemon"):
            with self.subTest(failure=failure):
                self.engine.info.return_value = {"ID": "daemon-a"}
                placement, candidates = self.owned_identity_candidates()
                if failure == "missing-map":
                    placement.record.pop("qualified_images")
                elif failure == "changed-map":
                    placement.record["qualified_images"]["images"]["hello_a"]["execution_id"] = IMAGES["hello_a"]["image_id"]
                else:
                    self.engine.info.return_value = {"ID": "foreign-daemon"}
                runtime = Mock()
                with self.assertRaises(FixtureBoundaryFailure):
                    RecordedDockerRuntime(runtime, resources=placement).execute(replacement_record().request)
                runtime.execute.assert_not_called()
                with patch.object(placement, "detach") as detach:
                    with self.assertRaises(FixtureBoundaryFailure):
                        dispose_fixture(placement)
                    detach.assert_not_called()
                for container in candidates:
                    container.remove.assert_not_called()
        self.network.remove.assert_not_called()
        self.network.disconnect.assert_not_called()

    def test_manifest_container_result_is_checked_before_recording_incarnation(self):
        proof_set = qualified_images("manifest-valued")
        placement = OwnedControllerPlacement(self.engine, self.sdk, "workspace-a", "b" * 64,
            "daemon-a", qualified_images=proof_set)
        placement.network_id = self.network.id
        record = replacement_record()
        container = Mock()
        container.id = "d" * 64
        container.labels = {PREFIX + "workspace": "workspace-a", PREFIX + "runtime": "docker",
                            PREFIX + "node": "api", PREFIX + "kind": "container"}
        container.attrs = {"Image": proof_set.images["hello_b"].execution_id,
                           "Config": {"User": IMAGES["hello_b"]["user"]}}
        self.engine.containers.get.return_value = container
        self.sdk.inspect_container.return_value = SimpleNamespace(container_id=container.id, running=True,
            network_attachments=(SimpleNamespace(network_id=self.network.id),))
        record = replace(record, result=replace(record.result,
            evidence={**record.result.evidence, "container": container.id, "runtime_id": "docker"}))
        placement.observed(record)
        self.assertEqual(placement.record["containers"][container.id],
                         {"node": "api", "image_role": "hello_b"})
        wrong = Mock()
        wrong.id = "e" * 64
        wrong.labels = container.labels
        wrong.attrs = {**container.attrs, "Image": IMAGES["hello_b"]["image_id"]}
        self.engine.containers.get.return_value = wrong
        self.sdk.inspect_container.return_value = SimpleNamespace(container_id=wrong.id, running=True,
            network_attachments=(SimpleNamespace(network_id=self.network.id),))
        wrong_record = replace(record, result=replace(record.result,
            evidence={**record.result.evidence, "container": wrong.id}))
        with self.assertRaises(FixtureBoundaryFailure):
            placement.observed(wrong_record)
        self.assertNotIn(wrong.id, placement.record["containers"])


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
