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
from control_plane_kit_operations.advancement import CurrentGraphAdvancementFailure

from .profile import ClientProfile


MAXIMUM_RESPONSE_BYTES = 1_048_576
MAXIMUM_ADVANCEMENT_ERROR_BYTES = 8192


class ClientTransportError(RuntimeError):
    """Fixed transport failure that retains no response or credential material."""

    def __init__(self, message: str = "cpk-server request could not be verified", *,
                 http_status: int | None = None, diagnostic: object = None) -> None:
        super().__init__(message)
        self.http_status = safe_http_status(http_status)
        self.diagnostic = validated_advancement_diagnostic(diagnostic,
            diagnostic.get("correlation") if type(diagnostic) is dict else None
        ) if self.http_status is not None else None


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
                url += "?" + _encode_query(payload, route.request_schema.max_bytes)
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
            "User-Agent": "control-plane-kit-cpk-client/0.1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=route.method.value, headers=headers)
        failure = None
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
            with response:
                raw = response.read(MAXIMUM_RESPONSE_BYTES + 1)
        except HTTPError as error:
            status = safe_http_status(error.code)
            diagnostic = None
            try:
                if status not in {None, 401, 403} and route_id == "command.graph.advance-current":
                    raw_error = error.read(MAXIMUM_ADVANCEMENT_ERROR_BYTES + 1)
                    if len(raw_error) <= MAXIMUM_ADVANCEMENT_ERROR_BYTES:
                        envelope = json.loads(raw_error.decode("utf-8"), object_pairs_hook=_unique_object)
                        if (type(envelope) is dict and set(envelope) == {"error"}
                                and type(envelope["error"]) is dict
                                and set(envelope["error"]) == {"status", "message", "diagnostic"}
                                and type(envelope["error"]["status"]) is int
                                and envelope["error"]["status"] == status
                                and envelope["error"]["message"] == "application service failed"):
                            diagnostic = validated_advancement_diagnostic(envelope["error"]["diagnostic"], {
                                "workspace_id": path_parameters.get("workspace_id"),
                                "run_id": path_parameters.get("run_id"),
                                "plan_id": payload.get("plan_id"),
                                "idempotency_key": payload.get("idempotency_key"),
                            })
            except Exception:
                # Malformed, truncated or unreadable evidence never replaces the known status.
                diagnostic = None
            finally:
                try:
                    error.close()
                except Exception:
                    pass
            failure = (ClientAuthorizationError() if status in {401, 403} else
                ClientTransportError(http_status=status, diagnostic=diagnostic))
        except (OSError, TimeoutError, URLError):
            failure = ClientTransportError()
        finally:
            credential = b""
            headers["Authorization"] = ""
        if failure is not None:
            # Raise outside the handler so the error retains no HTTPError/body context.
            raise failure
        if len(raw) > MAXIMUM_RESPONSE_BYTES:
            raise ClientTransportError("cpk-server response exceeds the client bound")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ClientTransportError("cpk-server response is invalid") from error
        if not isinstance(value, dict):
            raise ClientTransportError("cpk-server response is invalid")
        return value


def safe_http_status(value: object) -> int | None:
    return value if type(value) is int and 400 <= value <= 599 else None


def validated_advancement_diagnostic(value: object, correlation: object) -> dict[str, object] | None:
    """Copy only the closed owner vocabulary bound to the requested coordinates."""
    if (type(value) is not dict or set(value) != {"stage", "reason", "acceptance", "correlation"}
            or value["acceptance"] != "unverified" or type(value["correlation"]) is not dict
            or type(correlation) is not dict
            or set(correlation) != {"workspace_id", "run_id", "plan_id", "idempotency_key"}
            or value["correlation"] != correlation):
        return None
    try:
        owner = CurrentGraphAdvancementFailure(value["stage"], value["reason"], **correlation)
        result = owner.descriptor()
        envelope = {"error": {"status": 500, "message": "application service failed", "diagnostic": result}}
        if len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAXIMUM_ADVANCEMENT_ERROR_BYTES:
            return None
        return result
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _encode_query(payload: Mapping[str, object], maximum: int) -> str:
    try:
        query = []
        for name, value in payload.items():
            if type(name) is not str:
                raise ValueError
            if name in {"runtime_id", "authority_ref"}:
                if type(value) is not str or not value:
                    raise ValueError
                encoded = value
            elif name == "limit":
                if type(value) is not int or value <= 0:
                    raise ValueError
                encoded = str(value)
            else:
                if name in {"target", "after"} and type(value) is not dict:
                    raise ValueError
                encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            query.append((name, encoded))
        result = urlencode(query, quote_via=quote)
        if len(result.encode("ascii")) > maximum:
            raise ValueError
        return result
    except (TypeError, ValueError, RecursionError, UnicodeError):
        failure = ClientTransportError("public query is invalid")
    # Do not retain a serialization exception containing private request values.
    raise failure


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value
