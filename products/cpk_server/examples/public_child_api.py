"""The narrow public API steps used by the complete-child acceptance recipe.

Run in the ordinary Docker controller with explicit ClientProfiles. This module
has no Docker/SQL/provider access and never approves a plan implicitly. The
owning fixture supplies the external root, initial custody and controlled parent
restart under its separately reviewed action plan.
"""

import json
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime, SocketConnection
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductDescriptorCodec, ProductInstanceConfiguration, instantiate_product
from control_plane_kit_core.public_ingress import PublicIngressTarget
from control_plane_kit_core.topology import DeploymentGraph, GraphDescriptorCodec, compile_topology
from control_plane_kit_core.verification import HttpCheck, VerificationContract
from control_plane_kit_servers_cpk_server.client import SavedDesiredRevision
from control_plane_kit_servers_cpk_server.client.installation import (
    ChildInstallationHold, child_installation_document, initialize_child_workspace,
)


def _read(client, route, **coordinates):
    return client.transport.call(route,
        path_parameters={"workspace_id": client.profile.workspace_id, **coordinates},
        payload={}, credential_role="operator")


def parent_tracking(client, operation_ref):
    """Reconnect-safe authoritative coordinates, independent of process memory."""
    status = client.status(operation_ref)
    if (status.status != "converged" or status.execution != "succeeded"
            or status.advancement != "advanced" or not status.plan_id or not status.run_id):
        raise ChildInstallationHold("parent operation is not verified converged")
    detail = _read(client, "read.plan-detail", plan_id=status.plan_id).get("plan", {})
    current = _read(client, "read.current-graph")
    workspace = _read(client, "read.workspace").get("workspace", {})
    if (workspace.get("workspace_id") != client.profile.workspace_id
            or detail.get("plan_id") != status.plan_id
            or current.get("graph_id") != detail.get("desired_graph_id")
            or current.get("realized_projection_id") != detail.get("desired_realized_projection_id")
            or workspace.get("current_graph_id") != current.get("graph_id")
            or workspace.get("current_realized_projection_id") != current.get("realized_projection_id")):
        raise ChildInstallationHold("parent history does not match realized child deployment")
    # The existing report owns run/history pagination and correlation, not this
    # recipe. Persist it as evidence without treating it as a fresh child probe.
    report = client.report([operation_ref]).descriptor()
    rows = report.get("operations", [])
    if len(rows) != 1 or rows[0].get("operation_ref") != operation_ref:
        raise ChildInstallationHold("parent history report does not identify the operation")
    history = rows[0]
    if (any(history.get(name, {}).get("state") != "observed" for name in ("plan", "session", "approval", "runs"))
            or history.get("association", {}).get("state") not in {"matched", "not-applicable"}):
        raise ChildInstallationHold("parent history association is not verified")
    runs = history["runs"].get("data", [])
    run = next((item for item in runs if item.get("run_id") == status.run_id), None)
    if (run is None or run.get("status") != "succeeded"
            or run.get("events", {}).get("state") not in {"observed", "truncated"}
            or not run["events"].get("data")):
        raise ChildInstallationHold("parent successful run history is unavailable")
    return {"operation_ref": operation_ref, "workspace_id": client.profile.workspace_id,
            "plan_id": status.plan_id, "run_id": status.run_id,
            "current_graph_id": current["graph_id"],
            "current_realized_projection_id": current["realized_projection_id"],
            "history": history, "report": report}


