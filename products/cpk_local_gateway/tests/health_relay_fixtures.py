"""Synthetic request pairs and real SDK receiver; no provider, Docker or host I/O."""
from dataclasses import replace
from types import SimpleNamespace
import json

import httpx
import jwt
from fastapi import FastAPI
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, BlockSpec, ProviderSocket
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.types import Protocol, BlockFamily, RuntimeKind
from control_plane_kit_core.topology import DeploymentGraph, Node, RuntimeRecord, validate_graph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.planning import compile_graph_activity_plan, ObserveNodeHealth
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from control_plane_kit_operations.runtime_management_targets import project_management_health_target
from control_plane_kit_server_sdk.fastapi import install_cpk_control_routes
from control_plane_kit_server_sdk.health import WorkloadNodeHealthReadDispatcher
from control_plane_kit_server_sdk.verification import (
    Ed25519WorkloadNodeHealthReadVerifier, Ed25519WorkloadNodeControlSurfaceReadVerifier,
)
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeHealthReadVerifierKeySet, AtomicWorkloadNodeHealthReadVerifierKeySet,
    WorkloadNodeControlSurfaceReadVerifierKeySet, AtomicWorkloadNodeControlSurfaceReadVerifierKeySet,
)
import test_health_transit as transit


def wire(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


class World:
    def __init__(self):
        self.transit = transit.GatewayHealthTransitTests()
        self.transit.setUp()
        self.target = replace(self.transit.target, node_id=replace(self.transit.target.node_id, value="wrapped-db"))
        self.runtime = self.transit.runtime
        self.declaration = self.transit.declaration
        self.request = replace(self.transit.request, target=self.target)
        self.private = Ed25519PrivateKey.generate()
        self.key = self.transit.public(self.private, "workload-health")
        self.static_private = Ed25519PrivateKey.generate()
        self.static_key = self.transit.public(self.static_private, "workload-surface")
        self.now = 150
        self.callbacks = []
        self.outcome = core.NodeHealthReadOutcome.HEALTHY
        self.contract = ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("application", Protocol.HTTP),
                ProviderSocket("sql", Protocol.POSTGRES), ProviderSocket("management", Protocol.HTTP))),
            provider_ports=(ProviderRuntimePort("application", 8080), ProviderRuntimePort("sql", 5432),
                ProviderRuntimePort("management", 8087)), control_surfaces=(self.declaration.surface,),
            capabilities=(CapabilityName.NODE_CONTROLLABLE, CapabilityName.HEALTH_CHECKABLE))

    def pair(self, request=None, *, workload_private=None, transit_changes=None):
        request = self.request if request is None else request
        grant = core.DelegatedWorkloadNodeHealthReadGrant(
            profile=core.DelegatedWorkloadNodeHealthReadGrantProfile.V1,
            canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
            issuer="workload-issuer", key_id=self.key.key_id,
            audience=core.workload_node_control_audience(self.target), target=request.target,
            runtime_id=request.runtime_id, kind=request.kind, declaration_identity=request.declaration_identity,
            request_id=request.request_id, request_digest=request.canonical_digest(),
            issued_at=100, not_before=110, expires_at=200, jti="workload-jti")
        token = jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at,
            nbf=grant.not_before, exp=grant.expires_at, jti=grant.jti,
            workload_node_health_read=grant.descriptor()),
            self.private if workload_private is None else workload_private, algorithm="EdDSA",
            headers={"typ":"CPK-WORKLOAD-NODE-HEALTH-READ+JWT", "kid":self.key.key_id})
        signed = self.transit.token(self.transit.grant(request, **(transit_changes or {}))).decode()
        return signed, token

    def envelope(self, request=None, *, workload=None):
        request = self.request if request is None else request
        _, token = self.pair(request)
        return dict(profile="cpk-gateway-health-relay-request.v1", target_id="database-management",
            attempt_id="attempt-a", request=request.descriptor(),
            workload_credential=token if workload is None else workload)

    def receiver(self):
        audience = core.workload_node_control_audience(self.target)
        verifier = Ed25519WorkloadNodeHealthReadVerifier(
            AtomicWorkloadNodeHealthReadVerifierKeySet(WorkloadNodeHealthReadVerifierKeySet(
                core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (self.key,))),
            expected_issuer="workload-issuer", expected_audience=audience, clock=lambda:self.now)
        static = Ed25519WorkloadNodeControlSurfaceReadVerifier(
            AtomicWorkloadNodeControlSurfaceReadVerifierKeySet(WorkloadNodeControlSurfaceReadVerifierKeySet(
                core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (self.static_key,))),
            expected_issuer="surface-issuer", expected_audience=audience, clock=lambda:self.now)
        def callback(kind):
            self.callbacks.append(kind)
            return self.outcome
        app = FastAPI()
        install_cpk_control_routes(app, target=self.target, declaration=self.declaration,
            surface_read_verifier=static, health_dispatcher=WorkloadNodeHealthReadDispatcher(
                target=self.target, runtime_id=self.runtime, declaration=self.declaration, verifier=verifier,
                liveness=lambda:callback(core.NodeHealthReadKind.LIVENESS),
                readiness=lambda:callback(core.NodeHealthReadKind.READINESS)))
        return app

    def projection(self):
        gateway_id = self.transit.gateway.value
        gateway_surface = core.WorkloadNodeControlSurfaceDescriptor(
            self.transit.ref(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"), (),
            health_reads=(core.NodeHealthReadKind.READINESS,))
        gateway_sockets = BlockSockets(providers=(ProviderSocket("control", Protocol.HTTP),))
        nodes = {
            gateway_id: Node(gateway_id, BlockFamily.APPLICATION,
                BlockSpec(gateway_id, capabilities=self.contract.capabilities, control_surfaces=(gateway_surface,), gateway_transit=
                    core.GatewayTransitDeclaration("control", core.GatewayTransitProtocol.NODE_HEALTH_READ_V1)),
                "container-server", self.runtime.value, gateway_sockets,
                endpoints={"control":Endpoint(LiteralAddress("http://gateway:8000"), Protocol.HTTP)}),
            self.target.node_id.value: Node(self.target.node_id.value, BlockFamily.APPLICATION,
                BlockSpec(self.target.node_id.value, capabilities=self.contract.capabilities, control_surfaces=(self.declaration.surface,)),
                "container-server", self.runtime.value, self.contract.sockets,
                endpoints={name:Endpoint(LiteralAddress(address), protocol) for name,address,protocol in (
                    ("management", "http://wrapped-db:8087", Protocol.HTTP),
                    ("application", "http://wrapped-db:8080", Protocol.HTTP),
                    ("sql", "postgres://wrapped-db:5432", Protocol.POSTGRES))}),
            "connector":Node("connector", BlockFamily.APPLICATION, BlockSpec("connector"),
                "container-server", self.runtime.value, BlockSockets()),
        }
        graph = DeploymentGraph("relay-fixture", nodes=nodes,
            runtimes={self.runtime.value:RuntimeRecord(self.runtime.value, RuntimeKind.DOCKER, tuple(nodes),
                management=core.RuntimeManagement(gateway_id, "management"))},
            public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("synthetic-authority"),
                PublicIngressTarget(gateway_id, "control"), "connector", "management.example.invalid"),))
        desired = validate_graph(graph)
        current = validate_graph(DeploymentGraph("relay-fixture"))
        desired.require_valid()
        current.require_valid()
        plan = compile_graph_activity_plan(current, desired)
        if not plan.ready_for_execution:
            raise ValueError("synthetic management plan is not ready")
        activity = next(item for item in plan.activities if type(item.operation) is ObserveNodeHealth
            and item.operation.node_id == self.target.node_id.value)
        result = project_management_health_target(plan, activity.activity_id, activity.operation, current, desired)
        return SimpleNamespace(graph=graph, projected=result)


class ReceiverTransport(httpx.AsyncBaseTransport):
    def __init__(self, app):
        self.inner = httpx.ASGITransport(app=app)
        self.requests = []
        self.closed = False

    async def handle_async_request(self, request):
        self.requests.append(request)
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        self.closed = True
        await self.inner.aclose()
