"""Generated local test authority; never a deployable product default."""
from contextlib import contextmanager
from dataclasses import replace
from http.client import HTTPConnection
from threading import Thread
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import control_plane_kit_core as core
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)


def fixture(suffix="a"):
    from control_plane_kit_servers_http_active_router.configuration import RouterControlConfiguration, router_control_declaration
    def key(family):
        private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey(
            f"{family}-{suffix}", core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"),
        )
        return private, public
    static_private, static_key = key("static")
    health_private, health_key = key("health")
    roles = core.NodeControlGraphReferenceRole
    target = core.NodeControlTarget(
        core.NodeControlGraphReference(roles.WORKSPACE, f"workspace-{suffix}"),
        core.NodeControlGraphReference(roles.GRAPH_REVISION, f"revision-{suffix}"),
        core.NodeControlGraphReference(roles.NODE, f"router-{suffix}"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "internal"),
    )
    config = RouterControlConfiguration(
        target=target, runtime_id=core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}"),
        declaration=router_control_declaration(), surface_issuer=f"surface-{suffix}", health_issuer=f"health-{suffix}",
        surface_keys=WorkloadNodeControlSurfaceReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (static_key,)),
        health_keys=WorkloadNodeHealthReadVerifierKeySet(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (health_key,)),
    )
    return SimpleNamespace(config=config, static_private=static_private, health_private=health_private)


def token(f, *, static=False, kind=None, request_changes=None):
    config = f.config
    if static:
        request = core.NodeControlSurfaceReadRequest(
            config.target, kind or core.NodeControlSurfaceReadKind.CAPABILITIES,
            config.declaration.identity(), "surface-request",
        )
        grant_type = core.DelegatedWorkloadNodeControlSurfaceReadGrant
        profile = core.DelegatedWorkloadNodeControlSurfaceReadGrantProfile.V1
        family = config.surface_keys
        issuer, private = config.surface_issuer, f.static_private
        payload_key = "workload_node_control_surface_read"
        typ = "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
    else:
        request = core.NodeHealthReadRequest(config.target, config.runtime_id,
            kind or core.NodeHealthReadKind.LIVENESS, config.declaration.identity(), "health-request")
        grant_type = core.DelegatedWorkloadNodeHealthReadGrant
        profile = core.DelegatedWorkloadNodeHealthReadGrantProfile.V1
        family = config.health_keys
        issuer, private = config.health_issuer, f.health_private
        payload_key = "workload_node_health_read"
        typ = "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
    request = replace(request, **(request_changes or {}))
    grant = grant_type(
        profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=family.purpose, issuer=issuer, key_id=family.public_keys[0].key_id,
        audience=core.workload_node_control_audience(config.target), target=request.target, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=100, not_before=100, expires_at=200, jti="router-test",
        **({} if static else {"runtime_id": request.runtime_id}),
    )
    return jwt.encode({"iss": issuer, "aud": grant.audience, "iat":100, "nbf":100, "exp":200,
                       "jti":grant.jti, payload_key:grant.descriptor()}, private, algorithm="EdDSA",
                      headers={"kid":grant.key_id, "typ":typ})


@contextmanager
def running(test, f, environ=None, **kwargs):
    from control_plane_kit_servers_http_active_router.server import create_router_server
    from control_plane_kit_servers_http_active_router.configuration import RouterSettings
    server = create_router_server(f.config, RouterSettings.from_environment({"ACTIVE_TARGET_URL":"http://upstream.invalid"} if environ is None else environ), address=("127.0.0.1", 0), clock=lambda:150, **kwargs)
    server.daemon_threads = False
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval":0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        test.assertFalse(thread.is_alive())
        test.assertEqual(server.socket.fileno(), -1)


def request(server, path, credential=None, method="GET"):
    connection = HTTPConnection(*server.server_address, timeout=2)
    try:
        headers = {} if credential is None else {"Authorization": f"Bearer {credential}"}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read(131073)
        if len(body) > 131072:
            raise AssertionError("test response exceeded bound")
        return response.status, body, dict(response.getheaders())
    finally:
        connection.close()
