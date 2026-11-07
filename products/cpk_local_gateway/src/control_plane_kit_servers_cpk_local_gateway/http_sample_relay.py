"""Supplied-input HTTP sample relay; the SDK and caller own sample semantics.

This opt-in composition authenticates gateway transit, structurally pairs the
workload credential, and performs one fixed configured child GET. It neither
issues credentials nor installs a second registry of original HTTP checks.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field, replace
import math
import re
from typing import Callable

from cryptography.exceptions import InvalidSignature
from fastapi import Request
from fastapi.responses import Response
import httpx
import rfc8785
import control_plane_kit_core as core
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequestCodec, HttpVerificationSampleGrantCodec,
    verify_http_verification_sample_grant,
)

from .health_transit_configuration import _decode_json, _object, _public_key, _INPUT_ERRORS

_PROFILE = "cpk-gateway-http-verification-sample-request.v1"
_FIELDS = frozenset({"profile", "target_id", "request", "workload_credential"})
_HEADER_FIELDS = frozenset({"alg", "typ", "kid"})
_OUTER_CLAIMS = dict(iss="issuer", aud="audience", iat="issued_at", nbf="not_before",
                     exp="expires_at", jti="jti")
_BASE64URL = re.compile(rb"[A-Za-z0-9_-]+\Z")
_CODES = {400: "request-invalid", 401: "transit-rejected", 403: "target-or-pair-rejected",
          413: "request-too-large", 500: "internal-failure", 502: "target-failure", 504: "timeout"}


class _Refusal(Exception):
    def __init__(self, status):
        self.status = status


def _response(status, body):
    return Response(body, status_code=status, media_type="application/json",
                    headers={"Cache-Control": "no-store"})


def _failure(status):
    return _response(status, ('{"code":"gateway.http-sample.' + _CODES[status] + '"}').encode())


def _authorization(headers):
    if type(headers) is not list or len(headers) > 64:
        raise _Refusal(413)
    values, size = [], 0
    for item in headers:
        if (type(item) is not tuple or len(item) != 2
                or type(item[0]) is not bytes or type(item[1]) is not bytes):
            raise _Refusal(400)
        name, value = item
        size += len(name) + len(value)
        if size > 32768:
            raise _Refusal(413)
        if name.lower() == b"authorization":
            values.append(value)
    if len(values) != 1 or not values[0].startswith(b"Bearer "):
        raise _Refusal(401)
    raw = values[0][7:]
    if not 1 <= len(raw) <= 16384:
        raise _Refusal(401)
    return raw


def _credential(raw, *, gateway):
    """Decode closed framing, preserving the exact signed bytes for G verification."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 16384:
        raise ValueError
    parts = raw.split(b".")
    if len(parts) != 3:
        raise ValueError
    decoded = []
    for part, maximum in zip(parts, (1024, 15104, 128), strict=True):
        if not 1 <= len(part) <= maximum or _BASE64URL.fullmatch(part) is None:
            raise ValueError
        value = base64.b64decode(part + b"=" * (-len(part) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(value).rstrip(b"=") != part:
            raise ValueError
        decoded.append(value)
    if len(decoded[2]) != 64:
        raise ValueError
    role = "GATEWAY-HTTP-VERIFICATION-SAMPLE-TRANSIT" if gateway else "WORKLOAD-HTTP-VERIFICATION-SAMPLE"
    claim = "gateway_http_verification_sample_transit" if gateway else "workload_http_verification_sample"
    header = _object(_decode_json(decoded[0], 768), _HEADER_FIELDS)
    claims = _object(_decode_json(decoded[1], 11328), frozenset(_OUTER_CLAIMS) | {claim})
    grant = HttpVerificationSampleGrantCodec().decode(claims[claim])
    if header != dict(alg="EdDSA", typ="CPK-" + role + "+JWT", kid=grant.key_id):
        raise ValueError
    for outer, inner in _OUTER_CLAIMS.items():
        expected = getattr(grant, inner)
        if type(claims[outer]) is not type(expected) or claims[outer] != expected:
            raise ValueError
    return grant, parts[0] + b"." + parts[1], decoded[2]


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHttpSampleTrust:
    """Independently supplied gateway receiver identity and transit public trust."""

    gateway_target: core.NodeControlReceiverTarget
    issuer: str
    public_keys: tuple[core.DelegationPublicKey, ...] = field(repr=False)

    def __post_init__(self):
        try:
            codec = core.NodeControlReceiverTargetCodec()
            if (type(self.gateway_target) is not core.NodeControlReceiverTarget
                    or codec.decode(codec.encode(self.gateway_target)) != self.gateway_target
                    or type(self.issuer) is not str or not 1 <= len(self.issuer) <= 128
                    or not self.issuer.isascii() or not self.issuer.isprintable()
                    or self.issuer.strip() != self.issuer
                    or type(self.public_keys) is not tuple or not 1 <= len(self.public_keys) <= 16):
                raise ValueError
            for key in self.public_keys:
                _public_key(key)
            if (len({key.key_id for key in self.public_keys}) != len(self.public_keys)
                    or len({key.fingerprint_sha256 for key in self.public_keys}) != len(self.public_keys)):
                raise ValueError
        except _INPUT_ERRORS:
            raise ValueError("gateway HTTP sample trust is invalid") from None

    @property
    def audience(self):
        return f"gateway:{self.gateway_target.workspace_id.value}:{self.gateway_target.node_id.value}"


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHttpSampleRelay:
    configuration: core.ReceiverManagementRoutes
    trust: GatewayHttpSampleTrust
    clock: Callable[[], int | float] = field(repr=False)
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    timeout_seconds: float = 5

    def __post_init__(self):
        try:
            if (type(self.configuration) is not core.ReceiverManagementRoutes
                    or type(self.trust) is not GatewayHttpSampleTrust
                    or self.configuration.gateway_target != self.trust.gateway_target
                    or not callable(self.clock) or type(self.timeout_seconds) not in (int, float)
                    or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 5
                    or (self.transport is not None and not isinstance(self.transport, httpx.AsyncBaseTransport))):
                raise ValueError
            object.__setattr__(self, "configuration", replace(self.configuration))
            object.__setattr__(self, "trust", replace(self.trust))
        except _INPUT_ERRORS:
            raise ValueError("gateway HTTP sample relay composition is invalid") from None

    async def handle(self, inbound: Request):
        try:
            loop = asyncio.get_running_loop()
            # One deadline covers body admission and the entire one-hop exchange.
            async with asyncio.timeout_at(loop.time() + self.timeout_seconds) as budget:
                if (inbound.scope.get("raw_path") != b"/cpk/verification/http"
                        or inbound.scope.get("query_string") != b""
                        or inbound.headers.get("content-type", "").lower() != "application/json"):
                    raise _Refusal(400)
                credential = _authorization(inbound.scope.get("headers"))
                body = bytearray()
                async for chunk in inbound.stream():
                    if type(chunk) is not bytes:
                        raise _Refusal(400)
                    if len(body) + len(chunk) > 32768:
                        raise _Refusal(413)
                    body.extend(chunk)
                try:
                    raw = bytes(body)
                    value = _object(_decode_json(raw, 32768), _FIELDS)
                    if (value["profile"] != _PROFILE or type(value["target_id"]) is not str
                            or rfc8785.dumps(value) != raw):
                        raise ValueError
                    request = HttpVerificationSampleRequestCodec().decode(value["request"])
                except _INPUT_ERRORS:
                    raise _Refusal(400) from None
                clock_sample_time = loop.time()
                now = self.clock()
                if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now <= 2**53 - 1:
                    raise ValueError
                transit = self._transit(credential, request, now)
                binding = next((item for item in self.configuration.targets
                                if item.target_id == value["target_id"]), None)
                if (binding is None or binding.target_id != request.route_id
                        or binding.target != request.target
                        or binding.declaration.identity().value != request.declaration_identity
                        or request.gateway_target != self.trust.gateway_target):
                    raise _Refusal(403)
                try:
                    workload = value["workload_credential"].encode("ascii")
                    grant, _, _ = _credential(workload, gateway=False)
                    if (grant.request != request
                            or grant.purpose is not core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE
                            or grant.audience != core.receiver_node_control_audience(binding.target)
                            or now < grant.not_before):
                        raise ValueError
                except _INPUT_ERRORS:
                    raise _Refusal(403) from None
                remaining = min(transit.expires_at, grant.expires_at) - now
                if remaining <= 0:
                    raise _Refusal(504)
                # Clip the original absolute deadline; never reset it per phase.
                deadline = min(budget.when(), clock_sample_time + remaining)
                budget.reschedule(deadline)
                if loop.time() >= deadline:
                    raise _Refusal(504)
                result = await self._forward(binding, workload, deadline)
                if loop.time() >= deadline:
                    raise _Refusal(504)
                return _response(200, result)
        except _Refusal as error:
            return _failure(error.status)
        except (TimeoutError, httpx.TimeoutException):
            return _failure(504)
        except Exception:
            # No candidate, peer body, URL, bearer or exception is reflected.
            return _failure(500)

    def _transit(self, credential, request, now):
        try:
            grant, signed, signature = _credential(credential, gateway=True)
            key = next(key for key in self.trust.public_keys if key.key_id == grant.key_id)
            _public_key(key).verify(signature, signed)
            if (grant.request != request
                    or grant.purpose is not core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT
                    or grant.issuer != self.trust.issuer or grant.audience != self.trust.audience
                    or now < grant.not_before):
                raise ValueError
            if now >= grant.expires_at:
                raise _Refusal(504)
            if not verify_http_verification_sample_grant(grant, request,
                    expected_purpose=core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT,
                    expected_issuer=self.trust.issuer, expected_key_id=key.key_id,
                    expected_audience=self.trust.audience, now=math.floor(now)):
                raise ValueError
            return grant
        except _INPUT_ERRORS + (InvalidSignature, StopIteration):
            raise _Refusal(401) from None

    async def _forward(self, binding, workload, deadline):
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise _Refusal(504)
            async with httpx.AsyncClient(transport=self.transport, trust_env=False,
                    follow_redirects=False, timeout=remaining) as client:
                async with client.stream("GET", binding.origin + "/__control/verification/http",
                        headers={"Authorization": "Bearer " + workload.decode("ascii"),
                                 "Accept": "application/json", "Accept-Encoding": "identity"}) as response:
                    if (response.status_code != 200
                            or len(response.headers.raw) > 64
                            or sum(len(k) + len(v) for k, v in response.headers.raw) > 32768
                            or response.headers.get("content-encoding", "identity") != "identity"
                            or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"):
                        raise _Refusal(502)
                    body = bytearray()
                    if response.is_stream_consumed:
                        if len(response.content) > 2048:
                            raise _Refusal(502)
                        body.extend(response.content)
                    else:
                        async for chunk in response.aiter_raw():
                            if len(body) + len(chunk) > 2048:
                                raise _Refusal(502)
                            body.extend(chunk)
                    return bytes(body)
        except (TimeoutError, httpx.TimeoutException):
            raise _Refusal(504) from None
        except _Refusal:
            raise
        except Exception:
            raise _Refusal(502) from None
