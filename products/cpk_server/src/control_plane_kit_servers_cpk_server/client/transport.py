"""Bounded authenticated HTTP transport for public cpk-server contracts."""

from __future__ import annotations

import json
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from control_plane_kit_core.operations import (
    HttpMethod,
    operator_command_http_routes,
    operator_read_http_routes,
)

from .profile import ClientProfile


MAXIMUM_RESPONSE_BYTES = 1_048_576


class ClientTransportError(RuntimeError):
    """Fixed transport failure that retains no response or credential material."""

    def __init__(self, message: str = "cpk-server request could not be verified") -> None:
        super().__init__(message)


class ClientAuthorizationError(ClientTransportError):
    def __init__(self) -> None:
        super().__init__("cpk-server authorization was refused")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class PublicHttpTransport:
    """Invoke only routes from the pinned public Core HTTP contract."""

    def __init__(self, profile: ClientProfile, *, timeout_seconds: float = 30.0) -> None:
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 120:
            raise ValueError("transport timeout is invalid")
        self.profile = profile
        self.timeout_seconds = float(timeout_seconds)
        self._routes = {
            route.route_id: route
            for route in (*operator_read_http_routes(), *operator_command_http_routes())
        }
        self._opener = build_opener(_RejectRedirects())

    def call(
        self,
        route_id: str,
        *,
        path_parameters: Mapping[str, str],
        payload: Mapping[str, object],
        credential_role: str,
    ) -> dict[str, object]:
        try:
            route = self._routes[route_id]
        except KeyError as error:
            raise ClientTransportError("public route is unsupported") from error
        path = route.path_template
        for name, value in path_parameters.items():
            if not isinstance(value, str) or not value:
                raise ClientTransportError("public route coordinate is invalid")
            path = path.replace("{" + name + "}", quote(value, safe=""))
        if "{" in path or "}" in path:
            raise ClientTransportError("public route coordinate is missing")
        url = self.profile.endpoint + path
        data: bytes | None
        if route.method is HttpMethod.GET:
            data = None
            if payload:
                query: list[tuple[str, str]] = []
                for name, value in payload.items():
                    if name == "limit" and type(value) is int:
                        encoded = str(value)
                    else:
                        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
                    query.append((name, encoded))
                url += "?" + urlencode(query)
        else:
            try:
                data = json.dumps(
                    dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            except (TypeError, ValueError) as error:
                raise ClientTransportError("public request is invalid") from error
            if len(data) > route.request_schema.max_bytes:
                raise ClientTransportError("public request exceeds its contract")
        credential = self.profile.credential(credential_role)
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + credential.decode("ascii"),
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=route.method.value, headers=headers)
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
            with response:
                raw = response.read(MAXIMUM_RESPONSE_BYTES + 1)
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ClientAuthorizationError() from None
            raise ClientTransportError() from None
        except (OSError, TimeoutError, URLError):
            raise ClientTransportError() from None
        finally:
            credential = b""
            headers["Authorization"] = ""
        if len(raw) > MAXIMUM_RESPONSE_BYTES:
            raise ClientTransportError("cpk-server response exceeds the client bound")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ClientTransportError("cpk-server response is invalid") from error
        if not isinstance(value, dict):
            raise ClientTransportError("cpk-server response is invalid")
        return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value
