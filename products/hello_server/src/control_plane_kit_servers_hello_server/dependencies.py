"""Finite Hello dependency inputs and cooperative HTTP/TCP observations."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import socket
import time
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from control_plane_kit_core import NodeHealthReadOutcome
from .configuration import HelloConfigurationError, _unique_object

_DEPENDENCY_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")
_MAX_RESPONSE_BYTES = 16_384
MAX_DEPENDENCIES = 8
MAX_DEPENDENCY_BYTES = 8192
MAX_URL_BYTES = 2048
BUDGET_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class DependencyObservation:
    outcome: NodeHealthReadOutcome
    failures: tuple[str, ...] = ()

    def legacy_response(self) -> tuple[int, bytes]:
        if self.outcome is NodeHealthReadOutcome.HEALTHY:
            return 200, b"ready\n"
        if self.outcome is NodeHealthReadOutcome.UNKNOWN:
            return 503, b"dependency observation budget exhausted\n"
        return 503, ("\n".join(self.failures) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class DependencySnapshot:
    dependencies: tuple[DependencyCheck, ...]
    environ: Mapping[str, str]

    def __post_init__(self) -> None:
        if type(self.dependencies) is not tuple or len(self.dependencies) > MAX_DEPENDENCIES:
            raise HelloConfigurationError("Hello dependency snapshot is invalid")
        selected = {}
        names = set()
        for dependency in self.dependencies:
            if type(dependency) is not DependencyCheck or dependency.name in names:
                raise HelloConfigurationError("Hello dependency snapshot is invalid")
            names.add(dependency.name)
            for name in (dependency.http_environment, dependency.database_environment):
                value = self.environ.get(name)
                if value is not None:
                    valid = False
                    try:
                        valid = type(value) is str and len(value.encode("utf-8")) <= MAX_URL_BYTES
                    except UnicodeError:
                        pass
                    if not valid:
                        raise HelloConfigurationError("Hello dependency URL exceeds its bound")
                    selected[name] = value
        object.__setattr__(self, "environ", MappingProxyType(selected))

    def inspect(self, *, clock: Callable[[], float] = time.monotonic) -> DependencyObservation:
        deadline = clock() + BUDGET_SECONDS
        failures = []
        for dependency in self.dependencies:
            for name, check in ((dependency.http_environment, _check_http),
                                (dependency.database_environment, _check_postgres)):
                remaining = deadline - clock()
                if remaining <= 0:
                    return DependencyObservation(NodeHealthReadOutcome.UNKNOWN)
                url = self.environ.get(name)
                if url is None:
                    failures.append(f"{dependency.name}: missing {name}")
                else:
                    failures.extend(check(dependency.name, url, timeout=min(2.0, remaining)))
                if clock() >= deadline:
                    return DependencyObservation(NodeHealthReadOutcome.UNKNOWN)
        if clock() >= deadline:
            return DependencyObservation(NodeHealthReadOutcome.UNKNOWN)
        return DependencyObservation(NodeHealthReadOutcome.UNHEALTHY if failures else NodeHealthReadOutcome.HEALTHY,
                                     tuple(failures))

class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    """One named pair of HTTP and Postgres dependency environment bindings."""

    name: str
    http_environment: str
    database_environment: str

    def __post_init__(self) -> None:
        _validate_dependency_name(self.name)
        _validate_environment_name(self.http_environment)
        _validate_environment_name(self.database_environment)

    def check(self, environ: Mapping[str, str]) -> list[str]:
        failures: list[str] = []
        http_url = environ.get(self.http_environment)
        database_url = environ.get(self.database_environment)
        if http_url is None:
            failures.append(f"{self.name}: missing {self.http_environment}")
        else:
            failures.extend(_check_http(self.name, http_url))
        if database_url is None:
            failures.append(f"{self.name}: missing {self.database_environment}")
        else:
            failures.extend(_check_postgres(self.name, database_url))
        return failures

    def descriptor(self) -> dict[str, str]:
        return {
            "name": self.name,
            "http_environment": self.http_environment,
            "database_environment": self.database_environment,
        }


def dependency_environment_names(name: str) -> tuple[str, str]:
    """Return the conventional HTTP/Postgres environment pair for a dependency."""

    _validate_dependency_name(name)
    suffix = name.upper().replace("-", "_")
    return (
        f"HELLO_HTTP_{suffix}_URL",
        f"HELLO_DATABASE_{suffix}_URL",
    )


def load_dependencies(raw: str | None) -> tuple[DependencyCheck, ...]:
    """Decode the bounded runtime dependency declaration language."""

    if raw in (None, ""):
        return ()
    bounded = False
    try:
        bounded = type(raw) is str and len(raw.encode("utf-8")) <= MAX_DEPENDENCY_BYTES
    except UnicodeError:
        pass
    if not bounded:
        raise HelloConfigurationError("Hello dependency declaration exceeds its bound")
    try:
        decoded = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        decoded = None
    if not isinstance(decoded, list) or len(decoded) > MAX_DEPENDENCIES:
        raise HelloConfigurationError("HELLO_DEPENDENCIES_JSON must be a list")
    dependencies: list[DependencyCheck] = []
    seen: set[str] = set()
    for item in decoded:
        if not isinstance(item, dict) or set(item) - {
            "name",
            "http_environment",
            "database_environment",
        }:
            raise HelloConfigurationError("dependency declaration is malformed")
        name = _required_text(item, "name")
        if name in seen:
            raise HelloConfigurationError("dependency names must be unique")
        seen.add(name)
        http_environment = item.get("http_environment")
        database_environment = item.get("database_environment")
        if http_environment is None or database_environment is None:
            http_environment, database_environment = dependency_environment_names(name)
        dependencies.append(
            DependencyCheck(
                name=name,
                http_environment=_text(http_environment, "http_environment"),
                database_environment=_text(database_environment, "database_environment"),
            )
        )
    return tuple(dependencies)


def _check_http(name: str, url: str, *, timeout: float = 2) -> list[str]:
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in {"http", "https"} and parsed.netloc and parsed.port != 0
    except ValueError:
        valid = False
    if not valid:
        return [f"{name}: HTTP dependency URL is malformed"]
    request = Request(url, method="GET")
    opener = build_opener(NoRedirects)
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(_MAX_RESPONSE_BYTES + 1)
            if response.status >= 400:
                return [f"{name}: HTTP dependency returned {response.status}"]
    except HTTPError as error:
        error.close()
        return [f"{name}: HTTP dependency returned {error.code}"]
    except (OSError, URLError) as error:
        return [f"{name}: HTTP dependency unavailable: {type(error).__name__}"]
    return []


def _check_postgres(name: str, url: str, *, timeout: float = 2) -> list[str]:
    try:
        parsed = urlsplit(url)
        port = parsed.port or 5432
    except ValueError:
        return [f"{name}: Postgres dependency URL is malformed"]
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        return [f"{name}: Postgres dependency URL has unsupported scheme"]
    if not parsed.hostname:
        return [f"{name}: Postgres dependency URL is missing host"]
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return []
    except OSError as error:
        return [f"{name}: Postgres dependency unavailable: {type(error).__name__}"]


def _required_text(value: Mapping[str, object], key: str) -> str:
    return _text(value.get(key), key)


def _text(value: object, key: str) -> str:
    if not isinstance(value, str) or value == "":
        raise HelloConfigurationError(f"{key} must be a nonempty string")
    return value


def _validate_dependency_name(value: str) -> None:
    if not isinstance(value, str) or len(value) > 64 or _DEPENDENCY_NAME.fullmatch(value) is None:
        raise HelloConfigurationError(
            "dependency name must start with a lowercase letter and contain only "
            "lowercase letters, digits, and hyphens"
        )


def _validate_environment_name(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value):
        raise HelloConfigurationError("dependency environment name is malformed")
