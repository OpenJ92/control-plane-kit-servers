import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from control_plane_kit_core import NodeHealthReadOutcome, NodeHealthReadKind
from control_plane_kit_servers_hello_server import dependencies as deps
from control_plane_kit_servers_hello_server.configuration import HelloConfigurationError
from hello_control_fixtures import fixture, running, request, token


class HelloDependencyTests(unittest.TestCase):
    def snapshot(self, count=1):
        values = [{"name":f"item-{index}"} for index in range(count)]
        dependencies = deps.load_dependencies(json.dumps(values))
        environ = {}
        for dependency in dependencies:
            environ[dependency.http_environment] = "http://example.invalid"
            environ[dependency.database_environment] = "postgresql://user:private@example.invalid/database"
        return deps.DependencySnapshot(dependencies, environ)

    def test_finite_input_boundaries_reject_without_truncating(self):
        exact = "[]" + " " * (8192 - 2)
        self.assertEqual(deps.load_dependencies(exact), ())
        self.assertEqual(len(self.snapshot(8).dependencies), 8)
        name = "a" * 64
        self.assertEqual(deps.load_dependencies(json.dumps([{"name":name}]))[0].name, name)
        for raw in (exact + " ", json.dumps([{"name":f"a-{i}"} for i in range(9)]),
                    json.dumps([{"name":name + "a"}]), '[{"name":"a","name":"b"}]',
                    '[{"name":"a"},{"name":"a"}]', "\ud800"):
            with self.subTest(raw_size=len(raw)), self.assertRaises(HelloConfigurationError):
                deps.load_dependencies(raw)
        snapshot = self.snapshot()
        key = snapshot.dependencies[0].http_environment
        for value in ("a" * 2048, "é" * 1024):
            self.assertEqual(deps.DependencySnapshot(snapshot.dependencies, {key:value}).environ[key], value)
            with self.assertRaises(HelloConfigurationError):
                deps.DependencySnapshot(snapshot.dependencies, {key:value + "a"})
        with self.assertRaises(HelloConfigurationError):
            deps.DependencyCheck("a", "A" * 129, "DATABASE")
        with self.assertRaises(HelloConfigurationError) as caught:
            deps.DependencySnapshot(snapshot.dependencies, {key:"\ud800"})
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(deps.DependencyCheck("a", "A" * 128, "DATABASE").http_environment, "A" * 128)
        self.assertNotIn("private", repr(snapshot))

    def test_cooperative_budget_caps_work_propagates_remaining_and_never_reports_late_healthy(self):
        now = [0.0]
        def quick(*args, **kwargs):
            now[0] += 0.1
            return []
        with patch.object(deps, "_check_http", side_effect=quick) as http, \
                patch.object(deps, "_check_postgres", side_effect=quick) as postgres:
            self.assertIs(self.snapshot(8).inspect(clock=lambda:now[0]).outcome, NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(http.call_count + postgres.call_count, 16)
            self.assertTrue(all(call.kwargs["timeout"] == 2 for call in http.call_args_list + postgres.call_args_list))
        now[0] = 0
        def slow_http(*args, **kwargs):
            now[0] = 4.8
            return []
        def late_tcp(*args, **kwargs):
            now[0] = 5.1
            return []
        with patch.object(deps, "_check_http", side_effect=slow_http) as http, \
                patch.object(deps, "_check_postgres", side_effect=late_tcp) as postgres:
            result = self.snapshot(2).inspect(clock=lambda:now[0])
            self.assertIs(result.outcome, NodeHealthReadOutcome.UNKNOWN)
            self.assertEqual(http.call_count, 1)
            self.assertEqual(postgres.call_count, 1)
            self.assertAlmostEqual(postgres.call_args.kwargs["timeout"], 0.2)
            self.assertEqual(result.legacy_response(), (503,b"dependency observation budget exhausted\n"))
        times = iter((0, 5))
        with patch.object(deps, "_check_http") as http:
            self.assertIs(self.snapshot().inspect(clock=lambda:next(times)).outcome, NodeHealthReadOutcome.UNKNOWN)
            http.assert_not_called()
        self.assertIs(deps.DependencySnapshot((), {}).inspect().outcome, NodeHealthReadOutcome.HEALTHY)

    def test_http_status_and_capped_sample_preserve_meaning_and_tcp_is_only_connect(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"x" * 16385
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(deps, "build_opener", return_value=opener) as build:
            self.assertEqual(deps._check_http("a", "https://example.invalid", timeout=0.25), [])
            response.read.assert_called_once_with(16385)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 0.25)
            self.assertEqual(opener.open.call_args.args[0].method, "GET")
            self.assertIsNone(build.call_args.args[0].redirect_request(None,None,302,"",None,"http://redirect"))
            response.status = 503
            self.assertEqual(deps._check_http("a", "http://example.invalid"), ["a: HTTP dependency returned 503"])
            opener.open.side_effect = HTTPError("http://secret",302,"private",{},None)
            self.assertEqual(deps._check_http("a", "http://example.invalid"), ["a: HTTP dependency returned 302"])
            opener.open.side_effect = URLError("private credential")
            self.assertNotIn("private", str(deps._check_http("a", "http://example.invalid")))
        connection = MagicMock()
        with patch.object(deps.socket, "create_connection", return_value=connection) as connect:
            self.assertEqual(deps._check_postgres("a", "postgresql://user:private@host:5433/db", timeout=0.1), [])
            connect.assert_called_once_with(("host",5433), timeout=0.1)
            self.assertEqual(connection.method_calls, [])  # No SQL/login protocol is attempted.
        for url in ("postgresql-fake://host", "postgresql://", "postgresql://host:invalid"):
            self.assertTrue(deps._check_postgres("a",url))

    def test_sdk_and_legacy_share_budget_and_failure_results(self):
        f = fixture()
        environment = {"HELLO_DEPENDENCIES_JSON":'[{"name":"a"}]',
                       "HELLO_HTTP_A_URL":"http://private", "HELLO_DATABASE_A_URL":"postgresql://private"}
        now = [0.0]
        def late(*args, **kwargs):
            now[0] += 6
            return []
        with patch.object(deps, "_check_http", side_effect=late), \
                patch.object(deps, "_check_postgres") as postgres, \
                running(self,f,environment,observation_clock=lambda:now[0]) as host:
            self.assertEqual(request(host,"/health/ready")[:2], (503,b"dependency observation budget exhausted\n"))
            status, body, _ = request(host,"/__control/health/readiness",token(f))
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)["outcome"],"unknown")
            postgres.assert_not_called()
            status, body, _ = request(host,"/__control/health/liveness",token(f,kind=NodeHealthReadKind.LIVENESS))
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)["outcome"],"healthy")