def initialize_after_parent(installation, *, parent, prepared, child, setup, state_directory):
    """Require observed parent convergence before any child initialization call."""
    expected = child_installation_document(installation, child_workspace_id=child.profile.workspace_id)
    if (parent.profile.workspace_id != expected["parent_workspace_id"]
            or prepared.workspace_id != parent.profile.workspace_id or not prepared.plan_id):
        raise ChildInstallationHold("parent preparation does not identify this installation")
    tracking = parent_tracking(parent, prepared.operation_ref)
    if tracking["plan_id"] != prepared.plan_id:
        raise ChildInstallationHold("parent operation plan differs from reviewed preparation")
    # Public graph reads redact protected bindings. Use the existing client's
    # validated original-input digest and returned plan coordinates to bind the
    # exact composed graph; node names alone cannot establish identity.
    invocation = parent.journal.read(prepared.operation_ref)
    expected_bytes = json.dumps(expected["graph"], sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode()
    coordinates = invocation.get("coordinates", {})
    target = invocation.get("target", {})
    if (invocation.get("desired", {}).get("sha256") != sha256(expected_bytes).hexdigest()
            or target.get("workspace_id") != parent.profile.workspace_id
            or target.get("endpoint_sha256") != parent.profile.target_digest
            or coordinates.get("plan_id") != prepared.plan_id
            or coordinates.get("desired_graph_id") != tracking["current_graph_id"]
            or coordinates.get("desired_realized_projection_id") != tracking["current_realized_projection_id"]):
        raise ChildInstallationHold("parent operation is not bound to the exact intended child graph")
    initialized = initialize_child_workspace(installation, child=child, setup=setup,
                                             state_directory=state_directory)
    return {"parent": tracking, "child": initialized}


def gateway_signer_product(selected_cpk_document):
    """Select an existing process option without changing its image/defaults."""
    product = selected_cpk_document.product
    environment = {value.name: value for value in product.runtime_contract.public_environment}
    if environment.get('CPK_PRODUCT_MATERIAL_RESOLVER') != PublicStaticEnvironmentBinding(
            'CPK_PRODUCT_MATERIAL_RESOLVER', 'provider'):
        raise ChildInstallationHold('gateway signer requires the provider-backed CPK product')
    environment['CPK_GATEWAY_PROBE_SIGNER'] = PublicStaticEnvironmentBinding('CPK_GATEWAY_PROBE_SIGNER', 'ed25519')
    return ProductDescriptorCodec().encode_document(replace(product, runtime_contract=replace(
        product.runtime_contract, public_environment=tuple(environment.values()))))


def child_application_graph(installation, child_workspace_id, *, hello_product, router_product,
                            gateway_product, connector_product, ingress, delegation_authority):
    """Declared products, target/delegation and ingress; no provider calls."""
    from control_plane_kit_servers_hello_server.server import render_hello

    prefix = installation.installation_id
    hello_id, router_id, gateway_id = (prefix + suffix for suffix in ('-hello', '-router', '-gateway'))
    if (ingress.target != PublicIngressTarget(gateway_id, 'control')
            or ingress.connector_node_id != prefix + '-gateway-connector'
            or delegation_authority.delegate_node_id != gateway_id
            or delegation_authority.purpose is not DelegationKeyPurpose.GATEWAY_PROBE):
        raise ChildInstallationHold('application gateway bindings differ from the intended composition')
    message, color = 'Hello from the child control plane', 'blue'
    hello_config = ProductInstanceConfiguration.from_contract(hello_product.runtime_contract)
    hello_config = replace(hello_config, public_environment=tuple(
        PublicStaticEnvironmentBinding(value.name, message if value.name == 'HELLO_MESSAGE' else color)
        if value.name in {'HELLO_MESSAGE', 'HELLO_COLOR'} else value
        for value in hello_config.public_environment))
    children = (
        instantiate_product(hello_product, hello_id, hello_config),
        instantiate_product(router_product, router_id, ProductInstanceConfiguration.from_contract(router_product.runtime_contract)),
        instantiate_product(gateway_product, gateway_id, ProductInstanceConfiguration.from_contract(gateway_product.runtime_contract)),
        instantiate_product(connector_product, ingress.connector_node_id,
                            ProductInstanceConfiguration.from_contract(connector_product.runtime_contract)),
        SocketConnection(hello_id, 'internal', router_id, 'active'),
        SocketConnection(router_id, 'internal', gateway_id, 'target-http'),
    )
    graph = compile_topology(DeploymentTopology(child_workspace_id,
        DockerRuntime(runtime_id=prefix + '-proof', network_name='cpk-' + prefix + '-proof',
                      authority_ref=installation.runtime_access.authority_ref, children=children),
        public_ingresses=(ingress,), delegation_authorities=(delegation_authority,)))
    router = graph.node(router_id)
    check = HttpCheck(check_id='root-response', provider_socket='internal', path='/',
                      expected_body_sha256=sha256(render_hello(message, color)).hexdigest())
    return graph.update_node(replace(router, block_spec=replace(router.block_spec,
        verification=VerificationContract((*router.block_spec.verification.checks, check)))))


def verify_gateway_probe_response(response, *, expected, request, not_before, not_after):
    """Fresh status/size evidence, separate from deployment body-hash proof."""
    def require(condition):
        if not condition:
            raise ChildInstallationHold('fresh gateway probe evidence does not match the requested application')

    def coordinate(value):
        require(isinstance(value, str) and 0 < len(value.encode()) <= 256)
        return value

    def timestamp(value):
        require(isinstance(value, str) and len(value) <= 64)
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None)
        return parsed

    try:
        require(response.get('replayed') is False)
        attempt = response['gateway_probe']
        fields = ('workspace_id', 'current_graph_id', 'gateway_node_id', 'gateway_runtime_id', 'request_id', 'actor_id')
        for field in fields:
            require(attempt.get(field) == coordinate(expected[field]))
        require(attempt.get('access_path') == 'named-public-ingress'
                and attempt.get('probe_kind') == request.kind.value == 'http-status'
                and attempt.get('target_id') == request.target_id.value
                and attempt.get('request_digest') == request.canonical_digest().value
                and attempt.get('status') == 'succeeded' and attempt.get('result_code') == 'probe-succeeded')
        requested, completed = timestamp(attempt['requested_at']), timestamp(attempt['completed_at'])
        require(not_before.tzinfo is not None and not_after.tzinfo is not None
                and not_before <= requested <= completed <= not_after)
        grant = attempt['grant']
        require(grant.get('issuer') == expected['issuer'] and grant.get('key_id') == expected['key_id']
                and grant.get('audience') == f"gateway:{expected['workspace_id']}:{expected['gateway_node_id']}")
        issued, expires = grant['issued_at'], grant['expires_at']
        require(type(issued) is int and type(expires) is int
                and int(not_before.timestamp()) <= issued <= int(not_after.timestamp())
                and 0 < expires - issued <= 300 and issued <= completed.timestamp() < expires)
        coordinate(grant['jti'])
        evidence = attempt['evidence']
        require(set(evidence) == {'outcome', 'target_id', 'probe', 'http_status', 'body_size'}
                and evidence['outcome'] == 'passed' and evidence['target_id'] == request.target_id.value
                and evidence['probe'] == 'http-status' and type(evidence['http_status']) is int
                and evidence['http_status'] == 200 and type(evidence['body_size']) is int
                and 0 < evidence['body_size'] <= 16_384)
        return {**{field: attempt[field] for field in fields}, 'probe_id': coordinate(attempt['probe_id']),
            'access_path': attempt['access_path'], 'probe_kind': attempt['probe_kind'],
            'target_id': attempt['target_id'], 'request_digest': attempt['request_digest'],
            'requested_at': attempt['requested_at'], 'completed_at': attempt['completed_at'],
            'grant': {field: grant[field] for field in ('issuer', 'key_id', 'audience', 'jti', 'issued_at', 'expires_at')},
            'status': 'succeeded', 'result_code': 'probe-succeeded', 'evidence': dict(evidence)}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ChildInstallationHold('fresh gateway probe evidence could not be verified') from None


