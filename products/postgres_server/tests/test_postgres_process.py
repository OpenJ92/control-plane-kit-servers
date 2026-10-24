from dataclasses import replace
from contextlib import redirect_stdout
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from unittest.mock import ANY, Mock, call, patch

import control_plane_kit_core as core
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer
from control_plane_kit_servers_postgres_server import process, server
from control_plane_kit_servers_postgres_server.readiness import ProductState, ReadinessController
from postgres_control_fixtures import fixture, health_token, readiness_only

with patch.dict(os.environ, {
    "CPK_POSTGRES_TEST_RUN": "cpk-postgres-unit",
    "CPK_POSTGRES_HOST_RECORDS": "/tmp/cpk-postgres-unit",
}):
    import live_postgres_image as live_witness


class PgdataAdmissionTests(unittest.TestCase):
    def test_pgdata_must_be_real_directory_owned_by_runtime_uid(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            with patch.object(process, "_owner_uid", return_value=70):
                process.validate_pgdata(data)
            with patch.object(process, "_owner_uid", return_value=71):
                with self.assertRaises(process.PostgresProcessError):
                    process.validate_pgdata(data)
            link = root / "link"
            link.symlink_to(data, target_is_directory=True)
            with patch.object(process, "_owner_uid", return_value=70):
                with self.assertRaises(process.PostgresProcessError):
                    process.validate_pgdata(link)
            regular = root / "file"
            regular.write_text("not data")
            with patch.object(process, "_owner_uid", return_value=70):
                with self.assertRaises(process.PostgresProcessError):
                    process.validate_pgdata(regular)


class ManagementServerTests(unittest.TestCase):
    def test_real_sdk_host_has_daemon_requests_and_native_readiness(self):
        controller = ReadinessController(password=b"secret")
        host = server.create_management_server(
            readiness_only(fixture().config),
            controller,
            address=("127.0.0.1", 0),
        )
        try:
            self.assertIs(type(host), CpkThreadingHTTPServer)
            self.assertTrue(host.daemon_threads)
            self.assertEqual(host.server_address[0], "127.0.0.1")
        finally:
            host.server_close()

    def test_authentication_denial_precedes_readiness_callback(self):
        value = fixture()
        value.config = readiness_only(value.config)
        controller = Mock()
        controller.inspect.return_value = core.NodeHealthReadOutcome.HEALTHY
        host = server.create_management_server(
            value.config, controller, address=("127.0.0.1", 0), clock=lambda: 150,
        )
        host.daemon_threads = False
        thread = Thread(target=host.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()

        def request(token):
            connection = HTTPConnection(*host.server_address, timeout=2)
            try:
                connection.request("GET", "/__control/health/readiness",
                    headers={"Authorization": "Bearer " + token})
                response = connection.getresponse()
                return response.status, response.read(65537)
            finally:
                connection.close()

        try:
            deadline = time.monotonic() + 2
            while not host.cpk_is_serving:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.001)
            wrong = replace(value.config.target, receiver_id="f" * 32)
            for denied in ("invalid", health_token(value, issued_at=100,
                    request_changes={"target": wrong})[1]):
                self.assertNotEqual(request(denied)[0], 200)
            controller.inspect.assert_not_called()
            status, body = request(health_token(value, issued_at=100)[1])
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["outcome"], "healthy")
            controller.inspect.assert_called_once_with()
        finally:
            host.shutdown()
            host.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_bind_failure_closes_listener_without_spawning_native(self):
        controller = ReadinessController(password=b"secret")
        with patch.object(CpkThreadingHTTPServer, "server_bind", side_effect=RuntimeError("bind")):
            with self.assertRaises(RuntimeError):
                server.create_management_server(
                    readiness_only(fixture().config), controller, address=("127.0.0.1", 0)
                )


