"""Process-only consumption of the two required selected configuration files."""
import os
import stat
import time

from .health_relay import GatewayHealthRelay
from .health_relay_configuration import (
    CONFIGURATION_PATH as TARGET_PATH, MAX_CONFIGURATION_BYTES as MAX_TARGET_BYTES,
    decode_gateway_health_relay_configuration,
)
from .health_transit_configuration import (
    CONFIGURATION_PATH as TRUST_PATH, MAX_CONFIGURATION_BYTES as MAX_TRUST_BYTES,
    decode_gateway_health_transit_configuration,
)
from .health_transit_verification import Ed25519GatewayHealthTransitVerifier


def _read(path, maximum):
    with open(path, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("gateway startup configuration is invalid")
        content = source.read(maximum + 1)
    if not 1 <= len(content) <= maximum:
        raise ValueError("gateway startup configuration is invalid")
    return content


def load_health_relay():
    trust = decode_gateway_health_transit_configuration(_read(TRUST_PATH, MAX_TRUST_BYTES))
    targets = decode_gateway_health_relay_configuration(_read(TARGET_PATH, MAX_TARGET_BYTES))
    return GatewayHealthRelay(configuration=targets, verifier=Ed25519GatewayHealthTransitVerifier(trust),
                              clock=lambda:int(time.time()))
