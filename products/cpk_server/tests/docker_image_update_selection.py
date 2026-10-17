"""Public exact-choice fixture and genuine Docker recipient receipt assertions."""
import asyncio
from dataclasses import replace
import json
from uuid import uuid4

from control_plane_kit_core.secret_installation import secret_installation_receipt_for_result
from control_plane_kit_core.secret_selections import author_secret_selections, SecretVersionSelection
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_operations.graph_authoring import GraphAuthoringError
from control_plane_kit_interpreters.docker.configuration import _container_incarnation_fingerprint
from control_plane_kit_servers_cpk_server.client.transport import ClientTransportError

from docker_image_update_material import APPLICATION_REFERENCE, APPLICATION_INTENT, selected_metadata
from docker_image_update_ports import FixtureBoundaryFailure


def consumer_graph(graph, document):
    contract = document.product.runtime_contract
    node = graph.node("api")
    # An image update carries all selected configuration and exact versions.
    return graph.update_node(replace(node, metadata=selected_metadata(document),
        secret_deliveries=contract.secret_deliveries,
        secret_selections=author_secret_selections(contract.secret_deliveries, previous=node.secret_selections)))


def application_content_graph(graph):
    node = graph.node("api")
    assert sum(value.artifact_id == "application-settings" for value in node.configuration_artifacts) == 1
    return graph.update_node(replace(node, configuration_artifacts=tuple(
        replace(value, content='{"revision":2}') if value.artifact_id == "application-settings" else value
        for value in node.configuration_artifacts)))


class ObservedMetadataReader:
    """Forward actual metadata IO; retain only requested coordinates and outcome."""
    def __init__(self, reader):
        self.reader, self.observations = reader, []

    def read_version(self, request):
        try:
            result = self.reader.read_version(request)
        except GraphAuthoringError:
            self.observations.append((request.workspace_id, request.selection, "refused"))
            raise
        self.observations.append((request.workspace_id, request.selection, "returned"))
        return result


