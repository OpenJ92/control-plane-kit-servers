"""Gateway-owned local process truth and actual SDK receiver composition."""
from dataclasses import dataclass

import control_plane_kit_core as core
from control_plane_kit_server_sdk.fastapi import install_cpk_control_routes
from control_plane_kit_server_sdk.health import WorkloadNodeHealthReadDispatcher
from control_plane_kit_server_sdk.verification import (
    Ed25519WorkloadNodeControlSurfaceReadVerifier, Ed25519WorkloadNodeHealthReadVerifier,
)
from control_plane_kit_server_sdk.verifier_keys import (
    AtomicWorkloadNodeControlSurfaceReadVerifierKeySet, AtomicWorkloadNodeHealthReadVerifierKeySet,
)
from .control_configuration import (
    gateway_control_configuration_artifact, gateway_control_configuration_from_artifact, require_matching_gateway_control,
)
from .health_relay import GatewayHealthRelay


@dataclass(slots=True, repr=False)
class GatewayLocalHealth:
    """No downstream/ingress check, durable observation, retry or runtime effect."""
    configured: bool = False
    serving: bool = False

    def liveness(self):
        return core.NodeHealthReadOutcome.HEALTHY

    def readiness(self):
        return (core.NodeHealthReadOutcome.HEALTHY if self.configured and self.serving
                else core.NodeHealthReadOutcome.UNHEALTHY)


def install_gateway_control(app, configuration, relay, health, clock):
    config = gateway_control_configuration_from_artifact(gateway_control_configuration_artifact(configuration))
    if type(relay) is not GatewayHealthRelay:
        raise ValueError("gateway control requires a configured health relay")
    require_matching_gateway_control(config, relay.configuration)
    audience = core.workload_node_control_audience(config.target)
    surface_verifier = Ed25519WorkloadNodeControlSurfaceReadVerifier(
        AtomicWorkloadNodeControlSurfaceReadVerifierKeySet(config.surface_keys),
        expected_issuer=config.surface_issuer, expected_audience=audience, clock=clock)
    health_verifier = Ed25519WorkloadNodeHealthReadVerifier(
        AtomicWorkloadNodeHealthReadVerifierKeySet(config.health_keys),
        expected_issuer=config.health_issuer, expected_audience=audience, clock=clock)
    install_cpk_control_routes(app, target=config.target, declaration=config.declaration,
        surface_read_verifier=surface_verifier, health_dispatcher=WorkloadNodeHealthReadDispatcher(
            target=config.target, runtime_id=config.runtime_id, declaration=config.declaration, verifier=health_verifier,
            liveness=health.liveness, readiness=health.readiness))
    health.configured = True
