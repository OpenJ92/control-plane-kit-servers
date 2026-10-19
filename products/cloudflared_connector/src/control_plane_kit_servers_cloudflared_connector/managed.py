"""Reviewed #188 target interfaces; deliberately unimplemented red checkpoint.

The existing native reader remains independent of the persistent SDK host.
"""


class ConnectorConfigurationError(ValueError):
    """Fixed product refusal, without submitted material."""


def control_configuration_artifact(configuration):
    raise NotImplementedError("#188 managed configuration is not implemented")


def source_runtime_contract(artifact, token_delivery):
    raise NotImplementedError("#188 managed source contract is not implemented")


class ConnectorHealth:
    def __init__(self, *, native_alive, read_connection):
        raise NotImplementedError("#188 native lifecycle health is not implemented")

    def liveness(self):
        raise NotImplementedError

    def readiness(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


def create_control_server(configuration, health, *, address=("0.0.0.0", 8000), clock=None):
    raise NotImplementedError("#188 SDK host composition is not implemented")