class CoordinatorTests(unittest.TestCase):
    def native(self, returncode=None):
        child = Mock()
        child.pid = 321
        child.poll.return_value = returncode
        child.wait.return_value = 0 if returncode is None else returncode
        return child

    def host(self, serving=True):
        host = Mock()
        host.cpk_is_serving = serving
        return host

    def test_native_spawn_is_exact_unmodified_upstream_entrypoint(self):
        child = self.native()
        spawned = Mock(return_value=child)
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"), spawn=spawned
        )
        coordinator.start_native()
        args, kwargs = spawned.call_args
        self.assertEqual(args[0], ("/usr/local/bin/docker-entrypoint.sh", "postgres"))
        self.assertTrue(kwargs["start_new_session"])
        self.assertNotIn("stdout", kwargs)
        self.assertNotIn("stderr", kwargs)

    def test_external_stop_is_idempotent_and_uses_fast_shutdown_once(self):
        child = self.native()
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"), spawn=Mock(return_value=child)
        )
        coordinator.start_native()
        with patch.object(process.os, "killpg") as kill:
            coordinator.request_stop()
            coordinator.request_stop()
            result = coordinator.stop()
        self.assertEqual(result, 0)
        self.assertEqual(kill.call_count, 1)
        self.assertEqual(coordinator.readiness.state, ProductState.EXITED)

    def test_unexpected_native_exit_is_failure_and_never_restart(self):
        child = self.native(returncode=7)
        spawned = Mock(return_value=child)
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"), spawn=spawned
        )
        coordinator.start_native()
        self.assertEqual(coordinator.wait(poll_seconds=0), 1)
        self.assertEqual(spawned.call_count, 1)
        self.assertEqual(coordinator.readiness.state, ProductState.EXITED)
        self.assertEqual(
            coordinator.lifecycle_record,
            process.LifecycleRecord(process.LifecycleReason.NATIVE_EXIT, 7),
        )

    def test_unexpected_native_exit_terminates_active_probe(self):
        native = self.native(returncode=7)
        probe = Mock()
        probe.poll.return_value = None
        controller = ReadinessController(password=b"secret")
        controller.set_state(ProductState.RUNNING)
        controller._active = probe
        coordinator = process.PostgresCoordinator(
            self.host(), controller, spawn=Mock(return_value=native)
        )
        coordinator.start_native()
        with patch.object(process.time, "monotonic", return_value=10.0), \
                patch.object(controller, "_terminate", return_value=True) as terminate:
            self.assertEqual(coordinator.wait(poll_seconds=0), 1)
        terminate.assert_called_once_with(probe, deadline=18.0)
        self.assertEqual(controller.state, ProductState.EXITED)

    def test_normal_management_return_is_failure_and_stops_native(self):
        child = self.native()
        host = self.host()
        coordinator = process.PostgresCoordinator(
            host, ReadinessController(password=b"secret"), spawn=Mock(return_value=child)
        )
        coordinator.start_native()
        coordinator.start_management()
        coordinator._serve_thread.join(2)
        self.assertFalse(coordinator._serve_thread.is_alive())

        with patch.object(process.os, "killpg") as kill:
            self.assertEqual(coordinator.wait(poll_seconds=0), 1)

        kill.assert_called_once_with(child.pid, process.signal.SIGINT)
        self.assertEqual(coordinator.readiness.state, ProductState.EXITED)
        self.assertEqual(
            coordinator.lifecycle_record,
            process.LifecycleRecord(process.LifecycleReason.MANAGEMENT_EXIT),
        )

    def test_readiness_fatal_records_first_observed_branch_and_stops(self):
        child = self.native()
        controller = ReadinessController(password=b"secret")
        controller.set_state(ProductState.FATAL)
        coordinator = process.PostgresCoordinator(
            self.host(), controller, spawn=Mock(return_value=child)
        )
        coordinator.start_native()

        with patch.object(process.os, "killpg"):
            self.assertEqual(coordinator.wait(poll_seconds=0), 1)

        self.assertEqual(
            coordinator.lifecycle_record,
            process.LifecycleRecord(process.LifecycleReason.READINESS_FATAL),
        )

    def test_native_exit_wins_existing_wait_precedence(self):
        child = self.native(returncode=9)
        controller = ReadinessController(password=b"secret")
        controller.set_state(ProductState.FATAL)
        coordinator = process.PostgresCoordinator(
            self.host(), controller, spawn=Mock(return_value=child)
        )
        coordinator._serve_failed.set()
        coordinator.start_native()

        self.assertEqual(coordinator.wait(poll_seconds=0), 1)
        self.assertEqual(
            coordinator.lifecycle_record,
            process.LifecycleRecord(process.LifecycleReason.NATIVE_EXIT, 9),
        )

    def test_first_lifecycle_record_is_retained(self):
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret")
        )
        first = process.LifecycleRecord(process.LifecycleReason.MANAGEMENT_EXIT)
        coordinator._record_lifecycle(first)
        coordinator._record_lifecycle(
            process.LifecycleRecord(process.LifecycleReason.READINESS_FATAL)
        )
        self.assertEqual(coordinator.lifecycle_record, first)

    def test_stop_request_is_flag_only_while_readiness_spawn_lock_is_held(self):
        controller = ReadinessController(password=b"secret")
        controller.set_state(ProductState.RUNNING)
        coordinator = process.PostgresCoordinator(self.host(), controller)
        returned = Event()
        controller._lock.acquire()
        try:
            requester = Thread(target=lambda: (coordinator.request_stop(), returned.set()))
            requester.start()
            self.assertTrue(returned.wait(0.2), "signal callback waited on readiness state")
            self.assertTrue(coordinator._stop_requested.is_set())
        finally:
            controller._lock.release()
            requester.join(2)
        self.assertEqual(controller.state, ProductState.RUNNING)

    def test_stop_uses_one_deadline_for_probe_management_and_native(self):
        child = self.native()
        controller = ReadinessController(password=b"secret")
        controller.set_state(ProductState.RUNNING)
        coordinator = process.PostgresCoordinator(
            self.host(), controller, spawn=Mock(return_value=child)
        )
        coordinator.start_native()

        with patch.object(process.time, "monotonic", return_value=10.0), \
                patch.object(controller, "stop_active", return_value=True) as stop_probe, \
                patch.object(coordinator, "_close_management", return_value=True) as close, \
                patch.object(coordinator, "_stop_native", return_value=True) as stop_native:
            self.assertEqual(coordinator.stop(), 0)

        stop_probe.assert_called_once_with(deadline=18.0)
        close.assert_called_once_with(18.0)
        stop_native.assert_called_once_with(18.0)
        self.assertEqual(controller.state, ProductState.EXITED)

    def test_stop_signals_native_while_probe_and_management_cleanup_are_blocked(self):
        child = self.native()
        controller = ReadinessController(password=b"secret")
        coordinator = process.PostgresCoordinator(
            self.host(), controller, spawn=Mock(return_value=child)
        )
        coordinator.start_native()
        release = Event()
        native_started = Event()

        def blocked(*args, **kwargs):
            self.assertTrue(release.wait(2))
            return True

        def stop_native(deadline):
            native_started.set()
            return True

        with patch.object(controller, "stop_active", side_effect=blocked), \
                patch.object(coordinator, "_close_management", side_effect=blocked), \
                patch.object(coordinator, "_stop_native", side_effect=stop_native):
            result = []
            stopping = Thread(target=lambda: result.append(coordinator.stop()))
            stopping.start()
            self.assertTrue(native_started.wait(1), "native stop waited behind other cleanup")
            release.set()
            stopping.join(2)

        self.assertEqual(result, [0])

    def test_nonzero_native_exit_during_stop_is_failure_and_remains_idempotent(self):
        child = self.native()
        child.wait.return_value = 7
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"), spawn=Mock(return_value=child)
        )
        coordinator.start_native()

        with patch.object(process.os, "killpg"):
            self.assertEqual(coordinator.stop(), 1)
            self.assertEqual(coordinator.stop(), 1)
        self.assertIsNone(coordinator.lifecycle_record)

    def test_native_stop_rejects_already_failed_and_signal_terminated_children(self):
        already_failed = self.native(returncode=7)
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"),
            spawn=Mock(return_value=already_failed),
        )
        coordinator.start_native()
        with patch.object(process.os, "killpg") as kill:
            self.assertFalse(coordinator._stop_native(time.monotonic() + 1))
        kill.assert_not_called()

        signaled = self.native()
        signaled.wait.return_value = -process.signal.SIGINT
        coordinator = process.PostgresCoordinator(
            self.host(), ReadinessController(password=b"secret"),
            spawn=Mock(return_value=signaled),
        )
        coordinator.start_native()
        with patch.object(process.os, "killpg"):
            self.assertFalse(coordinator._stop_native(time.monotonic() + 1))


