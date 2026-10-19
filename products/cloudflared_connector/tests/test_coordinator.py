"""#188 new-law coordinator targets; real process/image proof is separately staged."""
import fcntl
import os
import signal
import stat
import subprocess
from types import SimpleNamespace
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_servers_cloudflared_connector import coordinator
from coordinator_fixtures import Harness


class StartupTests(unittest.TestCase):
    def test_invalid_configuration_and_path_refuse_before_effects(self):
        for path in ('', 'relative', '/run/a\x00b', None, 123):
            with self.subTest(path=repr(path)), Harness() as h:
                self.assertEqual(h.run(token_path=path), 1)
                self.assertEqual((h.spawned, h.bound), (0, 0))
        with Harness() as h:
            self.assertEqual(h.run(configuration=object()), 1)
            self.assertEqual((h.spawned, h.bound), (0, 0))

    def test_stop_before_spawn_is_clean_cancellation_without_child(self):
        with Harness() as h:
            h.on_install = lambda sig, handler: handler(sig, None) if sig == signal.SIGTERM else None
            self.assertEqual(h.run(), 0)
            self.assertEqual((h.spawned, h.bound, h.signals), (0, 0, []))

    def test_stop_during_spawn_does_not_bind_and_reaps_created_child(self):
        with Harness() as h:
            h.after_spawn = h.stop
            self.assertEqual(h.run(), 0)
            self.assertEqual((h.spawned, h.bound), (1, 0))
            self.assertTrue(h.child.reaped)
            self.assertEqual([sig for _, sig in h.signals], [signal.SIGTERM])

    def test_stop_during_bind_closes_host_without_starting_serve(self):
        with Harness() as h:
            h.after_bind = h.stop
            self.assertEqual(h.run(), 0)
            self.assertTrue(h.host.closed)
            self.assertFalse(h.host.started.is_set())
            self.assertTrue(h.child.reaped)

    def test_spawn_or_bind_failure_is_sticky_even_if_cleanup_child_zero(self):
        for stage in ('spawn_error', 'bind_error'):
            with self.subTest(stage=stage), Harness() as h:
                setattr(h, stage, OSError('PRIVATE_STARTUP_SENTINEL'))
                self.assertEqual(h.run(), 1)
                if stage == 'bind_error':
                    self.assertTrue(h.child.reaped)
                    self.assertEqual(h.child.code, 0)

    def test_serving_thread_start_failure_closes_bound_host_and_reaps_child(self):
        real_start = Thread.start
        calls = []
        def start(thread):
            calls.append(thread)
            if len(calls) == 1:
                raise RuntimeError('PRIVATE_THREAD_START')
            return real_start(thread)
        with Harness() as h, patch.object(Thread, 'start', new=start):
            h.host.allow_shutdown.clear()
            self.assertEqual(h.run(), 1)
            self.assertEqual((h.spawned, h.bound), (1, 1))
            self.assertTrue(h.host.closed)
            self.assertFalse(h.host.started.is_set())
            self.assertTrue(h.child.reaped)
            self.assertLess(h.now, 1)
            self.assertEqual(h.handlers, h.original_handlers)


