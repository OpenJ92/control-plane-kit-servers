"""Generated local test authority; never a deployable product default."""
from dataclasses import replace
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import control_plane_kit_core as core
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)


def fixture(suffix="a"):

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
        core.NodeControlGraphReference(roles.NODE, f"cpk-{suffix}"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "http-api"),
    )
    config = SimpleNamespace(
        target=target, runtime_id=core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}"),
        declaration=core.WorkloadNodeControlSurfaceDeclaration(core.WorkloadNodeControlSurfaceDescriptor(target.provider_socket_name, (), health_reads=(core.NodeHealthReadKind.LIVENESS,)), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2), surface_issuer=f"surface-{suffix}", health_issuer=f"health-{suffix}",
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
        request_digest=request.canonical_digest(), issued_at=100, not_before=100, expires_at=200, jti="cpk-host-test",
        **({} if static else {"runtime_id": request.runtime_id}),
    )
    return jwt.encode({"iss": issuer, "aud": grant.audience, "iat":100, "nbf":100, "exp":200,
                       "jti":grant.jti, payload_key:grant.descriptor()}, private, algorithm="EdDSA",
                      headers={"kid":grant.key_id, "typ":typ})



def install_control(app, f):
    """Compose the real SDK on a test host; production adoption belongs to #200."""
    from control_plane_kit_server_sdk.fastapi import install_cpk_control_routes
    from control_plane_kit_server_sdk.health import WorkloadNodeHealthReadDispatcher
    from control_plane_kit_server_sdk.verification import (
        Ed25519WorkloadNodeControlSurfaceReadVerifier, Ed25519WorkloadNodeHealthReadVerifier,
    )
    from control_plane_kit_server_sdk.verifier_keys import (
        AtomicWorkloadNodeControlSurfaceReadVerifierKeySet, AtomicWorkloadNodeHealthReadVerifierKeySet,
    )
    c = f.config
    audience = core.workload_node_control_audience(c.target)
    static = Ed25519WorkloadNodeControlSurfaceReadVerifier(
        AtomicWorkloadNodeControlSurfaceReadVerifierKeySet(c.surface_keys),
        expected_issuer=c.surface_issuer, expected_audience=audience, clock=lambda:150,
    )
    health = Ed25519WorkloadNodeHealthReadVerifier(
        AtomicWorkloadNodeHealthReadVerifierKeySet(c.health_keys),
        expected_issuer=c.health_issuer, expected_audience=audience, clock=lambda:150,
    )
    install_cpk_control_routes(
        app, target=c.target, declaration=c.declaration, surface_read_verifier=static,
        health_dispatcher=WorkloadNodeHealthReadDispatcher(
            target=c.target, runtime_id=c.runtime_id, declaration=c.declaration, verifier=health,
            liveness=lambda:core.NodeHealthReadOutcome.HEALTHY, readiness=None,
        ),
    )