def prepare_saved_empty(client, *, graph_path: Path):
    """Save/select/read EMPTY desired state before preparing that saved revision.

    The caller separately inspects and supplies exact destructive approval to
    TopologyClient.apply. No runtime effect or retained deletion occurs here.
    """
    empty = GraphDescriptorCodec().encode(DeploymentGraph(client.profile.workspace_id))
    # This is a new invocation-owned, secret-free graph artifact. Refuse reuse.
    with graph_path.open("x", encoding="utf-8") as stream:
        json.dump(empty, stream, sort_keys=True, separators=(",", ":"))
    saved = client.draft_save(graph_path, title="Remove child installation").descriptor()
    if saved.get("status") != "recorded" or saved.get("workspace_id") != client.profile.workspace_id:
        raise ChildInstallationHold("empty desired revision was not saved")
    revision = saved.get("revision", {})
    source = SavedDesiredRevision(revision.get("draft_id"), revision.get("revision"))
    selected = client.draft_select(source.draft_id, source.revision).descriptor()
    if selected.get("status") != "recorded" or selected.get("revision") != revision:
        raise ChildInstallationHold("empty desired revision was not selected")
    detail = _read(client, "read.desired-topology-draft-revision",
                   draft_id=source.draft_id, revision=str(source.revision))
    desired = _read(client, "read.desired-graph")
    overview = _read(client, "read.operator-overview")
    draft = overview.get("graphs", {}).get("desired", {}).get("draft", {})
    if (detail.get("workspace_id") != client.profile.workspace_id
            or detail.get("draft_id") != source.draft_id or detail.get("revision") != source.revision
            or detail.get("graph_id") != revision.get("graph_id") or detail.get("graph_descriptor") != empty
            or desired.get("graph_id") != revision.get("graph_id") or desired.get("graph_descriptor") != empty
            or draft.get("state") != "selected" or draft.get("selected") != revision or draft.get("head") != revision):
        raise ChildInstallationHold("selected latest desired revision is not the saved empty graph")
    planned = client.plan(source, title="Deploy selected empty revision")
    return {"revision": revision, "prepared": planned}


def verify_empty_convergence(client, operation_ref, *, revision):
    """API convergence proves graph removal; it never claims retained data wiped."""
    tracking = parent_tracking(client, operation_ref)
    expected = GraphDescriptorCodec().encode(DeploymentGraph(client.profile.workspace_id))
    current = _read(client, "read.current-graph")
    desired = _read(client, "read.desired-graph")
    if (current.get("graph_id") != revision["graph_id"] or current.get("graph_descriptor") != expected
            or desired.get("graph_id") != revision["graph_id"] or desired.get("graph_descriptor") != expected):
        raise ChildInstallationHold("empty desired revision has not converged")
    return {"tracking": tracking, "compute_graph": "empty", "retained_data": "requires-explicit-accounting"}