class LifecycleRecordTests(unittest.TestCase):
    def runtime(self, coordinator):
        return (
            patch.object(process.os, "getuid", return_value=70),
            patch.object(process.os, "getgid", return_value=70),
            patch.object(process, "validate_pgdata"),
            patch.object(process, "read_password", return_value=b"secret"),
            patch.object(process, "read_postgres_control_configuration", return_value=Mock()),
            patch.object(process, "create_management_server", return_value=Mock()),
            patch.object(process, "PostgresCoordinator", return_value=coordinator),
            patch.object(process.signal, "signal"),
        )

    def test_startup_failure_is_phase_bounded_and_redacted(self):
        coordinator = Mock()
        coordinator.start_native.side_effect = OSError("RAW_STARTUP_SENTINEL")
        coordinator.lifecycle_record = None
        stderr = io.StringIO()
        patches = self.runtime(coordinator)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                patches[7], \
                patch.object(process.sys, "stderr", stderr):
            self.assertEqual(process.main(), 1)

        output = stderr.getvalue()
        self.assertIn(process.LIFECYCLE_PREFIX, output)
        self.assertIn('"reason":"startup_failure"', output)
        self.assertNotIn("RAW_STARTUP_SENTINEL", output)
        coordinator.stop.assert_called_once_with(failure=True)

    def test_post_start_failure_remains_unclassified(self):
        coordinator = Mock()
        coordinator.lifecycle_record = None
        coordinator.wait.side_effect = OSError("RAW_POST_START_SENTINEL")
        stderr = io.StringIO()
        patches = self.runtime(coordinator)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                patches[7], \
                patch.object(process.sys, "stderr", stderr):
            self.assertEqual(process.main(), 1)

        output = stderr.getvalue()
        self.assertNotIn(process.LIFECYCLE_PREFIX, output)
        self.assertNotIn("RAW_POST_START_SENTINEL", output)
        coordinator.stop.assert_called_once_with(failure=True)

    def test_lifecycle_emission_is_best_effort(self):
        stream = Mock()
        stream.write.side_effect = OSError("closed")
        process.emit_lifecycle_record(
            process.LifecycleRecord(process.LifecycleReason.NATIVE_EXIT, 7), stream=stream
        )

    def test_main_failure_result_survives_lifecycle_output_sink_failure(self):
        coordinator = Mock()
        coordinator.wait.return_value = 1
        coordinator.lifecycle_record = process.LifecycleRecord(
            process.LifecycleReason.NATIVE_EXIT, 7
        )
        stream = Mock()
        stream.write.side_effect = OSError("RAW_SINK_SENTINEL")
        patches = self.runtime(coordinator)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                patches[7], patch.object(process.sys, "stderr", stream):
            self.assertEqual(process.main(), 1)
        coordinator.wait.assert_called_once_with()
        coordinator.stop.assert_not_called()

    def test_lifecycle_record_rejects_non_closed_shapes(self):
        with self.assertRaises(ValueError):
            process.LifecycleRecord(process.LifecycleReason.NATIVE_EXIT)
        with self.assertRaises(ValueError):
            process.LifecycleRecord(process.LifecycleReason.NATIVE_EXIT, True)
        with self.assertRaises(ValueError):
            process.LifecycleRecord(process.LifecycleReason.MANAGEMENT_EXIT, 1)


