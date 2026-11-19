"""Product-owned configuration and native health over the common SDK host.

Process supervision and image launch are separate #188 implementation steps.
The existing fixed-loopback reader remains the native connection authority.
"""
from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from threading import Lock
import time

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.secrets import SecretFileDelivery, SecretFileMode, SecretUseIntent
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT

from .readiness import ConnectionSample


_CONTROL_PATH = '/etc/cpk/cloudflared/control.json'
_ARTIFACT_ID = 'cloudflared-control'
_ERROR = 'Cloudflared control configuration is invalid'


class ConnectorConfigurationError(ValueError):
    """Fixed product refusal, without submitted material."""


def control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    """The product's public control surface, independent of instance material."""
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, 'control'),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
        profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)


def declared_runtime_contract() -> ProductRuntimeContract:
    """Declare the control file requirement without default config or token."""
    return ProductRuntimeContract(
        sockets=BlockSockets(providers=(ProviderSocket('control', Protocol.HTTP),)),
        provider_ports=(ProviderRuntimePort('control', 8000),),
        configuration_requirements=(core.ConfigurationArtifactRequirement(
            _ARTIFACT_ID, _CONTROL_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY),),
        public_environment=(PublicStaticEnvironmentBinding(
            WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, _CONTROL_PATH),),
        capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
        control_surfaces=(control_declaration().surface,), verification=VerificationContract())


def _validated(configuration):
    if type(configuration) is not core.ReceiverNodeControlConfiguration:
        raise ValueError
    codec = core.ReceiverNodeControlConfigurationCodec()
    value = codec.decode_bytes(codec.encode_bytes(configuration))
    if value.declaration != control_declaration():
        raise ValueError
    return value


def control_configuration_artifact(configuration):
    """Render common receiving configuration after exact product validation."""
    try:
        value = _validated(configuration)
        content = core.ReceiverNodeControlConfigurationCodec().encode_bytes(value).decode('utf-8')
        return ConfigurationArtifact(_ARTIFACT_ID, _CONTROL_PATH, ConfigurationMediaType.JSON,
            content, ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = ConnectorConfigurationError(_ERROR)
    raise failure


def source_runtime_contract(artifact, token_delivery):
    """Source contract only; never rewrites historical published coordinates."""
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != _ARTIFACT_ID
                or artifact.target_path != _CONTROL_PATH or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        _validated(core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode('utf-8')))
        if (type(token_delivery) is not SecretFileDelivery
                or token_delivery.intent is not SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN
                or token_delivery.file_mode is not SecretFileMode.OWNER_READ_ONLY
                or token_delivery.path_binding is None
                or token_delivery.path_binding.environment_name != 'TUNNEL_TOKEN_FILE'):
            raise ValueError
        token_delivery.__post_init__()
        return replace(declared_runtime_contract(),
            configuration_requirements=(), configuration_artifacts=(artifact,),
            secret_deliveries=(token_delivery,))
    except Exception:
        failure = ConnectorConfigurationError(_ERROR)
    raise failure


class ConnectorHealth:
    """One bounded native read at a time; stopping permanently invalidates it."""

    def __init__(self, *, native_alive, read_connection):
        if not callable(native_alive) or not callable(read_connection):
            raise TypeError('Cloudflared health callbacks are invalid')
        self._native_alive = native_alive
        self._read_connection = read_connection
        self._state = Lock()
        self._probe = Lock()
        self._stopping = False

    def _liveness_locked(self):
        if self._stopping:
            return core.NodeHealthReadOutcome.UNHEALTHY
        try:
            alive = self._native_alive()
        except Exception:
            return core.NodeHealthReadOutcome.UNKNOWN
        if type(alive) is not bool:
            return core.NodeHealthReadOutcome.UNKNOWN
        return core.NodeHealthReadOutcome.HEALTHY if alive else core.NodeHealthReadOutcome.UNHEALTHY

    def liveness(self):
        with self._state:
            return self._liveness_locked()

    def readiness(self):
        before = self.liveness()
        if before is not core.NodeHealthReadOutcome.HEALTHY:
            return before
        if not self._probe.acquire(blocking=False):
            # A stop can race with contention, too; stop is never masked by unknown.
            current = self.liveness()
            return (core.NodeHealthReadOutcome.UNKNOWN
                if current is core.NodeHealthReadOutcome.HEALTHY else current)
        try:
            outcome = core.NodeHealthReadOutcome.UNKNOWN
            try:
                sample = self._read_connection()
                if type(sample) is ConnectionSample:
                    outcome = {
                        'connected': core.NodeHealthReadOutcome.HEALTHY,
                        'disconnected': core.NodeHealthReadOutcome.UNHEALTHY,
                        'unknown': core.NodeHealthReadOutcome.UNKNOWN,
                    }.get(sample.outcome, core.NodeHealthReadOutcome.UNKNOWN)
            except Exception:
                outcome = core.NodeHealthReadOutcome.UNKNOWN
            with self._state:
                current = self._liveness_locked()
                return outcome if current is core.NodeHealthReadOutcome.HEALTHY else current
        finally:
            self._probe.release()

    def stop(self):
        with self._state:
            self._stopping = True


class _ManagementOnlyHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(404)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, format, *args):
        return


def create_control_server(configuration, health, *, address=('0.0.0.0', 8000), clock=None):
    """Validate before socket creation, then reuse SDK auth/routes/lifecycle."""
    try:
        value = _validated(configuration)
        if type(health) is not ConnectorHealth:
            raise ValueError
    except Exception:
        value = None
    if value is None:
        raise ConnectorConfigurationError(_ERROR)
    from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer
    server = CpkThreadingHTTPServer(address, _ManagementOnlyHandler, bind_and_activate=False,
        configuration=value, clock=clock if clock is not None else lambda: int(time.time()),
        liveness=health.liveness, readiness=health.readiness)
    try:
        server.server_bind()
        server.server_activate()
        return server
    except BaseException:
        server.server_close()
        raise
