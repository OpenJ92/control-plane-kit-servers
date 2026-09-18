"""#180 connection laws: selected gateway -> actual protected SDK health route."""
import asyncio
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from health_relay_fixtures import World, ReceiverTransport, wire

PACKAGE = "control_plane_kit_servers_cpk_local_gateway"


class HealthRelayTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.receiver = self.world.receiver()
        self.transport = ReceiverTransport(self.receiver)

    def api(self):
        # All upstream fixtures construct first. Missing product behavior is an
        # assertion, not broken collection, a replacement verifier or an xfail.
        for name in ("health_relay_configuration", "health_relay"):
            self.assertIsNotNone(importlib.util.find_spec(PACKAGE + "." + name),
                "#180 gateway health relay connection is missing: " + name)
        return (importlib.import_module(PACKAGE + ".health_relay_configuration"),
                importlib.import_module(PACKAGE + ".health_relay"))

    def composition(self, *, transport=None, timeout_seconds=5):
        config_api, relay_api = self.api()
        w = self.world
        binding = config_api.gateway_health_target_binding(target_id="database-management", target=w.target,
            runtime_id=w.runtime, runtime_contract=w.contract, hostname="wrapped-db")
        config = config_api.GatewayHealthRelayConfiguration(workspace_id=w.target.workspace_id,
            gateway_node_id=w.transit.gateway, runtime_id=w.runtime, targets=(binding,))
        trust_api, verify_api = w.transit.api()
        verifier = w.transit.verifier(trust_api, verify_api)
        relay = relay_api.GatewayHealthRelay(configuration=config, verifier=verifier,
            clock=lambda:w.now, transport=self.transport if transport is None else transport,
            timeout_seconds=timeout_seconds)
        server = importlib.import_module(PACKAGE + ".server")
        return server.create_app(health_relay=relay), config, binding

    def call(self, client, *, request=None, envelope=None, token=None, path=None, headers=None):
        w = self.world
        request = w.request if request is None else request
        signed, _ = w.pair(request)
        return client.post(path or "/cpk/health/" + request.kind.value,
            content=wire(w.envelope(request) if envelope is None else envelope),
            headers=headers if headers is not None else {"Authorization":"Bearer " + (signed if token is None else token),
                "Content-Type":"application/json"})

    def assert_bounded_failure(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(set(response.json()), {"code"})
        self.assertLess(len(response.content), 160)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        for marker in ("wrapped-db", "8087", "workload_credential", "request-a", "Bearer", "private-marker"):
            self.assertNotIn(marker, response.text)

    def test_prerequisite_actual_sdk_accepts_pair_and_rejects_bad_signature_before_callback(self):
        w = self.world
        with TestClient(self.receiver) as client:
            for kind in core.NodeHealthReadKind:
                request = replace(w.request, kind=kind)
                _, token = w.pair(request)
                response = client.get("/__control/health/" + kind.value,
                    headers={"Authorization":"Bearer " + token})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(core.NodeHealthReadResultCodec(request, w.declaration).decode(response.json()).request, request)
            before = list(w.callbacks)
            _, bad = w.pair(workload_private=Ed25519PrivateKey.generate())
            response = client.get("/__control/health/readiness", headers={"Authorization":"Bearer " + bad})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(w.callbacks, before)

    def test_prerequisite_actual_transit_and_edge_free_management_projection(self):
        w = self.world
        config_api, verify_api = w.transit.api()
        signed, _ = w.pair()
        verifier = w.transit.verifier(config_api, verify_api)
        self.assertEqual(w.transit.verify(verifier, signed.encode(), w.request, expected_target=w.target), w.request)
        projected = w.projection()
        self.assertFalse(projected.graph.edges)
        self.assertEqual(projected.projected.workload_surface, w.declaration.surface)
        self.assertEqual(projected.projected.operation.node_id, "wrapped-db")

    def test_both_kinds_all_outcomes_and_repeated_original_request_are_preserved(self):
        app, _, binding = self.composition()
        w = self.world
        with TestClient(app) as client:
            for kind in core.NodeHealthReadKind:
                request = replace(w.request, kind=kind)
                for outcome in core.NodeHealthReadOutcome:
                    w.outcome = outcome
                    for _ in range(2):
                        response = self.call(client, request=request)
                        self.assertEqual(response.status_code, 200)
                        result = core.NodeHealthReadResultCodec(request, w.declaration).decode(response.json())
                        self.assertIs(result.outcome, outcome)
                        self.assertEqual(response.content, result.canonical_bytes())
                        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(len(w.callbacks), 16)
        self.assertEqual(len(self.transport.requests), 16)
        self.assertEqual(binding.origin, "http://wrapped-db:8087")
        for request in self.transport.requests:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.content, b"")
            self.assertEqual(request.url.host, "wrapped-db")
            self.assertEqual(request.url.port, 8087)
            self.assertIn(request.url.path, ("/__control/health/liveness", "/__control/health/readiness"))

    def test_transit_context_original_window_and_attempt_refusal_have_zero_outbound(self):
        app, _, _ = self.composition()
        w = self.world
        with TestClient(app) as client:
            self.assert_bounded_failure(self.call(client, token="forged"), 401)
            wrong = w.envelope()
            wrong["attempt_id"] = "other-attempt"
            self.assert_bounded_failure(self.call(client, envelope=wrong), 401)
            for field in ("workspace_id", "graph_revision", "node_id", "provider_socket_name"):
                target = replace(w.target, **{field:replace(getattr(w.target, field), value="other")})
                candidate = replace(w.request, target=target)
                response = self.call(client, request=candidate)
                self.assertIn(response.status_code, (401, 403))
            for now in (109, 200):
                w.now = now
                self.assert_bounded_failure(self.call(client), 401)
            self.assertEqual(self.transport.requests, [])
            self.assertEqual(w.callbacks, [])
            for now in (110, 199):
                w.now = now
                self.assertEqual(self.call(client).status_code, 200)

    def test_pair_mismatch_or_transit_substitution_is_zero_outbound_but_bad_signature_is_sdk_denial(self):
        app, _, _ = self.composition()
        w = self.world
        with TestClient(app) as client:
            for candidate in (replace(w.request, request_id="other-request"),
                              replace(w.request, kind=core.NodeHealthReadKind.LIVENESS),
                              replace(w.request, runtime_id=replace(w.runtime, value="other-runtime"))):
                _, token = w.pair(candidate)
                self.assert_bounded_failure(self.call(client, envelope=w.envelope(workload=token)), 403)
            transit, _ = w.pair()
            self.assert_bounded_failure(self.call(client, envelope=w.envelope(workload=transit)), 403)
            self.assertEqual(self.transport.requests, [])
            _, bad = w.pair(workload_private=Ed25519PrivateKey.generate())
            self.assert_bounded_failure(self.call(client, envelope=w.envelope(workload=bad)), 502)
            self.assertEqual(len(self.transport.requests), 1)
            self.assertEqual(w.callbacks, [])

    def test_unknown_target_and_closed_framing_reject_before_http(self):
        app, _, _ = self.composition()
        w = self.world
        signed, _ = w.pair()
        with TestClient(app) as client:
            for change, status in (({"target_id":"same-runtime-peer"}, 403),
                    ({"url":"http://arbitrary.invalid"}, 400), ({"attempt_id":True}, 400),
                    ({"profile":"unknown"}, 400)):
                self.assert_bounded_failure(self.call(client, envelope=w.envelope() | change), status)
            response = self.call(client, path="/cpk/health/readiness?url=http://arbitrary.invalid")
            self.assert_bounded_failure(response, 400)
            duplicate = wire(w.envelope())[:-1] + b',"attempt_id":"attempt-a"}'
            self.assert_bounded_failure(client.post("/cpk/health/readiness", content=duplicate,
                headers={"Authorization":"Bearer " + signed}), 400)
            response = self.call(client, headers=[("Authorization", "Bearer " + signed),
                ("Authorization", "Bearer " + signed)])
            self.assert_bounded_failure(response, 401)
            self.assert_bounded_failure(client.post("/cpk/health/readiness", content=b"x"*16385,
                headers={"Authorization":"Bearer " + signed}), 413)
            response = self.call(client, headers={"Authorization":"Bearer " + signed, "X-Oversized":"x"*32768})
            self.assert_bounded_failure(response, 413)
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(w.callbacks, [])

    def test_only_workload_authorization_is_forwarded_and_environment_proxy_is_disabled(self):
        w = self.world
        signed, workload = w.pair()
        original = httpx.AsyncClient.__init__
        options = []
        def capture(instance, *args, **kwargs):
            options.append(kwargs.copy())
            original(instance, *args, **kwargs)
        with patch.object(httpx.AsyncClient, "__init__", capture), patch.dict("os.environ",
                {"HTTP_PROXY":"http://private-marker.invalid", "HTTPS_PROXY":"http://private-marker.invalid"}):
            app, _, _ = self.composition()
            with TestClient(app) as client:
                response = self.call(client, headers={"Authorization":"Bearer " + signed,
                    "Cookie":"operator-private-marker", "X-Operator":"private-marker"})
                self.assertEqual(response.status_code, 200)
        self.assertTrue(options)
        for kwargs in options:
            self.assertIs(kwargs.get("trust_env"), False)
            self.assertIs(kwargs.get("follow_redirects"), False)
        sent = self.transport.requests[0]
        self.assertEqual(sent.headers["authorization"], "Bearer " + workload)
        self.assertNotIn("cookie", sent.headers)
        self.assertNotIn("x-operator", sent.headers)
        self.assertNotIn(signed, str(sent.headers))
        self.assertTrue(self.transport.closed)

    def test_transport_refusal_redirect_and_uncorrelated_200_never_become_health(self):
        w = self.world
        valid = core.NodeHealthReadResult(w.request, w.declaration, core.NodeHealthReadOutcome.HEALTHY).descriptor()
        candidates = [(302, b"private-marker", {"Location":"http://foreign.invalid"}),
            (401, b"private-marker", {}), (503, b"private-marker", {}),
            (200, b'{"status":"ready"}', {}),
            (200, wire(valid | {"request_id":"stale-request"}), {}),
            (200, wire(valid | {"request_digest":"f"*64}), {}),
            (200, wire(valid | {"outcome":"transport-error"}), {}),
            (200, b"x"*447, {})]
        for status, body, headers in candidates:
            calls = []
            async def handler(request):
                calls.append(request)
                return httpx.Response(status, content=body, headers=headers)
            app, _, _ = self.composition(transport=httpx.MockTransport(handler))
            with self.subTest(status=status, body_size=len(body)), TestClient(app) as client:
                self.assert_bounded_failure(self.call(client), 502)
            self.assertEqual(len(calls), 1)
        encoded_events = []
        class EncodedStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                encoded_events.append("read")
                yield b"private-marker"
            async def aclose(self):
                encoded_events.append("closed")
        async def encoded_response(request):
            return httpx.Response(200, headers={"Content-Encoding":"gzip"}, stream=EncodedStream())
        app, _, _ = self.composition(transport=httpx.MockTransport(encoded_response))
        with TestClient(app) as client:
            self.assert_bounded_failure(self.call(client), 502)
        self.assertEqual(encoded_events, ["closed"], "encoding must be rejected before reading or decoding body")
        self.assertEqual(w.callbacks, [])

    def test_overall_deadline_cancels_slow_response_and_closes_stream(self):
        finished = []
        class SlowStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{'
                try:
                    await asyncio.Event().wait()
                finally:
                    finished.append("cancelled")
            async def aclose(self):
                finished.append("closed")
        async def handler(request):
            return httpx.Response(200, stream=SlowStream())
        app, _, _ = self.composition(transport=httpx.MockTransport(handler), timeout_seconds=0.02)
        with TestClient(app) as client:
            self.assert_bounded_failure(self.call(client), 504)
        self.assertIn("cancelled", finished)
        self.assertIn("closed", finished)
        self.assertEqual(self.world.callbacks, [])

    def test_response_stream_stops_at_size_bound_and_releases_transport(self):
        seen = []
        class LargeStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                seen.append("first")
                yield b"x"*447
                seen.append("second")
                yield b"private-marker"
            async def aclose(self):
                seen.append("closed")
        async def handler(request):
            return httpx.Response(200, stream=LargeStream())
        app, _, _ = self.composition(transport=httpx.MockTransport(handler))
        with TestClient(app) as client:
            self.assert_bounded_failure(self.call(client), 502)
        self.assertEqual(seen, ["first", "closed"])

    def test_input_stream_stops_before_aggregation_beyond_limit(self):
        app, _, _ = self.composition()
        signed, _ = self.world.pair()
        async def invoke():
            reads = []
            messages = []
            chunks = iter((b"x"*8192, b"x"*8193, b"private-marker"))
            async def receive():
                chunk = next(chunks)
                reads.append(len(chunk))
                return {"type":"http.request", "body":chunk, "more_body":True}
            async def send(message):
                messages.append(message)
            await app({"type":"http", "asgi":{"version":"3.0"}, "http_version":"1.1",
                "method":"POST", "scheme":"http", "path":"/cpk/health/readiness",
                "raw_path":b"/cpk/health/readiness", "query_string":b"", "root_path":"",
                "headers":[(b"authorization", b"Bearer " + signed.encode())],
                "server":("testserver", 80), "client":("fixture", 1)}, receive, send)
            return reads, messages
        reads, messages = asyncio.run(invoke())
        self.assertEqual(reads, [8192, 8193])
        self.assertEqual(next(item["status"] for item in messages if item["type"] == "http.response.start"), 413)
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(self.world.callbacks, [])
