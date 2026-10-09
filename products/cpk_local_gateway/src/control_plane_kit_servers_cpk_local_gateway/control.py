"""Gateway-owned local process truth and actual SDK receiver composition."""
from dataclasses import dataclass

import control_plane_kit_core as core
from control_plane_kit_server_sdk.fastapi import install_cpk_wrapper
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
    install_cpk_wrapper(app, configuration=config, clock=clock,
        liveness=health.liveness, readiness=health.readiness)
    health.configured = True
