"""Product declaration and SDK host for the managed website."""
from http.server import BaseHTTPRequestHandler
import time

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer

CONTROL_PATH = "/etc/cpk/website/control.json"


def control_declaration():
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
        profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)


def declared_runtime_contract():
    return ProductRuntimeContract(
        sockets=BlockSockets(providers=(
            ProviderSocket("http", Protocol.HTTP), ProviderSocket("control", Protocol.HTTP))),
        provider_ports=(ProviderRuntimePort("http", 8080), ProviderRuntimePort("control", 8000)),
        configuration_requirements=(core.ConfigurationArtifactRequirement(
            "website-control", CONTROL_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY),),
        public_environment=(PublicStaticEnvironmentBinding(
            WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),),
        capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
        control_surfaces=(control_declaration().surface,))


def control_configuration_artifact(configuration):
    valid = False
    try:
        codec = core.ReceiverNodeControlConfigurationCodec()
        value = codec.decode_bytes(codec.encode_bytes(configuration))
        valid = type(configuration) is core.ReceiverNodeControlConfiguration and value.declaration == control_declaration()
        if valid:
            return ConfigurationArtifact("website-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                         codec.encode_bytes(value).decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        raise ValueError("Website control configuration is invalid") from None
    raise ValueError("Website control configuration is invalid")


class ManagementHandler(BaseHTTPRequestHandler):
    server_version = "control-plane-kit-website/1"

    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        return


def create_control_server(configuration, health, *, address=("0.0.0.0", 8000), clock=None):
    control_configuration_artifact(configuration)
    host = CpkThreadingHTTPServer(
        address, ManagementHandler, bind_and_activate=False,
        configuration=configuration, clock=clock if clock is not None else lambda: int(time.time()),
        liveness=health.liveness, readiness=health.readiness)
    try:
        host.daemon_threads = True
        host.server_bind()
        host.server_activate()
        return host
    except BaseException:
        host.server_close()
        raise