class FailureTests(unittest.TestCase):
    def test_signal_between_native_poll_and_classification_cannot_erase_exit(self):
        with Harness() as h:
            original_poll = h.child.poll
            injected = []
            def poll():
                observed = original_poll()
                if observed == 0 and not injected:
                    injected.append(True)
                    h.stop()
                return observed
            h.child.poll = poll
            h.at(0.1, lambda: h.native_exit(0))
            self.assertEqual(h.run(), 1)
            self.assertEqual(injected, [True])

    def test_unexpected_native_exit_maps_zero_nonzero_and_signal(self):
        for code, expected in ((0, 1), (7, 7), (-signal.SIGTERM, 143)):
            with self.subTest(code=code), Harness() as h:
                h.at(0.1, lambda: h.native_exit(code))
                self.assertEqual(h.run(), expected)
                self.assertTrue(h.child.reaped)
                self.assertTrue(h.host.closed)
                self.assertEqual(h.spawned, 1)

    def test_host_return_or_exception_is_failure_despite_native_zero(self):
        for error in (None, RuntimeError('PRIVATE_THREAD_SENTINEL')):
            with self.subTest(error=error), Harness() as h, patch('threading.excepthook') as uncaught:
                h.host.failure = error
                h.at(0.1, h.host.finish.set)
                self.assertEqual(h.run(), 1)
                self.assertEqual(h.child.code, 0)
                self.assertTrue(h.host.closed)
                uncaught.assert_not_called()

    def test_requested_stop_preserves_native_nonzero(self):
        with Harness() as h:
            h.native_stop_code = 9
            h.at(0.1, h.stop)
            self.assertEqual(h.run(), 9)
            self.assertTrue(h.host.closed)

    def test_host_failure_and_forced_cleanup_select_forced_result(self):
        with Harness() as h:
            h.ignore_term = True
            h.at(0.1, h.host.finish.set)
            self.assertEqual(h.run(), 124)
            self.assertIn(signal.SIGKILL, [sig for _, sig in h.signals])

    def test_available_host_failure_wins_over_simultaneous_native_exit(self):
        with Harness() as h:
            def fail_both():
                h.host.finish_and_join()
                h.native_exit(7)
            h.at(0.1, fail_both)
            self.assertEqual(h.run(), 1)
            self.assertTrue(h.host.closed)
            self.assertTrue(h.child.reaped)

    def test_later_requested_stop_does_not_erase_observed_unexpected_native_zero(self):
        with Harness() as h:
            h.host.before_shutdown = h.stop
            h.at(0.1, lambda: h.native_exit(0))
            self.assertEqual(h.run(), 1)
            self.assertIsNotNone(h.first_stop_at)
            self.assertTrue(h.host.closed)


