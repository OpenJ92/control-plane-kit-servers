"""Pure signed health-transit admission; no clock, replay state or target I/O."""
from __future__ import annotations

import base64
from dataclasses import replace
import re
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.node_health_transit import (
    DelegatedGatewayNodeHealthReadTransitGrantCodec, verify_gateway_node_health_read_transit_grant,
)

from .health_transit_configuration import (
    GatewayHealthTransitConfiguration, GatewayHealthTransitConfigurationError,
    _configuration_from_artifact, _decode_json, _INPUT_ERRORS, _object, _public_key,
)


TOKEN_TYPE = "CPK-GATEWAY-NODE-HEALTH-READ-TRANSIT+JWT"
MAX_CREDENTIAL_BYTES = 12_288  # Coarse early cap; segment caps imply9304.
_SEGMENT_BOUNDS = (1024, 8192, 86)
_BASE64URL = re.compile(rb"[A-Za-z0-9_-]+\Z")
_HEADER_KEYS = frozenset({"alg", "kid", "typ"})
_CLAIM = "gateway_node_health_read_transit"
_PAYLOAD_KEYS = frozenset({"iss", "aud", "iat", "nbf", "exp", "jti", _CLAIM})
_ERROR = "gateway health transit credential was rejected"
_VERIFICATION_ERRORS = _INPUT_ERRORS + (InvalidSignature,)


class GatewayHealthTransitVerificationError(ValueError):
    """Fixed, candidate-free credential refusal."""


class Ed25519GatewayHealthTransitVerifier:
    """Authenticate against configured trust and independently admitted context."""

    __slots__ = ("_configuration", "_keys")

    def __init__(self, configuration: GatewayHealthTransitConfiguration) -> None:
        try:
            if type(configuration) is not GatewayHealthTransitConfiguration:
                raise TypeError
            self._configuration = replace(configuration)
            self._keys = MappingProxyType({key.key_id: _public_key(key)
                for key in self._configuration.public_keys})
            return
        except _INPUT_ERRORS:
            failure = GatewayHealthTransitConfigurationError("gateway health transit configuration is invalid")
        raise failure

    def __repr__(self) -> str:
        return "Ed25519GatewayHealthTransitVerifier(<redacted>)"

    def verify(self, credential: bytes, request: core.NodeHealthReadRequest, *,
               expected_attempt_id: str, expected_target: core.NodeControlTarget,
               expected_runtime_id: core.NodeControlGraphReference,
               expected_declaration: core.WorkloadNodeControlSurfaceDeclaration,
               expected_kind: core.NodeHealthReadKind, now: int) -> core.NodeHealthReadRequest:
        try:
            configuration = self._configuration
            if (type(request) is not core.NodeHealthReadRequest
                    or type(expected_target) is not core.NodeControlTarget
                    or type(expected_runtime_id) is not core.NodeControlGraphReference
                    or expected_target.workspace_id != configuration.workspace_id
                    or expected_runtime_id != configuration.runtime_id
                    or type(now) is not int or not 0 <= now <= 2**53 - 1):
                raise ValueError
            parts, decoded = _compact(credential)
            header = _object(_decode_json(decoded[0], 768), _HEADER_KEYS)
            claims = _object(_decode_json(decoded[1], 6144), _PAYLOAD_KEYS)
            if (any(type(header[name]) is not str for name in _HEADER_KEYS)
                    or header["alg"] != "EdDSA" or header["typ"] != TOKEN_TYPE
                    or any(type(claims[name]) is not str for name in ("iss", "aud", "jti"))
                    or any(type(claims[name]) is not int for name in ("iat", "nbf", "exp"))
                    or type(claims[_CLAIM]) is not dict):
                raise ValueError
            key = self._keys[header["kid"]]
            key.verify(decoded[2], parts[0] + b"." + parts[1])
            grant = DelegatedGatewayNodeHealthReadTransitGrantCodec().decode(claims[_CLAIM])
            if (header["kid"] != grant.key_id
                    or claims["iss"] != grant.issuer or claims["aud"] != grant.audience
                    or claims["iat"] != grant.issued_at or claims["nbf"] != grant.not_before
                    or claims["exp"] != grant.expires_at or claims["jti"] != grant.jti
                    or grant.audience != configuration.audience):
                raise ValueError
            comparison = verify_gateway_node_health_read_transit_grant(
                grant, request, expected_issuer=configuration.issuer, expected_key_id=header["kid"],
                expected_attempt_id=expected_attempt_id, expected_gateway_node_id=configuration.gateway_node_id,
                expected_target=expected_target, expected_runtime_id=expected_runtime_id,
                expected_declaration=expected_declaration, expected_kind=expected_kind, now=now)
            if not comparison.is_accepted:
                raise ValueError
            return request
        except _VERIFICATION_ERRORS:
            failure = GatewayHealthTransitVerificationError(_ERROR)
        raise failure


def _compact(credential: bytes) -> tuple[list[bytes], list[bytes]]:
    if type(credential) is not bytes or not 1 <= len(credential) <= MAX_CREDENTIAL_BYTES:
        raise ValueError
    credential.decode("ascii")
    parts = credential.split(b".")
    if len(parts) != 3:
        raise ValueError
    decoded = []
    for segment, maximum in zip(parts, _SEGMENT_BOUNDS, strict=True):
        if not 1 <= len(segment) <= maximum or _BASE64URL.fullmatch(segment) is None:
            raise ValueError
        value = base64.b64decode(segment + b"=" * (-len(segment) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(value).rstrip(b"=") != segment:
            raise ValueError
        decoded.append(value)
    if len(decoded[2]) != 64:
        raise ValueError
    return parts, decoded


def gateway_health_transit_verifier_from_artifact(
    artifact: ConfigurationArtifact,
) -> Ed25519GatewayHealthTransitVerifier:
    return Ed25519GatewayHealthTransitVerifier(_configuration_from_artifact(artifact))
