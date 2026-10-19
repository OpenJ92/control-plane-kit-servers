"""Local receiving authority for PostgreSQL wrapper tests."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import control_plane_kit_core as core
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt


def fixture(suffix: str = "a"):
    from control_plane_kit_servers_postgres_server.configuration import postgres_control_declaration

    def key(family: str):
        private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey(
            f"{family}-{suffix}",
            core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("ascii"),
        )
        return private, public

    static_private, static_key = key("static")
    health_private, health_key = key("health")
    roles = core.NodeControlGraphReferenceRole
    target = core.NodeControlReceiverTarget(
        core.NodeControlGraphReference(roles.WORKSPACE, f"workspace-{suffix}"),
        core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}"),
        core.NodeControlGraphReference(roles.NODE, f"postgres-{suffix}"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "management"),
        suffix * 32,
    )
    config = core.ReceiverNodeControlConfiguration(
        target,
        postgres_control_declaration(),
        (
            NodeControlVerificationConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                f"surface-{suffix}",
                (static_key,),
            ),
            NodeControlVerificationConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
                f"health-{suffix}",
                (health_key,),
            ),
        ),
    )
    return SimpleNamespace(
        config=config,
        static_private=static_private,
        health_private=health_private,
        authority=core.NodeControlAuthorityContext(f"revision-{suffix}", f"projection-{suffix}"),
    )


def readiness_only(configuration):
    declaration = configuration.declaration
    return replace(
        configuration,
        declaration=replace(
            declaration,
            surface=replace(
                declaration.surface,
                health_reads=(core.NodeHealthReadKind.READINESS,),
            ),
        ),
    )


def health_token(value, *, issued_at: int, request_changes=None):
    config = value.config
    request = core.ReceiverHealthReadRequest(
        config.target,
        value.authority,
        core.NodeHealthReadKind.READINESS,
        config.declaration.identity(),
        "postgres-health-" + uuid4().hex,
    )
    request = replace(request, **(request_changes or {}))
    family = next(
        item for item in config.verifiers
        if item.purpose is core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ
    )
    grant = core.DelegatedWorkloadReceiverHealthReadGrant(
        profile=core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2,
        canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=family.purpose,
        issuer=family.issuer,
        key_id=family.public_keys[0].key_id,
        audience=core.receiver_node_control_audience(config.target),
        target=request.target,
        kind=request.kind,
        declaration_identity=request.declaration_identity,
        request_id=request.request_id,
        request_digest=request.canonical_digest(),
        issued_at=issued_at,
        not_before=issued_at,
        expires_at=issued_at + 120,
        jti=uuid4().hex,
        authority_context=value.authority,
    )
    token = jwt.encode({
        "iss": grant.issuer,
        "aud": grant.audience,
        "iat": grant.issued_at,
        "nbf": grant.not_before,
        "exp": grant.expires_at,
        "jti": grant.jti,
        "workload_node_health_read": grant.descriptor(),
    }, value.health_private, algorithm="EdDSA", headers={
        "kid": grant.key_id,
        "typ": "CPK-WORKLOAD-NODE-HEALTH-READ+JWT",
    })
    return request, token
