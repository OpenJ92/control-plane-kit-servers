"""Public product inputs built from real service/Core/SDK types inside owner tests."""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import control_plane_kit_core as core
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet,
    WorkloadNodeHealthReadVerifierKeySet,
)


def configuration():
    # The product-interface guard runs before this dependency is required.
    from control_plane_kit_secrets.control import SecretsControlConfiguration, secrets_control_declaration

    roles = core.NodeControlGraphReferenceRole
    target = core.NodeControlTarget(
        core.NodeControlGraphReference(roles.WORKSPACE, "product-workspace"),
        core.NodeControlGraphReference(roles.GRAPH_REVISION, "product-revision"),
        core.NodeControlGraphReference(roles.NODE, "product-provider"),
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"),
    )

    def public_key(key_id):
        private = Ed25519PrivateKey.generate()
        return core.DelegationPublicKey(
            key_id, core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("ascii"),
        )

    return SecretsControlConfiguration(
        target=target,
        runtime_id=core.NodeControlGraphReference(roles.RUNTIME, "product-runtime"),
        declaration=secrets_control_declaration(),
        surface_issuer="product-surface",
        surface_keys=WorkloadNodeControlSurfaceReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            (public_key("surface-key"),),
        ),
        health_issuer="product-health",
        health_keys=WorkloadNodeHealthReadVerifierKeySet(
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
            (public_key("health-key"),),
        ),
    )
