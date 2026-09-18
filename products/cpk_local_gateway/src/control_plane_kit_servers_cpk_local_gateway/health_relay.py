"""Closed health relay: transit admission, structural pairing, fixed HTTP effect."""
import asyncio
from dataclasses import dataclass, field, replace
import math
from typing import Callable

import httpx
from fastapi import Request
from fastapi.responses import Response
import control_plane_kit_core as core
from .health_relay_configuration import GatewayHealthRelayConfiguration, require_matching_receiver
from .health_transit_configuration import _decode_json, _object, _INPUT_ERRORS
from .health_transit_verification import (
    Ed25519GatewayHealthTransitVerifier, GatewayHealthTransitVerificationError, _compact,
)

_PROFILE = "cpk-gateway-health-relay-request.v1"
_FIELDS = frozenset({"profile", "target_id", "attempt_id", "request", "workload_credential"})
_HEADER_FIELDS = frozenset({"alg", "typ", "kid"})
_CLAIM = "workload_node_health_read"
_CLAIMS = frozenset({"iss", "aud", "iat", "nbf", "exp", "jti", _CLAIM})
_CODES = {400:"request-invalid", 401:"transit-rejected", 403:"target-or-pair-rejected", 413:"request-too-large",
          500:"internal-failure", 502:"target-failure", 504:"timeout"}


class _Refusal(Exception):
    def __init__(self, status):
        self.status = status


def _response(status, body):
    return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control":"no-store"})


def _failure(status):
    return _response(status, ('{"code":"gateway.health.' + _CODES[status] + '"}').encode())


def _authorization(headers):
    if type(headers) is not list or len(headers) > 64:
        raise _Refusal(413)
    values = []
    size = 0
    for item in headers:
        if type(item) is not tuple or len(item) != 2:
            raise _Refusal(400)
        name, value = item
        if type(name) is not bytes or type(value) is not bytes:
            raise _Refusal(400)
        size += len(name) + len(value)
        if size > 32768:
            raise _Refusal(413)
        if name.lower() == b"authorization":
            values.append(value)
    if len(values) != 1 or not values[0].startswith(b"Bearer "):
        raise _Refusal(401)
    credential = values[0][7:]
    if not 1 <= len(credential) <= 12288:
        raise _Refusal(401)
    return credential


