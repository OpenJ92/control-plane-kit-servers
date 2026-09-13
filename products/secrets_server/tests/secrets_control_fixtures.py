"""Synthetic product authority; private keys stay in the owning test process."""
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import control_plane_kit_core as core
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet,
    WorkloadNodeHealthReadVerifierKeySet,
)


class SourceControlAuthority:
    def __init__(self, suffix="product"):
        from control_plane_kit_secrets.control import secrets_control_declaration

        roles = core.NodeControlGraphReferenceRole
        self.target = core.NodeControlTarget(
            core.NodeControlGraphReference(roles.WORKSPACE, f"workspace-{suffix}"),
            core.NodeControlGraphReference(roles.GRAPH_REVISION, f"revision-{suffix}"),
            core.NodeControlGraphReference(roles.NODE, f"provider-{suffix}"),
            core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"),
        )
        self.runtime = core.NodeControlGraphReference(roles.RUNTIME, f"runtime-{suffix}")
        self.declaration = secrets_control_declaration()
        self.surface_issuer = f"surface-{suffix}"
        self.health_issuer = f"health-{suffix}"
        self.surface_private, surface_public = self._key("surface-key")
        self.health_private, health_public = self._key("health-key")
        self.surface_keys = WorkloadNodeControlSurfaceReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (surface_public,),
        )
        self.health_keys = WorkloadNodeHealthReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (health_public,),
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
        from control_plane_kit_secrets.control import SecretsControlConfiguration

        return SecretsControlConfiguration(
            target=self.target, runtime_id=self.runtime, declaration=self.declaration,
            surface_issuer=self.surface_issuer, surface_keys=self.surface_keys,
            health_issuer=self.health_issuer, health_keys=self.health_keys,
        )

    def signed_read(self, *, static: bool, issued_at: int):
        if static:
            request = core.NodeControlSurfaceReadRequest(
                self.target, core.NodeControlSurfaceReadKind.CAPABILITIES,
                self.declaration.identity(), "source-static",
            )
            grant_type = core.DelegatedWorkloadNodeControlSurfaceReadGrant
            profile = core.DelegatedWorkloadNodeControlSurfaceReadGrantProfile.V1
            issuer, keys, private = self.surface_issuer, self.surface_keys, self.surface_private
            payload_key = "workload_node_control_surface_read"
            token_type = "CPK-WORKLOAD-NODE-CONTROL-SURFACE-READ+JWT"
        else:
            request = core.NodeHealthReadRequest(
                self.target, self.runtime, core.NodeHealthReadKind.LIVENESS,
                self.declaration.identity(), "source-health",
            )
            grant_type = core.DelegatedWorkloadNodeHealthReadGrant
            profile = core.DelegatedWorkloadNodeHealthReadGrantProfile.V1
            issuer, keys, private = self.health_issuer, self.health_keys, self.health_private
            payload_key = "workload_node_health_read"
            token_type = "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
        grant = grant_type(
            profile=profile, canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=keys.purpose, issuer=issuer, key_id=keys.public_keys[0].key_id,
            audience=core.workload_node_control_audience(self.target), target=self.target,
            kind=request.kind, declaration_identity=request.declaration_identity,
            request_id=request.request_id, request_digest=request.canonical_digest(),
            issued_at=issued_at, not_before=issued_at, expires_at=issued_at + 120, jti=uuid4().hex,
            **({} if static else {"runtime_id": self.runtime}),
        )
        token = jwt.encode({
            "iss": grant.issuer, "aud": grant.audience, "iat": grant.issued_at,
            "nbf": grant.not_before, "exp": grant.expires_at, "jti": grant.jti,
            payload_key: grant.descriptor(),
        }, private, algorithm="EdDSA", headers={"kid": keys.public_keys[0].key_id, "typ": token_type})
        return request, token


def configuration():
    return SourceControlAuthority().configuration()
