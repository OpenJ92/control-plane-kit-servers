"""Generated local test authority; never a deployable product default."""
from dataclasses import replace
from http.client import HTTPConnection
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import control_plane_kit_core as core
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration


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
    target = core.NodeControlReceiverTarget(
        core.NodeControlGraphReference(roles.WORKSPACE, f"workspace-{suffix}"),
        core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}"),
        core.NodeControlGraphReference(roles.NODE, f"connector-{suffix}"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"),
        suffix * 32,
    )
    config = core.ReceiverNodeControlConfiguration(
        target, core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"), (),
                health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2), (
            NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                f"surface-{suffix}", (static_key,)),
            NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
                f"health-{suffix}", (health_key,))),
    )
    return SimpleNamespace(config=config, static_private=static_private, health_private=health_private,
        authority=core.NodeControlAuthorityContext(f"revision-{suffix}", f"projection-{suffix}"))


def token(f, *, static=False, kind=None, request_changes=None):
    config = f.config
    if static:
        request = core.ReceiverControlSurfaceReadRequest(
            config.target, f.authority, kind or core.NodeControlSurfaceReadKind.CAPABILITIES,
            config.declaration.identity(), "surface-request",
        )
        grant_type = core.DelegatedWorkloadReceiverControlSurfaceReadGrant
        profile = core.DelegatedWorkloadReceiverControlSurfaceReadGrantProfile.V2
        family = next(item for item in config.verifiers
            if item.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ)
        issuer, private = family.issuer, f.static_private
        payload_key = "workload_node_control_surface_read"
        typ = "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
    else:
        request = core.ReceiverHealthReadRequest(config.target, f.authority,
            kind or core.NodeHealthReadKind.READINESS, config.declaration.identity(), "health-request")
        grant_type = core.DelegatedWorkloadReceiverHealthReadGrant
        profile = core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2
        family = next(item for item in config.verifiers
            if item.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
        issuer, private = family.issuer, f.health_private
        payload_key = "workload_node_health_read"
        typ = "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
    request = replace(request, **(request_changes or {}))
    grant = grant_type(
        profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=family.purpose, issuer=issuer, key_id=family.public_keys[0].key_id,
        audience=core.receiver_node_control_audience(config.target), target=request.target, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=100, not_before=100, expires_at=200, jti="connector-test",
        authority_context=request.authority_context,
    )
    return jwt.encode({"iss": issuer, "aud": grant.audience, "iat":100, "nbf":100, "exp":200,
                       "jti":grant.jti, payload_key:grant.descriptor()}, private, algorithm="EdDSA",
                      headers={"kid":grant.key_id, "typ":typ})


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
