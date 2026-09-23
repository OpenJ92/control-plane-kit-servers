"""Finite #221 provider-read laws; synthetic credentials and HTTP only."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from control_plane_kit_interpreters.cloudflare.client import CloudflareHttpResponse


HOST = "cpk-bootstrap-grandparent.openj92.dev"
TUNNEL = "d77c7e6b-9a41-4d35-b20c-aed03e0a21ea"
BASE = "https://api.cloudflare.com/client/v4"
ROOT = "/accounts/account-1/cfd_tunnel/" + TUNNEL
TOKEN = "synthetic-private-token"
ORIGIN = "http://retained-origin.internal:8080"


def api(test):
    try:
        return importlib.import_module("control_plane_kit_servers_cpk_server.gateway_ingress_admission")
    except ModuleNotFoundError as error:
        if error.name != "control_plane_kit_servers_cpk_server.gateway_ingress_admission":
            raise
        test.fail("missing finite ingress admission reader")


def env(path):
    path.write_text("\n".join((
        "# existing protected configuration", "export OPENJ92_CLOUDFLARE_ACCOUNT_ID=account-1",
        "OPENJ92_CLOUDFLARE_ZONE_ID='zone-1'", "OPENJ92_CLOUDFLARE_ZONE=openj92.dev",
        'OPENJ92_CLOUDFLARE_API_TOKEN="' + TOKEN + '"',
        "UNRELATED_SETTING=ignored")), encoding="utf-8")
    path.chmod(0o600)


class Provider:
    def __init__(self):
        self.calls = []
        self.responses = {
            "/zones/zone-1/dns_records": {"success": True,
                "result": [{"id": "record-1", "type": "CNAME", "name": HOST,
                            "content": TUNNEL + ".cfargotunnel.com", "proxied": True}],
                "result_info": {"page": 1, "total_pages": 1, "total_count": 1}},
            ROOT: {"success": True, "result": {"id": TUNNEL, "deleted_at": None, "config_src": "cloudflare"}},
            ROOT + "/connections": {"success": True, "result": []},
            ROOT + "/configurations": {"success": True, "result": {"config": {"ingress": [
                {"hostname": HOST, "service": ORIGIN}, {"service": "http_status:404"}]}}},
        }

    def request(self, method, url, *, headers, json=None, params=None):
        self.calls.append((method, url, params, json))
        if headers.get("Authorization") != "Bearer " + TOKEN:
            raise AssertionError("credential not supplied to provider")
        return CloudflareHttpResponse(200, self.responses[url.removeprefix(BASE)])


class GatewayIngressAdmissionTests(unittest.TestCase):
    def test_exact_four_gets_bind_retained_ingress_and_keep_origin_private(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            env(path)
            credentials = module.load_credentials(path)
            provider = Provider()
            result = module.inspect_ingress(credentials, transport=provider)
            self.assertEqual(provider.calls, [
                ("GET", BASE + "/zones/zone-1/dns_records", {"name": HOST, "page": "1", "per_page": "2"}, None),
                ("GET", BASE + ROOT, None, None),
                ("GET", BASE + ROOT + "/connections", None, None),
                ("GET", BASE + ROOT + "/configurations", None, None)])
            self.assertEqual(result.public()["status"], "read-only-compatible")
            self.assertEqual(result.private()["origin_service"], ORIGIN)
            self.assertEqual(result.private()["tunnel_id"], TUNNEL)
            for text in (repr(credentials), repr(result), json.dumps(result.public())):
                self.assertNotIn(TOKEN, text)
                self.assertNotIn(ORIGIN, text)

    def test_dns_identity_or_pagination_drift_stops_before_tunnel_reads(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            env(path)
            for field in ("content", "name", "type", "proxied", "duplicates", "pages", "success"):
                with self.subTest(field=field):
                    provider = Provider()
                    response = provider.responses["/zones/zone-1/dns_records"]
                    if field == "duplicates": response["result"] *= 2
                    elif field == "pages": response["result_info"]["total_pages"] = 2
                    elif field == "success": response["success"] = False
                    else: response["result"][0][field] = False if field == "proxied" else "different"
                    with self.assertRaises(module.AdmissionError):
                        module.inspect_ingress(module.load_credentials(path), transport=provider)
                    self.assertEqual(len(provider.calls), 1)

    def test_tunnel_drift_or_existing_connections_never_reaches_configuration(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            env(path)
            for field in ("id", "deleted_at", "config_src", "connections"):
                with self.subTest(field=field):
                    provider = Provider()
                    if field == "connections": provider.responses[ROOT + "/connections"]["result"] = [{"id": "active"}]
                    else: provider.responses[ROOT]["result"][field] = "different"
                    with self.assertRaises(module.AdmissionError):
                        module.inspect_ingress(module.load_credentials(path), transport=provider)
                    self.assertEqual(len(provider.calls), 3 if field == "connections" else 2)

    def test_ambiguous_or_unsafe_origin_configuration_refuses_without_disclosing_it(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            env(path)
            for rules in (
                [{"hostname": "*.openj92.dev", "service": ORIGIN}, {"service": "http_status:404"}],
                [{"hostname": HOST, "service": "http://user:secret@host/"}, {"service": "http_status:404"}],
                [{"hostname": HOST, "service": ORIGIN, "path": "/private"}, {"service": "http_status:404"}],
                [{"hostname": HOST, "service": ORIGIN}, {"service": ORIGIN}],
                [{"hostname": HOST, "service": ORIGIN, "originRequest": {"httpHostHeader": "other"}}, {"service": "http_status:404"}],
            ):
                provider = Provider()
                provider.responses[ROOT + "/configurations"]["result"]["config"]["ingress"] = rules
                with self.assertRaises(module.AdmissionError) as raised:
                    module.inspect_ingress(module.load_credentials(path), transport=provider)
                self.assertNotIn(ORIGIN, repr(raised.exception))
                self.assertNotIn("secret@", repr(raised.exception))
                self.assertEqual(len(provider.calls), 4)

    def test_protected_literal_environment_rejects_unsafe_or_ambiguous_inputs(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            for suffix in ("\nOPENJ92_CLOUDFLARE_API_TOKEN=duplicate", "\nOPENJ92_CLOUDFLARE_ZONE=$(unsafe)"):
                env(path)
                with path.open("a") as stream: stream.write(suffix)
                with self.assertRaises(module.AdmissionError): module.load_credentials(path)
            env(path)
            path.chmod(0o644)
            with self.assertRaises(module.AdmissionError): module.load_credentials(path)
            path.chmod(0o600)
            link = Path(directory) / "link.env"
            link.symlink_to(path)
            with self.assertRaises(module.AdmissionError): module.load_credentials(link)
            env(path)
            path.write_text(path.read_text().replace(TOKEN, "$(unsafe)"))
            with self.assertRaises(module.AdmissionError): module.load_credentials(path)

    def test_transport_is_get_only_bounded_and_never_redirects_or_retries(self):
        module = api(self)
        url = BASE + ROOT
        for mode in ("redirect", "oversize", "timeout"):
            with self.subTest(mode=mode):
                calls = []
                def handle(request):
                    calls.append(request)
                    if mode == "timeout": raise httpx.ReadTimeout(TOKEN, request=request)
                    if mode == "redirect": return httpx.Response(302, headers={"Location": "https://unrelated.invalid"})
                    return httpx.Response(200, content=b"x" * 65537)
                transport = module.ReadOnlyTransport({url}, transport=httpx.MockTransport(handle))
                with self.assertRaises(module.AdmissionError) as raised:
                    transport.request("GET", url, headers={"Authorization": "Bearer " + TOKEN})
                self.assertEqual(len(calls), 1)
                self.assertNotIn(TOKEN, repr(raised.exception))
        calls = []
        transport = module.ReadOnlyTransport({url}, transport=httpx.MockTransport(lambda request: calls.append(request)))
        for method, target in (("POST", url), ("GET", url + "/token")):
            with self.assertRaises(module.AdmissionError): transport.request(method, target, headers={})
        self.assertEqual(calls, [])

    def test_receipt_is_private_exclusive_and_has_no_token_or_raw_provider_body(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            env(path)
            result = module.inspect_ingress(module.load_credentials(path), transport=Provider())
            receipt = Path(directory) / "receipt.json"
            module.write_receipt(receipt, result)
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            raw = receipt.read_text()
            self.assertNotIn(TOKEN, raw)
            self.assertNotIn("Authorization", raw)
            self.assertEqual(json.loads(raw)["origin_service"], ORIGIN)
            with self.assertRaises(module.AdmissionError): module.write_receipt(receipt, result)
            self.assertEqual(receipt.read_text(), raw)
