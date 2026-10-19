import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_servers_postgres_server import readiness


class PasswordFileTests(unittest.TestCase):
    def test_password_bytes_preserve_content_and_strip_only_trailing_lf(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "password"
            path.write_bytes(b"alpha\r\nbeta\r\n\n")
            path.chmod(0o400)
            with patch.object(readiness, "_owner_uid", return_value=70):
                self.assertEqual(readiness.read_password(path), b"alpha\r\nbeta\r")

    def test_password_admission_rejects_unsafe_or_ambiguous_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid"
            valid.write_bytes(b"secret")
            valid.chmod(0o400)
            cases = []
            empty = root / "empty"; empty.write_bytes(b""); empty.chmod(0o400); cases.append(empty)
            nul = root / "nul"; nul.write_bytes(b"bad\x00value"); nul.chmod(0o400); cases.append(nul)
            mode = root / "mode"; mode.write_bytes(b"secret"); mode.chmod(0o440); cases.append(mode)
            large = root / "large"; large.write_bytes(b"x" * (readiness.MAX_PASSWORD_BYTES + 1)); large.chmod(0o400); cases.append(large)
            link = root / "link"; link.symlink_to(valid); cases.append(link)
            cases.append(root / "missing")
            for path in cases:
                with self.subTest(path=path.name), patch.object(readiness, "_owner_uid", return_value=70):
                    with self.assertRaises(readiness.PasswordFileError):
                        readiness.read_password(path)
            with patch.object(readiness, "_owner_uid", return_value=71):
                with self.assertRaises(readiness.PasswordFileError):
                    readiness.read_password(valid)


class ReadinessProbeTests(unittest.TestCase):
    def test_exact_psql_invocation_has_allowlisted_environment_and_no_secret_argv(self):
        invocation = readiness.psql_invocation(b"SECRET_SENTINEL")
        self.assertEqual(invocation.argv, (
            "/usr/local/bin/psql", "-X", "--no-psqlrc", "-h", "127.0.0.1", "-p", "5432",
            "-U", "cpk", "-d", "cpk", "-tA", "-c", "SET statement_timeout = '2s'; SELECT 1;",
        ))
        self.assertEqual(set(invocation.environ), {"PATH", "LANG", "LC_ALL", "PGPASSWORD", "PGCONNECT_TIMEOUT"})
        self.assertEqual(invocation.environ["PGPASSWORD"], "SECRET_SENTINEL")
        self.assertNotIn("SECRET_SENTINEL", " ".join(invocation.argv))
        self.assertNotIn("PGHOST", invocation.environ)
        self.assertNotIn("PGSERVICEFILE", invocation.environ)

    def test_result_classification_preserves_truth_boundaries(self):
        self.assertIs(readiness.classify_psql(0, b"1\n"), core.NodeHealthReadOutcome.HEALTHY)
        for output in (b"", b"0\n", b"1\nextra\n", b"x" * 65):
            with self.subTest(output=output[:10]):
                self.assertIs(readiness.classify_psql(0, output), core.NodeHealthReadOutcome.UNHEALTHY)
        self.assertIs(readiness.classify_psql(2, b""), core.NodeHealthReadOutcome.UNKNOWN)

    def test_probe_contention_never_spawns_a_second_child(self):
        process = Mock()
        process.poll.return_value = None
        controller = readiness.ReadinessController(
            password=b"secret",
            spawn=Mock(return_value=process),
        )
        self.assertTrue(controller._slot.acquire(blocking=False))
        try:
            self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNKNOWN)
            controller._spawn.assert_not_called()
        finally:
            controller._slot.release()

    def test_locally_known_stop_or_native_exit_cannot_report_healthy(self):
        for state in (readiness.ProductState.STOPPING, readiness.ProductState.EXITED):
            controller = readiness.ReadinessController(password=b"secret", spawn=Mock())
            controller.set_state(state)
            with self.subTest(state=state):
                self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNHEALTHY)
                controller._spawn.assert_not_called()

    def test_stop_during_spawn_publishes_then_terminates_and_reaps_probe(self):
        spawn_entered = Event()
        release_spawn = Event()
        terminated = Event()
        process = Mock()
        process.poll.return_value = None

        def spawn(invocation):
            spawn_entered.set()
            self.assertTrue(release_spawn.wait(2))
            return process

        controller = readiness.ReadinessController(password=b"secret", spawn=spawn)
        controller.set_state(readiness.ProductState.RUNNING)

        def observe(active):
            self.assertIs(active, process)
            self.assertTrue(terminated.wait(2))
            return core.NodeHealthReadOutcome.UNKNOWN

        def terminate(active):
            self.assertIs(active, process)
            terminated.set()
            return True

        result = []
        inspection = Thread(target=lambda: result.append(controller.inspect()))
        with patch.object(controller, "_observe", side_effect=observe), \
                patch.object(controller, "_terminate", side_effect=terminate) as stop_probe:
            inspection.start()
            self.assertTrue(spawn_entered.wait(2))
            stopped = []

            def stop():
                controller.set_state(readiness.ProductState.STOPPING)
                stopped.append(controller.stop_active())

            stopping = Thread(target=stop)
            stopping.start()
            self.assertTrue(stopping.is_alive(), "stop crossed an unpublished probe spawn")
            release_spawn.set()
            stopping.join(2)
            inspection.join(2)
            self.assertFalse(stopping.is_alive())
            self.assertFalse(inspection.is_alive())
            self.assertEqual(stopped, [True])
            self.assertEqual(result, [core.NodeHealthReadOutcome.UNHEALTHY])
            stop_probe.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