class WitnessQueryOrderingTests(unittest.TestCase):
    QUERY_COMMAND = (
        "/usr/local/bin/psql",
        "-X",
        "-U",
        "cpk",
        "-d",
        "cpk",
        "-tA",
        "-c",
        "SELECT value FROM cpk_witness;",
    )

    class Clock:
        def __init__(self):
            self.now = 0.0
            self.sleeps = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    @staticmethod
    def running_container():
        container = Mock()
        container.name = "postgres-recovery"
        container.status = "running"
        return container

    @staticmethod
    def result(stdout=b"retained-row\n", stderr=b"", exit_code=0):
        result = Mock()
        result.output = (stdout, stderr)
        result.exit_code = exit_code
        return result

    def assert_only_retained_query(self, container):
        observed = container.exec_run.call_args_list
        self.assertTrue(observed)
        self.assertEqual(
            observed,
            [call(self.QUERY_COMMAND, stdin=False, demux=True)] * len(observed),
        )

    def test_persisted_query_waits_for_listener_and_still_requires_sql_proof(self):
        clock = self.Clock()
        container = self.running_container()
        connection = Mock()
        events = []
        addresses = []
        attempts = []

        def connect(address, *, timeout):
            events.append("connect")
            addresses.append(address)
            attempts.append((clock.now, timeout))
            if len(attempts) == 1:
                raise ConnectionRefusedError
            return connection

        query_results = iter((self.result(stdout=b""), self.result()))
        container.exec_run.side_effect = lambda *args, **kwargs: (
            events.append("exec") or next(query_results)
        )
        socket_module = Mock()
        socket_module.create_connection.side_effect = connect
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(live_witness.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(live_witness.time, "sleep", side_effect=clock.sleep):
            live_witness.wait_query(container, seconds=1.0, observe_native=True)

        self.assertEqual(events, ["connect", "connect", "exec", "exec"])
        self.assertEqual(addresses, [(container.name, 5432)] * 2)
        self.assertTrue(all(
            0.0 < timeout <= 1.0 - attempt_time
            for attempt_time, timeout in attempts
        ))
        self.assert_only_retained_query(container)
        connection.close.assert_called_once_with()
        self.assertGreater(len(clock.sleeps), 1)
        self.assertLess(clock.now, 1.0)

    def test_terminal_container_before_listener_refuses_without_exec(self):
        container = self.running_container()
        container.status = "exited"
        socket_module = Mock()
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(
                    live_witness,
                    "raise_container_failure",
                    side_effect=AssertionError("bounded failure"),
                ) as failure, self.assertRaisesRegex(AssertionError, "bounded failure"):
            live_witness.wait_query(container, observe_native=True)

        failure.assert_called_once_with(
            container, "PostgreSQL source container exited before readiness"
        )
        socket_module.create_connection.assert_not_called()
        container.exec_run.assert_not_called()

    def test_terminal_container_after_listener_closes_socket_and_refuses_without_exec(self):
        container = self.running_container()
        container.exec_run.return_value = self.result()
        listener_observed = False

        def reload():
            container.status = "exited" if listener_observed else "running"

        def connect(address, *, timeout):
            nonlocal listener_observed
            self.assertEqual(address, (container.name, 5432))
            self.assertGreater(timeout, 0.0)
            listener_observed = True
            return connection

        container.reload.side_effect = reload
        connection = Mock()
        socket_module = Mock()
        socket_module.create_connection.side_effect = connect
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(
                    live_witness,
                    "raise_container_failure",
                    side_effect=AssertionError("bounded failure"),
                ) as failure, self.assertRaisesRegex(AssertionError, "bounded failure"):
            live_witness.wait_query(container, observe_native=True)

        connection.close.assert_called_once_with()
        failure.assert_called_once_with(
            container, "PostgreSQL source container exited before readiness"
        )
        container.exec_run.assert_not_called()

    def test_listener_attempts_and_backoff_share_one_bounded_query_deadline(self):
        clock = self.Clock()
        container = self.running_container()
        container.exec_run.return_value = self.result()
        attempts = []

        def connect(address, *, timeout):
            self.assertEqual(address, (container.name, 5432))
            attempts.append((clock.now, timeout))
            raise ConnectionRefusedError

        socket_module = Mock()
        socket_module.create_connection.side_effect = connect
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(live_witness.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(live_witness.time, "sleep", side_effect=clock.sleep), \
                self.assertRaisesRegex(AssertionError, "retained row was not queryable"):
            live_witness.wait_query(container, seconds=0.25, observe_native=True)

        self.assertGreater(len(attempts), 1)
        self.assertTrue(all(
            0.0 < timeout <= 0.25 - attempt_time
            for attempt_time, timeout in attempts
        ))
        self.assertTrue(all(0.0 < delay <= 0.25 for delay in clock.sleeps))
        self.assertAlmostEqual(clock.now, 0.25)
        container.exec_run.assert_not_called()

    def test_listener_and_sql_polling_share_the_original_deadline(self):
        clock = self.Clock()
        container = self.running_container()
        connection = Mock()
        exec_times = []

        def connect(address, *, timeout):
            self.assertEqual(address, (container.name, 5432))
            clock.now = 0.20
            return connection

        def exec_run(*args, **kwargs):
            exec_times.append(clock.now)
            return self.result(stdout=b"")

        container.exec_run.side_effect = exec_run
        socket_module = Mock()
        socket_module.create_connection.side_effect = connect
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(live_witness.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(live_witness.time, "sleep", side_effect=clock.sleep), \
                self.assertRaisesRegex(AssertionError, "retained row was not queryable"):
            live_witness.wait_query(container, seconds=0.25, observe_native=True)

        connection.close.assert_called_once_with()
        self.assertTrue(exec_times)
        self.assertTrue(all(observed < 0.25 for observed in exec_times))
        self.assert_only_retained_query(container)
        self.assertAlmostEqual(clock.now, 0.25)

    def test_listener_success_after_deadline_closes_socket_without_exec(self):
        clock = self.Clock()
        container = self.running_container()
        container.exec_run.return_value = self.result()
        connection = Mock()

        def connect(address, *, timeout):
            self.assertEqual(address, (container.name, 5432))
            clock.now = 0.25
            return connection

        socket_module = Mock()
        socket_module.create_connection.side_effect = connect
        with patch.object(live_witness, "socket", socket_module, create=True), \
                patch.object(live_witness.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(live_witness.time, "sleep", side_effect=clock.sleep), \
                self.assertRaisesRegex(AssertionError, "retained row was not queryable"):
            live_witness.wait_query(container, seconds=0.25, observe_native=True)

        connection.close.assert_called_once_with()
        container.exec_run.assert_not_called()

    def test_listener_success_does_not_replace_exact_sql_proof(self):
        cases = (
            (self.result(exit_code=1), "retained row was not queryable"),
            (
                self.result(stderr=b"unexpected stderr"),
                "successful retained query wrote stderr",
            ),
        )
        for result, expected_error in cases:
            with self.subTest(
                exit_code=result.exit_code,
                stderr=result.output[1],
                expected_error=expected_error,
            ):
                clock = self.Clock()
                container = self.running_container()
                container.exec_run.return_value = result
                connection = Mock()
                socket_module = Mock()
                socket_module.create_connection.return_value = connection

                with patch.object(live_witness, "socket", socket_module, create=True), \
                        patch.object(
                            live_witness.time,
                            "monotonic",
                            side_effect=clock.monotonic,
                        ), patch.object(
                            live_witness.time,
                            "sleep",
                            side_effect=clock.sleep,
                        ), self.assertRaisesRegex(
                            AssertionError,
                            expected_error,
                        ):
                    live_witness.wait_query(
                        container,
                        seconds=0.25,
                        observe_native=True,
                    )

                socket_module.create_connection.assert_called_once_with(
                    (container.name, 5432),
                    timeout=ANY,
                )
                self.assert_only_retained_query(container)
                connection.close.assert_called_once_with()


class WitnessFailureRecordTests(unittest.TestCase):
    def record(self, reason="management_exit", code=None):
        return (process.LIFECYCLE_PREFIX + json.dumps({
            "reason": reason,
            "native_exit_code": code,
        }, separators=(",", ":"), sort_keys=True)).encode()

    def test_scanner_accepts_only_closed_records(self):
        cases = (
            ("native_exit", 7),
            ("management_exit", None),
            ("readiness_fatal", None),
            ("startup_failure", None),
        )
        for reason, code in cases:
            with self.subTest(reason=reason):
                observed = live_witness.scan_lifecycle_record(self.record(reason, code))
                self.assertEqual(observed, {
                    "lifecycle_record_present": True,
                    "lifecycle_record_valid": True,
                    "lifecycle_record_ambiguous": False,
                    "lifecycle_reason": reason,
                    "native_exit_code": code,
                })

    def test_scanner_rejects_malformed_ambiguous_and_duplicate_records(self):
        prefix = process.LIFECYCLE_PREFIX.encode()
        invalid = (
            prefix + b'{"reason":"management_exit"',
            prefix + b'{"reason":"management_exit"}',
            prefix + b'{"reason":"unknown","native_exit_code":null}',
            prefix + b'{"reason":"management_exit","native_exit_code":null,"extra":1}',
            prefix + b'{"reason":"native_exit","native_exit_code":true}',
            prefix + b'{"reason":"native_exit","native_exit_code":null}',
            prefix + b'{"reason":"management_exit","native_exit_code":7}',
            prefix + b'{"reason":"management_exit","reason":"management_exit","native_exit_code":null}',
            prefix + b'{"reason":"management_exit","reason":"native_exit","native_exit_code":7}',
            self.record() + b"\n" + self.record("readiness_fatal"),
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                observed = live_witness.scan_lifecycle_record(raw)
                self.assertTrue(observed["lifecycle_record_present"])
                self.assertFalse(observed["lifecycle_record_valid"])
                self.assertTrue(observed["lifecycle_record_ambiguous"])
                self.assertIsNone(observed["lifecycle_reason"])
                self.assertIsNone(observed["native_exit_code"])
                self.assertNotIn("unknown", repr(observed))

        self.assertEqual(live_witness.scan_lifecycle_record(b"ordinary log"), {
            "lifecycle_record_present": False,
            "lifecycle_record_valid": False,
            "lifecycle_record_ambiguous": False,
            "lifecycle_reason": None,
            "native_exit_code": None,
        })

    def test_scanner_rejects_bounded_recursive_json(self):
        prefix = process.LIFECYCLE_PREFIX.encode()
        nested = prefix + (b"[" * 2000) + b"0" + (b"]" * 2000)
        self.assertLess(len(nested), live_witness.MAX_FAILURE_LOG_BYTES)
        observed = live_witness.scan_lifecycle_record(nested)
        self.assertEqual(observed, {
            "lifecycle_record_present": True,
            "lifecycle_record_valid": False,
            "lifecycle_record_ambiguous": True,
            "lifecycle_reason": None,
            "native_exit_code": None,
        })

    def test_recursive_or_unexpected_scanner_failure_preserves_original_assertion(self):
        prefix = process.LIFECYCLE_PREFIX.encode()
        nested = prefix + (b"[" * 2000) + b"0" + (b"]" * 2000) + b"RAW_LOG_SENTINEL"
        container = Mock()
        container.attrs = {"State": {"Status": "exited", "ExitCode": 1}}
        container.logs.return_value = nested
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(AssertionError, "original failure"):
            live_witness.raise_container_failure(container, "original failure")
        event_text = output.getvalue()
        event = json.loads(event_text)["postgres_source_failure"]
        self.assertTrue(event["lifecycle_record_present"])
        self.assertFalse(event["lifecycle_record_valid"])
        self.assertTrue(event["lifecycle_record_ambiguous"])
        self.assertNotIn("RAW_LOG_SENTINEL", event_text)

        with patch.object(
            live_witness, "scan_lifecycle_record", side_effect=RuntimeError("RAW_SCAN_SENTINEL")
        ), redirect_stdout(io.StringIO()), self.assertRaisesRegex(
            AssertionError, "original failure"
        ):
            live_witness.raise_container_failure(container, "original failure")

    def test_failure_summary_sink_error_preserves_original_assertion(self):
        container = Mock()
        container.attrs = {"State": {"Status": "exited", "ExitCode": 1}}
        container.logs.return_value = b""
        with patch("builtins.print", side_effect=OSError("RAW_SINK_SENTINEL")), \
                self.assertRaisesRegex(AssertionError, "original failure"):
            live_witness.raise_container_failure(container, "original failure")

    def test_refresh_failure_preserves_logs_redaction_and_original_assertion(self):
        class Container:
            attrs = {"State": {"Status": "cached", "ExitCode": 99, "OOMKilled": True}}

            def __init__(self):
                self.logs_called = False

            def reload(self):
                raise RuntimeError("RAW_REFRESH_SENTINEL")

            def logs(self, **kwargs):
                self.logs_called = True
                return self_record

        self_record = self.record("native_exit", 6)
        container = Container()
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(AssertionError, "original failure"):
            live_witness.raise_container_failure(container, "original failure")

        event_text = output.getvalue()
        event = json.loads(event_text)["postgres_source_failure"]
        self.assertTrue(container.logs_called)
        self.assertFalse(event["state_refresh_available"])
        self.assertIsNone(event["status"])
        self.assertIsNone(event["exit_code"])
        self.assertIsNone(event["oom_killed"])
        self.assertIsNone(event["daemon_error_present"])
        self.assertIsNone(event["daemon_error_sha256"])
        self.assertTrue(event["lifecycle_record_valid"])
        self.assertEqual(event["lifecycle_reason"], "native_exit")
        self.assertEqual(event["native_exit_code"], 6)
        self.assertNotIn("RAW_REFRESH_SENTINEL", event_text)
        self.assertNotIn(process.LIFECYCLE_PREFIX, event_text)


class RefusedLockPidDiagnosticTests(unittest.TestCase):
    def hint(self, pid=b"37"):
        return (b'2026-10-24 20:05:15 UTC [9] FATAL:  lock file "postmaster.pid" already exists\n'
                b'2026-10-24 20:05:15 UTC [9] HINT:  Is another postmaster (PID ' + pid
                + b') running in data directory "/RAW_PRIVATE_PATH"?\n')

    def test_unique_ascii_pid_projects_only_closed_numeric_fields(self):
        for pid in (b"1",b"37",b"2147483647"):
            for role in (b"postmaster",b"postgres"):
                with self.subTest(pid=pid,role=role):
                    raw=self.hint(pid).replace(b'Is another postmaster',b'Is another '+role)
                    self.assertEqual(live_witness.scan_refused_lock_pid(raw),
                                     {"lock_pid_status":"one","refused_lock_pid":int(pid)})

    def test_absent_and_ambiguous_never_select_a_pid(self):
        self.assertEqual(live_witness.scan_refused_lock_pid(b'ordinary log'),
                         {"lock_pid_status":"absent","refused_lock_pid":None})
        for raw in (self.hint()+self.hint(),self.hint()+self.hint(b"38"),
                    self.hint().replace(b'HINT:',b'Is another HINT:')):
            with self.subTest(raw=raw):
                self.assertEqual(live_witness.scan_refused_lock_pid(raw),
                                 {"lock_pid_status":"ambiguous","refused_lock_pid":None})

    def test_malformed_or_unassociated_hints_are_invalid_and_redacted(self):
        invalid=[self.hint(pid) for pid in
                 (b"0",b"-1",b"+1",b"01",b"2147483648",b"9"*11,b"37x",b"\xff",b"\t37")]
        invalid += [self.hint().replace(b'HINT:',b'INFO:'),
                    self.hint().replace(b'already exists',b'is empty'),
                    self.hint().replace(b'"?\n',b'"'),
                    self.hint().replace(b'/RAW_PRIVATE_PATH',b'x'*1024)]
        for raw in invalid:
            with self.subTest(raw=raw[:100]):
                self.assertEqual(live_witness.scan_refused_lock_pid(raw),
                                 {"lock_pid_status":"invalid","refused_lock_pid":None})

    def test_byte_line_and_explicit_truncation_refuse_unique_pid(self):
        cases=((self.hint(),True),
               (b'x'*live_witness.MAX_FAILURE_LOG_BYTES+self.hint(),False),
               (b'ordinary\n'*126+self.hint(),False),
               (self.hint().splitlines()[1],True))
        for raw,truncated in cases:
            with self.subTest(size=len(raw),truncated=truncated):
                self.assertEqual(live_witness.scan_refused_lock_pid(raw,truncated=truncated),
                                 {"lock_pid_status":"truncated","refused_lock_pid":None})

    def test_refusal_and_hint_require_one_adjacent_native_emitter_pair(self):
        fatal,hint=self.hint().splitlines()
        invalid=(fatal+b'\n'+hint.replace(b'[9]',b'[10]'),
                 fatal+b'\nLOG: copied text '+hint,
                 b'LOG: copied text '+fatal+b'\n'+hint,
                 hint+b'\n'+fatal,
                 fatal+b'\nunrelated\n'+hint,
                 fatal+b'\n'+hint.replace(b'UTC',b'unknown'),
                 fatal.replace(b'[9]',b'[2147483648]')+b'\n'+hint.replace(b'[9]',b'[2147483648]'))
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertEqual(live_witness.scan_refused_lock_pid(raw),
                                 {"lock_pid_status":"invalid","refused_lock_pid":None})
        self.assertEqual(live_witness.scan_refused_lock_pid(fatal+b'\n'+fatal+b'\n'+hint),
                         {"lock_pid_status":"ambiguous","refused_lock_pid":None})
        # Millisecond timestamps may differ; the adjacent emitter must match.
        raw=fatal.replace(b'15 UTC',b'15.123 UTC')+b'\n'+hint.replace(b'15 UTC',b'15.124 UTC')
        self.assertEqual(live_witness.scan_refused_lock_pid(raw),
                         {"lock_pid_status":"one","refused_lock_pid":37})

    def test_failure_path_projects_without_raw_text_or_changed_assertion(self):
        container=Mock();container.attrs={"State":{"Status":"exited","ExitCode":1}}
        for raw,status,pid in ((self.hint(),"one",37),
                               (b'x'*live_witness.MAX_FAILURE_LOG_BYTES+self.hint(),"truncated",None)):
            container.logs.return_value=raw
            output=io.StringIO()
            with redirect_stdout(output),self.assertRaisesRegex(AssertionError,'original failure'):
                live_witness.raise_container_failure(container,'original failure')
            event=json.loads(output.getvalue())['postgres_source_failure']
            self.assertEqual((event['lock_pid_status'],event['refused_lock_pid']),(status,pid))
            self.assertNotIn('RAW_PRIVATE_PATH',output.getvalue())
            self.assertNotIn('Is another',output.getvalue())
            container.logs.assert_called_with(stdout=True,stderr=True,tail=128)
        container.logs.side_effect=OSError('RAW_LOG_ERROR')
        output=io.StringIO()
        with redirect_stdout(output),self.assertRaisesRegex(AssertionError,'original failure'):
            live_witness.raise_container_failure(container,'original failure')
        event=json.loads(output.getvalue())['postgres_source_failure']
        self.assertEqual(event['lock_pid_status'],'unavailable')
        self.assertIsNone(event['refused_lock_pid'])
        self.assertNotIn('RAW_LOG_ERROR',output.getvalue())

    def test_parser_exception_preserves_main_failure_and_borrowed_cleanup(self):
        container=Mock();container.attrs={"State":{"Status":"exited","ExitCode":1}}
        container.logs.return_value=self.hint()
        image=Mock()
        output=io.StringIO()
        with patch.object(live_witness,'select_image',return_value=(image,False)), \
                patch.object(live_witness.docker,'from_env'), \
                patch.object(live_witness,'exercise',side_effect=lambda *_:
                             live_witness.raise_container_failure(container,'original failure')), \
                patch.object(live_witness,'scan_refused_lock_pid',side_effect=RuntimeError('RAW_PARSER_ERROR')), \
                patch.object(live_witness,'cleanup_files') as files, \
                patch.object(live_witness,'cleanup_image') as cleanup, \
                redirect_stdout(output),self.assertRaisesRegex(AssertionError,'original failure'):
            live_witness.main()
        files.assert_called_once()
        self.assertIs(cleanup.call_args.args[1],image)
        self.assertFalse(cleanup.call_args.args[3])
        event=json.loads(output.getvalue())['postgres_source_failure']
        self.assertEqual(event['lock_pid_status'],'invalid')
        self.assertIsNone(event['refused_lock_pid'])
        self.assertNotIn('RAW_PARSER_ERROR',output.getvalue())
        self.assertNotIn('PASS',output.getvalue())


class ImageDefinitionTests(unittest.TestCase):
    def test_image_is_exact_official_postgres_nonroot_pid1_wrapper(self):
        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
        source = dockerfile.read_text()
        self.assertIn("postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777", source)
        self.assertIn("USER 70:70", source)
        self.assertIn("EXPOSE 5432 8000", source)
        self.assertIn("control_plane_kit_servers_postgres_server.process", source)
        self.assertNotIn("docker.sock", source)
        self.assertNotIn("POSTGRES_PASSWORD=", source)


if __name__ == "__main__":
    unittest.main()
