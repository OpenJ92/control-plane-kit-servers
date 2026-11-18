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

    def test_password_admission_refuses_fifo_without_waiting_for_a_writer(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "password-fifo"
            os.mkfifo(path, 0o400)
            started = Event()
            finished = Event()
            failures = []
            outcomes = []

            def read():
                started.set()
                try:
                    readiness.read_password(path)
                except readiness.PasswordFileError:
                    outcomes.append("rejected")
                except BaseException as failure:
                    failures.append(failure)
                else:
                    failures.append(AssertionError("FIFO password path was accepted"))
                finally:
                    finished.set()

            worker = Thread(target=read, daemon=True)
            worker.start()
            self.assertTrue(started.wait(1))
            completed_without_writer = finished.wait(1)
            try:
                self.assertTrue(
                    completed_without_writer, "FIFO admission blocked waiting for a writer"
                )
                if failures:
                    raise failures[0]
                self.assertEqual(outcomes, ["rejected"])
            finally:
                if not completed_without_writer:
                    writer = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
                    os.close(writer)
                worker.join(1)
                self.assertFalse(worker.is_alive(), "FIFO admission worker was not reaped")


class ReadinessProbeTests(unittest.TestCase):
    def test_exact_psql_invocation_has_allowlisted_environment_and_no_secret_argv(self):
        invocation = readiness.psql_invocation(b"SECRET_SENTINEL")
        self.assertEqual(invocation.argv, (
            "/usr/local/bin/psql", "-X", "--no-psqlrc", "-h", "127.0.0.1", "-p", "5432",
            "-U", "cpk", "-d", "cpk", "-tA", "--quiet", "-c",
            "SET statement_timeout = '2s'; SELECT 1;",
        ))
        self.assertEqual(set(invocation.environ), {"PATH", "LANG", "LC_ALL", "PGPASSWORD", "PGCONNECT_TIMEOUT"})
        self.assertEqual(invocation.environ["PGPASSWORD"], "SECRET_SENTINEL")
        self.assertNotIn("SECRET_SENTINEL", " ".join(invocation.argv))
        self.assertNotIn("PGHOST", invocation.environ)
        self.assertNotIn("PGSERVICEFILE", invocation.environ)

    def test_result_classification_preserves_truth_boundaries(self):
        self.assertIs(readiness.classify_psql(0, b"1\n"), core.NodeHealthReadOutcome.HEALTHY)
        for output in (b"", b"0\n", b"SET\n1\n", b"1\nextra\n"):
            with self.subTest(output=output[:10]):
                self.assertIs(readiness.classify_psql(0, output), core.NodeHealthReadOutcome.UNHEALTHY)
        self.assertIs(readiness.classify_psql(2, b""), core.NodeHealthReadOutcome.UNKNOWN)
        self.assertIs(
            readiness.classify_psql(0, b"x" * (readiness.MAX_OUTPUT_BYTES + 1)),
            core.NodeHealthReadOutcome.UNKNOWN,
        )

    def test_observation_exception_terminates_and_reaps_before_releasing_slot(self):
        process = Mock()
        process.poll.return_value = None
        controller = readiness.ReadinessController(password=b"secret", spawn=Mock(return_value=process))
        controller.set_state(readiness.ProductState.RUNNING)

        with patch.object(controller, "_observe", side_effect=OSError("read failed")), \
                patch.object(controller, "_terminate", return_value=True) as terminate:
            self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNKNOWN)

        terminate.assert_called_once_with(process)
        self.assertIsNone(controller._active)
        self.assertTrue(controller._slot.acquire(blocking=False))
        controller._slot.release()

    def test_selector_registration_failure_uses_real_terminate_and_reap(self):
        process = Mock()
        process.pid = 456
        process.stdout = Mock()
        process.poll.side_effect = (None, None)
        process.wait.return_value = 0
        selector = Mock()
        selector.register.side_effect = OSError("selector registration failed")
        controller = readiness.ReadinessController(
            password=b"secret", spawn=Mock(return_value=process)
        )
        controller.set_state(readiness.ProductState.RUNNING)

        with patch.object(readiness.selectors, "DefaultSelector", return_value=selector), \
                patch.object(readiness.os, "killpg") as kill:
            self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNKNOWN)

        kill.assert_called_once_with(process.pid, readiness.signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=readiness.REAP_SECONDS)
        selector.close.assert_called_once_with()
        self.assertIsNone(controller._active)

    def test_failed_exception_cleanup_preserves_handle_and_refuses_new_probe(self):
        process = Mock()
        process.poll.return_value = None
        spawned = Mock(return_value=process)
        controller = readiness.ReadinessController(password=b"secret", spawn=spawned)
        controller.set_state(readiness.ProductState.RUNNING)

        with patch.object(controller, "_observe", side_effect=OSError("read failed")), \
                patch.object(controller, "_terminate", return_value=False):
            self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNKNOWN)

        self.assertIs(controller._active, process)
        self.assertIs(controller.inspect(), core.NodeHealthReadOutcome.UNKNOWN)
        spawned.assert_called_once()

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

        def terminate(active, *, deadline=None):
            self.assertIs(active, process)
            self.assertIsNone(deadline)
            process.poll.return_value = 0
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
            stop_probe.assert_called_once_with(process, deadline=None)


if __name__ == "__main__":
    unittest.main()