class PublicSecretChoices:
    def __init__(self, transport, workspace, runtime, metadata):
        self.transport, self.workspace, self.runtime = transport, workspace, runtime
        self.metadata = metadata
        self.accepted = []

    def effect_counts(self):
        return len(self.runtime.completed), len(self.runtime.resources.record["intents"])

    async def call(self, route, payload=None, **coordinates):
        return await asyncio.to_thread(self.transport.call, route,
            path_parameters={"workspace_id": self.workspace, **coordinates},
            payload=payload or {}, credential_role="operator")

    async def selected_baseline(self, graph, version, pending):
        """Revise the genuine pending draft after public exact-version selection."""
        assert pending.expected_head_revision == 1
        calls = self.effect_counts()
        path = {"draft_id": pending.draft_id, "revision": "1"}
        first = await self.call("read.desired-topology-draft-revision", **path)
        original = await self.call("read.receiver-authoring-context", {"pending_draft": {
            "draft_id": pending.draft_id, "expected_head_revision": 1}})
        selected = await self.select(graph, version)
        session = await self.call("command.operation-session.start", {
            "workspace_id": self.workspace, "title": "Select consumer-bearing initial draft",
            "metadata": {}, "idempotency_key": str(uuid4())})
        names = ("current_graph_id", "current_realized_projection_id", "desired_graph_id",
            "desired_realized_projection_id", "desired_graph_revision")
        fresh = (await self.call("read.workspace"))["workspace"]
        second = await self.call("command.desired-topology-draft.revise", {
            "session_id": session["session_id"], "graph": DEFAULT_GRAPH_CODEC.encode(selected),
            "expected_head_revision": pending.expected_head_revision,
            "receiver_lifecycle": {key: fresh[key] for key in names},
            "idempotency_key": str(uuid4())}, draft_id=pending.draft_id)
        assert second["draft_id"] == pending.draft_id and second["revision"] == 2
        assert second["graph_id"] != first["graph_id"]
        fresh = (await self.call("read.workspace"))["workspace"]
        selection = await self.call("command.desired-topology-draft.select", {
            "session_id": session["session_id"], "revision": second["revision"],
            **{"expected_" + key: fresh[key] for key in names[2:]},
            "receiver_lifecycle": {key: fresh[key] for key in names},
            "idempotency_key": str(uuid4())}, draft_id=pending.draft_id)
        assert all(selection[key] == second[key] for key in ("workspace_id", "draft_id", "revision", "graph_id"))
        context = await self.call("read.receiver-authoring-context", {"pending_draft": {
            "draft_id": pending.draft_id, "expected_head_revision": second["revision"]}})
        assert context["current"] == original["current"]
        assert context["pending_draft"]["graph_id"] == second["graph_id"]
        after = (await self.call("read.workspace"))["workspace"]
        assert after["desired_graph_id"] == second["graph_id"]
        assert after["desired_realized_projection_id"] == selection["desired_realized_projection_id"]
        assert after["desired_graph_revision"] == selection["desired_graph_revision"]
        for before, current in zip(original["pending_draft"]["receivers"],
                context["pending_draft"]["receivers"], strict=True):
            assert current == {**before, "binding": {**before["binding"],
                "graph_id": second["graph_id"],
                "realized_projection_id": context["pending_draft"]["realized_projection_id"]}}
            assert current["origin"]["introducing_graph_id"] == first["graph_id"]
            assert current["origin"]["introducing_draft_id"] == pending.draft_id
        assert await self.call("read.desired-topology-draft-revision", **path) == first
        assert self.effect_counts() == calls and not self.transport.preparations
        print("selected consumer: public draft revision 1 preserved; actual revision 2 selected", flush=True)
        return selected, replace(pending, expected_head_revision=second["revision"])

    async def register(self):
        from receiver_acceptance_operations import utc_now
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
        calls = self.effect_counts()
        observations = len(self.metadata.observations)
        selection = SecretVersionSelection(APPLICATION_REFERENCE, APPLICATION_INTENT, version)
        try:
            response = await self.call("command.desired-graph.set", payload)
        except ClientTransportError:
            if not refused:
                raise
            after = (await self.call("read.workspace"))["workspace"]
            assert all(after[key] == before[key] for key in names)
            assert self.effect_counts() == calls
            assert self.metadata.observations[observations:] == [(self.workspace, selection, "refused")]
            return None
        assert not refused, "unavailable explicit version was accepted"
        assert self.metadata.observations[observations:] == [(self.workspace, selection, "returned")]
        self.accepted.append((payload, response))
        current = await self.call("read.desired-graph")
        assert current["graph_id"] == response["desired_graph_id"]
        # Public descriptors are redacted projections, not round-trip source.
        # Retain our declared input choice; actual subsequent requests/receipts
        # must independently prove that the public owner admitted and carried it.
        node = graph.node("api")
        selected = graph.update_node(replace(node, secret_selections=author_secret_selections(
            node.secret_deliveries, previous=node.secret_selections, explicit=(selection,))))
        assert self.effect_counts() == calls
        return selected

    async def replay(self):
        calls = self.effect_counts()
        observations = len(self.metadata.observations)
        for payload, expected in self.accepted:
            assert expected["replayed"] is False
            actual = await self.call("command.desired-graph.set", payload)
            assert actual["replayed"] is True
            assert actual == {**expected, "replayed": True}
        assert self.effect_counts() == calls
        assert len(self.metadata.observations) == observations


def require_selected_recipient(record, version, prior_id, current_id):
    material, = record.request.products
    selection, = material.secret_selections
    assert selection.version_id == version and selection.reference == APPLICATION_REFERENCE
    receipt = secret_installation_receipt_for_result(record.request, record.result)
    if receipt is None:
        raise FixtureBoundaryFailure("actual recipient receipt is absent")
    assert receipt.disposition.value == ("created" if prior_id is None else "replaced")
    assert receipt.prior_realization_fingerprint == (
        None if prior_id is None else _container_incarnation_fingerprint(prior_id))
    assert receipt.current_realization_fingerprint == _container_incarnation_fingerprint(current_id)
    # No fixture plaintext or plaintext digest is returned by this assertion.
    json.dumps(receipt.descriptor())
    return receipt
