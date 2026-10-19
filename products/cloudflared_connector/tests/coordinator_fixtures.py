"""Controlled owner effects; no substitute lifecycle algorithm."""
from contextlib import ExitStack
import os
import signal
import subprocess
from threading import Event, current_thread
import time
from unittest.mock import patch

from control_plane_kit_servers_cloudflared_connector import coordinator
from managed_control_fixtures import fixture

_real_sleep = time.sleep


class Child:
    pid = 43210

    def __init__(self):
        self.code = None
        self.reaped = False

    def poll(self):
        if self.code is not None:
            self.reaped = True
        return self.code

    def wait(self, timeout=None):
        if self.code is None:
            raise subprocess.TimeoutExpired('controlled-child', timeout)
        self.reaped = True
        return self.code


class Host:
    def __init__(self):
        self.started = Event()
        self.finish = Event()
        self.allow_shutdown = Event()
        self.allow_shutdown.set()
        self.closed = False
        self.failure = None
        self.threads = []
        self.serve_thread = None
        self.before_shutdown = None

    @property
    def cpk_is_serving(self):
        return self.started.is_set() and not self.finish.is_set()

    def serve_forever(self, poll_interval=0.05):
        if self.closed:
            raise RuntimeError('controlled serving entered a closed host')
        self.serve_thread = current_thread()
        self.threads.append(current_thread())
        self.started.set()
        self.finish.wait()
        if self.failure is not None:
            raise self.failure

    def shutdown(self):
        self.threads.append(current_thread())
        if self.before_shutdown is not None:
            self.before_shutdown()
        self.allow_shutdown.wait()
        self.finish.set()

    def finish_and_join(self):
        if not self.started.wait(1):
            raise AssertionError('controlled host never started')
        self.finish.set()
        self.serve_thread.join(1)
        if self.serve_thread.is_alive():
            raise AssertionError('controlled host completion was not observed')

    def server_close(self):
        self.closed = True


class Harness:
    def __init__(self):
        self.config = fixture().config
        self.child = Child()
        self.host = Host()
        self.now = 0.0
        self.actions = []
        self.original_handlers = {signal.SIGTERM: lambda sig, frame: None, signal.SIGINT: signal.SIG_IGN}
        self.handlers = dict(self.original_handlers)
        self.group_alive = False
        self.group_unknown = False
        self.ignore_term = False
        self.ignore_kill = False
        self.native_stop_code = 0
        self.signals = []
        self.spawned = 0
        self.bound = 0
        self.spawn_error = None
        self.bind_error = None
        self.after_spawn = None
        self.after_bind = None
        self.on_install = None
        self.health = None
        self.first_stop_at = None
        self.on_clock = None
        self.stack = ExitStack()

    def at(self, when, action):
        self.actions.append((when, action))
        self.actions.sort(key=lambda item: item[0])

    def stop(self, signum=signal.SIGTERM):
        if self.first_stop_at is None:
            self.first_stop_at = self.now
        self.handlers[signum](signum, None)

    def native_exit(self, code, *, group_alive=False):
        self.child.code = code
        self.group_alive = group_alive

    def sleep(self, duration):
        if duration < 0 or duration > 0.5:
            raise AssertionError('coordinator wait must be short and bounded')
        self.now += max(duration, 0.01)
        if self.now > 12:
            raise AssertionError('coordinator exceeded controlled deadline')
        while self.actions and self.actions[0][0] <= self.now:
            _, action = self.actions.pop(0)
            action()
        _real_sleep(0.001)

    def clock(self):
        if self.on_clock is not None:
            callback, self.on_clock = self.on_clock, None
            callback()
        return self.now

    def install(self, signum, handler):
        old = self.handlers.get(signum, signal.SIG_DFL)
        self.handlers[signum] = handler
        if (self.on_install is not None and callable(handler)
                and handler not in self.original_handlers.values()):
            self.on_install(signum, handler)
        return old

    def spawn(self, path):
        self.spawned += 1
        if self.spawn_error:
            raise self.spawn_error
        self.group_alive = True
        if self.after_spawn:
            self.after_spawn()
        return self.child

    def bind(self, configuration, health, **kwargs):
        self.bound += 1
        self.health = health
        if self.bind_error:
            raise self.bind_error
        if self.after_bind:
            self.after_bind()
        return self.host

    def killpg(self, pid, signum):
        if pid != self.child.pid:
            raise AssertionError('foreign process group')
        if signum == 0:
            if self.group_unknown:
                raise PermissionError('controlled unknown group')
            if not self.group_alive:
                raise ProcessLookupError
            return
        self.signals.append((self.now, signum))
        if not self.group_alive:
            raise ProcessLookupError
        if signum == signal.SIGKILL:
            if not self.ignore_kill:
                self.group_alive = False
                if self.child.code is None:
                    self.child.code = -signal.SIGKILL
        elif not self.ignore_term:
            self.group_alive = False
            if self.child.code is None:
                self.child.code = self.native_stop_code

    def __enter__(self):
        self.stack.enter_context(patch.object(coordinator.time, 'monotonic', side_effect=self.clock))
        self.stack.enter_context(patch.object(coordinator.time, 'sleep', side_effect=self.sleep))
        self.stack.enter_context(patch.object(coordinator.signal, 'signal', side_effect=self.install))
        self.stack.enter_context(patch.object(coordinator.signal, 'getsignal', side_effect=lambda sig: self.handlers.get(sig, signal.SIG_DFL)))
        self.stack.enter_context(patch.object(coordinator, '_spawn_native', side_effect=self.spawn))
        self.stack.enter_context(patch.object(coordinator.managed, 'create_control_server', side_effect=self.bind))
        self.stack.enter_context(patch.object(coordinator.os, 'killpg', side_effect=self.killpg))
        self.stack.enter_context(patch.object(coordinator, '_open_diagnostic_sink', return_value=None))
        self.stack.enter_context(patch.object(coordinator, '_emit_diagnostic', return_value=None))
        self.stack.enter_context(patch.object(coordinator, '_close_diagnostic_sink', return_value=None))
        return self

    def __exit__(self, *error):
        self.host.allow_shutdown.set()
        self.host.finish.set()
        try:
            for thread in set(self.host.threads):
                if thread is not current_thread():
                    thread.join(1)
                    if thread.is_alive():
                        raise AssertionError('controlled host thread leaked')
        finally:
            self.stack.close()

    def run(self, *, configuration=None, token_path='/run/secrets/tunnel'):
        return coordinator.run(self.config if configuration is None else configuration, token_path=token_path)
