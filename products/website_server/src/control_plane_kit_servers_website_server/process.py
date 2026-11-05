"""PID1 supervisor for exactly one native website generation and its SDK host."""
import os
import signal
import subprocess
from threading import Event, Lock, Thread

import control_plane_kit_core as core
from control_plane_kit_server_sdk import wrapper

from .index_probe import load_expectation, read_index
from .managed import control_configuration_artifact, create_control_server

# Managed Node drains within 7 seconds; total cleanup stays below Docker's 10s.
NODE_STOP_SECONDS = 8


def node_environment(environment):
    upstream = environment.get("CPK_WEB_UPSTREAM")
    if type(upstream) is not str or not upstream or len(upstream) > 2048 or environment.get("PORT", "8080") != "8080":
        raise ValueError("Website runtime configuration is invalid")
    return {"NODE_ENV": "production", "PORT": "8080", "CPK_WEB_UPSTREAM": upstream}


class WebsiteHealth:
    """Owned child generation only; a stopped/exited generation stays invalid."""

    def __init__(self, child=None, *, expectation=None):
        self._child = child
        self._lock = Lock()
        self._stopped = False
        self._listening = False
        self._expectation = expectation
        self._probe = Lock()

    def attach(self, child):
        with self._lock:
            if self._child is not None or self._stopped or child is None:
                raise ValueError("Website generation is already bound")
            self._child = child

    def listening(self, child):
        with self._lock:
            if child is not self._child or self._stopped or child.poll() is not None:
                return
            self._listening = True

    def stop(self):
        with self._lock:
            self._stopped = True
            self._listening = False

    def liveness(self):
        with self._lock:
            if self._child is None:
                return core.NodeHealthReadOutcome.UNHEALTHY if self._stopped else core.NodeHealthReadOutcome.UNKNOWN
            if self._child.poll() is not None:
                self._stopped = True
            return core.NodeHealthReadOutcome.UNHEALTHY if self._stopped else core.NodeHealthReadOutcome.HEALTHY

    def readiness(self):
        before = self.liveness()
        if before is not core.NodeHealthReadOutcome.HEALTHY:
            return before
        with self._lock:
            expected = self._expectation if self._listening and not self._stopped else None
        if expected is None or not self._probe.acquire(blocking=False):
            current = self.liveness()
            return core.NodeHealthReadOutcome.UNKNOWN if current is core.NodeHealthReadOutcome.HEALTHY else current
        try:
            result = read_index(expected)
            after = self.liveness()
            return result if after is core.NodeHealthReadOutcome.HEALTHY else after
        finally:
            self._probe.release()


def run(configuration, environment, *, expectation=None):
    control_configuration_artifact(configuration)
    child_env = node_environment(environment)
    stop = Event()
    host_failed = Event()
    previous = {}
    signals = {}
    child = host = health = serving = None

    def request_stop(_signum, _frame):
        signals.setdefault("requested", _signum)

    def serve():
        try:
            host.serve_forever(poll_interval=0.05)
        except BaseException:
            host_failed.set()
        finally:
            if not stop.is_set():
                host_failed.set()
            stop.set()

    result = 1
    reason = "startup_failed"
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
        health = WebsiteHealth(expectation=expectation)
        host = create_control_server(configuration, health)
        if not signals:
            child = subprocess.Popen(
                ["/usr/local/bin/node", "/app/website-managed/main.mjs"], env=child_env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True)
            health.attach(child)
            os.set_blocking(child.stdout.fileno(), False)
            startup = b""
            notification = b"CPK_WEBSITE_LISTENING_V1\n"
            serving = Thread(target=serve, name="website-control", daemon=True)
            serving.start()
            reason = "running"
            while not stop.wait(0.05):
                if signals:
                    break
                try:
                    chunk = os.read(child.stdout.fileno(), 64)
                except BlockingIOError:
                    chunk = b""
                startup += chunk
                if not notification.startswith(startup):
                    reason = "startup_failed"
                    break
                if startup == notification:
                    health.listening(child)
                if child.poll() is not None:
                    reason = "website_exited"
                    break
            if host_failed.is_set():
                reason = "management_exited"
            elif child.poll() is not None:
                reason = "website_exited"
            elif reason != "startup_failed" or signals:
                reason = "stopped"
                result = 0
    except Exception:
        result = 1
    finally:
        stop.set()
        if health is not None:
            health.stop()
        if child is not None:
            try:
                # The wrapper owns this process group, even if Node exited first.
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                child.poll()
            except OSError:
                result = 1
            try:
                child_code = child.wait(timeout=NODE_STOP_SECONDS)
                if child_code != 0:
                    result = 1
                    if reason == "stopped":
                        reason = "website_drain_failed"
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    child.poll()
                except OSError:
                    result = 1
                try:
                    child.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    result = 1
                result = 1
        if child is not None and child.stdout is not None:
            child.stdout.close()
        if host is not None:
            if serving is not None:
                shutdown = Thread(target=host.shutdown, daemon=True)
                shutdown.start()
                shutdown.join(timeout=0.25)
                serving.join(timeout=0.25)
                if shutdown.is_alive() or serving.is_alive():
                    result = 1
            host.server_close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    print("website lifecycle " + reason, flush=True)
    return result


def main():
    try:
        configuration = wrapper.load_wrapper_configuration()
        return run(configuration, os.environ, expectation=load_expectation())
    except Exception:
        print("website lifecycle configuration_failed", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