class SignalDeadlineTests(unittest.TestCase):
    def test_first_published_stop_survives_interrupted_internal_or_requested_stop(self):
        for origin in ('internal', 'requested'):
            with self.subTest(origin=origin), Harness() as h:
                h.ignore_term = True
                def interrupt():
                    h.stop(signal.SIGINT)
                    h.now += 0.25
                def trigger():
                    h.on_clock = interrupt
                    if origin == 'internal':
                        h.native_exit(0, group_alive=True)
                    else:
                        h.stop(signal.SIGTERM)
                h.at(0.1, trigger)
                self.assertEqual(h.run(), 124)
                self.assertEqual([sig for _, sig in h.signals], [signal.SIGINT, signal.SIGKILL])
                self.assertAlmostEqual(h.signals[1][0] - h.first_stop_at, 7, delta=0.15)

    def test_delayed_serving_entry_is_cancelled_before_closed_host_is_entered(self):
        entry = Event()
        threads = []
        def make_thread(*, target, **kwargs):
            if not threads:
                actual_target = target
                def delayed():
                    entry.wait()
                    actual_target()
                target = delayed
            thread = Thread(target=target, **kwargs)
            threads.append(thread)
            return thread
        try:
            with Harness() as h, patch.object(coordinator, 'Thread', side_effect=make_thread):
                h.at(0.1, h.stop)
                h.at(0.2, entry.set)
                self.assertEqual(h.run(), 0)
                self.assertTrue(h.host.closed)
                self.assertFalse(h.host.started.is_set())
                self.assertTrue(h.child.reaped)
                self.assertLess(h.now, 1)
        finally:
            entry.set()
            for thread in threads:
                thread.join(1)
                self.assertFalse(thread.is_alive(), 'delayed owner thread leaked')

    def test_term_and_int_forward_once_and_expected_host_return_is_clean(self):
        for selected in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(selected=selected), Harness() as h:
                h.at(0.1, lambda: h.stop(selected))
                self.assertEqual(h.run(), 0)
                self.assertEqual([sig for _, sig in h.signals], [selected])
                self.assertTrue(h.host.closed)
                self.assertTrue(h.child.reaped)
                self.assertEqual(h.handlers, h.original_handlers)

    def test_repeated_signals_share_first_clock_and_one_escalation(self):
        with Harness() as h:
            h.ignore_term = True
            h.ignore_kill = True
            h.at(0.1, h.stop)
            h.at(2, lambda: h.stop(signal.SIGINT))
            h.at(6, h.stop)
            self.assertEqual(h.run(), 124)
            self.assertEqual([sig for _, sig in h.signals], [signal.SIGTERM, signal.SIGKILL])
            self.assertAlmostEqual(h.signals[1][0] - h.first_stop_at, 7, delta=0.15)
            self.assertLessEqual(h.now - h.first_stop_at, 8.15)
            self.assertFalse(h.child.reaped)

    def test_stalled_shutdown_helper_does_not_extend_native_deadline(self):
        with Harness() as h:
            h.host.allow_shutdown.clear()
            h.ignore_term = True
            h.at(0.1, h.stop)
            self.assertEqual(h.run(), 124)
            self.assertTrue(h.host.closed)
            self.assertTrue(h.child.reaped)
            self.assertLessEqual(h.now - h.first_stop_at, 8.15)
            self.assertAlmostEqual(h.signals[1][0] - h.first_stop_at, 7, delta=0.15)

    def test_health_and_listener_stop_while_native_and_host_cleanup_are_pending(self):
        with Harness() as h:
            observed = []
            h.ignore_term = True
            h.host.allow_shutdown.clear()
            h.at(0.1, h.stop)
            h.at(1.0, lambda: observed.append((h.host.closed, h.health.liveness(), h.child.code)))
            self.assertEqual(h.run(), 124)
            self.assertEqual(observed, [(True, core.NodeHealthReadOutcome.UNHEALTHY, None)])
            self.assertLessEqual(h.now - h.first_stop_at, 8.15)

    def test_leader_exit_does_not_establish_group_absence(self):
        with Harness() as h:
            h.ignore_term = True
            h.at(0.1, lambda: h.native_exit(0, group_alive=True))
            self.assertEqual(h.run(), 124)
            self.assertEqual([sig for _, sig in h.signals], [signal.SIGTERM, signal.SIGKILL])
            self.assertEqual(h.child.code, 0)

    def test_group_observation_uncertainty_is_incomplete_not_absence(self):
        with Harness() as h:
            h.group_unknown = True
            h.at(0.1, h.stop)
            self.assertEqual(h.run(), 124)
            self.assertLessEqual(h.now - h.first_stop_at, 8.15)


