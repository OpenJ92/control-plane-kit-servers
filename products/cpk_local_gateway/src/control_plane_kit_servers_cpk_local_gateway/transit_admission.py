"""Pure admission for signed gateway node-control transit authority."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import ipaddress
import json
import re
from typing import Mapping

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import rfc8785

from control_plane_kit_core.delegation_keys import (
    DelegationKeyAlgorithm,
    DelegationPublicKey,
)
from control_plane_kit_core.node_control import (
    MAX_NODE_CONTROL_PAYLOAD_BYTES,
    NodeControlCommandRequest,
    NodeControlCommandRequestCodec,
    NodeControlContractError,
    NodeControlGraphReference,
    NodeControlGraphReferenceRole,
)
from control_plane_kit_core.node_control_transit import (
    DelegatedGatewayNodeControlTransitGrant,
    DelegatedGatewayNodeControlTransitGrantCodec,
    GatewayNodeControlTransitContractError,
    verify_gateway_node_control_transit_grant,
)


GATEWAY_NODE_CONTROL_TRANSIT_TOKEN_TYPE = (
    "CPK-GATEWAY-NODE-CONTROL-TRANSIT+JWT"
)
MAX_GATEWAY_NODE_CONTROL_TRANSIT_HEADER_SEGMENT_BYTES = 263
MAX_GATEWAY_NODE_CONTROL_TRANSIT_PAYLOAD_SEGMENT_BYTES = 4_816
MAX_GATEWAY_NODE_CONTROL_TRANSIT_SIGNATURE_SEGMENT_BYTES = 86
MAX_GATEWAY_NODE_CONTROL_TRANSIT_CREDENTIAL_BYTES = 5_167

_ERROR_MESSAGE = "gateway node-control transit credential was rejected"
_MAX_PUBLIC_KEYS = 16
_MAX_STRUCTURAL_JSON_DEPTH = 16
_MAX_STRUCTURAL_JSON_MEMBERS = 64
_MAX_SAFE_INTEGER = 2**53 - 1
_BASE64URL = re.compile(rb"^[A-Za-z0-9_-]+$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_ASCII_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_AUTHORIZATION_ENVELOPE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(?:"
    r"authorization[ \t]*:[ \t]*[A-Za-z][A-Za-z0-9._+-]*[ \t]+"
    r"|bearer[ \t]+"
    r")[^\s,;]+"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])"
    r"(?:credential|password|secret|signature|token)"
    r"[ \t]*=[ \t]*[^\s,;]+"
)
_PRIVATE_KEY_ARMOR = re.compile(
    r"(?i)-----begin(?: [A-Za-z0-9]+)* private key-----"
)
_COMPACT_TOKEN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:sk-|sg\.)[A-Za-z0-9][A-Za-z0-9._-]*"
)
_SCHEME_ENDPOINT = re.compile(r"(?i)[A-Za-z][A-Za-z0-9+.-]*://[^\s/]")
_PROTOCOL_RELATIVE_ENDPOINT = re.compile(r"(?:^|[\s(\"'=])//[^\s/]")
_HOST_PORT_ENDPOINT = re.compile(
    r"(?<![A-Za-z0-9._:\[\]-])"
    r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9][A-Za-z0-9.-]*):(\d{1,5})"
    r"(?![A-Za-z0-9])"
)
_ENDPOINT_TOKEN_SPLIT = re.compile(r"[\s,;(){}<>\"']+")
_HEADER_KEYS = frozenset({"alg", "kid", "typ"})
_PAYLOAD_KEYS = frozenset(
    {
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
        "jti",
        "gateway_node_control_transit",
    }
)


class GatewayNodeControlTransitAdmissionError(ValueError):
    """Bounded rejection for every signed-transit admission failure."""

    __slots__ = ()


class _TransitAdmissionRejected(Exception):
    pass


class _ObjectPairs(list[tuple[str, object]]):
    pass


@dataclass(frozen=True, repr=False)
class VerifiedGatewayNodeControlTransit:
    """One exact verified transit grant and its canonical Core request."""

    grant: DelegatedGatewayNodeControlTransitGrant
    request: NodeControlCommandRequest
    effective_now: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.grant, DelegatedGatewayNodeControlTransitGrant)
            or not isinstance(self.request, NodeControlCommandRequest)
            or not _is_epoch(self.effective_now)
        ):
            raise GatewayNodeControlTransitAdmissionError(_ERROR_MESSAGE)

    def __repr__(self) -> str:
        return "VerifiedGatewayNodeControlTransit(<redacted>)"


class Ed25519GatewayNodeControlTransitVerifier:
    """Verify one signed transit credential against trusted gateway identity."""

    __slots__ = (
        "_gateway_node_id",
        "_issuer",
        "_public_keys",
        "_workspace_id",
    )

    def __init__(
        self,
        *,
        issuer: str,
        workspace_id: NodeControlGraphReference,
        gateway_node_id: NodeControlGraphReference,
        public_keys: tuple[DelegationPublicKey, ...],
    ) -> None:
        rejected = False
        keys: tuple[tuple[DelegationPublicKey, Ed25519PublicKey], ...] = ()
        try:
            _require_reference(issuer)
            _require_graph_reference(
                workspace_id,
                NodeControlGraphReferenceRole.WORKSPACE,
            )
            _require_graph_reference(
                gateway_node_id,
                NodeControlGraphReferenceRole.NODE,
            )
            keys = _validated_public_keys(public_keys)
        except _TransitAdmissionRejected:
            rejected = True
        if rejected:
            raise GatewayNodeControlTransitAdmissionError(_ERROR_MESSAGE)
        self._issuer = issuer
        self._workspace_id = workspace_id
        self._gateway_node_id = gateway_node_id
        self._public_keys = keys

    def verify(
        self,
        *,
        credential: bytes,
        request_bytes: bytes,
        expected_attempt_id: str,
        effective_now: int,
    ) -> VerifiedGatewayNodeControlTransit:
        rejected = False
        try:
            return self._verify(
                credential=credential,
                request_bytes=request_bytes,
                expected_attempt_id=expected_attempt_id,
                effective_now=effective_now,
            )
        except (
            _TransitAdmissionRejected,
            GatewayNodeControlTransitContractError,
            NodeControlContractError,
        ):
            rejected = True
        if rejected:
            raise GatewayNodeControlTransitAdmissionError(_ERROR_MESSAGE)
        raise AssertionError("transit admission reached an invalid state")

    def _verify(
        self,
        *,
        credential: bytes,
        request_bytes: bytes,
        expected_attempt_id: str,
        effective_now: int,
    ) -> VerifiedGatewayNodeControlTransit:
        _require_identifier(expected_attempt_id)
        if not _is_epoch(effective_now):
            raise _TransitAdmissionRejected
        if type(request_bytes) is not bytes or not 1 <= len(request_bytes) <= (
            MAX_NODE_CONTROL_PAYLOAD_BYTES
        ):
            raise _TransitAdmissionRejected

        encoded, decoded = _decode_compact(credential)
        header = _decode_structural_json(decoded[0])
        payload = _decode_structural_json(decoded[1])
        _require_canonical_json(header, decoded[0])
        _require_canonical_json(payload, decoded[1])
        key_id = _require_header_profile(header)
        public_key = self._select_key(key_id)
        _verify_signature(
            public_key,
            decoded[2],
            encoded[0] + b"." + encoded[1],
        )

        _require_payload_profile(payload)
        grant = DelegatedGatewayNodeControlTransitGrantCodec().decode(
            payload["gateway_node_control_transit"]
        )
        request = NodeControlCommandRequestCodec().decode_canonical_bytes(
            request_bytes
        )
        _require_outer_claim_congruence(payload, key_id, grant)
        if grant.workspace_id != self._workspace_id:
            raise _TransitAdmissionRejected
        result = verify_gateway_node_control_transit_grant(
            grant,
            request,
            expected_issuer=self._issuer,
            expected_key_id=key_id,
            expected_attempt_id=expected_attempt_id,
            expected_gateway_node_id=self._gateway_node_id,
            now=effective_now,
        )
        if not result.is_accepted:
            raise _TransitAdmissionRejected
        return VerifiedGatewayNodeControlTransit(
            grant=grant,
            request=request,
            effective_now=effective_now,
        )

    def _select_key(self, key_id: str) -> Ed25519PublicKey:
        selected = tuple(
            parsed for key, parsed in self._public_keys if key.key_id == key_id
        )
        if len(selected) != 1:
            raise _TransitAdmissionRejected
        return selected[0]

    def __repr__(self) -> str:
        return "Ed25519GatewayNodeControlTransitVerifier(<redacted>)"


def _validated_public_keys(
    public_keys: object,
) -> tuple[tuple[DelegationPublicKey, Ed25519PublicKey], ...]:
    if (
        type(public_keys) is not tuple
        or not 1 <= len(public_keys) <= _MAX_PUBLIC_KEYS
        or not all(isinstance(value, DelegationPublicKey) for value in public_keys)
    ):
        raise _TransitAdmissionRejected
    ordered = tuple(sorted(public_keys, key=lambda value: value.key_id))
    if len({value.key_id for value in ordered}) != len(ordered):
        raise _TransitAdmissionRejected
    if any(
        value.algorithm is not DelegationKeyAlgorithm.ED25519 for value in ordered
    ):
        raise _TransitAdmissionRejected

    parsed: list[tuple[DelegationPublicKey, Ed25519PublicKey]] = []
    for value in ordered:
        failed = False
        loaded: object | None = None
        try:
            loaded = serialization.load_pem_public_key(
                value.public_key_pem.encode("ascii")
            )
        except (TypeError, ValueError, UnsupportedAlgorithm):
            failed = True
        if failed or not isinstance(loaded, Ed25519PublicKey):
            raise _TransitAdmissionRejected
        parsed.append((value, loaded))
    return tuple(parsed)


def _decode_compact(
    credential: object,
) -> tuple[tuple[bytes, bytes, bytes], tuple[bytes, bytes, bytes]]:
    if (
        type(credential) is not bytes
        or not 1 <= len(credential) <= MAX_GATEWAY_NODE_CONTROL_TRANSIT_CREDENTIAL_BYTES
    ):
        raise _TransitAdmissionRejected
    encoded = credential.split(b".")
    if len(encoded) != 3:
        raise _TransitAdmissionRejected
    bounds = (
        MAX_GATEWAY_NODE_CONTROL_TRANSIT_HEADER_SEGMENT_BYTES,
        MAX_GATEWAY_NODE_CONTROL_TRANSIT_PAYLOAD_SEGMENT_BYTES,
        MAX_GATEWAY_NODE_CONTROL_TRANSIT_SIGNATURE_SEGMENT_BYTES,
    )
    decoded: list[bytes] = []
    for segment, maximum in zip(encoded, bounds, strict=True):
        if not 1 <= len(segment) <= maximum or _BASE64URL.fullmatch(segment) is None:
            raise _TransitAdmissionRejected
        failed = False
        value = b""
        try:
            value = base64.b64decode(
                segment + b"=" * (-len(segment) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, ValueError):
            failed = True
        if failed or base64.urlsafe_b64encode(value).rstrip(b"=") != segment:
            raise _TransitAdmissionRejected
        decoded.append(value)
    return (
        (encoded[0], encoded[1], encoded[2]),
        (decoded[0], decoded[1], decoded[2]),
    )


def _decode_structural_json(value: bytes) -> dict[str, object]:
    parsed: object | None = None
    failed = False
    try:
        parsed = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_ObjectPairs,
            parse_constant=_reject_json_constant,
            parse_int=_parse_jcs_integer_token,
        )
        parsed = _walk_structural_json(parsed)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        failed = True
    if failed or type(parsed) is not dict:
        raise _TransitAdmissionRejected
    return parsed


def _walk_structural_json(value: object) -> object:
    member_count = [0]

    def walk(candidate: object, depth: int) -> object:
        if depth > _MAX_STRUCTURAL_JSON_DEPTH:
            raise _TransitAdmissionRejected
        if type(candidate) is _ObjectPairs:
            member_count[0] += len(candidate)
            keys = [key for key, _value in candidate]
            if (
                member_count[0] > _MAX_STRUCTURAL_JSON_MEMBERS
                or any(type(key) is not str for key in keys)
                or len(set(keys)) != len(keys)
            ):
                raise _TransitAdmissionRejected
            return {key: walk(nested, depth + 1) for key, nested in candidate}
        if type(candidate) is list:
            return [walk(nested, depth + 1) for nested in candidate]
        if candidate is None or type(candidate) in (str, int, float, bool):
            return candidate
        raise _TransitAdmissionRejected

    return walk(value, 0)


def _require_canonical_json(value: object, encoded: bytes) -> None:
    failed = False
    canonical = b""
    try:
        canonical = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError:
        failed = True
    if failed or canonical != encoded:
        raise _TransitAdmissionRejected


def _require_header_profile(header: object) -> str:
    if type(header) is not dict or frozenset(header) != _HEADER_KEYS:
        raise _TransitAdmissionRejected
    if any(type(header[key]) is not str for key in _HEADER_KEYS):
        raise _TransitAdmissionRejected
    if (
        header["alg"] != "EdDSA"
        or header["typ"] != GATEWAY_NODE_CONTROL_TRANSIT_TOKEN_TYPE
    ):
        raise _TransitAdmissionRejected
    return header["kid"]


def _require_payload_profile(payload: object) -> None:
    if type(payload) is not dict or frozenset(payload) != _PAYLOAD_KEYS:
        raise _TransitAdmissionRejected
    if any(type(payload[key]) is not str for key in ("iss", "aud", "jti")):
        raise _TransitAdmissionRejected
    if any(type(payload[key]) is not int for key in ("iat", "nbf", "exp")):
        raise _TransitAdmissionRejected
    if type(payload["gateway_node_control_transit"]) is not dict:
        raise _TransitAdmissionRejected


def _require_outer_claim_congruence(
    payload: Mapping[str, object],
    header_key_id: str,
    grant: DelegatedGatewayNodeControlTransitGrant,
) -> None:
    if (
        payload.get("iss") != grant.issuer
        or payload.get("aud") != grant.audience
        or payload.get("iat") != grant.issued_at
        or payload.get("nbf") != grant.not_before
        or payload.get("exp") != grant.expires_at
        or payload.get("jti") != grant.jti
        or header_key_id != grant.key_id
    ):
        raise _TransitAdmissionRejected


def _verify_signature(
    public_key: Ed25519PublicKey,
    signature: bytes,
    signing_input: bytes,
) -> None:
    if len(signature) != 64:
        raise _TransitAdmissionRejected
    failed = False
    try:
        public_key.verify(signature, signing_input)
    except InvalidSignature:
        failed = True
    if failed:
        raise _TransitAdmissionRejected


def _reject_json_constant(_value: str) -> object:
    raise _TransitAdmissionRejected


def _parse_jcs_integer_token(token: str) -> int | float:
    value = int(token)
    return value if abs(value) <= _MAX_SAFE_INTEGER else float(token)


def _require_graph_reference(
    value: object,
    role: NodeControlGraphReferenceRole,
) -> None:
    if not isinstance(value, NodeControlGraphReference) or value.role is not role:
        raise _TransitAdmissionRejected


def _require_identifier(value: object) -> None:
    if (
        type(value) is not str
        or _IDENTIFIER.fullmatch(value) is None
        or _contains_unsafe_public_material(value)
    ):
        raise _TransitAdmissionRejected


def _require_reference(value: object) -> None:
    if (
        type(value) is not str
        or _REFERENCE.fullmatch(value) is None
        or _contains_unsafe_public_material(value)
    ):
        raise _TransitAdmissionRejected


def _contains_unsafe_public_material(value: str) -> bool:
    projections = (value, _ascii_percent_projection(value))
    return any(
        _contains_credential_envelope(candidate)
        or _contains_endpoint_envelope(candidate)
        for candidate in projections
    )


def _ascii_percent_projection(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        decoded = int(match.group(1), 16)
        return chr(decoded) if decoded <= 0x7F else match.group(0)

    return _ASCII_PERCENT_ESCAPE.sub(replace, value)


def _contains_credential_envelope(value: str) -> bool:
    return any(
        pattern.search(value) is not None
        for pattern in (
            _AUTHORIZATION_ENVELOPE,
            _CREDENTIAL_ASSIGNMENT,
            _PRIVATE_KEY_ARMOR,
            _COMPACT_TOKEN,
        )
    )


def _contains_endpoint_envelope(value: str) -> bool:
    if (
        _SCHEME_ENDPOINT.search(value) is not None
        or _PROTOCOL_RELATIVE_ENDPOINT.search(value) is not None
    ):
        return True
    for match in _HOST_PORT_ENDPOINT.finditer(value):
        if 1 <= int(match.group(2)) <= 65_535:
            return True
    for token in _ENDPOINT_TOKEN_SPLIT.split(value):
        atom = token.strip("[]").rstrip(".")
        if not atom:
            continue
        if _is_localhost_endpoint(atom):
            return True
        try:
            ipaddress.ip_address(atom)
        except ValueError:
            continue
        return True
    return False


def _is_localhost_endpoint(atom: str) -> bool:
    lowered = atom.lower().rstrip(".")
    if ":" in lowered:
        host, separator, port = lowered.rpartition(":")
        if not separator or not port.isdigit() or not 1 <= int(port) <= 65_535:
            return False
        lowered = host.rstrip(".")
    return lowered == "localhost" or lowered.endswith(".localhost")


def _is_epoch(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_SAFE_INTEGER


__all__ = [
    "GATEWAY_NODE_CONTROL_TRANSIT_TOKEN_TYPE",
    "MAX_GATEWAY_NODE_CONTROL_TRANSIT_CREDENTIAL_BYTES",
    "MAX_GATEWAY_NODE_CONTROL_TRANSIT_HEADER_SEGMENT_BYTES",
    "MAX_GATEWAY_NODE_CONTROL_TRANSIT_PAYLOAD_SEGMENT_BYTES",
    "MAX_GATEWAY_NODE_CONTROL_TRANSIT_SIGNATURE_SEGMENT_BYTES",
    "Ed25519GatewayNodeControlTransitVerifier",
    "GatewayNodeControlTransitAdmissionError",
    "VerifiedGatewayNodeControlTransit",
]
