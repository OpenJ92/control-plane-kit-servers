"""Product startup observations and management admission, without a live daemon."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import os
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_servers_postgres_server import process
from control_plane_kit_servers_postgres_server.readiness import ProductState, ReadinessController
from postgres_control_fixtures import fixture


class NativeListenerObservationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.binary = self.root / "postgres"
        self.binary.write_bytes(b"fixture executable identity")
        self.child = self.root / "321"
        (self.child / "fd").mkdir(parents=True)
        (self.child / "net").mkdir()
        (self.child / "exe").symlink_to(self.binary)
        (self.child / "fd" / "4").symlink_to("socket:[12345]")
        self.table("00000000:1538", "0A", "12345")

    def table(self, endpoint, state, inode):
        (self.child / "net" / "tcp").write_text(
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
            f"   0: {endpoint} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000 70 0 {inode}\n"
        )

    def observe(self, **kwargs):
        observer = getattr(process, "native_listener_observed", None)
        self.assertTrue(callable(observer), "native child listener observation is missing")
        return observer(321, proc_root=self.root, native_executable=self.binary, **kwargs)

    def test_only_current_native_executable_owned_ipv4_listener_admits(self):
        self.assertTrue(self.observe())
        for endpoint, state, inode in (
            ("0100007F:1538", "0A", "12345"),
            ("00000000:1538", "01", "12345"),
            ("00000000:1539", "0A", "12345"),
            ("0200007F:1538", "0A", "12345"),
            ("00000000:1538", "0A", "99999"),
        ):
            with self.subTest(endpoint=endpoint, state=state, inode=inode):
                self.table(endpoint, state, inode)
                self.assertEqual(self.observe(), endpoint == "0100007F:1538")
        self.table("00000000:1538", "0A", "12345")
        shell = self.root / "shell"
        shell.write_bytes(b"different executable")
        (self.child / "exe").unlink()
        (self.child / "exe").symlink_to(shell)
        self.assertFalse(self.observe())

    def test_child_descriptor_is_rechecked_after_socket_table_observation(self):
        original = os.readlink
        seen = 0

        def readlink(path, *args, **kwargs):
            nonlocal seen
            if Path(path) == self.child / "fd" / "4":
                seen += 1
                if seen > 1:
                    return "socket:[99999]"
            return original(path, *args, **kwargs)

        with patch.object(process.os, "readlink", side_effect=readlink):
            self.assertFalse(self.observe())
        self.assertGreaterEqual(seen, 2)

    def test_unavailable_or_malformed_metadata_fails_closed_without_raw_data(self):
        for content in ("PRIVATE_INVALID_METADATA\n", "x" * 300000):
            with self.subTest(size=len(content)):
                (self.child / "net" / "tcp").write_text(content)
                with self.assertRaises(process.PostgresProcessError) as error:
                    self.observe()
                self.assertNotIn("PRIVATE_INVALID_METADATA", str(error.exception))
                self.assertNotIn(str(self.root), str(error.exception))
        self.table("00000000:1538", "0A", "12345")
        with patch.object(process.os, "scandir", side_effect=PermissionError("PRIVATE_DENIAL")):
            with self.assertRaises(process.PostgresProcessError) as error:
                self.observe()
        self.assertNotIn("PRIVATE_DENIAL", str(error.exception))

    def test_descriptor_enumeration_is_bounded_even_for_non_socket_entries(self):
        for number in range(5, 262):
            (self.child / "fd" / str(number)).symlink_to("/dev/null")
        with self.assertRaises(process.PostgresProcessError):
            self.observe()

    def test_cancellation_does_not_require_reading_child_metadata(self):
        with patch.object(process.os, "scandir", side_effect=AssertionError("unexpected read")):
            self.assertFalse(self.observe(cancelled=lambda: True))

    def test_tcp_observation_bounds_cumulative_valid_rows_and_cancels_during_scan(self):
        header = "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
        row = "0: 00000000:1539 00000000:0000 0A 00000000:00000000 00:00000000 00000000 70 0 99999\n"
        (self.child / "net" / "tcp").write_text(header + row * 4000)
        with self.assertRaises(process.PostgresProcessError):
            self.observe()
        self.table("00000000:1538", "0A", "12345")
        stopped = False
        original = os.readlink

        def readlink(path, *args, **kwargs):
            nonlocal stopped
            result = original(path, *args, **kwargs)
            stopped = True
            return result

        with patch.object(process.os, "readlink", side_effect=readlink):
            self.assertFalse(self.observe(cancelled=lambda: stopped))
        self.assertTrue(stopped)

    def test_changed_executable_or_vanished_descriptor_cannot_admit(self):
        other = self.root / "other"
        other.write_bytes(b"other executable")
        other_status = other.stat()
        original = os.stat
        seen = 0

        def stat(path, *args, **kwargs):
            nonlocal seen
            if Path(path) == self.child / "exe":
                seen += 1
                if seen > 1:
                    return other_status
            return original(path, *args, **kwargs)

        with patch.object(process.os, "stat", side_effect=stat):
            self.assertFalse(self.observe())
        self.assertGreaterEqual(seen, 2)
        with patch.object(process.os, "readlink", side_effect=FileNotFoundError("vanished")):
            self.assertFalse(self.observe())


class NativeStartupLifecycleTests(unittest.TestCase):
    def coordinator(self):
        child = Mock()
        child.pid = 321
        child.poll.return_value = None
        child.wait.return_value = 0
        controller = ReadinessController(password=b"fixture")
        coordinator = process.PostgresCoordinator(None, controller, spawn=Mock(return_value=child))
        coordinator.start_native()
        return coordinator, child

    def wait_listener(self, coordinator):
        waiter = getattr(coordinator, "wait_for_native_listener", None)
        self.assertTrue(callable(waiter), "native startup wait is missing")
        return waiter()

    def test_repeated_not_ready_observations_do_not_create_aggregate_deadline(self):
        coordinator, _ = self.coordinator()
        observer = Mock(side_effect=[False, False, True])
        with patch.object(process, "native_listener_observed", observer, create=True), \
                patch.object(coordinator._stop_requested, "wait", return_value=False), \
                patch.object(process.time, "monotonic", side_effect=[0, 10000, 20000, 30000]), \
                patch.object(process, "Thread", side_effect=AssertionError("startup worker")):
            self.assertTrue(self.wait_listener(coordinator))
        self.assertEqual(observer.call_count, 3)
        self.assertEqual(coordinator.readiness.state, ProductState.NOT_STARTED)
        self.assertIsNone(coordinator.host)

    def test_stop_during_observation_prevents_admission_and_reaps_without_worker(self):
        coordinator, child = self.coordinator()

        def observed(*args, **kwargs):
            coordinator.request_stop()
            return True

        with patch.object(process, "native_listener_observed", side_effect=observed, create=True), \
                patch.object(process, "Thread", side_effect=AssertionError("startup worker")), \
                patch.object(process.os, "killpg") as kill:
            self.assertFalse(self.wait_listener(coordinator))
            self.assertEqual(coordinator.wait(), 0)
        kill.assert_called_once_with(child.pid, signal.SIGINT)
        child.wait.assert_called_once()
        self.assertGreaterEqual(child.wait.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(child.wait.call_args.kwargs["timeout"], process.STOP_SECONDS)

    def test_native_exit_during_observation_wins_and_retains_diagnostics(self):
        coordinator, child = self.coordinator()

        def observed(*args, **kwargs):
            child.poll.return_value = 7
            return True

        with patch.object(process, "native_listener_observed", side_effect=observed, create=True), \
                patch.object(process, "Thread", side_effect=AssertionError("startup worker")):
            self.assertFalse(self.wait_listener(coordinator))
            self.assertEqual(coordinator.wait(), 1)
        self.assertEqual(coordinator.lifecycle_record.native_exit_code, 7)
        self.assertIsNone(coordinator.role_diagnostic["management_native_id"])
        self.assertFalse(coordinator.role_diagnostic["management_entered"])

    def test_pre_management_reap_timeout_escalates_boundedly_without_workers(self):
        coordinator, child = self.coordinator()
        child.wait.side_effect = [subprocess.TimeoutExpired("postgres", 8), 0]
        with patch.object(process, "Thread", side_effect=AssertionError("startup worker")), \
                patch.object(process.os, "killpg") as kill:
            self.assertEqual(coordinator.stop(), 1)
        self.assertEqual([value.args[1] for value in kill.call_args_list], [signal.SIGINT, signal.SIGKILL])
        self.assertEqual(child.wait.call_args.kwargs["timeout"], process.FINAL_REAP_SECONDS)

    def test_observation_failure_preserves_native_exit_precedence(self):
        coordinator, child = self.coordinator()

        def failed(*args, **kwargs):
            child.poll.return_value = 9
            raise process.PostgresProcessError("native metadata unavailable")

        with patch.object(process, "native_listener_observed", side_effect=failed, create=True):
            self.assertFalse(self.wait_listener(coordinator))
        self.assertEqual(coordinator.lifecycle_record.native_exit_code, 9)

    def test_main_constructs_management_only_after_native_listener(self):
        events = []
        child = Mock(pid=321)
        child.poll.return_value = None
        coordinator = process.PostgresCoordinator(None, ReadinessController(password=b"fixture"),
            spawn=Mock(return_value=child))
        coordinator.start_management = Mock(side_effect=lambda: events.append("serve"))
        coordinator.wait = Mock(return_value=0)
        host = Mock()
        with ExitStack() as stack:
            for name, replacement in (
                ("validate_pgdata", Mock()), ("read_password", Mock(return_value=b"fixture")),
                ("read_postgres_control_configuration", Mock(return_value=fixture().config)),
                ("create_management_server", Mock(side_effect=lambda *a, **k: (events.append("bind"), host)[1])),
                ("PostgresCoordinator", Mock(return_value=coordinator)),
                ("native_listener_observed", Mock(side_effect=lambda *a, **k: (events.append("listener"), True)[1])),
            ):
                stack.enter_context(patch.object(process, name, replacement, create=True))
            stack.enter_context(patch.object(process.os, "getuid", return_value=70))
            stack.enter_context(patch.object(process.os, "getgid", return_value=70))
            stack.enter_context(patch.object(process.signal, "signal"))
            self.assertEqual(process.main(), 0)
        self.assertEqual(events, ["listener", "bind", "serve"])
        self.assertIs(coordinator.host, host)

    def test_main_startup_stops_without_management_on_cancel_exit_or_observation_failure(self):
        for scenario in ("cancel", "exit", "observation-error", "bind-error"):
            with self.subTest(scenario=scenario):
                child = Mock(pid=321)
                child.poll.return_value = None
                child.wait.return_value = 0
                spawn = Mock(return_value=child)
                coordinator = process.PostgresCoordinator(None, ReadinessController(password=b"fixture"), spawn=spawn)
                coordinator.start_management = Mock()
                original_wait = coordinator.wait

                def wait():
                    # Keeps the pre-correction main finite without faking its cleanup.
                    coordinator.request_stop()
                    return original_wait()

                coordinator.wait = wait

                def observe(*args, **kwargs):
                    if scenario == "cancel":
                        coordinator.request_stop()
                        return False
                    if scenario == "exit":
                        child.poll.return_value = 7
                        return False
                    if scenario == "observation-error":
                        raise process.PostgresProcessError("PRIVATE_OBSERVATION_ERROR")
                    return True

                bind = Mock(side_effect=OSError("PRIVATE_BIND_ERROR"))
                stderr = io.StringIO()
                with ExitStack() as stack:
                    for name, replacement in (
                        ("validate_pgdata", Mock()), ("read_password", Mock(return_value=b"fixture")),
                        ("read_postgres_control_configuration", Mock(return_value=fixture().config)),
                        ("create_management_server", bind),
                        ("PostgresCoordinator", Mock(return_value=coordinator)),
                        ("native_listener_observed", Mock(side_effect=observe)),
                    ):
                        stack.enter_context(patch.object(process, name, replacement, create=True))
                    stack.enter_context(patch.object(process.os, "getuid", return_value=70))
                    stack.enter_context(patch.object(process.os, "getgid", return_value=70))
                    stack.enter_context(patch.object(process.signal, "signal"))
                    stack.enter_context(patch.object(process, "Thread", side_effect=AssertionError("startup worker")))
                    kill = stack.enter_context(patch.object(process.os, "killpg"))
                    stack.enter_context(patch.object(process.sys, "stderr", stderr))
                    self.assertEqual(process.main(), 0 if scenario == "cancel" else 1)
                spawn.assert_called_once()
                coordinator.start_management.assert_not_called()
                if scenario == "bind-error":
                    bind.assert_called_once()
                else:
                    bind.assert_not_called()
                if scenario == "exit":
                    kill.assert_not_called()
                    self.assertEqual(coordinator.lifecycle_record.native_exit_code, 7)
                else:
                    kill.assert_called_once_with(child.pid, signal.SIGINT)
                    child.wait.assert_called_once()
                self.assertNotIn("PRIVATE_", stderr.getvalue())
                if scenario in ("observation-error", "bind-error"):
                    self.assertIn('"reason":"startup_failure"', stderr.getvalue())
