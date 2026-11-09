"""Owned-network probe evidence stays bounded and tied to the real read contract."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from receiver_network_probe import check_shared_store, header, probe, request_json


class ReceiverNetworkProbeTests(unittest.TestCase):
    def test_shared_store_requires_authority_refusal_and_exact_operations_result(self):
        def reply(request):
            self.assertEqual(str(request.url), "http://cpk-source:8080/workspaces/root-workspace")
            if "authorization" not in request.headers:
                return httpx.Response(401, json={"error": "unauthorized"})
            self.assertEqual(request.headers["authorization"], "Bearer valid-token")
            return httpx.Response(404, json={"error": {"status": 404,
                "message": "missing workspace 'root-workspace'"}})
        with httpx.Client(base_url="http://cpk-source:8080", transport=httpx.MockTransport(reply)) as client:
            result = check_shared_store(client)
        self.assertTrue(result["shared_store_read_verified"])
        self.assertEqual(result["unauthorized_workspace_status"], 401)

    def test_an_unrelated_404_does_not_prove_the_shared_store_read(self):
        def reply(request):
            return httpx.Response(401 if "authorization" not in request.headers else 404,
                json={"error": {"status": 404, "message": "missing workspace"}})
        with httpx.Client(base_url="http://cpk-source:8080", transport=httpx.MockTransport(reply)) as client:
            with self.assertRaisesRegex(ValueError, "owned shared-store read failed"):
                check_shared_store(client)

    def test_response_size_is_bounded_before_decoding(self):
        with httpx.Client(base_url="http://cpk-source:8080", transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"x" * 65_537))) as client:
            with self.assertRaisesRegex(ValueError, "response exceeds bound"):
                request_json(client, "/health/live")

    def test_header_injection_is_refused_without_returning_credential(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "surface.headers").write_text("Authorization: Bearer fixture\nInjected: value\n")
            with self.assertRaisesRegex(ValueError, "owned header is invalid") as caught:
                header(path, "surface.headers")
            self.assertNotIn("fixture", str(caught.exception))

    def test_readiness_evidence_survives_a_later_workspace_failure_for_signed_sampling(self):
        from source_control_fixture import generate
        with TemporaryDirectory() as directory:
            path = Path(directory)
            generate(path, child=True)
            surface = header(path, "surface.headers")["Authorization"]
            def reply(request):
                route = request.url.path
                authority = request.headers.get("authorization")
                if route == "/health/live":
                    return httpx.Response(200, json={"status": "live"})
                if route == "/health/ready":
                    return httpx.Response(200, json={"status": "ready", "stores": "configured"})
                if not authority or (route.endswith("health/liveness") and authority == surface):
                    return httpx.Response(401, json={"error": "unauthorized"})
                if route == "/workspaces/root-workspace":
                    return httpx.Response(404, json={"error": {"status": 404, "message": "unrelated"}})
                return httpx.Response(200, json={})
            client = httpx.Client(base_url="http://cpk-source:8080", transport=httpx.MockTransport(reply))
            result = {"live_status": None, "ready_status": None,
                "source_control_verified": False, "shared_store_read_verified": False}
            # The existing response verifier owns Core correlation; this case
            # isolates transport evidence retained after a subsequent failure.
            with patch("receiver_network_probe.httpx.Client", return_value=client), patch(
                    "receiver_network_probe.verify_response"):
                with self.assertRaisesRegex(ValueError, "owned shared-store read failed"):
                    probe(path, result)
            self.assertEqual((result["live_status"], result["ready_status"]), (200, 200))
            self.assertEqual(result["stage"], "owned-shared-store-read")
            self.assertFalse(result["shared_store_read_verified"])
