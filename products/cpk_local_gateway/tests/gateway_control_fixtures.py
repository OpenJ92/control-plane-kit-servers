"""Synthetic gateway-owned trust and complete topology; no external effects."""
from dataclasses import replace
from types import SimpleNamespace

import httpx
import jwt
import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSpec, BlockSockets
from control_plane_kit_core.public_ingress import NamedPublicIngress, PublicIngressTarget, IngressAuthorityReference
from control_plane_kit_core.topology import DeploymentGraph, Node, RuntimeRecord, validate_graph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, RuntimeKind
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)
from health_relay_fixtures import World

CONTROL_PATH = "/etc/cpk/gateway/control.json"


def configuration(api, world):
    target = replace(world.target, node_id=world.transit.gateway,
        provider_socket_name=replace(world.target.provider_socket_name, value="control"))
    return api.GatewayControlConfiguration(target=target, runtime_id=world.runtime,
        declaration=api.gateway_control_declaration(), surface_issuer="surface-issuer",
        surface_keys=WorkloadNodeControlSurfaceReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (world.static_key,)),
        health_issuer="own-health-issuer", health_keys=WorkloadNodeHealthReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (world.key,)))


def fixture(api, world=None):
    from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
        GatewayHealthRelayConfiguration, gateway_health_target_binding, gateway_health_relay_configuration_artifact,
    )
    from control_plane_kit_servers_cpk_local_gateway.health_relay import GatewayHealthRelay
    from control_plane_kit_servers_cpk_local_gateway.health_transit_verification import gateway_health_transit_verifier_from_artifact
    world = World() if world is None else world
    config = configuration(api, world)
    trust_api, _ = world.transit.api()
    trust = world.transit.artifact(trust_api)
    targets = GatewayHealthRelayConfiguration(config.target.workspace_id, world.transit.gateway, world.runtime,
        (gateway_health_target_binding(target_id="database-management", target=world.target,
            runtime_id=world.runtime, runtime_contract=world.contract, hostname="wrapped-db"),))
    outbound = FailingDownstream()
    relay = GatewayHealthRelay(targets, gateway_health_transit_verifier_from_artifact(trust),
        clock=lambda:world.now, transport=outbound)
    artifacts = (trust, gateway_health_relay_configuration_artifact(targets),
                 api.gateway_control_configuration_artifact(config))
    return SimpleNamespace(world=world, config=config, relay=relay, outbound=outbound, artifacts=artifacts)


class FailingDownstream(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(503)


def credential(value, *, static=False, kind=core.NodeHealthReadKind.READINESS,
               request_changes=None, private=None, issued=100, expires=200):
    config, world = value.config, value.world
    if static:
        request = core.NodeControlSurfaceReadRequest(config.target, core.NodeControlSurfaceReadKind.CAPABILITIES,
            config.declaration.identity(), "own-surface")
        family, issuer = config.surface_keys, config.surface_issuer
        grant_type, profile = core.DelegatedWorkloadNodeControlSurfaceReadGrant, core.DelegatedWorkloadNodeControlSurfaceReadGrantProfile.V1
        claim, typ = "workload_node_control_surface_read", "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
        private = world.static_private if private is None else private
    else:
        request = core.NodeHealthReadRequest(config.target, config.runtime_id, kind, config.declaration.identity(), "own-health")
        family, issuer = config.health_keys, config.health_issuer
        grant_type, profile = core.DelegatedWorkloadNodeHealthReadGrant, core.DelegatedWorkloadNodeHealthReadGrantProfile.V1
        claim, typ = "workload_node_health_read", "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
        private = world.private if private is None else private
    request = replace(request, **(request_changes or {}))
    grant = grant_type(profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=family.purpose, issuer=issuer, key_id=family.public_keys[0].key_id,
        audience=core.workload_node_control_audience(config.target), target=request.target, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=issued, not_before=issued, expires_at=expires,
        jti="own-health-fixture", **({} if static else {"runtime_id":request.runtime_id}))
    token = jwt.encode(dict(iss=issuer, aud=grant.audience, iat=issued, nbf=issued, exp=expires,
        jti=grant.jti, **{claim:grant.descriptor()}), private, algorithm="EdDSA",
        headers={"kid":grant.key_id, "typ":typ})
    return request, token


def topology(value, contract):
    """Copy the actual complete contract into graph facts without weakening it."""
    world = value.world
    nodes = {}
    for node_id, selected in ((world.transit.gateway.value, contract), (world.target.node_id.value, world.contract)):
        ports = {port.provider_socket:port.container_port for port in selected.provider_ports}
        nodes[node_id] = Node(node_id, BlockFamily.APPLICATION,
            BlockSpec(node_id, capabilities=selected.capabilities, verification=selected.verification,
                control_surfaces=selected.control_surfaces, gateway_transit=selected.gateway_transit),
            "container-server", world.runtime.value, selected.sockets,
            configuration_artifacts=selected.configuration_artifacts,
            endpoints={provider.name:Endpoint(LiteralAddress(
                ("http" if provider.protocol.value == "http" else "postgres") + "://" + node_id + ":" + str(ports[provider.name])),
                provider.protocol) for provider in selected.sockets.providers})
    nodes["connector"] = Node("connector", BlockFamily.APPLICATION, BlockSpec("connector"),
        "container-server", world.runtime.value, BlockSockets())
    graph = DeploymentGraph("gateway-self-health", nodes=nodes,
        runtimes={world.runtime.value:RuntimeRecord(world.runtime.value, RuntimeKind.DOCKER, tuple(nodes),
            management=core.RuntimeManagement(world.transit.gateway.value, "management"))},
        public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("synthetic-authority"),
            PublicIngressTarget(world.transit.gateway.value, "control"), "connector", "gateway.example.invalid"),))
    return validate_graph(DeploymentGraph("gateway-self-health")), validate_graph(graph)
