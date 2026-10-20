"""Product-local process ownership; image/PID1 qualification is a separate stage."""
import fcntl
import os
import signal
import stat
import subprocess
import time
from threading import Event, Lock, Thread, current_thread, main_thread

from . import managed
from .readiness import read_connection


def run(configuration, *, token_path):
    """Own this process's native group, SDK host and signal handlers until stopped."""
    if current_thread() is not main_thread():
        return 1
    try:
        managed.control_configuration_artifact(configuration)
        if type(token_path) is not str or not token_path.startswith('/') or '\x00' in token_path:
            return 1
    except Exception:
        return 1
    return _Coordinator(configuration, token_path).run()


def _spawn_native(token_path):
    return subprocess.Popen(
        ['/usr/local/bin/cloudflared', '--no-autoupdate', '--metrics',
         '127.0.0.1:20241', 'tunnel', '--grace-period', '5s', 'run'],
        env={'TUNNEL_TOKEN_FILE': token_path}, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_diagnostic_sink():
    descriptor = None
    try:
        descriptor = os.dup(2)
        os.set_inheritable(descriptor, False)
        if (stat.S_ISFIFO(os.fstat(descriptor).st_mode)
                and fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_NONBLOCK):
            return descriptor
    except Exception:
        _close_diagnostic_sink(descriptor)
        return None
    _close_diagnostic_sink(descriptor)
    return None


def _emit_diagnostic(descriptor, reason, code=None):
    if descriptor is None or reason not in (
            'startup_failure', 'management_exit', 'native_exit', 'stopping', 'forced_cleanup'):
        return
    if code is not None and (type(code) is not int or not -255 <= code <= 255):
        return
    record = f'cloudflared lifecycle {reason} code={code}\n'.encode('ascii')
    try:
        os.write(descriptor, record)
    except Exception:
        return


def _close_diagnostic_sink(descriptor):
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except Exception:
        return


class _Coordinator:
    """One invocation's owned resources; no restart or cross-product policy."""

    def __init__(self, configuration, token_path):
        self.configuration = configuration
        self.token_path = token_path
        self.child = None
        self.host = None
        self.health = managed.ConnectorHealth(native_alive=self._native_alive, read_connection=read_connection)
        self._stop = {}
        self.startup_failed = False
        self.host_failed = Event()
        self.serve_done = Event()
        self.shutdown_done = Event()
        self.serve_started = False
        self.serve_gate = Lock()
        self.serve_entered = False
        self.serve_cancelled = False
        self.unexpected_native = None
        self.cleanup_incomplete = False
        self.escalated = False
        self.sink = None

    def _native_alive(self):
        return self.child is not None and self.child.poll() is None

    @property
    def stop_intent(self):
        return self._stop.get('first')

    def _request_stop(self, signum, frame):
        # Signal handler records intent only; no locks, logging, cleanup or waits.
        if self.stop_intent is None:
            # CPython's atomic setdefault publishes the whole fact once, even if
            # another signal interrupts candidate timestamp construction.
            self._stop.setdefault('first', (time.monotonic(), signum, True))

    def _begin_stop(self):
        if self.stop_intent is None:
            self._stop.setdefault('first', (time.monotonic(), signal.SIGTERM, False))

    def _serve(self):
        try:
            with self.serve_gate:
                if self.serve_cancelled or self.stop_intent is not None:
                    self.serve_cancelled = True
                    return
                self.serve_entered = True
            self.host.serve_forever(poll_interval=0.05)
        except BaseException:
            self.host_failed.set()
        finally:
            if self.stop_intent is None:
                self.host_failed.set()
            self.serve_done.set()

    def _shutdown(self):
        try:
            self.host.shutdown()
        except BaseException:
            self.host_failed.set()
        finally:
            self.shutdown_done.set()

    def _start(self):
        if self.stop_intent is not None:
            return
        self.child = _spawn_native(self.token_path)
        if self.stop_intent is not None:
            return
        self.host = managed.create_control_server(self.configuration, self.health)
        if self.stop_intent is not None:
            return
        serving = Thread(target=self._serve, name='cloudflared-control', daemon=True)
        serving.start()
        self.serve_started = True

    def _watch(self):
        while True:
            # Collect available failure facts before selecting a terminal cause.
            host_failure = self.host_failed.is_set()
            stop_before_observation = self.stop_intent
            code = self.child.poll() if self.child is not None else None
            if host_failure:
                self._begin_stop()
                return
            # An exit observed by a poll begun before stop is not made successful
            # by a handler running between poll return and classification.
            if code is not None and stop_before_observation is None:
                self.unexpected_native = code
                self._begin_stop()
                return
            if self.stop_intent is not None:
                return
            time.sleep(0.05)

    def _group_absent(self):
        if self.child is None:
            return True
        try:
            os.killpg(self.child.pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False

    def _signal_group(self, signum):
        if self.child is None:
            return
        try:
            os.killpg(self.child.pid, signum)
        except ProcessLookupError:
            return
        except OSError:
            self.cleanup_incomplete = True

    def _child_completion(self):
        if self.child is None:
            return True, None
        try:
            code = self.child.poll()  # Popen.poll reaps the leader; no blocking wait.
            return code is not None, code
        except Exception:
            return False, None

    def _cleanup(self):
        self._begin_stop()
        started, signum, requested = self.stop_intent
        kill_at, finish_at = started + 7.0, started + 8.0
        self.health.stop()
        with self.serve_gate:
            if not self.serve_entered:
                self.serve_cancelled = True
        host_closed = self.host is None
        if host_closed:
            self.shutdown_done.set()
        self._signal_group(signum)
        while True:
            now = time.monotonic()
            if not host_closed:
                # Do not close between Thread.start and SDK selector registration.
                # A cancelled entry never calls serve_forever. An admitted entry
                # must report actual SDK serving (or completion) before closure.
                ready = (not self.serve_started or self.serve_cancelled
                         or self.serve_done.is_set() or self.host.cpk_is_serving)
                if ready or now >= finish_at:
                    if not ready:
                        self.cleanup_incomplete = True
                    if self.serve_started and not self.serve_cancelled and not self.serve_done.is_set():
                        try:
                            Thread(target=self._shutdown, name='cloudflared-shutdown', daemon=True).start()
                        except Exception:
                            self.cleanup_incomplete = True
                    else:
                        self.shutdown_done.set()
                    try:
                        self.host.server_close()
                    except Exception:
                        self.cleanup_incomplete = True
                    host_closed = True
            reaped, code = self._child_completion()
            absent = self._group_absent()
            host_done = (host_closed and (not self.serve_started or self.serve_done.is_set())
                         and self.shutdown_done.is_set())
            if reaped and absent and host_done:
                if now > finish_at:
                    self.cleanup_incomplete = True
                break
            if now >= kill_at and not self.escalated and not (reaped and absent):
                self.escalated = True
                self._signal_group(signal.SIGKILL)
            if now >= finish_at:
                self.cleanup_incomplete = True
                break
            next_deadline = kill_at if now < kill_at else finish_at
            time.sleep(min(0.05, max(0.0, next_deadline - now)))
        if self.escalated or self.cleanup_incomplete:
            return 124, 'forced_cleanup'
        if self.startup_failed:
            return 1, 'startup_failure'
        if self.host_failed.is_set():
            return 1, 'management_exit'
        if self.unexpected_native is not None:
            return _exit_code(self.unexpected_native, unexpected=True), 'native_exit'
        if self.child is None:
            return (0 if requested else 1), 'stopping'
        return _exit_code(code, unexpected=False), 'stopping'

    def run(self):
        previous = {}
        self.sink = _open_diagnostic_sink()
        try:
            try:
                for signum in (signal.SIGTERM, signal.SIGINT):
                    previous[signum] = signal.getsignal(signum)
                    signal.signal(signum, self._request_stop)
                self._start()
                self._watch()
            except Exception:
                self.startup_failed = True
                self._begin_stop()
            result, reason = self._cleanup()
            _emit_diagnostic(self.sink, reason, result)
            return result
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            _close_diagnostic_sink(self.sink)


def _exit_code(code, *, unexpected):
    if code is None:
        return 124
    if code < 0:
        return 128 - code
    return 1 if unexpected and code == 0 else code
