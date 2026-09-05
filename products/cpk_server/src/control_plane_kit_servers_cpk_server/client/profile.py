"""Private client profile and credential-reference loading."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping
from urllib.parse import SplitResult, urlsplit, urlunsplit


PROFILE_SCHEMA = "cpk.client-profile.v1"
MAXIMUM_PROFILE_BYTES = 65_536
MAXIMUM_CREDENTIAL_BYTES = 16_384
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_CREDENTIAL_ROLES = frozenset({"operator", "approver", "worker"})


class ClientConfigurationError(ValueError):
    """Fixed, secret-free client configuration failure."""


@dataclass(frozen=True, slots=True)
class ClientProfile:
    endpoint: str
    workspace_id: str
    credentials: Mapping[str, Path]
    state_directory: Path

    def __post_init__(self) -> None:
        endpoint = normalize_endpoint(self.endpoint)
        if endpoint != self.endpoint:
            raise ClientConfigurationError("profile endpoint is not canonical")
        if not _is_identity(self.workspace_id):
            raise ClientConfigurationError("profile workspace_id is invalid")
        if set(self.credentials) != _CREDENTIAL_ROLES:
            raise ClientConfigurationError("profile credential roles are invalid")
        if not all(
            isinstance(path, Path) and path.is_absolute()
            for path in self.credentials.values()
        ):
            raise ClientConfigurationError("profile credential references are invalid")
        if not isinstance(self.state_directory, Path) or not self.state_directory.is_absolute():
            raise ClientConfigurationError("profile state_directory is invalid")

    @property
    def target_digest(self) -> str:
        return hashlib.sha256(self.endpoint.encode("utf-8")).hexdigest()

    def credential(self, role: str) -> bytes:
        try:
            path = self.credentials[role]
        except KeyError as error:
            raise ClientConfigurationError("credential role is unavailable") from error
        value = _read_private_regular(path, MAXIMUM_CREDENTIAL_BYTES)
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as error:
            raise ClientConfigurationError("credential is invalid") from error
        if not text or any(character.isspace() for character in text):
            raise ClientConfigurationError("credential is invalid")
        return value


def load_profile(name: str, *, config_home: Path | None = None) -> ClientProfile:
    """Load one closed named profile without following symlinks."""

    if not is_safe_component(name):
        raise ClientConfigurationError("profile name is invalid")
    root = config_home if config_home is not None else _default_config_home()
    if not isinstance(root, Path) or not root.is_absolute():
        raise ClientConfigurationError("profile directory is invalid")
    path = root / "cpk" / "profiles" / f"{name}.json"
    raw = _read_private_regular(path, MAXIMUM_PROFILE_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ClientConfigurationError("profile document is invalid") from error
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "endpoint",
        "workspace_id",
        "credentials",
        "state_directory",
    }:
        raise ClientConfigurationError("profile document is invalid")
    if value["schema"] != PROFILE_SCHEMA:
        raise ClientConfigurationError("profile schema is unsupported")
    credentials = value["credentials"]
    if not isinstance(credentials, dict) or set(credentials) != _CREDENTIAL_ROLES:
        raise ClientConfigurationError("profile credential roles are invalid")
    try:
        endpoint = normalize_endpoint(value["endpoint"])
        workspace_id = value["workspace_id"]
        credential_paths = {
            role: _absolute_private_path(path_value)
            for role, path_value in credentials.items()
        }
        state_directory = _absolute_private_path(value["state_directory"])
    except (TypeError, ValueError) as error:
        raise ClientConfigurationError("profile document is invalid") from error
    return ClientProfile(endpoint, workspace_id, credential_paths, state_directory)


def normalize_endpoint(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 2048:
        raise ClientConfigurationError("profile endpoint is invalid")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ClientConfigurationError("profile endpoint is invalid")
    if parsed.username is not None or parsed.password is not None:
        raise ClientConfigurationError("profile endpoint is invalid")
    if parsed.query or parsed.fragment:
        raise ClientConfigurationError("profile endpoint is invalid")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ClientConfigurationError("plaintext endpoint must be loopback")
    path = parsed.path.rstrip("/")
    if path and (not path.startswith("/") or ".." in path.split("/")):
        raise ClientConfigurationError("profile endpoint is invalid")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError as error:
        raise ClientConfigurationError("profile endpoint is invalid") from error
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(SplitResult(parsed.scheme, netloc, path, "", ""))


def is_safe_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and value not in {".", ".."}
        and _SAFE_COMPONENT.fullmatch(value) is not None
    )


def _is_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= 200
        and re.fullmatch(r"[A-Za-z0-9._-]+", value) is not None
    )


def _default_config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        path = Path(configured)
        if path.is_absolute():
            return path
    return Path.home() / ".config"


def _absolute_private_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ClientConfigurationError("profile path is invalid")
    path = Path(value)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise ClientConfigurationError("profile path is invalid")
    return path


def _read_private_regular(path: Path, maximum: int) -> bytes:
    _reject_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ClientConfigurationError("private file is unavailable") from error
    try:
        information = os.fstat(descriptor)
        if (
            not stat.S_ISREG(information.st_mode)
            or information.st_uid != os.getuid()
            or stat.S_IMODE(information.st_mode) & 0o077
            or information.st_size > maximum
        ):
            raise ClientConfigurationError("private file is unsafe")
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) > maximum:
            raise ClientConfigurationError("private file is too large")
        return value
    finally:
        os.close(descriptor)


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            information = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(information.st_mode):
            raise ClientConfigurationError("private path contains a symlink")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value
