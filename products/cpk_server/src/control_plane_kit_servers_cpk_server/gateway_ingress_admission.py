"""Finite, read-only #221 retained-ingress observation; never authority to mutate."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import time
from urllib.parse import urlsplit

import httpx
from control_plane_kit_core.secrets import SecretReference, SecretValue
from control_plane_kit_interpreters.cloudflare.client import (
    CloudflareApiClient, CloudflareHttpResponse, CloudflareZoneAuthority,
)
from control_plane_kit_servers_cpk_server._gateway_diagnostic_bootstrap import read_file
from control_plane_kit_servers_cpk_server._gateway_diagnostic_input import bounded_json


HOSTNAME = "cpk-bootstrap-grandparent.openj92.dev"
EXPECTED_TUNNEL = "d77c7e6b-9a41-4d35-b20c-aed03e0a21ea"
BASE = "https://api.cloudflare.com/client/v4"
_PREFIX = "OPENJ92_CLOUDFLARE_"
_INPUTS = frozenset({"ACCOUNT_ID", "ZONE_ID", "ZONE", "API_TOKEN"})


class AdmissionError(ValueError):
    def __init__(self):
        super().__init__("ingress admission unavailable")


@dataclass(frozen=True, repr=False)
class Credentials:
    account: str
    zone: str
    token: SecretValue

    def __repr__(self):
        return "Credentials(<redacted>)"


def load_credentials(path):
    """Read known literal assignments only; never execute an environment file."""
    try:
        values = {}
        for raw in read_file(path, 65536, protected=True).decode("utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, separator, value = line.partition("=")
            if name not in {_PREFIX + item for item in _INPUTS}:
                continue
            if not separator or name in values or any(char in value for char in "`$\\\x00"):
                raise AdmissionError
            parsed = shlex.split(value, comments=True, posix=True)
            if len(parsed) != 1 or not parsed[0] or len(parsed[0]) > 4096:
                raise AdmissionError
            values[name] = parsed[0]
        if set(values) != {_PREFIX + item for item in _INPUTS}:
            raise AdmissionError
        if values[_PREFIX + "ZONE"] != "openj92.dev":
            raise AdmissionError
        for item in ("ACCOUNT_ID", "ZONE_ID"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", values[_PREFIX + item]):
                raise AdmissionError
        token = values[_PREFIX + "API_TOKEN"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,4096}", token):
            raise AdmissionError
        return Credentials(values[_PREFIX + "ACCOUNT_ID"], values[_PREFIX + "ZONE_ID"], SecretValue(token))
    except Exception:
        raise AdmissionError from None


class ReadOnlyTransport:
    """Exact URL allowlist, one GET, bounded body and time, no redirect or retry."""
    def __init__(self, urls, *, transport=None):
        self.urls = frozenset(urls)
        self.transport = transport

    def request(self, method, url, *, headers, json=None, params=None):
        try:
            if method != "GET" or url not in self.urls or json is not None:
                raise AdmissionError
            deadline = time.monotonic() + 20
            with httpx.Client(timeout=10, verify=True, follow_redirects=False,
                              trust_env=False, transport=self.transport) as client:
                with client.stream("GET", url, headers={**headers, "Accept-Encoding": "identity"}, params=params) as response:
                    if not 200 <= response.status_code < 300:
                        raise AdmissionError
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise AdmissionError
                    if int(response.headers.get("content-length", "0")) > 65536:
                        raise AdmissionError
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline or len(body) + len(chunk) > 65536:
                            raise AdmissionError
                        body.extend(chunk)
                    if time.monotonic() > deadline:
                        raise AdmissionError
                    value = bounded_json(bytes(body), 65536)
                    if type(value) is not dict or value.get("success") is not True:
                        raise AdmissionError
                    return CloudflareHttpResponse(response.status_code, value)
        except Exception:
            raise AdmissionError from None


@dataclass(frozen=True, repr=False)
class AdmissionResult:
    dns_record_id: str
    origin_service: str
    observed_at: str

    def public(self):
        return {"status": "read-only-compatible", "hostname": HOSTNAME,
                "active_connections": 0, "observed_at": self.observed_at}

    def private(self):
        return {**self.public(), "schema": "cpk.gateway-ingress-admission.v1",
                "tunnel_id": EXPECTED_TUNNEL, "dns_record_id": self.dns_record_id,
                "origin_service": self.origin_service}

    def __repr__(self):
        return "AdmissionResult(<private routing>)"


def inspect_ingress(credentials, *, transport=None):
    try:
        if type(credentials) is not Credentials:
            raise AdmissionError
        root = f"/accounts/{credentials.account}/cfd_tunnel/{EXPECTED_TUNNEL}"
        dns = f"/zones/{credentials.zone}/dns_records"
        paths = (dns, root, root + "/connections", root + "/configurations")
        authority = CloudflareZoneAuthority(credentials.account, credentials.zone, "openj92.dev",
            SecretReference("secret://bootstrap/cpk221/cloudflare-api"), HOSTNAME)
        client = CloudflareApiClient(authority, credentials.token,
            transport if transport is not None else ReadOnlyTransport({BASE + path for path in paths}))

        def read(path, params=None):
            # Reuse the selected provider's auth/error mechanics; only these four GETs.
            response = client._request("GET", path, params=params)
            if type(response) is not dict or response.get("success") is not True:
                raise AdmissionError
            return response

        response = read(dns, {"name": HOSTNAME, "page": "1", "per_page": "2"})
        records, page = response.get("result"), response.get("result_info")
        if (type(records) is not list or len(records) != 1 or type(page) is not dict
                or any(type(page.get(key)) is not int or page[key] != 1
                       for key in ("page", "total_pages", "total_count"))):
            raise AdmissionError
        record = records[0]
        if (type(record) is not dict or record.get("type") != "CNAME"
                or record.get("name") != HOSTNAME or record.get("proxied") is not True
                or record.get("content") != EXPECTED_TUNNEL + ".cfargotunnel.com"
                or type(record.get("id")) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record["id"])):
            raise AdmissionError
        tunnel = read(root).get("result")
        if (type(tunnel) is not dict or tunnel.get("id") != EXPECTED_TUNNEL
                or "deleted_at" not in tunnel or tunnel["deleted_at"] is not None
                or tunnel.get("config_src") != "cloudflare"):
            raise AdmissionError
        if read(root + "/connections").get("result") != []:
            raise AdmissionError
        configured = read(root + "/configurations").get("result")
        if type(configured) is not dict or type(configured.get("config")) is not dict:
            raise AdmissionError
        config = configured["config"]
        if set(config) - {"ingress", "originRequest", "warp-routing"}:
            raise AdmissionError
        if config.get("originRequest", {}) != {} or config.get("warp-routing", {"enabled": False}) != {"enabled": False}:
            raise AdmissionError
        rules = config.get("ingress")
        if type(rules) is not list or len(rules) != 2 or rules[1] != {"service": "http_status:404"}:
            raise AdmissionError
        rule = rules[0]
        if (type(rule) is not dict or set(rule) - {"hostname", "service", "originRequest"}
                or rule.get("hostname") != HOSTNAME or rule.get("originRequest", {}) != {}):
            raise AdmissionError
        service = rule.get("service")
        if type(service) is not str or not 1 <= len(service) <= 1024 or not service.isascii():
            raise AdmissionError
        origin = urlsplit(service)
        if (origin.scheme != "http" or not origin.hostname or origin.username is not None
                or origin.password is not None or origin.path not in ("", "/")
                or origin.query or origin.fragment or any(char.isspace() for char in service)
                or "\\" in service or not 1 <= (80 if origin.port is None else origin.port) <= 65535):
            raise AdmissionError
        return AdmissionResult(record["id"], service, datetime.now(timezone.utc).isoformat())
    except Exception:
        raise AdmissionError from None


def write_receipt(path, result):
    descriptor = None
    try:
        path = Path(path)
        parent = path.parent.stat()
        if not path.is_absolute() or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise AdmissionError
        raw = json.dumps(result.private(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > 4096:
            raise AdmissionError
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    except Exception:
        raise AdmissionError from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(arguments)
    try:
        receipt = Path(args.receipt)
        if receipt.exists() or receipt.is_symlink():
            raise AdmissionError
        result = inspect_ingress(load_credentials(Path(args.env_file)))
        write_receipt(receipt, result)
        print(json.dumps(result.public(), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('{"status":"ingress-admission-unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
