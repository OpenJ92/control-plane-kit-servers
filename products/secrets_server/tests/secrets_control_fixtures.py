"""Synthetic product authority; private keys stay in the owning test process."""
from uuid import uuid4
import hashlib

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import control_plane_kit_core as core
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration


class SourceControlAuthority:
    def __init__(self, suffix="product"):
        from control_plane_kit_secrets.control import secrets_control_declaration

        roles = core.NodeControlGraphReferenceRole
        self.target = core.NodeControlReceiverTarget(
            core.NodeControlGraphReference(roles.WORKSPACE, f"workspace-{suffix}"),
            core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}"),
            core.NodeControlGraphReference(roles.NODE, f"provider-{suffix}"),
            core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"),
            hashlib.sha256(("synthetic-source-receiver:" + suffix).encode()).hexdigest()[:32],
        )
        self.runtime = core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}")
        self.authority = core.NodeControlAuthorityContext("source-authored", "source-projection")
        self.declaration = secrets_control_declaration()
        self.surface_issuer = f"surface-{suffix}"
        self.health_issuer = f"health-{suffix}"
        self.surface_private, surface_public = self._key("surface-key")
        self.health_private, health_public = self._key("health-key")
        self.surface_keys = NodeControlVerificationConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, self.surface_issuer, (surface_public,),
        )
        self.health_keys = NodeControlVerificationConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, self.health_issuer, (health_public,),
        )

    @staticmethod
    def _key(key_id):
        private = Ed25519PrivateKey.generate()
        return private, core.DelegationPublicKey(
            key_id, core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("ascii"),
        )

    def configuration(self):
        return core.ReceiverNodeControlConfiguration(self.target, self.declaration,
            (self.surface_keys, self.health_keys))

    def signed_read(self, *, static: bool, issued_at: int):
        if static:
            request = core.ReceiverControlSurfaceReadRequest(
                self.target, self.authority, core.NodeControlSurfaceReadKind.CAPABILITIES,
                self.declaration.identity(), "source-static",
            )
            grant_type = core.DelegatedWorkloadReceiverControlSurfaceReadGrant
            profile = core.DelegatedWorkloadReceiverControlSurfaceReadGrantProfile.V2
            issuer, keys, private = self.surface_issuer, self.surface_keys, self.surface_private
            payload_key = "workload_node_control_surface_read"
            token_type = "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
        else:
            request = core.ReceiverHealthReadRequest(
                self.target, self.authority, core.NodeHealthReadKind.LIVENESS,
                self.declaration.identity(), "source-health",
            )
            grant_type = core.DelegatedWorkloadReceiverHealthReadGrant
            profile = core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2
            issuer, keys, private = self.health_issuer, self.health_keys, self.health_private
            payload_key = "workload_node_health_read"
            token_type = "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
        grant = grant_type(
            profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=keys.purpose, issuer=issuer, key_id=keys.public_keys[0].key_id,
            audience=core.receiver_node_control_audience(self.target), target=self.target,
            kind=request.kind, declaration_identity=request.declaration_identity,
            request_id=request.request_id, request_digest=request.canonical_digest(),
            issued_at=issued_at, not_before=issued_at, expires_at=issued_at + 120, jti=uuid4().hex,
            authority_context=self.authority,
        )
        token = jwt.encode({
            "iss": grant.issuer, "aud": grant.audience, "iat": grant.issued_at,
            "nbf": grant.not_before, "exp": grant.expires_at, "jti": grant.jti,
            payload_key: grant.descriptor(),
        }, private, algorithm="EdDSA", headers={"kid": keys.public_keys[0].key_id, "typ": token_type})
        return request, token


def configuration():
    return SourceControlAuthority().configuration()
