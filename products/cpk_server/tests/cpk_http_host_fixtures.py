"""Generated local test authority; never a deployable product default."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import control_plane_kit_core as core
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration


def verifier_family(config, purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ):
    """Select fixture trust from the actual common configuration value."""
    family, = (item for item in config.verifiers if item.purpose is purpose)
    return family


def with_health(config, *, public_keys=None, issuer=None):
    family = verifier_family(config)
    family = replace(family, public_keys=family.public_keys if public_keys is None else public_keys,
                     issuer=family.issuer if issuer is None else issuer)
    return replace(config, verifiers=tuple(family if item.purpose is family.purpose else item
                                          for item in config.verifiers))


def fixture(suffix="a", *, issued_at=100, lifetime=100):
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
        core.NodeControlGraphReference(roles.NODE, f"cpk-{suffix}"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "http-api"),
        sha256(suffix.encode()).hexdigest()[:32],
    )
    config = core.ReceiverNodeControlConfiguration(target,
        core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(target.provider_socket_name, (),
                health_reads=(core.NodeHealthReadKind.LIVENESS,)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2),
        (NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            f"surface-{suffix}", (static_key,)),
         NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
            f"health-{suffix}", (health_key,))))
    return SimpleNamespace(config=config, static_private=static_private, health_private=health_private,
        authority=core.NodeControlAuthorityContext(f"revision-{suffix}", f"projection-{suffix}"),
        issued_at=issued_at, expires_at=issued_at+lifetime)


def token(f, *, static=False, kind=None, request_changes=None):
    config = f.config
    if static:
        request = core.ReceiverControlSurfaceReadRequest(config.target, f.authority,
            kind or core.NodeControlSurfaceReadKind.CAPABILITIES, config.declaration.identity(), "surface-request")
        grant_type = core.DelegatedWorkloadReceiverControlSurfaceReadGrant
        profile = core.DelegatedWorkloadReceiverControlSurfaceReadGrantProfile.V2
        family = verifier_family(config, core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ)
        private = f.static_private
        payload_key = "workload_node_control_surface_read"
        typ = "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
    else:
        request = core.ReceiverHealthReadRequest(config.target, f.authority,
            kind or core.NodeHealthReadKind.LIVENESS, config.declaration.identity(), "health-request")
        grant_type = core.DelegatedWorkloadReceiverHealthReadGrant
        profile = core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2
        family = verifier_family(config)
        private = f.health_private
        payload_key = "workload_node_health_read"
        typ = "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
    request = replace(request, **(request_changes or {}))
    grant = grant_type(profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=family.purpose, issuer=family.issuer, key_id=family.public_keys[0].key_id,
        audience=core.receiver_node_control_audience(request.target), target=request.target, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=f.issued_at, not_before=f.issued_at,
        expires_at=f.expires_at, jti="cpk-host-test", authority_context=request.authority_context)
    return jwt.encode({"iss": family.issuer, "aud": grant.audience, "iat":f.issued_at, "nbf":f.issued_at,
                       "exp":f.expires_at, "jti":grant.jti, payload_key:grant.descriptor()}, private,
                      algorithm="EdDSA", headers={"kid":grant.key_id, "typ":typ})


def install_control(app, f):
    """Compose the actual SDK wrapper beside the production CPK host."""
    from control_plane_kit_server_sdk.fastapi import install_cpk_wrapper
    install_cpk_wrapper(app, configuration=f.config, clock=lambda:150)
