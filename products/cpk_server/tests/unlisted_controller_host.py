"""Real loopback HTTP host for the bounded Servers #237 source witness.

The host composes maintained cpk-server routes, authentication, process
boundaries, and injected actual Operations services.  It owns only its listener,
thread, temporary client credentials, and bounded prepare-exchange recording.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
from threading import Lock, Thread
from time import monotonic, sleep
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
import uvicorn

from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalKind
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_servers_cpk_server import (
    CpkServerApplicationBoundary,
    CpkServerHttpProcessBoundary,
    create_cpk_server_composition,
)
from control_plane_kit_servers_cpk_server.authentication import (
    StaticDevelopmentMultiCredentialVerifier,
    StaticDevelopmentPrincipalCredential,
)
from control_plane_kit_servers_cpk_server.client import ClientProfile, TopologyClient
from control_plane_kit_servers_cpk_server.http_host import install_operator_http_routes
from receiver_acceptance_operations import witness_principal


_ROLES = ("operator", "approver", "worker")


class DiagnosticApplicationBoundary(CpkServerApplicationBoundary):
    """Observe exception identity/source coordinates, then preserve sanitization."""
    diagnostic_count = 0

    async def dispatch_async(self, request):
        try:
            return await super().dispatch_async(request)
        except Exception as error:
            try:
                self._diagnose(error, request.route_id)
            except Exception:
                raise error  # Preserve the original owner error if diagnostics fail.
            raise

    def _diagnose(self, error, route_id):
        if self.diagnostic_count >= 8:
            return
        self.diagnostic_count += 1
        chain, seen = [], set()
        while error is not None and len(chain) < 8 and id(error) not in seen:
            seen.add(id(error))
            chain.append(_exception_source(error))
            # from None suppresses traceback display, but preserves __context__.
            error = error.__cause__ if error.__cause__ is not None else error.__context__
        print(json.dumps({"unlisted_owner_exception": chain[0]["kind"],
            "route": route_id, "frames": chain[0]["frames"],
            "exception_chain": chain, "chain_truncated": error is not None}), flush=True)


def _exception_source(error):
    frames = []
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        module = trace.tb_frame.f_globals.get("__name__", "")
        if (isinstance(module, str) and len(module) <= 160
                and module.startswith(("control_plane_kit_", "unlisted_controller_host",
                    "live_unlisted_receiver", "receiver_acceptance_"))
                and all(part.isidentifier() for part in module.split("."))):
            frames.append({"module": module,
                "function": code.co_name if code.co_name.isidentifier()
                    and len(code.co_name) <= 128 else "anonymous", "line": trace.tb_lineno})
            frames = frames[-8:]
        trace = trace.tb_next
    kind = type(error).__name__
    return {"kind": kind if kind in {"InvalidOperationCommand", "InvalidEffectRecoveryContract",
        "CpkServerApplicationError", "GraphDescriptorError", "MalformedGraphDescriptor", "InvalidDeploymentProgramContract",
        "DesiredGraphCommandError", "GraphAuthoringError", "TypeError", "ValueError"} else "other",
        "frames": frames}


_MAXIMUM_PREPARE_EXCHANGES = 16


class ControllerHostError(RuntimeError):
    """Fixed failure for listener ownership or malformed injected composition."""


@dataclass(frozen=True)
class PrepareExchange:
    """One actual prepare request and its completed public boundary response."""

    request_body: bytes
    response_status: int
    response_body: Mapping[str, object]


class ControllerHost:
    """Context-managed real HTTP entrance over injected Operations services."""

    def __init__(
        self,
        application_factory: Callable[[], object],
        driver: object,
        state_root: Path,
        *,
        startup_timeout_seconds: float = 10.0,
        shutdown_timeout_seconds: float = 10.0,
    ) -> None:
        if not callable(application_factory):
            raise TypeError("Operations application factory is required")
        workspace_id = getattr(driver, "workspace_id", None)
        operator = getattr(driver, "operator", None)
        worker = getattr(driver, "worker", None)
        if (
            not isinstance(workspace_id, str)
            or not workspace_id
            or not isinstance(operator, AuthenticatedPrincipal)
            or not isinstance(worker, AuthenticatedPrincipal)
        ):
            raise TypeError("actual public Operations driver is required")
        if (
            not isinstance(state_root, Path)
            or not state_root.is_absolute()
            or not state_root.parent.is_dir()
            or state_root.exists()
        ):
            raise ValueError("fresh absolute controller state root is required")
        for value in (startup_timeout_seconds, shutdown_timeout_seconds):
            if not isinstance(value, (int, float)) or not 0 < value <= 60:
                raise ValueError("host timeout is invalid")
        self._application_factory = application_factory
        self._principals = {
            "operator": operator,
            "approver": witness_principal(
                workspace_id,
                subject_id="unlisted-sdk-approver",
                kind=PrincipalKind.OPERATOR,
                scopes=(
                    PolicyScope.PLAN_APPROVE,
                    PolicyScope.PLAN_APPROVE_DESTRUCTIVE,
                ),
            ),
            "worker": worker,
        }
        self.workspace_id = workspace_id
        self._state_root = state_root
        self._startup_timeout = float(startup_timeout_seconds)
        self._shutdown_timeout = float(shutdown_timeout_seconds)
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._listener: socket.socket | None = None
        self._server: uvicorn.Server | None = None
        self._thread: Thread | None = None
        self._thread_failures: list[BaseException] = []
        self._profile: ClientProfile | None = None
        self._endpoint: str | None = None
        self._prepare_exchanges: list[PrepareExchange] = []
        self._record_lock = Lock()
        self._started_successfully = False

    @property
    def endpoint(self) -> str:
        if self._endpoint is None:
            raise ControllerHostError("loopback host is not running")
        return self._endpoint

    @property
    def profile(self) -> ClientProfile:
        if self._profile is None:
            raise ControllerHostError("client profile is not available")
        return self._profile

    @property
    def credential_files(self) -> Mapping[str, Path]:
        return dict(self.profile.credentials)

    @property
    def prepare_exchanges(self) -> tuple[PrepareExchange, ...]:
        with self._record_lock:
            return tuple(self._prepare_exchanges)

    def topology_client(self, **arguments: Any) -> TopologyClient:
        """Construct the maintained client; callers may inject a loss wrapper."""

        return TopologyClient(self.profile, **arguments)

    def __enter__(self) -> "ControllerHost":
        if self._temporary is not None:
            raise ControllerHostError("loopback host is already entered")
        try:
            self._state_root.mkdir(mode=0o700)
            temporary = tempfile.TemporaryDirectory(
                prefix="cpk-237-unlisted-",
                dir=self._state_root,
            )
            self._temporary = temporary
            root = Path(temporary.name).resolve()
            credentials = self._credential_material(root)
            composition = create_cpk_server_composition()
            operations = self._application_factory()
            services = getattr(operations, "services", None)
            if not isinstance(services, Mapping):
                raise ControllerHostError(
                    "Operations application factory did not expose services"
                )
            verifier = StaticDevelopmentMultiCredentialVerifier(
                tuple(
                    StaticDevelopmentPrincipalCredential(
                        credentials[role], self._principals[role]
                    )
                    for role in _ROLES
                )
            )
            application = DiagnosticApplicationBoundary(services, verifier)
            boundary = CpkServerHttpProcessBoundary(composition, application)
            prepare_route = composition.http_api.route("command.deployment.prepare")
            prepare_path = prepare_route.path_template.replace(
                "{workspace_id}", self.workspace_id
            )

            app = FastAPI()
            diagnostic_count = 0

            async def http(request: Request) -> JSONResponse:
                nonlocal diagnostic_count
                body = await request.body()
                response = await boundary.handle_async(
                    method=request.method,
                    path=request.url.path,
                    headers=request.headers,
                    body=body,
                    query_string=request.scope["query_string"],
                )
                if request.method == "POST" and request.url.path == prepare_path:
                    self._record_prepare(body, response.status, response.body)
                if response.status >= 400 and diagnostic_count < 16:
                    diagnostic_count += 1
                    error = response.body.get("error")
                    message = error.get("message") if isinstance(error, Mapping) else None
                    allowed = {
                        "invalid operation arguments": "invalid-operation-arguments",
                        "draft command was not admitted": "draft-not-admitted",
                        "draft graph is malformed": "draft-graph-malformed",
                        "receiver expectation is malformed": "receiver-expectation-malformed",
                        "draft intent conflicts with current truth": "draft-conflict",
                    }
                    for route_id in ("command.desired-topology-draft.create",
                            "command.desired-topology-draft.select"):
                        allowed[f"{route_id!r} is not configured in cpk-server operations"] = "draft-service-not-configured"
                    print(json.dumps({"unlisted_http_failure_status": response.status,
                        "reason": allowed.get(message, "unclassified")
                            if isinstance(message, str) else "unclassified"}), flush=True)
                return JSONResponse(status_code=response.status, content=dict(response.body))

            install_operator_http_routes(app, composition.http_api, http)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listener = listener
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            self._endpoint = f"http://127.0.0.1:{port}"
            state_directory = root / "state"
            state_directory.mkdir(mode=0o700)
            credential_paths = {
                role: root / f"{role}.credential" for role in _ROLES
            }
            self._profile = ClientProfile(
                self._endpoint,
                self.workspace_id,
                credential_paths,
                state_directory,
            )
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                access_log=False,
                log_config=None,
                log_level="warning",
                lifespan="off",
            )
            server = uvicorn.Server(config)
            self._server = server
            thread = Thread(
                target=self._run_server,
                args=(server, listener),
                name="cpk-237-unlisted-http",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            deadline = monotonic() + self._startup_timeout
            while not server.started:
                if self._thread_failures or not thread.is_alive():
                    raise ControllerHostError(
                        "loopback HTTP host stopped during startup"
                    )
                if monotonic() >= deadline:
                    raise ControllerHostError(
                        "loopback HTTP host startup exceeded its bound"
                    )
                sleep(0.01)
            self._started_successfully = True
            return self
        except BaseException as original:
            try:
                self._stop()
            except BaseException as cleanup:
                raise cleanup from original
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self._stop()
        except BaseException as cleanup:
            if exc is not None:
                raise cleanup from exc
            raise

    def _credential_material(self, root: Path) -> dict[str, bytes]:
        credentials: dict[str, bytes] = {}
        for role in _ROLES:
            credential = secrets.token_urlsafe(32).encode("ascii")
            path = root / f"{role}.credential"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, 0o600)
            try:
                os.write(descriptor, credential)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(path, 0o600, follow_symlinks=False)
            credentials[role] = credential
        return credentials

    def _record_prepare(
        self,
        request_body: bytes,
        response_status: int,
        response_body: Mapping[str, object],
    ) -> None:
        # Decode only to reject accidental non-object recordings. The exact
        # request bytes and actual boundary response remain the retained facts.
        try:
            decoded = json.loads(request_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(decoded, dict):
            return
        with self._record_lock:
            if len(self._prepare_exchanges) >= _MAXIMUM_PREPARE_EXCHANGES:
                raise ControllerHostError(
                    "prepare exchange recording exceeded its bound"
                )
            self._prepare_exchanges.append(
                PrepareExchange(bytes(request_body), response_status, dict(response_body))
            )

    def _run_server(self, server: uvicorn.Server, listener: socket.socket) -> None:
        try:
            server.run(sockets=[listener])
        except BaseException as error:
            self._thread_failures.append(error)

    def _stop(self) -> None:
        server, thread, listener = self._server, self._thread, self._listener
        failures: list[Exception] = []
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(self._shutdown_timeout)
            if thread.is_alive():
                if server is not None:
                    server.force_exit = True
                if listener is not None:
                    listener.close()
                thread.join(min(self._shutdown_timeout, 5.0))
            if thread.is_alive():
                failures.append(
                    ControllerHostError(
                        "loopback HTTP host shutdown exceeded its bound"
                    )
                )
        if listener is not None:
            try:
                listener.close()
            except OSError:
                failures.append(ControllerHostError("loopback listener did not close"))
        if self._thread_failures:
            failures.append(ControllerHostError("loopback HTTP host thread failed"))
        temporary = self._temporary
        started_successfully = self._started_successfully
        self._server = None
        self._thread = None
        self._listener = None
        self._profile = None
        self._endpoint = None
        self._temporary = None
        self._started_successfully = False
        if temporary is not None:
            try:
                temporary.cleanup()
            except BaseException:
                failures.append(
                    ControllerHostError("private controller files were not removed")
                )
        if self._state_root.exists():
            try:
                self._state_root.rmdir()
            except OSError:
                failures.append(
                    ControllerHostError(
                        "controller state root was not empty after cleanup"
                    )
                )
        verified = (
            (thread is None or not thread.is_alive())
            and (listener is None or listener.fileno() == -1)
            and not self._state_root.exists()
        )
        if not verified and not failures:
            failures.append(ControllerHostError("controller cleanup is incomplete"))
        if failures:
            if len(failures) == 1:
                raise failures[0]
            raise ExceptionGroup("controller cleanup encountered failures", failures)
        if started_successfully:
            print(
                "unlisted controller host: thread, listener, private credentials, "
                "and state cleanup verified",
                flush=True,
            )
