from dataclasses import replace
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer
from control_plane_kit_servers_postgres_server import process, server
from control_plane_kit_servers_postgres_server.readiness import ProductState, ReadinessController
from postgres_control_fixtures import fixture, health_token, readiness_only


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
