"""Local receiving authority for PostgreSQL wrapper tests."""

from dataclasses import replace
from types import SimpleNamespace

import control_plane_kit_core as core
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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
