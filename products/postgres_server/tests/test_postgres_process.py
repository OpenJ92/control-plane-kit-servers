from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer
from control_plane_kit_servers_postgres_server import process, server
from control_plane_kit_servers_postgres_server.readiness import ProductState, ReadinessController
from postgres_control_fixtures import fixture, readiness_only


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