def _paired_workload(credential, request):
    """Structural comparison only. The SDK owns workload signature verification."""
    try:
        if type(credential) is not str:
            raise ValueError
        raw = credential.encode("ascii")
        _, decoded = _compact(raw)
        header = _object(_decode_json(decoded[0], 768), _HEADER_FIELDS)
        claims = _object(_decode_json(decoded[1], 6144), _CLAIMS)
        if (any(type(header[name]) is not str for name in _HEADER_FIELDS)
                or header["alg"] != "EdDSA" or header["typ"] != "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"
                or any(type(claims[name]) is not str for name in ("iss", "aud", "jti"))
                or any(type(claims[name]) is not int for name in ("iat", "nbf", "exp"))):
            raise ValueError
        grant = core.DelegatedWorkloadNodeHealthReadGrantCodec().decode(claims[_CLAIM])
        if (header["kid"] != grant.key_id or claims["iss"] != grant.issuer or claims["aud"] != grant.audience
                or claims["iat"] != grant.issued_at or claims["nbf"] != grant.not_before
                or claims["exp"] != grant.expires_at or claims["jti"] != grant.jti
                or grant.audience != core.workload_node_control_audience(request.target)
                or grant.target != request.target or grant.runtime_id != request.runtime_id or grant.kind != request.kind
                or grant.declaration_identity != request.declaration_identity or grant.request_id != request.request_id
                or grant.request_digest != request.canonical_digest()):
            raise ValueError
        return raw
    except _INPUT_ERRORS:
        failure = _Refusal(403)
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthRelay:
    configuration: GatewayHealthRelayConfiguration
    verifier: Ed25519GatewayHealthTransitVerifier
    clock: Callable[[], int] = field(repr=False)
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    timeout_seconds: float = 5

    def __post_init__(self):
        try:
            if (type(self.configuration) is not GatewayHealthRelayConfiguration
                    or type(self.verifier) is not Ed25519GatewayHealthTransitVerifier or not callable(self.clock)
                    or type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds)
                    or not 0 < self.timeout_seconds <= 5
                    or (self.transport is not None and not isinstance(self.transport, httpx.AsyncBaseTransport))):
                raise ValueError
            object.__setattr__(self, "configuration", replace(self.configuration))
            # Both are product-owned values; this never obtains authority from a token.
            require_matching_receiver(self.verifier._configuration, self.configuration)
            return
        except _INPUT_ERRORS:
            failure = ValueError("gateway health relay composition is invalid")
        raise failure

    async def handle(self, inbound: Request, health_kind: str):
        try:
            try:
                kind = core.NodeHealthReadKind(health_kind)
            except ValueError:
                raise _Refusal(400) from None
            if (inbound.scope.get("raw_path") != b"/cpk/health/" + kind.value.encode("ascii")
                    or len(inbound.scope["raw_path"]) > 1024 or inbound.scope.get("query_string") != b""):
                raise _Refusal(400)
            credential = _authorization(inbound.scope.get("headers"))
            body = bytearray()
            async with asyncio.timeout(self.timeout_seconds):
                async for chunk in inbound.stream():
                    if type(chunk) is not bytes:
                        raise _Refusal(400)
                    if len(body) + len(chunk) > 16384:
                        raise _Refusal(413)
                    body.extend(chunk)
            try:
                value = _object(_decode_json(bytes(body), 16384), _FIELDS)
                if (value["profile"] != _PROFILE or type(value["target_id"]) is not str
                        or type(value["attempt_id"]) is not str or not 1 <= len(value["attempt_id"]) <= 128):
                    raise ValueError
                request = core.NodeHealthReadRequestCodec().decode(value["request"])
            except _INPUT_ERRORS:
                raise _Refusal(400) from None
            binding = next((item for item in self.configuration.targets if item.target_id == value["target_id"]), None)
            if binding is None:
                raise _Refusal(403)
            self.verifier.verify(credential, request, expected_attempt_id=value["attempt_id"],
                expected_target=binding.target, expected_runtime_id=binding.runtime_id,
                expected_declaration=binding.declaration, expected_kind=kind, now=self.clock())
            workload = _paired_workload(value["workload_credential"], request)
            result = await self._forward(binding, request, workload)
            return _response(200, result.canonical_bytes())
        except GatewayHealthTransitVerificationError:
            return _failure(401)
        except _Refusal as error:
            return _failure(error.status)
        except TimeoutError:
            return _failure(504)
        except Exception:
            # No exception, URL, body or bearer reaches an HTTP error or log.
            return _failure(500)

    async def _forward(self, binding, request, workload):
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False,
                        timeout=self.timeout_seconds) as client:
                    async with client.stream("GET", binding.origin + "/__control/health/" + request.kind.value,
                            headers={"Authorization":"Bearer " + workload.decode("ascii"),
                                     "Accept":"application/json", "Accept-Encoding":"identity"}) as response:
                        if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity":
                            raise _Refusal(502)
                        body = bytearray()
                        if response.is_stream_consumed:
                            # HTTPX's in-memory transport may provide an already buffered response.
                            if len(response.content) > 446:
                                raise _Refusal(502)
                            body.extend(response.content)
                        else:
                            async for chunk in response.aiter_raw():
                                if len(body) + len(chunk) > 446:
                                    raise _Refusal(502)
                                body.extend(chunk)
                        return core.NodeHealthReadResultCodec(request, binding.declaration).decode(_decode_json(bytes(body), 446))
        except (TimeoutError, httpx.TimeoutException):
            raise _Refusal(504) from None
        except Exception:
            # Even unexpected transport failures cannot expose peer exception text.
            failure = _Refusal(502)
        raise failure
