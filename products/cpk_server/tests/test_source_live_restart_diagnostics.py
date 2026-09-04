from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_source_live_module():
    spec = importlib.util.spec_from_file_location(
        "cpk_server_secret_provider_source_live_restart",
        SCRIPTS / "cpk_server_secret_provider_source_live.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("source-live controller module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Image:
    id = "sha256:" + "a" * 64


class _Container:
    def __init__(self, states_after_start: tuple[dict[str, object], ...]) -> None:
        self.id = "b" * 64
        self.name = "cpk-workspace-gateway"
        self.image = _Image()
        self._started = False
        self._states_after_start = list(states_after_start)
        self.attrs = {
            "State": _state(running=True, started_at="old"),
            "NetworkSettings": {
                "Networks": {
                    "cpk-workspace-runtime": {
                        "IPAddress": "172.30.0.4",
                    }
                }
            },
            "Config": {
                "Env": ["SECRET_VALUE=must-not-appear"],
                "Cmd": ["--token", "must-not-appear"],
                "Labels": {"secret": "must-not-appear"},
            },
        }

    def reload(self) -> None:
        if self._started and self._states_after_start:
            self.attrs["State"] = self._states_after_start.pop(0)

    def stop(self, *, timeout: int) -> None:
        if timeout != 10:
            raise AssertionError("unexpected stop timeout")
        self.attrs["State"] = _state(running=False, started_at="old")

    def start(self) -> None:
        self._started = True


def _state(
    *,
    running: bool,
    started_at: str,
    exit_code: int = 0,
    oom_killed: bool = False,
) -> dict[str, object]:
    return {
        "Status": "running" if running else "exited",
        "Running": running,
        "Restarting": False,
        "Paused": False,
        "Dead": False,
        "OOMKilled": oom_killed,
        "ExitCode": exit_code,
        "Error": "must-not-appear",
        "StartedAt": started_at,
        "FinishedAt": "finished" if not running else "",
        "Health": {"Status": "starting" if running else "unhealthy"},
    }


class SourceLiveRestartDiagnosticTests(unittest.TestCase):
    def test_public_gateway_retry_policy_is_bounded(self) -> None:
        module = _load_source_live_module()

        self.assertEqual(
            module.PUBLIC_GATEWAY_PROBE_POLICY,
            module.VerificationPolicy(
                timeout_seconds=5,
                interval_seconds=2,
                maximum_attempts=5,
            ),
        )

    def test_restart_rejects_container_that_exits_after_transient_running(self) -> None:
        module = _load_source_live_module()
        container = _Container(
            (
                _state(running=True, started_at="new"),
                _state(running=False, started_at="new", exit_code=17),
            )
        )
        client = type(
            "Client",
            (),
            {
                "containers": type(
                    "Containers",
                    (),
                    {"get": lambda _self, _container_id: container},
                )()
            },
        )()

        with (
            patch.object(module.docker, "from_env", return_value=client),
            patch.object(module.time, "monotonic", side_effect=(0.0, 0.1, 0.2)),
            patch.object(module.time, "sleep"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "container exited before restart stability",
            ) as raised:
                module._restart_container(container.id)

        message = str(raised.exception)
        self.assertIn('"exit_code": 17', message)
        self.assertIn('"image_id": "sha256:', message)
        self.assertIn('"network_names": ["cpk-workspace-runtime"]', message)
        self.assertNotIn("must-not-appear", message)
        self.assertNotIn("SECRET_VALUE", message)
        self.assertNotIn("Config", message)

    def test_restart_requires_continuous_running_stability(self) -> None:
        module = _load_source_live_module()
        container = _Container(
            (
                _state(running=True, started_at="new"),
                _state(running=True, started_at="new"),
            )
        )
        client = type(
            "Client",
            (),
            {
                "containers": type(
                    "Containers",
                    (),
                    {"get": lambda _self, _container_id: container},
                )()
            },
        )()

        with (
            patch.object(module.docker, "from_env", return_value=client),
            patch.object(module.time, "monotonic", side_effect=(0.0, 0.1, 1.2)),
            patch.object(module.time, "sleep"),
        ):
            module._restart_container(container.id)

    def test_readiness_failure_includes_only_bounded_container_state(self) -> None:
        module = _load_source_live_module()
        container = _Container(
            (_state(running=False, started_at="new", exit_code=19),)
        )
        container._started = True
        policy = type(
            "Policy",
            (),
            {
                "maximum_attempts": 1,
                "interval_seconds": 0.0,
                "timeout_seconds": 0.1,
            },
        )()

        with (
            patch.object(module, "_verification_policy", return_value=policy),
            patch.object(module, "urlopen", side_effect=OSError("connection")),
            patch.object(
                module.socket,
                "getaddrinfo",
                return_value=((None, None, None, None, ("172.30.0.4", 8000)),),
            ),
            patch.object(module, "_single_docker_container", return_value=container),
            patch.object(module, "_runtime_network_diagnostics", return_value=[]),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "private gateway did not become ready",
            ) as raised:
                module._wait_private_gateway_ready(object())

        message = str(raised.exception)
        self.assertIn('"exit_code": 19', message)
        self.assertNotIn("must-not-appear", message)
        self.assertNotIn("SECRET_VALUE", message)


if __name__ == "__main__":
    unittest.main()