class CustodyTests(unittest.TestCase):
    def test_actual_spawn_boundary_has_fixed_command_environment_group_and_streams(self):
        with patch.dict(os.environ, {'TUNNEL_TOKEN': 'PRIVATE_TOKEN', 'TUNNEL_GRACE_PERIOD': '90s',
                                     'HTTP_PROXY': 'PRIVATE_PROXY', 'PYTHONPATH': 'PRIVATE_PATH'}), \
                patch.object(coordinator.subprocess, 'Popen') as spawn:
            result = coordinator._spawn_native('/run/secrets/tunnel')
        self.assertIs(result, spawn.return_value)
        args, kwargs = spawn.call_args
        self.assertEqual(args[0], ['/usr/local/bin/cloudflared', '--no-autoupdate', '--metrics',
                                  '127.0.0.1:20241', 'tunnel', '--grace-period', '5s', 'run'])
        self.assertEqual(kwargs['env'], {'TUNNEL_TOKEN_FILE': '/run/secrets/tunnel'})
        self.assertTrue(kwargs['start_new_session'])
        self.assertFalse(kwargs.get('shell', False))
        for name in ('stdin', 'stdout', 'stderr'):
            self.assertEqual(kwargs[name], subprocess.DEVNULL)

    def test_sink_validates_owned_duplicate_and_never_mutates_shared_flags(self):
        with patch.object(coordinator.os, 'dup', return_value=71) as duplicate, \
                patch.object(coordinator.os, 'fstat', return_value=SimpleNamespace(st_mode=stat.S_IFIFO)) as inspect, \
                patch.object(coordinator.fcntl, 'fcntl', return_value=os.O_NONBLOCK) as flags, \
                patch.object(coordinator.os, 'set_inheritable') as inherit:
            self.assertEqual(coordinator._open_diagnostic_sink(), 71)
            duplicate.assert_called_once_with(2)
            inspect.assert_called_once_with(71)
            flags.assert_called_once_with(71, fcntl.F_GETFL)
            inherit.assert_called_once_with(71, False)

    def test_sink_refuses_blocking_and_nonpipe_descriptors_and_closes_only_duplicate(self):
        for mode, flags in ((stat.S_IFIFO, 0), (stat.S_IFREG, os.O_NONBLOCK),
                            (stat.S_IFSOCK, os.O_NONBLOCK)):
            with self.subTest(mode=mode, flags=flags), \
                    patch.object(coordinator.os, 'dup', return_value=71), \
                    patch.object(coordinator.os, 'fstat', return_value=SimpleNamespace(st_mode=mode)), \
                    patch.object(coordinator.fcntl, 'fcntl', return_value=flags), \
                    patch.object(coordinator.os, 'set_inheritable'), \
                    patch.object(coordinator.os, 'close') as close:
                self.assertIsNone(coordinator._open_diagnostic_sink())
                close.assert_called_once_with(71)

    def test_sink_setup_failure_disables_without_exposing_error(self):
        for stage in ('dup', 'fstat', 'set_inheritable', 'flags'):
            with self.subTest(stage=stage), \
                    patch.object(coordinator.os, 'dup', return_value=71) as duplicate, \
                    patch.object(coordinator.os, 'fstat', return_value=SimpleNamespace(st_mode=stat.S_IFIFO)) as inspect, \
                    patch.object(coordinator.fcntl, 'fcntl', return_value=os.O_NONBLOCK) as flags, \
                    patch.object(coordinator.os, 'set_inheritable') as inherit, \
                    patch.object(coordinator.os, 'close') as close:
                {'dup': duplicate, 'fstat': inspect, 'set_inheritable': inherit, 'flags': flags}[stage].side_effect = OSError('PRIVATE_SINK')
                self.assertIsNone(coordinator._open_diagnostic_sink())
                if stage == 'dup':
                    close.assert_not_called()
                else:
                    close.assert_called_once_with(71)

    def test_closed_records_one_write_and_full_broken_partial_sinks_are_dropped(self):
        for result in (BlockingIOError(), BrokenPipeError(), OSError('PRIVATE_SINK'), 1, 256):
            with self.subTest(result=repr(result)), patch.object(coordinator.os, 'write') as write:
                if isinstance(result, Exception):
                    write.side_effect = result
                else:
                    write.return_value = result
                coordinator._emit_diagnostic(71, 'native_exit', 7)
                write.assert_called_once()
                descriptor, record = write.call_args.args
                self.assertEqual(descriptor, 71)
                self.assertLessEqual(len(record), 256)
                self.assertTrue(record.isascii())
                self.assertIn(b'native_exit', record)
                self.assertNotIn(b'PRIVATE', record)
        with patch.object(coordinator.os, 'write') as write:
            coordinator._emit_diagnostic(None, 'native_exit', 7)
            coordinator._emit_diagnostic(71, 'PRIVATE_UNLISTED_REASON', 7)
            write.assert_not_called()

    def test_sink_close_error_does_not_escape_and_disabled_sink_is_inert(self):
        with patch.object(coordinator.os, 'close', side_effect=OSError('PRIVATE_CLOSE')) as close:
            coordinator._close_diagnostic_sink(71)
            close.assert_called_once_with(71)
        with patch.object(coordinator.os, 'close') as close:
            coordinator._close_diagnostic_sink(None)
            close.assert_not_called()
