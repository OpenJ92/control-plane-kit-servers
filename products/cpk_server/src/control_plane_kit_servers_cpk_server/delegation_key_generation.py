"""Compose Operations generation grants with the existing public provider client."""
from dataclasses import dataclass, field
from typing import Any

from control_plane_kit_interpreters.secret_provider import SecretProviderBootstrapRegistry
from control_plane_kit_interpreters.secret_provider.client import (
    ControlPlaneKitSecretsClient, SecretProviderClientPolicy,
)
from control_plane_kit_operations.delegation_key_generation import DelegationKeyGenerationGrant


@dataclass(frozen=True, repr=False)
class _ProviderDelegationKeyGenerator:
    bootstrap_registry: SecretProviderBootstrapRegistry
    policy: SecretProviderClientPolicy = field(default_factory=SecretProviderClientPolicy)
    transport: Any | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.bootstrap_registry, SecretProviderBootstrapRegistry):
            raise TypeError("generation requires provider bootstrap registry")
        if not isinstance(self.policy, SecretProviderClientPolicy):
            raise TypeError("generation requires provider client policy")

    def generate(self, grant: DelegationKeyGenerationGrant):
        if not isinstance(grant, DelegationKeyGenerationGrant):
            raise TypeError("generation requires a delegation key generation grant")
        custody = grant.custody_grant
        configuration = self.bootstrap_registry.configuration_for(
            endpoint_reference=custody.endpoint_reference,
            credential_reference=custody.credential_reference,
        )
        client = ControlPlaneKitSecretsClient(configuration, policy=self.policy, transport=self.transport)
        return client.generate_delegation_key(
            workspace_id=grant.workspace_id, reference=grant.reference,
            purpose=grant.purpose, issuer=grant.issuer,
            caller_subject=grant.actor_subject, correlation_id=grant.correlation_id,
        )
