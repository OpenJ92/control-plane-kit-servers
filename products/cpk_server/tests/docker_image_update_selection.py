"""Public exact-choice fixture and genuine Docker recipient receipt assertions."""
import asyncio
from dataclasses import replace
import json
from uuid import uuid4

from control_plane_kit_core.secret_installation import secret_installation_receipt_for_result
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_interpreters.docker.configuration import _container_incarnation_fingerprint
from control_plane_kit_servers_cpk_server.client.transport import ClientTransportError

from docker_image_update_material import APPLICATION_REFERENCE, APPLICATION_INTENT, selected_metadata
from docker_image_update_ports import FixtureBoundaryFailure
from receiver_acceptance_operations import utc_now


def consumer_graph(graph, document):
    contract = document.product.runtime_contract
    node = graph.node("api")
    # Receiver configuration remains authored by its existing owner. Only this
    # fixture's independent application-settings slot comes from the new product.
    artifacts = tuple(value for value in node.configuration_artifacts
        if value.artifact_id != "application-settings") + tuple(
        value for value in contract.configuration_artifacts if value.artifact_id == "application-settings")
    return graph.update_node(replace(node, metadata=selected_metadata(document),
        secret_deliveries=contract.secret_deliveries, configuration_artifacts=artifacts))


class PublicSecretChoices:
    def __init__(self, transport, workspace, runtime):
        self.transport, self.workspace, self.runtime = transport, workspace, runtime
        self.accepted = []

    async def call(self, route, payload=None):
        return await asyncio.to_thread(self.transport.call, route,
            path_parameters={"workspace_id": self.workspace}, payload=payload or {}, credential_role="operator")

    async def register(self):
        provider = await self.call("command.secret-provider.register", {
            "provider_id": "application-secrets", "display_name": "Owned application fixture",
            "provider_kind": "control-plane-kit-secrets", "endpoint_reference": "application-secrets",
            "credential_reference": "secret://bootstrap/application-secrets/client-token",
            "allowed_reference_prefixes": ["secret://application-secrets/api"],
            "allowed_intents": [APPLICATION_INTENT.value], "admitted_at": utc_now(),
            "metadata": {}, "idempotency_key": "application-provider"})
        reference = await self.call("command.secret-reference.register", {
            "reference": APPLICATION_REFERENCE.reference_id,
            "provider_registration_id": provider["registration_id"],
            "allowed_intents": [APPLICATION_INTENT.value], "admitted_at": utc_now(),
            "metadata": {}, "idempotency_key": "application-reference"})
        assert provider["status"] == reference["status"] == "active"

    async def select(self, graph, version, *, refused=False):
        before = (await self.call("read.workspace"))["workspace"]
        session = await self.call("command.operation-session.start", {
            "workspace_id": self.workspace, "title": "Select exact application version",
            "metadata": {}, "idempotency_key": str(uuid4())})
        names = ("current_graph_id", "current_realized_projection_id", "desired_graph_id",
            "desired_realized_projection_id", "desired_graph_revision")
        payload = {"session_id": session["session_id"], "graph": DEFAULT_GRAPH_CODEC.encode(graph),
            "explicit_secret_choices": {"api": [{"reference_id": APPLICATION_REFERENCE.reference_id,
                "intent": APPLICATION_INTENT.value, "version_id": version}]},
            "receiver_lifecycle": {key: before[key] for key in names},
            **{"expected_" + key: before[key] for key in names[2:]}, "idempotency_key": str(uuid4())}
        calls = len(self.runtime.completed)
        try:
            response = await self.call("command.desired-graph.set", payload)
        except ClientTransportError:
            if not refused:
                raise
            after = (await self.call("read.workspace"))["workspace"]
            assert all(after[key] == before[key] for key in names)
            assert len(self.runtime.completed) == calls
            return None
        assert not refused, "unavailable explicit version was accepted"
        self.accepted.append((payload, response))
        current = await self.call("read.desired-graph")
        selected = DEFAULT_GRAPH_CODEC.decode(current["graph_descriptor"])
        selection, = selected.node("api").secret_selections
        assert selection.version_id == version and selection.reference == APPLICATION_REFERENCE
        assert len(self.runtime.completed) == calls
        return selected

    async def replay(self):
        calls = len(self.runtime.completed)
        for payload, expected in self.accepted:
            assert await self.call("command.desired-graph.set", payload) == expected
        assert len(self.runtime.completed) == calls


def require_selected_recipient(record, version, prior_id, current_id):
    material, = record.request.products
    selection, = material.secret_selections
    assert selection.version_id == version and selection.reference == APPLICATION_REFERENCE
    receipt = secret_installation_receipt_for_result(record.request, record.result)
    if receipt is None:
        raise FixtureBoundaryFailure("actual recipient receipt is absent")
    assert receipt.disposition.value == "replaced"
    assert receipt.prior_realization_fingerprint == _container_incarnation_fingerprint(prior_id)
    assert receipt.current_realization_fingerprint == _container_incarnation_fingerprint(current_id)
    # No fixture plaintext or plaintext digest is returned by this assertion.
    json.dumps(receipt.descriptor())
    return receipt
