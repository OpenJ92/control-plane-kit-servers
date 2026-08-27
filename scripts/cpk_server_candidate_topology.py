"""Candidate-direct cpk-server topology acceptance orchestration."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from time import sleep as _sleep
from typing import Any, Callable
from urllib.request import urlretrieve

from control_plane_kit_core.algebra import (
    DeploymentTopology,
    DockerRuntime,
    SocketConnection,
)
from control_plane_kit_core.products import (
    ProductInstanceConfiguration,
    instantiate_product,
)
from control_plane_kit_core.planning import compile_activity_plan
from control_plane_kit_core.topology import (
    DeploymentGraph,
    compile_topology,
    diff_graphs,
    validate_graph,
)

from scripts.cpk_server_candidate_lifecycle import (
    admit_candidate_ledger,
    candidate_resource_name,
    interrupt_candidate_run,
    record_candidate_resource,
)
from scripts.cpk_server_hosted_activity import (
    HostedWorkflow,
    _product_document,
    _single_hello_graph,
    _with_public_environment,
)


ASSEMBLY_SCHEMA = "cpk.candidate-assembly.v1"
REPORT_SCHEMA = "cpk.candidate-topology-report.v1"
STARTUP_DIAGNOSTIC_SCHEMA = "cpk.candidate-startup-diagnostic.v1"
STARTUP_DIAGNOSTIC_FILENAME = "candidate-startup-diagnostic.json"
RUN_HISTORY_REJECTION_SCHEMA = "cpk.candidate-run-history-rejection.v1"
RUN_HISTORY_REJECTION_FILENAME = "candidate-run-history-rejection.json"
ASSEMBLY_ERROR = "candidate assembly is invalid"
WORKFLOW_ERROR = "candidate topology workflow failed"
PACKAGE_BUILD_FAILURE_CODE = "candidate-image-build-failed"
PACKAGE_BUILD_FAILURE_MESSAGE = "Candidate image build failed."
SERVER_BASELINE_COMMIT = "43e9f359ca828c83fe4994ed1b62e1be54277ddd"
SERVER_BASELINE_TREE = "ec259176eba3ce2f777d38c68fcc14e0a0e80cd3"
SNAPSHOT_MANIFEST_SHA256 = (
    "2cf09911ac9dcaa4e8ae86f8eefa60f191955d0e1f1f115f763aba78a831a48c"
)
POSTGRES_IMAGE = (
    "docker.io/library/postgres@sha256:"
    "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)
HELLO_RESPONSE = b"Hello, world!\n"
CPK_COMMIT = "2ae7f6fe1d34cad943e2e16a2cf93903d840ddc1"
CPK_TREE = "c950b2f1769298949fa0d9e584be7d6d4008d500"
PRODUCTION_DOCKERFILE_SHA256 = (
    "3b72cad8c90a773d534a711cb65cfed92a4b9da84e706fd7f2f827554d7a4c95"
)
HELLO_DESCRIPTOR_SHA256 = (
    "57ac661ca3f73ad4fa488df34390240e95da58e302bffb17c2197eeac29c2a24"
)
ROUTER_DESCRIPTOR_SHA256 = (
    "2e4c1ca0e0f59844c06bc754b41ca82a31826d3e12760912f49de1f15bd1f18d"
)
ROUTER_IMAGE = (
    "ghcr.io/openj92/control-plane-kit-servers/http-active-router@sha256:"
    "a58938fdc5c37bfda1b2b0dbd95fc0bf3ba7391f5ce3b8fdfb3956dccf0a01c8"
)
BLUE_GREEN_SCENARIO = "candidate.topology.blue-green.v1"
BLUE_RESPONSE = b"Hello from blue\n"
GREEN_RESPONSE = b"Hello from green\n"
POSTGRES_DB = "cpk"
POSTGRES_USER = "candidate"
POSTGRES_PASSWORD = "candidate-password-not-for-output"
POSTGRES_READY_ATTEMPTS = 15
POSTGRES_READY_RETRY_SECONDS = 1.0
OPERATOR_SCOPES = (
    "hub:instance:create",
    "hub:instance:read",
    "instance:workspace:read",
    "instance:workspace:edit",
    "plan:request",
    "plan:execute",
    "execution:operate",
    "runtime-authority:register",
    "runtime-authority:read",
    "runtime-authority:revoke",
    "runtime-authority:use",
    "runtime-authority-delivery:register",
    "runtime-authority-delivery:read",
    "runtime-authority-delivery:revoke",
    "secret-provider:register",
)
APPROVER_SCOPES = ("plan:approve", "plan:approve-destructive")
WORKER_SCOPES = ("execution:operate", "secret-provider:use")
DOCKER_SOCKET = "/var/run/docker.sock"
GHCR_PULL_CREDENTIAL_ENV = "CPK_CANDIDATE_GHCR_PULL_CREDENTIAL"
GHCR_PULL_CREDENTIAL_REFERENCE = "secret://docker-config/ghcr.io"
RFC8785_WHEEL_PATH = "dist/rfc8785-0.1.4-py3-none-any.whl"
RFC8785_WHEEL_SHA256 = (
    "520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48"
)
RFC8785_WHEEL_SIZE = 9240
RFC8785_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/4d/78/"
    "119878110660b2ad709888c8a1614fce7e2fab39080ab960656dc8605bf6/"
    "rfc8785-0.1.4-py3-none-any.whl"
)
CORE_WHEEL_PATH = "dist/control_plane_kit_core.whl"
OPERATIONS_WHEEL_PATH = "dist/control_plane_kit_operations.whl"
OVERLAY_PATH = "acceptance/candidate_topology/Dockerfile"

EXPECTED_ASSEMBLY = {
    "schema": ASSEMBLY_SCHEMA,
    "scenario": "candidate.topology.single-hello.v1",
    "acceptance_level": "source-built-candidate",
    "candidate": {
        "repository": "OpenJ92/control-plane-kit",
        "commit": CPK_COMMIT,
        "tree": CPK_TREE,
    },
    "server_source": {
        "repository": "OpenJ92/control-plane-kit-servers",
        "commit": "fc46e42d7143698ad6c7ab86d67c66a3f059ab68",
        "tree": "eeab26c68610d176078adbd68a319c806a8cd436",
    },
    "runner": {
        "repository": "OpenJ92/control-plane-kit-servers",
        "commit": "fc46e42d7143698ad6c7ab86d67c66a3f059ab68",
        "tree": "eeab26c68610d176078adbd68a319c806a8cd436",
    },
    "dependencies": {
        "control_plane_kit_interpreters": {
            "repository": "OpenJ92/control-plane-kit-interpreters",
            "commit": "2d6f1044e7ccc88b49f8689cec30f0c7c905414d",
            "tree": "733575f85da057e7d9f1965c10b695217a6140ed",
        },
        "control_plane_kit_secrets": {
            "repository": "OpenJ92/control-plane-kit-secrets",
            "commit": "96e86dc3248d578780d64d5d7fc5d6359631d1d6",
            "tree": "b1740225a93410349a9e9199c539e330b408abae",
        },
    },
    "products": {
        "cpk_server": {
            "classification": "source-built-candidate",
            "source_commit": CPK_COMMIT,
            "source_tree": CPK_TREE,
            "dockerfile_sha256": PRODUCTION_DOCKERFILE_SHA256,
        },
        "hello": {
            "classification": "published-digest",
            "reference": (
                "ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:"
                "e2288b23844b1f0b7526d2798cbc1eaf6e9f536399173a043e7957f0e7730cbf"
            ),
            "descriptor_sha256": HELLO_DESCRIPTOR_SHA256,
        },
    },
    "inputs": {
        "workspace_id": "candidate-topology-1695-20260826a",
        "foreign_resource_canary": "foreign-resource-1695-20260826a",
    },
}
EXPECTED_BLUE_GREEN_ASSEMBLY = deepcopy(EXPECTED_ASSEMBLY)
EXPECTED_BLUE_GREEN_ASSEMBLY["scenario"] = BLUE_GREEN_SCENARIO
EXPECTED_BLUE_GREEN_ASSEMBLY["products"]["http_active_router"] = {
    "classification": "published-digest",
    "reference": ROUTER_IMAGE,
    "descriptor_sha256": ROUTER_DESCRIPTOR_SHA256,
}
EXPECTED_INSPECTION = {
    "candidate": {"commit": CPK_COMMIT, "tree": CPK_TREE, "clean": True},
    "server_source": {
        "commit": EXPECTED_ASSEMBLY["server_source"]["commit"],
        "tree": EXPECTED_ASSEMBLY["server_source"]["tree"],
        "clean": True,
    },
    "files": {
        "products/cpk_server/Dockerfile": PRODUCTION_DOCKERFILE_SHA256,
        "acceptance/candidate_topology/Dockerfile": "c" * 64,
        "dist/control_plane_kit_core.whl": "d" * 64,
        "dist/control_plane_kit_operations.whl": "e" * 64,
        RFC8785_WHEEL_PATH: RFC8785_WHEEL_SHA256,
    },
    "images": {"cpk_server_base": "sha256:" + "9" * 64},
}


class CandidateAssemblyError(ValueError):
    """Raised when the source-built candidate join is not exact."""


class CandidateTopologyError(RuntimeError):
    """Raised for a bounded candidate workflow failure."""


class _RunHistoryRejection(Exception):
    """Candidate-local control value for closed run-history rejection evidence."""

    def __init__(
        self,
        *,
        outcome: str,
        location: str,
        reason: str,
        transition: str,
        event_ordinal: int | None = None,
    ) -> None:
        self.outcome = outcome
        self.location = location
        self.reason = reason
        self.transition = transition
        self.event_ordinal = event_ordinal


class _RunHistoryJsonError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _canonical_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _report_sha256(report: dict[str, Any]) -> str:
    projected = deepcopy(report)
    projected.pop("report_sha256", None)
    return _canonical_sha256(projected)


def _startup_diagnostic_sha256(diagnostic: dict[str, Any]) -> str:
    projected = deepcopy(diagnostic)
    projected.pop("diagnostic_sha256", None)
    return _canonical_sha256(projected)


_RUN_HISTORY_REJECTION_REASONS = {
    "input.workspace": ("identity-invalid",),
    **{
        f"input.{name}": ("identity-invalid", "identity-reused")
        for name in (
            "plan-id",
            "run-id",
            "desired-graph-id",
            "advanced-graph-id",
        )
    },
    "transition.advance": ("desired-advanced-mismatch",),
    **{
        f"pointer.{name}": (
            "pointer-shape",
            "http-mcp-mismatch",
            "not-current",
            "unassigned",
            "expected-graph-invalid",
            "graph-mismatch",
            "authored-mismatch",
            "projection-invalid",
            "version-mismatch",
            "name-invalid",
            "descriptor-not-object",
            "operator-not-object",
            "json-invalid",
            "json-over-bound",
        )
        for name in ("predecessor", "successor")
    },
    "lineage": ("predecessor-discontinuity",),
    "plan.before": (),
    "plan.after": (),
    "plan.diff": (),
    "plan.compile": (),
    "plan.activities": (),
    "plan.operations": ("operation-sequence",),
    "events.http": (),
    "events.mcp": (),
    "events.parity": ("http-mcp-mismatch", "json-invalid", "json-over-bound"),
    "page": (
        "page-shape",
        "workspace-mismatch",
        "kind-mismatch",
        "limit-mismatch",
        "items-not-list",
        "cursor-present",
        "event-count",
    ),
    "event": (
        "event-shape",
        "event-id-invalid",
        "event-id-duplicate",
        "run-mismatch",
        "ordinal-mismatch",
        "kind-mismatch",
        "activity-mismatch",
        "failure-present",
        "timestamp-shape",
        "timestamp-invalid",
        "timestamp-naive",
    ),
    "payload.run-opened": ("payload-shape", "attempt-mismatch"),
    "payload.run-started": ("payload-shape",),
    "payload.step": (
        "payload-shape",
        "attempt-shape",
        "attempt-mismatch",
        "fingerprint-invalid",
    ),
    "payload.run-succeeded": ("payload-shape", "result-mismatch"),
    "payload.advance": (
        "payload-shape",
        "workspace-mismatch",
        "plan-mismatch",
        "run-mismatch",
        "from-authored-mismatch",
        "from-realized-mismatch",
        "to-authored-mismatch",
        "to-realized-mismatch",
        "revision-mismatch",
        "revision-invalid",
        "digest-invalid",
    ),
    "history.copy": (),
    "unknown": (),
}
_RUN_HISTORY_REJECTION_RELATION = frozenset(
    ("rejected", location, reason)
    for location, reasons in _RUN_HISTORY_REJECTION_REASONS.items()
    for reason in reasons
) | frozenset(
    ("unavailable", f"events.{protocol}", "read-unavailable")
    for protocol in ("http", "mcp")
) | frozenset(
    ("unknown", location, "unknown")
    for location in _RUN_HISTORY_REJECTION_REASONS
)


def _run_history_rejection_ordinals(
    location: str, transition: str
) -> tuple[int | None, ...]:
    event_count = 10 if transition == "hello" else 12
    if location == "event":
        return tuple(range(1, event_count + 1))
    if location == "payload.run-opened":
        return (1,)
    if location == "payload.run-started":
        return (2,)
    if location == "payload.step":
        return tuple(range(3, event_count - 1))
    if location == "payload.run-succeeded":
        return (event_count - 1,)
    if location == "payload.advance":
        return (event_count,)
    return (None,)


def _run_history_rejection_diagnostic(
    *,
    outcome: str,
    location: str,
    reason: str,
    transition: str,
    event_ordinal: int | None = None,
) -> dict[str, Any]:
    string_values = (outcome, location, reason, transition)
    relation = (outcome, location, reason)
    transition_valid = (
        transition == "context"
        if location.startswith("input.")
        else transition in ({"context", "hello", "empty"} if location == "unknown" else {"hello", "empty"})
    )
    if (
        not all(type(value) is str for value in string_values)
        or relation not in _RUN_HISTORY_REJECTION_RELATION
        or not transition_valid
        or type(event_ordinal) not in {int, type(None)}
        or event_ordinal not in _run_history_rejection_ordinals(location, transition)
    ):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    diagnostic = {
        "schema": RUN_HISTORY_REJECTION_SCHEMA,
        "classification": "supporting",
        "phase": "run-history-capture",
        "outcome": outcome,
        "transition": transition,
        "location": location,
        "reason": reason,
        "event_ordinal": event_ordinal,
        "redaction_verified": True,
        "protected_material_retained": False,
    }
    diagnostic["diagnostic_sha256"] = _canonical_sha256(diagnostic)
    return diagnostic


def _validated_run_history_rejection_diagnostic(
    diagnostic: Any,
) -> dict[str, Any]:
    valid = False
    expected: dict[str, Any] | None = None
    if type(diagnostic) is dict and set(diagnostic) == {
        "schema",
        "classification",
        "phase",
        "outcome",
        "transition",
        "location",
        "reason",
        "event_ordinal",
        "redaction_verified",
        "protected_material_retained",
        "diagnostic_sha256",
    }:
        try:
            if (
                type(diagnostic["redaction_verified"]) is not bool
                or type(diagnostic["protected_material_retained"]) is not bool
            ):
                raise CandidateTopologyError(WORKFLOW_ERROR)
            expected = _run_history_rejection_diagnostic(
                outcome=diagnostic["outcome"],
                location=diagnostic["location"],
                reason=diagnostic["reason"],
                transition=diagnostic["transition"],
                event_ordinal=diagnostic["event_ordinal"],
            )
            valid = diagnostic == expected
        except Exception:
            pass
    if not valid or expected is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return expected


def _same_file_identity(path: Path, identity: tuple[int, int]) -> bool:
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return False
    return (observed.st_dev, observed.st_ino) == identity


def _persist_run_history_rejection(
    path: Path, diagnostic: dict[str, Any]
) -> None:
    accepted = _validated_run_history_rejection_diagnostic(diagnostic)
    payload = (
        json.dumps(accepted, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if len(payload) > 4096:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    temporary = Path(str(path) + ".part")
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
        if not _same_file_identity(temporary, identity):
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if _path_exists_without_following(path):
            raise CandidateAssemblyError(ASSEMBLY_ERROR)
        os.link(temporary, path)
        temporary.unlink()
        identity = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if identity is not None and _same_file_identity(temporary, identity):
            temporary.unlink()


_CANDIDATE_CONTAINER_STATES = frozenset(
    {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
)
_TERMINAL_CANDIDATE_CONTAINER_STATES = frozenset({"exited", "dead"})


def _project_candidate_startup_state(value: Any) -> dict[str, Any]:
    state = value if type(value) is dict else {}
    raw_status = state.get("status")
    status = (
        raw_status
        if type(raw_status) is str and raw_status in _CANDIDATE_CONTAINER_STATES
        else "unknown"
    )
    raw_exit_code = state.get("exit_code")
    exit_code = (
        raw_exit_code
        if status in _TERMINAL_CANDIDATE_CONTAINER_STATES
        and type(raw_exit_code) is int
        and 0 <= raw_exit_code <= 255
        else None
    )
    return {"status": status, "exit_code": exit_code}


def _startup_readiness_classification(error: BaseException) -> str:
    message = str(error)
    if message == "cpk-server did not become ready":
        return "policy-exhausted"
    if message == "cpk-server did not boot with Docker runtime":
        return "runtime-mismatch"
    return "unknown"


def _startup_diagnostic(
    prepared: dict[str, Any],
    *,
    readiness_error: BaseException,
    container_state: Any,
) -> dict[str, Any]:
    server = prepared.get("server")
    inspection = prepared.get("server_inspection")
    diagnostic = {
        "schema": STARTUP_DIAGNOSTIC_SCHEMA,
        "classification": "supporting",
        "phase": "hosted-readiness",
        "candidate_image_built": type(prepared.get("build")) is dict,
        "server_container_started": type(server) is dict,
        "server_package_inspected": type(inspection) is dict,
        "port_published": (
            type(server) is dict
            and type(server.get("base_url")) is str
            and bool(server["base_url"])
        ),
        "readiness": _startup_readiness_classification(readiness_error),
        "container_state": _project_candidate_startup_state(container_state),
        "redaction_verified": True,
        "protected_material_retained": False,
    }
    diagnostic["diagnostic_sha256"] = _startup_diagnostic_sha256(diagnostic)
    return diagnostic


def _path_exists_without_following(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _persist_startup_diagnostic(path: Path, diagnostic: dict[str, Any]) -> None:
    payload = (
        json.dumps(diagnostic, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if len(payload) > 4096:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    temporary = Path(str(path) + ".part")
    descriptor: int | None = None
    temporary_created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        temporary_created = True
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
        if _path_exists_without_following(path):
            raise CandidateAssemblyError(ASSEMBLY_ERROR)
        os.replace(temporary, path)
        temporary_created = False
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_created and _path_exists_without_following(temporary):
            temporary.unlink()


_PUBLIC_INVENTORY_KEYS = (
    "containers",
    "networks",
    "volumes",
    "images",
    "postgres_relations",
)
_PUBLIC_CLEANUP_KEYS = (*_PUBLIC_INVENTORY_KEYS, "foreign_canary_after")
_INTERNAL_CLEANUP_KEY_SETS = (
    frozenset(_PUBLIC_CLEANUP_KEYS),
    frozenset(
        (
            *_PUBLIC_CLEANUP_KEYS,
            "pre_inventory",
            "post_inventory",
            "ownership_labels",
        )
    ),
)
_INTERNAL_INVENTORY_KEY_SETS = (frozenset(_PUBLIC_INVENTORY_KEYS),)


def _public_inventory(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or frozenset(value) not in _INTERNAL_INVENTORY_KEY_SETS
    ):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return {key: deepcopy(value[key]) for key in _PUBLIC_INVENTORY_KEYS}


def _public_cleanup(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or frozenset(value) not in _INTERNAL_CLEANUP_KEY_SETS
    ):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return {key: deepcopy(value[key]) for key in _PUBLIC_CLEANUP_KEYS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fixed_assembly_error() -> CandidateAssemblyError:
    return CandidateAssemblyError(ASSEMBLY_ERROR)


def _exact_keys(value: Any, expected: set[str]) -> bool:
    return type(value) is dict and set(value) == expected


def _hex_digest(value: Any, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and value == value.lower()
        and set(value) <= set("0123456789abcdef")
    )


def _image_id(value: Any) -> bool:
    return type(value) is str and value.startswith("sha256:") and _hex_digest(
        value.removeprefix("sha256:"),
        64,
    )


def _docker_socket_group() -> str:
    missing = False
    observed = None
    try:
        observed = os.stat(DOCKER_SOCKET)
    except FileNotFoundError:
        missing = True
    if missing or observed is None or not stat.S_ISSOCK(observed.st_mode):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return str(observed.st_gid)


def _candidate_server_environment(
    postgres_name: str,
    *,
    ghcr_pull_credential: str | None = None,
) -> dict[str, str]:
    principals = [
        {
            "credential": "present",
            "subject_id": "hosted-operator",
            "kind": "operator",
            "workspace_grants": {
                EXPECTED_ASSEMBLY["inputs"]["workspace_id"]: list(OPERATOR_SCOPES)
            },
        },
        {
            "credential": "manager-present",
            "subject_id": "manager-a",
            "kind": "operator",
            "workspace_grants": {
                EXPECTED_ASSEMBLY["inputs"]["workspace_id"]: list(APPROVER_SCOPES)
            },
        },
        {
            "credential": "worker-present",
            "subject_id": "candidate-worker",
            "kind": "worker",
            "workspace_grants": {
                EXPECTED_ASSEMBLY["inputs"]["workspace_id"]: list(WORKER_SCOPES)
            },
        },
    ]
    database_url = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
        f"{postgres_name}:5432/{POSTGRES_DB}"
    )
    environment = {
        "CPK_SERVER_MODE": "execution-capable",
        "CPK_CONTROL_AUTH_VERIFIER": "static-development",
        "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(
            principals,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "CPK_PORT": "8080",
        "CPK_RUNTIME_INTERPRETERS": "docker",
        "CPK_INGRESS_INTERPRETERS": "none",
        "CPK_PRODUCT_MATERIAL_RESOLVER": (
            "local-development" if ghcr_pull_credential is not None else "none"
        ),
        "CPK_WORKPLACE_DATABASE_URL": database_url,
        "CPK_ACTIVITY_HISTORY_DATABASE_URL": database_url,
        "CPK_OBSERVER_STATE_DATABASE_URL": database_url,
        "CPK_GRAPH_TOPOLOGY_DATABASE_URL": database_url,
    }
    if ghcr_pull_credential is not None:
        environment["CPK_PRODUCT_SECRET_VALUES_JSON"] = json.dumps(
            {GHCR_PULL_CREDENTIAL_REFERENCE: ghcr_pull_credential},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    return environment


def admit_candidate_assembly(
    assembly: dict[str, Any],
    inspection: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        EXPECTED_ASSEMBLY["scenario"]: EXPECTED_ASSEMBLY,
        EXPECTED_BLUE_GREEN_ASSEMBLY["scenario"]: EXPECTED_BLUE_GREEN_ASSEMBLY,
    }.get(assembly.get("scenario"))
    if not _exact_keys(
        assembly,
        {
            "schema",
            "scenario",
            "acceptance_level",
            "candidate",
            "server_source",
            "runner",
            "dependencies",
            "products",
            "inputs",
        },
    ) or not _exact_keys(
        inspection,
        {"candidate", "server_source", "files", "images"},
    ):
        raise _fixed_assembly_error()
    if expected is None or (
        assembly["schema"] != ASSEMBLY_SCHEMA
        or assembly["acceptance_level"] != expected["acceptance_level"]
        or assembly["candidate"] != expected["candidate"]
        or assembly["dependencies"] != expected["dependencies"]
        or assembly["inputs"] != expected["inputs"]
    ):
        raise _fixed_assembly_error()
    source = assembly["server_source"]
    if (
        source != assembly["runner"]
        or not _exact_keys(source, {"repository", "commit", "tree"})
        or source["repository"] != "OpenJ92/control-plane-kit-servers"
        or not _hex_digest(source["commit"], 40)
        or not _hex_digest(source["tree"], 40)
    ):
        raise _fixed_assembly_error()
    candidate_inspection = inspection["candidate"]
    server_inspection = inspection["server_source"]
    if not _exact_keys(candidate_inspection, {"commit", "tree", "clean"}) or not _exact_keys(
        server_inspection,
        {"commit", "tree", "clean"},
    ):
        raise _fixed_assembly_error()
    if candidate_inspection != {
        "commit": assembly["candidate"]["commit"],
        "tree": assembly["candidate"]["tree"],
        "clean": True,
    } or server_inspection != {
        "commit": source["commit"],
        "tree": source["tree"],
        "clean": True,
    }:
        raise _fixed_assembly_error()
    products = assembly["products"]
    if not _exact_keys(products, set(expected["products"])):
        raise _fixed_assembly_error()
    server_product = products["cpk_server"]
    if not _exact_keys(
        server_product,
        {"classification", "source_commit", "source_tree", "dockerfile_sha256"},
    ) or server_product != expected["products"]["cpk_server"]:
        raise _fixed_assembly_error()
    if products["hello"] != expected["products"]["hello"]:
        raise _fixed_assembly_error()
    if assembly["scenario"] == BLUE_GREEN_SCENARIO and products[
        "http_active_router"
    ] != expected["products"]["http_active_router"]:
        raise _fixed_assembly_error()
    files = inspection["files"]
    if not _exact_keys(
        files,
        {
            "products/cpk_server/Dockerfile",
            "acceptance/candidate_topology/Dockerfile",
            "dist/control_plane_kit_core.whl",
            "dist/control_plane_kit_operations.whl",
            RFC8785_WHEEL_PATH,
        },
    ) or not all(_hex_digest(value, 64) for value in files.values()):
        raise _fixed_assembly_error()
    images = inspection["images"]
    if not _exact_keys(images, {"cpk_server_base"}) or not _image_id(
        images["cpk_server_base"]
    ):
        raise _fixed_assembly_error()
    if source == expected["server_source"] and inspection != EXPECTED_INSPECTION:
        raise _fixed_assembly_error()
    return assembly


def _stage(name: str) -> dict[str, str]:
    started = _now()
    return {
        "name": name,
        "started_at": started,
        "ended_at": _now(),
        "result": "passed",
    }


def _public_transition(
    workflow: Any,
    *,
    title: str,
    graph: Any,
    current_graph_id: str,
    expected_desired_graph_id: str | None,
) -> dict[str, Any]:
    session_id = workflow.start_session(title)
    desired_graph_id = workflow.set_desired_graph(
        session_id=session_id,
        graph=graph,
        title=title,
        expected_desired_graph_id=expected_desired_graph_id,
    )
    plan_id = workflow.plan_transition(
        session_id=session_id,
        title=title,
        current_graph_id=current_graph_id,
        desired_graph_id=desired_graph_id,
    )
    approval = workflow.request_approval(
        session_id=session_id,
        title=title,
        plan_id=plan_id,
    )
    workflow.assert_approval_visible(approval["request_id"], plan_id)
    workflow.approve(session_id=session_id, title=title, approval=approval)
    request_id = workflow.admit(
        session_id=session_id,
        title=title,
        plan_id=plan_id,
        approval_id=approval["request_id"],
    )
    run_id = workflow.claim(title=title, request_id=request_id)
    workflow.start_run(title=title, run_id=run_id)
    workflow.execute_to_completion(run_id, sync_runtime_networks=False)
    predecessor_http = workflow.read_current_graph_http()
    predecessor_mcp = workflow.read_current_graph_mcp()
    advanced = workflow.advance_current_graph(
        title=title,
        run_id=run_id,
        plan_id=plan_id,
        current_graph_id=current_graph_id,
        desired_graph_id=desired_graph_id,
    )
    successor_http = workflow.read_current_graph_http()
    successor_mcp = workflow.read_current_graph_mcp()
    return {
        "plan_id": plan_id,
        "run_id": run_id,
        "desired_graph_id": desired_graph_id,
        "advanced_graph_id": advanced,
        "predecessor_http": predecessor_http,
        "predecessor_mcp": predecessor_mcp,
        "successor_http": successor_http,
        "successor_mcp": successor_mcp,
    }


def _candidate_blue_green_graph(
    *,
    hello_document: Any,
    router_document: Any,
    workspace_id: str,
    present_roles: tuple[str, ...],
    active_role: str,
) -> DeploymentGraph:
    allowed_roles = ("hello-blue", "hello-green")
    allowed_profiles = (
        ("hello-blue",),
        ("hello-blue", "hello-green"),
        ("hello-green",),
    )
    if present_roles not in allowed_profiles or active_role not in present_roles:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    hello_product = hello_document.product
    messages = {
        "hello-blue": BLUE_RESPONSE.decode("ascii").rstrip("\n"),
        "hello-green": GREEN_RESPONSE.decode("ascii").rstrip("\n"),
    }
    hello_nodes = tuple(
        instantiate_product(
            hello_product,
            role,
            _with_public_environment(
                ProductInstanceConfiguration.from_contract(
                    hello_product.runtime_contract
                ),
                {"HELLO_MESSAGE": messages[role]},
            ),
        )
        for role in allowed_roles
        if role in present_roles
    )
    router_product = router_document.product
    router = instantiate_product(
        router_product,
        "router",
        ProductInstanceConfiguration.from_contract(router_product.runtime_contract),
    )
    return compile_topology(
        DeploymentTopology(
            workspace_id,
            DockerRuntime(
                runtime_id="docker",
                network_name=f"control-plane-kit-{workspace_id}-docker",
                children=(
                    *hello_nodes,
                    router,
                    SocketConnection(
                        active_role,
                        "internal",
                        "router",
                        "active",
                    ),
                ),
            ),
        )
    )


def run_candidate_blue_green(
    assembly: dict[str, Any],
    *,
    inspection: dict[str, Any],
    workflow: Any,
    effects: Any,
    hello_document: Any,
    router_document: Any,
    empty_graph: DeploymentGraph,
    current_graph_id: str,
    prepared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    admitted = admit_candidate_assembly(assembly, inspection)
    if admitted["scenario"] != BLUE_GREEN_SCENARIO:
        raise _fixed_assembly_error()
    active_prepared = (
        _prepare_candidate(admitted, inspection, effects)
        if prepared is None
        else prepared
    )
    workspace_id = admitted["inputs"]["workspace_id"]
    profiles = (
        (
            "blue-realization",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-blue",),
                active_role="hello-blue",
            ),
            BLUE_RESPONSE,
        ),
        (
            "green-preparation",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-blue",
            ),
            BLUE_RESPONSE,
        ),
        (
            "green-cutover",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-green",
            ),
            GREEN_RESPONSE,
        ),
        (
            "rollback-blue",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-blue",
            ),
            BLUE_RESPONSE,
        ),
        (
            "final-green",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-green",
            ),
            GREEN_RESPONSE,
        ),
        (
            "retire-blue",
            _candidate_blue_green_graph(
                hello_document=hello_document,
                router_document=router_document,
                workspace_id=workspace_id,
                present_roles=("hello-green",),
                active_role="hello-green",
            ),
            GREEN_RESPONSE,
        ),
        ("teardown", empty_graph, None),
    )
    transitions: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    failure: BaseException | None = None
    failure_stage = "blue-realization"
    active_current_graph_id = current_graph_id
    expected_desired_graph_id: str | None = None
    history_http: dict[str, Any] | None = None
    history_mcp: dict[str, Any] | None = None

    try:
        for title, graph, expected_response in profiles:
            failure_stage = title
            if expected_response is None:
                effects.remove_probe()
            transition = _public_transition(
                workflow,
                title=title,
                graph=graph,
                current_graph_id=active_current_graph_id,
                expected_desired_graph_id=expected_desired_graph_id,
            )
            transitions.append({"title": title, **transition})
            active_current_graph_id = transition["advanced_graph_id"]
            expected_desired_graph_id = transition["desired_graph_id"]
            if expected_response is None:
                continue
            observed = effects.probe_runtime_node(
                node_id="router",
                expected_image_reference=ROUTER_IMAGE,
                labelled=True,
                attach_runtime_network=True,
            )
            body = observed["response"]
            if body != expected_response:
                raise CandidateTopologyError(WORKFLOW_ERROR)
            responses.append(
                {
                    "stage": title,
                    "response": body.decode("ascii"),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "request_origin": observed["request_origin"],
                    "target_image_id": observed["target_image_id"],
                    "target_image_reference": observed["target_image_reference"],
                }
            )
        history_http = workflow.read_activity_http()
        history_mcp = workflow.read_activity_mcp()
    except BaseException as error:
        failure = error

    reason = "success" if failure is None else "error"
    cleanup_failure: BaseException | None = None
    try:
        cleanup = effects.cleanup(reason=reason)
    except BaseException as error:
        cleanup_failure = error
        cleanup = {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": (),
            "foreign_canary_after": (
                admitted["inputs"]["foreign_resource_canary"],
            ),
        }
    if failure is None and cleanup_failure is not None:
        failure = cleanup_failure
        failure_stage = "cleanup"
    if failure is not None:
        report = _failed_report(
            admitted,
            cleanup=cleanup,
            first_failed_stage=failure_stage,
            prepared=active_prepared,
        )
        _attach_report(failure, report)
        raise failure

    assert history_http is not None
    assert history_mcp is not None
    report = _base_report(
        admitted,
        cleanup=cleanup,
        first_failed_stage=None,
        status="passed",
    )
    build = active_prepared["build"]
    attestation: dict[str, Any] = {
        "image_id": build["image_id"],
        "router_descriptor_sha256": ROUTER_DESCRIPTOR_SHA256,
        "router_image": ROUTER_IMAGE,
    }
    if "base_image" in build:
        attestation.update(_attestation(inspection, active_prepared))
    report.update(
        {
            "attestation": attestation,
            "workflow": {
                "transitions": transitions,
                "history_http": history_http,
                "history_mcp": history_mcp,
            },
            "blue_green": {"responses": responses},
            "observations": _observations(active_prepared, cleanup),
            "evidence": [
                {
                    "claim": "candidate-server-attestation",
                    "classification": "candidate-direct",
                    "coordinate": build["image_id"],
                },
                {
                    "claim": "blue-green-public-workflow",
                    "classification": "candidate-direct",
                    "coordinate": workspace_id,
                },
                {
                    "claim": "router-published-digest",
                    "classification": "published-digest",
                    "coordinate": ROUTER_IMAGE,
                },
            ],
            "stages": [
                _stage(name)
                for name in (
                    "admission",
                    "build",
                    "blue-realization",
                    "green-preparation",
                    "green-cutover",
                    "rollback-blue",
                    "final-green",
                    "retire-blue",
                    "teardown",
                    "cleanup",
                )
            ],
        }
    )
    report["report_sha256"] = _report_sha256(report)
    return report


def _legacy_preflight(assembly: dict[str, Any]) -> dict[str, Any]:
    return {
        "inventory": {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": (),
        },
        "collisions": (),
        "foreign_canary_before": (assembly["inputs"]["foreign_resource_canary"],),
    }


def _default_artifact_fetcher(root: Path) -> Callable[..., dict[str, Any]]:
    def fetch(*, url: str, destination: str) -> dict[str, Any]:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(url, target)
        payload = target.read_bytes()
        return {
            "url": url,
            "path": destination,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    return fetch


def materialize_candidate_wheels(
    *,
    candidate_commit: str,
    candidate_tree: str,
    staging_root: str,
) -> dict[str, dict[str, Any]]:
    candidate_pin = "2ae7f6fe1d34cad943e2e16a2cf93903d840ddc1"
    candidate_tree_pin = "c950b2f1769298949fa0d9e584be7d6d4008d500"
    if (
        candidate_commit != candidate_pin
        or candidate_tree != candidate_tree_pin
    ):
        raise _fixed_assembly_error()
    root = Path(staging_root)
    sources = {
        "dist/control_plane_kit_core.whl": "control-plane-kit-core",
        "dist/control_plane_kit_operations.whl": "control-plane-kit-operations",
    }
    observations: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as wheelhouse:
        wheelhouse_root = Path(wheelhouse)
        for relative_path, subdirectory in sources.items():
            archive = (
                "https://github.com/OpenJ92/control-plane-kit/archive/"
                f"{candidate_pin}.tar.gz#subdirectory={subdirectory}"
            )
            subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheelhouse_root),
                    archive,
                ),
                check=True,
            )
            wheels = tuple(wheelhouse_root.glob("*.whl"))
            if len(wheels) != 1:
                raise _fixed_assembly_error()
            payload = wheels[0].read_bytes()
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".part")
            temporary.write_bytes(payload)
            if temporary.stat().st_size != len(payload):
                raise _fixed_assembly_error()
            os.replace(temporary, destination)
            observations[relative_path] = {
                "repository": "OpenJ92/control-plane-kit",
                "commit": candidate_commit,
                "tree": candidate_tree,
                "subdirectory": subdirectory,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "size": destination.stat().st_size,
            }
            wheels[0].unlink()
    return observations


def _measured_server_source(source_root: str) -> dict[str, Any]:
    root = Path(source_root)
    mounted_coordinate = Path("/candidate/source-coordinate.json")
    coordinate_path = (
        mounted_coordinate
        if mounted_coordinate.is_file()
        else root / "source-coordinate.json"
    )
    if coordinate_path.is_file():
        coordinate = _load_json(coordinate_path)
    else:
        commit = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ("git", "-C", str(root), "status", "--porcelain"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        coordinate = {
            "repository": "OpenJ92/control-plane-kit-servers",
            "commit": commit,
            "tree": tree,
            "clean": status == "",
        }
    if (
        not _exact_keys(coordinate, {"repository", "commit", "tree", "clean"})
        or coordinate["repository"] != "OpenJ92/control-plane-kit-servers"
        or not _hex_digest(coordinate["commit"], 40)
        or not _hex_digest(coordinate["tree"], 40)
        or coordinate["clean"] is not True
    ):
        raise _fixed_assembly_error()
    return coordinate


def _physical_artifact(
    root: Path,
    relative_path: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    path = root / relative_path
    if not path.is_file():
        raise _fixed_assembly_error()
    payload = path.read_bytes()
    measured = {
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    if observation.get("size") != measured["size"] or observation.get(
        "sha256"
    ) != measured["sha256"]:
        raise _fixed_assembly_error()
    return measured


def _admit_rfc8785_artifact(
    artifact_fetcher: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    observation = artifact_fetcher(
        url=RFC8785_WHEEL_URL,
        destination=RFC8785_WHEEL_PATH,
    )
    if observation != {
        "url": RFC8785_WHEEL_URL,
        "path": RFC8785_WHEEL_PATH,
        "size": RFC8785_WHEEL_SIZE,
        "sha256": RFC8785_WHEEL_SHA256,
    }:
        raise _fixed_assembly_error()
    return observation


def build_candidate_package_image(
    assembly: dict[str, Any],
    inspection: dict[str, Any],
    effects: Any,
    artifact_fetcher: Callable[..., dict[str, Any]] | None,
    candidate_base_image: str,
    candidate_image_tag: str | None,
) -> dict[str, Any]:
    if artifact_fetcher is not None:
        _admit_rfc8785_artifact(artifact_fetcher)
    preflight_method = getattr(effects, "preflight_inventory", None)
    preflight = (
        preflight_method(assembly)
        if callable(preflight_method)
        else _legacy_preflight(assembly)
    )
    if preflight.get("collisions"):
        error = _fixed_assembly_error()
        setattr(error, "candidate_stage", "admission")
        raise error
    build = effects.build_candidate_image(
        assembly,
        base_image=candidate_base_image,
        candidate_image_tag=candidate_image_tag,
    )
    return {
        "admitted": assembly,
        "inspection": inspection,
        "preflight": preflight,
        "build": build,
        "server": None,
        "server_inspection": None,
    }


def _prepare_candidate(
    admitted: dict[str, Any],
    inspection: dict[str, Any],
    effects: Any,
) -> dict[str, Any]:
    base_image = inspection["images"]["cpk_server_base"]
    prepared = build_candidate_package_image(
        admitted,
        inspection,
        effects,
        None,
        base_image,
        None,
    )
    build = prepared["build"]
    start_method = getattr(effects, "start_candidate_server", None)
    inspect_method = getattr(effects, "inspect_candidate_server", None)
    server = None
    server_inspection = None
    if callable(start_method) and callable(inspect_method):
        server = effects.start_candidate_server(build["image_id"])
        server_inspection = effects.inspect_candidate_server(server["container_id"])
    prepared["server"] = server
    prepared["server_inspection"] = server_inspection
    return prepared


def _observations(
    prepared: dict[str, Any],
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    inventory = prepared["preflight"].get("inventory", {})
    public_cleanup = _public_cleanup(cleanup)
    return {
        "pre_inventory": _public_inventory(
            cleanup.get("pre_inventory", inventory)
        ),
        "post_inventory": _public_inventory(
            cleanup.get("post_inventory", inventory)
        ),
        "postgres_relations": deepcopy(public_cleanup["postgres_relations"]),
    }


def _attestation(
    inspection: dict[str, Any],
    prepared: dict[str, Any],
) -> dict[str, Any]:
    build = prepared["build"]
    server = prepared["server"]
    observed = prepared["server_inspection"]
    record_paths = (
        observed["record_paths"]
        if observed is not None
        else build.get("record_paths", ())
    )
    module_paths = (
        observed["module_paths"]
        if observed is not None
        else build.get("module_paths", ())
    )
    result: dict[str, Any] = {
        "production_dockerfile_sha256": inspection["files"]["products/cpk_server/Dockerfile"],
        "acceptance_overlay_sha256": inspection["files"]["acceptance/candidate_topology/Dockerfile"],
        "wheel_sha256": {
            "control-plane-kit-core": inspection["files"]["dist/control_plane_kit_core.whl"],
            "control-plane-kit-operations": inspection["files"]["dist/control_plane_kit_operations.whl"],
            "rfc8785": inspection["files"][RFC8785_WHEEL_PATH],
        },
        "base_image": build["base_image"],
        "image_id": build["image_id"],
        "record_paths": record_paths,
        "module_paths": module_paths,
    }
    if server is not None and observed is not None:
        result.update(
            {
                "server_container_id": server["container_id"],
                "server_container_image_id": observed["image_id"],
                "record_origins": observed["record_origins"],
                "module_origins": observed["module_origins"],
            }
        )
    return result


def _base_report(
    assembly: dict[str, Any],
    *,
    cleanup: dict[str, Any],
    first_failed_stage: str | None,
    status: str,
) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "assembly": assembly,
        "assembly_sha256": _canonical_sha256(assembly),
        "external_coordinates": {
            "server_baseline_commit": SERVER_BASELINE_COMMIT,
            "server_baseline_tree": SERVER_BASELINE_TREE,
            "snapshot_manifest_sha256": SNAPSHOT_MANIFEST_SHA256,
            "postgres_image": POSTGRES_IMAGE,
        },
        "status": status,
        "first_failed_stage": first_failed_stage,
        "cleanup": _public_cleanup(cleanup),
        "redaction_verified": True,
        "protected_material_retained": False,
    }


def _failed_report(
    assembly: dict[str, Any],
    *,
    cleanup: dict[str, Any],
    first_failed_stage: str,
    prepared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = _base_report(
        assembly,
        cleanup=cleanup,
        first_failed_stage=first_failed_stage,
        status="failed",
    )
    if prepared is not None:
        report["observations"] = _observations(prepared, cleanup)
    report["stages"] = []
    report["report_sha256"] = _report_sha256(report)
    return report


def _attach_report(error: BaseException, report: dict[str, Any]) -> None:
    setattr(error, "candidate_terminal_report", report)


def _run_history_id(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", value) is not None


def _run_history_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise _RunHistoryJsonError("json-invalid") from None
    if len(encoded) > 262144:
        raise _RunHistoryJsonError("json-over-bound")
    return encoded


def _reject_run_history(
    location: str,
    reason: str,
    transition: str,
    *,
    outcome: str = "rejected",
    event_ordinal: int | None = None,
) -> None:
    raise _RunHistoryRejection(
        outcome=outcome,
        location=location,
        reason=reason,
        transition=transition,
        event_ordinal=event_ordinal,
    )


def _run_history_call(
    location: str,
    transition: str,
    callback: Callable[[], Any],
) -> Any:
    try:
        return callback()
    except _RunHistoryRejection:
        raise
    except Exception:
        _reject_run_history(location, "unknown", transition, outcome="unknown")


def _run_history_pointer(
    http: Any,
    mcp: Any,
    graph_id: str,
    version: int,
    *,
    location: str,
    transition: str,
) -> dict[str, Any]:
    required = {
        "pointer", "assigned", "graph_id", "authored_graph_id",
        "realized_projection_id", "version", "graph_name",
    }
    optional = {"graph_descriptor", "operator_graph"}
    if (
        type(http) is not dict
        or type(mcp) is not dict
        or not required <= set(http) <= required | optional
        or not required <= set(mcp) <= required | optional
    ):
        _reject_run_history(location, "pointer-shape", transition)
    try:
        http_json = _run_history_json(http)
        mcp_json = _run_history_json(mcp)
    except _RunHistoryJsonError as error:
        _reject_run_history(location, error.reason, transition)
    if http_json != mcp_json:
        _reject_run_history(location, "http-mcp-mismatch", transition)
    if http["pointer"] != "current":
        _reject_run_history(location, "not-current", transition)
    if http["assigned"] is not True:
        _reject_run_history(location, "unassigned", transition)
    if not _run_history_id(graph_id):
        _reject_run_history(location, "expected-graph-invalid", transition)
    if http["graph_id"] != graph_id:
        _reject_run_history(location, "graph-mismatch", transition)
    if http["authored_graph_id"] != graph_id:
        _reject_run_history(location, "authored-mismatch", transition)
    if not _run_history_id(http["realized_projection_id"]):
        _reject_run_history(location, "projection-invalid", transition)
    if type(http["version"]) is not int or http["version"] != version:
        _reject_run_history(location, "version-mismatch", transition)
    if type(http["graph_name"]) is not str or not 0 < len(http["graph_name"]) <= 256:
        _reject_run_history(location, "name-invalid", transition)
    if "graph_descriptor" in http and type(http["graph_descriptor"]) is not dict:
        _reject_run_history(location, "descriptor-not-object", transition)
    if "operator_graph" in http and type(http["operator_graph"]) is not dict:
        _reject_run_history(location, "operator-not-object", transition)
    return http


def _validate_candidate_run_page(
    page: Any,
    *,
    workspace_id: str,
    plan_id: str,
    run_id: str,
    activity_ids: tuple[str, ...],
    predecessor: dict[str, Any],
    successor: dict[str, Any],
    revision: int,
    event_ids: set[str],
    transition: str,
) -> None:
    if not _exact_keys(page, {"workspace_id", "kind", "limit", "items", "next_cursor"}):
        _reject_run_history("page", "page-shape", transition)
    if page["workspace_id"] != workspace_id:
        _reject_run_history("page", "workspace-mismatch", transition)
    if page["kind"] != "run-events":
        _reject_run_history("page", "kind-mismatch", transition)
    if type(page["limit"]) is not int or page["limit"] != 100:
        _reject_run_history("page", "limit-mismatch", transition)
    if type(page["items"]) is not list:
        _reject_run_history("page", "items-not-list", transition)
    if page["next_cursor"] is not None:
        _reject_run_history("page", "cursor-present", transition)
    expected = [("run_opened", None), ("run_started", None)]
    for activity_id in activity_ids:
        expected.extend((("step_started", activity_id), ("step_succeeded", activity_id)))
    expected.extend((("run_succeeded", None), ("current_graph_advanced", None)))
    if len(page["items"]) != len(expected):
        _reject_run_history("page", "event-count", transition)
    for ordinal, (event, (kind, activity_id)) in enumerate(zip(page["items"], expected), 1):
        if not _exact_keys(event, {
            "event_id", "run_id", "ordinal", "event_type",
            "occurred_at", "activity_id", "payload", "failure",
        }):
            _reject_run_history("event", "event-shape", transition, event_ordinal=ordinal)
        if not _run_history_id(event["event_id"]):
            _reject_run_history("event", "event-id-invalid", transition, event_ordinal=ordinal)
        if event["event_id"] in event_ids:
            _reject_run_history("event", "event-id-duplicate", transition, event_ordinal=ordinal)
        if event["run_id"] != run_id:
            _reject_run_history("event", "run-mismatch", transition, event_ordinal=ordinal)
        if type(event["ordinal"]) is not int or event["ordinal"] != ordinal:
            _reject_run_history("event", "ordinal-mismatch", transition, event_ordinal=ordinal)
        if event["event_type"] != kind:
            _reject_run_history("event", "kind-mismatch", transition, event_ordinal=ordinal)
        if event["activity_id"] != activity_id:
            _reject_run_history("event", "activity-mismatch", transition, event_ordinal=ordinal)
        if event["failure"] is not None:
            _reject_run_history("event", "failure-present", transition, event_ordinal=ordinal)
        if type(event["occurred_at"]) is not str or len(event["occurred_at"]) > 64:
            _reject_run_history("event", "timestamp-shape", transition, event_ordinal=ordinal)
        try:
            occurred_at = datetime.fromisoformat(event["occurred_at"])
        except ValueError:
            _reject_run_history("event", "timestamp-invalid", transition, event_ordinal=ordinal)
        if occurred_at.utcoffset() is None:
            _reject_run_history("event", "timestamp-naive", transition, event_ordinal=ordinal)
        payload = event["payload"]
        if kind == "run_opened":
            if not _exact_keys(payload, {"attempt"}):
                _reject_run_history("payload.run-opened", "payload-shape", transition, event_ordinal=ordinal)
            if type(payload["attempt"]) is not int or payload["attempt"] != 1:
                _reject_run_history("payload.run-opened", "attempt-mismatch", transition, event_ordinal=ordinal)
        elif kind == "run_started":
            if not _exact_keys(payload, set()):
                _reject_run_history("payload.run-started", "payload-shape", transition, event_ordinal=ordinal)
        elif kind in {"step_started", "step_succeeded"}:
            if not _exact_keys(payload, {"effect_attempt"}):
                _reject_run_history("payload.step", "payload-shape", transition, event_ordinal=ordinal)
            attempt = payload["effect_attempt"]
            if not _exact_keys(attempt, {"attempt", "state_fingerprint"}):
                _reject_run_history("payload.step", "attempt-shape", transition, event_ordinal=ordinal)
            if type(attempt["attempt"]) is not int or attempt["attempt"] != 1:
                _reject_run_history("payload.step", "attempt-mismatch", transition, event_ordinal=ordinal)
            if not _hex_digest(attempt["state_fingerprint"], 64):
                _reject_run_history("payload.step", "fingerprint-invalid", transition, event_ordinal=ordinal)
        elif kind == "run_succeeded":
            if not _exact_keys(payload, {"result"}):
                _reject_run_history("payload.run-succeeded", "payload-shape", transition, event_ordinal=ordinal)
            if payload["result"] != "all-activities-succeeded":
                _reject_run_history("payload.run-succeeded", "result-mismatch", transition, event_ordinal=ordinal)
        else:
            # Retain the public digest and fingerprints, without claiming to rederive them.
            coordinates = {
                "workspace_id": workspace_id, "plan_id": plan_id, "run_id": run_id,
                "from_authored_graph_id": predecessor["authored_graph_id"],
                "from_realized_projection_id": predecessor["realized_projection_id"],
                "to_authored_graph_id": successor["authored_graph_id"],
                "to_realized_projection_id": successor["realized_projection_id"],
                "desired_graph_revision": revision,
            }
            if not _exact_keys(payload, set(coordinates) | {"to_realized_projection_digest"}):
                _reject_run_history("payload.advance", "payload-shape", transition, event_ordinal=ordinal)
            reasons = {
                "workspace_id": "workspace-mismatch",
                "plan_id": "plan-mismatch",
                "run_id": "run-mismatch",
                "from_authored_graph_id": "from-authored-mismatch",
                "from_realized_projection_id": "from-realized-mismatch",
                "to_authored_graph_id": "to-authored-mismatch",
                "to_realized_projection_id": "to-realized-mismatch",
                "desired_graph_revision": "revision-mismatch",
            }
            for key, value in coordinates.items():
                if payload[key] != value:
                    _reject_run_history("payload.advance", reasons[key], transition, event_ordinal=ordinal)
            if type(payload["desired_graph_revision"]) is not int:
                _reject_run_history("payload.advance", "revision-invalid", transition, event_ordinal=ordinal)
            if not _hex_digest(payload["to_realized_projection_digest"], 64):
                _reject_run_history("payload.advance", "digest-invalid", transition, event_ordinal=ordinal)
        event_ids.add(event["event_id"])


def _capture_candidate_run_history(
    workflow: Any,
    *,
    workspace_id: str,
    current_graph_id: str,
    hello_graph: DeploymentGraph,
    empty_graph: DeploymentGraph,
    hello: dict[str, Any],
    empty: dict[str, Any],
    run_history_rejection_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    history: dict[str, Any] | None = None
    rejection: _RunHistoryRejection | None = None
    active_transition = "context"
    active_location = "unknown"
    try:
        if not _run_history_id(workspace_id):
            _reject_run_history("input.workspace", "identity-invalid", "context")
        for key in ("plan_id", "run_id", "desired_graph_id", "advanced_graph_id"):
            location = "input." + key.replace("_", "-")
            if not all(_run_history_id(row[key]) for row in (hello, empty)):
                _reject_run_history(location, "identity-invalid", "context")
            if hello[key] == empty[key]:
                _reject_run_history(location, "identity-reused", "context")
        history = {}
        event_ids: set[str] = set()
        previous = None
        # Only this fixed scenario has the identity projection used by these plans.
        for revision, (title, transition, before, after, operations) in enumerate((
            ("hello", hello, empty_graph, hello_graph, ("StartRuntime", "StartNode", "WaitForHealthy")),
            ("empty", empty, hello_graph, empty_graph, ("StopNode", "RemoveNodeResource", "StopRuntime", "RemoveRuntimeResource")),
        ), 1):
            active_transition = title
            active_location = "transition.advance"
            if transition["desired_graph_id"] != transition["advanced_graph_id"]:
                _reject_run_history("transition.advance", "desired-advanced-mismatch", title)
            predecessor = _run_history_pointer(
                transition["predecessor_http"], transition["predecessor_mcp"], current_graph_id, revision,
                location="pointer.predecessor", transition=title,
            )
            successor = _run_history_pointer(
                transition["successor_http"], transition["successor_mcp"], transition["desired_graph_id"], revision + 1,
                location="pointer.successor", transition=title,
            )
            active_location = "lineage"
            if previous is not None and _run_history_json(previous) != _run_history_json(predecessor):
                _reject_run_history("lineage", "predecessor-discontinuity", title)
            active_location = "plan.before"
            valid_before = _run_history_call("plan.before", title, lambda: validate_graph(before))
            active_location = "plan.after"
            valid_after = _run_history_call("plan.after", title, lambda: validate_graph(after))
            active_location = "plan.diff"
            difference = _run_history_call("plan.diff", title, lambda: diff_graphs(valid_before, valid_after))
            active_location = "plan.compile"
            plan = _run_history_call("plan.compile", title, lambda: compile_activity_plan(difference))
            active_location = "plan.operations"
            if tuple(type(item.operation).__name__ for item in plan.activities) != operations:
                _reject_run_history("plan.operations", "operation-sequence", title)
            active_location = "plan.activities"
            activity_ids = _run_history_call(
                "plan.activities", title,
                lambda: tuple(item.activity_id.value for item in plan.activities),
            )
            active_location = "events.http"
            try:
                http = workflow.read_run_events_http(transition["run_id"], limit=100)
            except Exception:
                _reject_run_history("events.http", "read-unavailable", title, outcome="unavailable")
            active_location = "events.mcp"
            try:
                mcp = workflow.read_run_events_mcp(transition["run_id"], limit=100)
            except Exception:
                _reject_run_history("events.mcp", "read-unavailable", title, outcome="unavailable")
            active_location = "events.parity"
            try:
                parity = _run_history_json(http) == _run_history_json(mcp)
            except _RunHistoryJsonError as error:
                _reject_run_history("events.parity", error.reason, title)
            if not parity:
                _reject_run_history("events.parity", "http-mcp-mismatch", title)
            active_location = "page"
            _validate_candidate_run_page(
                http, workspace_id=workspace_id, plan_id=transition["plan_id"], run_id=transition["run_id"],
                activity_ids=activity_ids, predecessor=predecessor, successor=successor,
                revision=revision, event_ids=event_ids, transition=title,
            )
            active_location = "history.copy"
            history[title] = _run_history_call(
                "history.copy",
                title,
                lambda: {
                    "plan_id": transition["plan_id"],
                    "run_id": transition["run_id"],
                    "http": deepcopy(http),
                    "mcp": deepcopy(mcp),
                },
            )
            current_graph_id = transition["advanced_graph_id"]
            previous = successor
    except _RunHistoryRejection as error:
        rejection = error
        history = None
    except Exception:
        rejection = _RunHistoryRejection(
            outcome="unknown",
            location=active_location,
            reason="unknown",
            transition=active_transition,
        )
        history = None
    # Raise outside the handler so public failure evidence retains no raw context.
    if history is None:
        assert rejection is not None
        if run_history_rejection_sink is not None:
            try:
                run_history_rejection_sink(_run_history_rejection_diagnostic(
                    outcome=rejection.outcome,
                    location=rejection.location,
                    reason=rejection.reason,
                    transition=rejection.transition,
                    event_ordinal=rejection.event_ordinal,
                ))
            except BaseException:
                pass
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return history


def run_candidate_topology(
    assembly: dict[str, Any],
    *,
    inspection: dict[str, Any],
    workflow: Any,
    effects: Any,
    hello_graph: Any = None,
    empty_graph: Any = None,
    current_graph_id: str = "graph-predecessor",
    prepared: dict[str, Any] | None = None,
    run_history_rejection_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    admitted = admit_candidate_assembly(assembly, inspection)
    active_prepared = (
        _prepare_candidate(admitted, inspection, effects)
        if prepared is None
        else prepared
    )
    cleanup: dict[str, Any] | None = None
    failure: BaseException | None = None
    failure_stage = "workflow"
    hello = None
    empty = None
    history_http = None
    history_mcp = None
    run_history = None
    probe_result: Any = None

    try:
        hello = _public_transition(
            workflow,
            title="hello",
            graph=hello_graph,
            current_graph_id=current_graph_id,
            expected_desired_graph_id=None,
        )
        failure_stage = "probe"
        probe_result = effects.probe_hello(
            labelled=True,
            attach_runtime_network=True,
        )
        effects.remove_probe()
        body = (
            probe_result["response"]
            if type(probe_result) is dict
            else probe_result
        )
        if body != HELLO_RESPONSE:
            failure = CandidateTopologyError(WORKFLOW_ERROR)
        else:
            failure_stage = "workflow"
            empty = _public_transition(
                workflow,
                title="empty",
                graph=empty_graph,
                current_graph_id=hello["advanced_graph_id"],
                expected_desired_graph_id=hello["desired_graph_id"],
            )
            history_http = workflow.read_activity_http()
            history_mcp = workflow.read_activity_mcp()
            run_history = _capture_candidate_run_history(
                workflow,
                workspace_id=admitted["inputs"]["workspace_id"],
                current_graph_id=current_graph_id,
                hello_graph=hello_graph,
                empty_graph=empty_graph,
                hello=hello,
                empty=empty,
                run_history_rejection_sink=run_history_rejection_sink,
            )
    except BaseException as error:
        failure = error

    reason = "success"
    if failure is not None:
        if type(failure) is KeyboardInterrupt:
            reason = "abort"
        elif type(failure) is TimeoutError:
            reason = "timeout"
        else:
            reason = "error"
    cleanup_failure: BaseException | None = None
    try:
        cleanup = effects.cleanup(reason=reason)
    except BaseException as error:
        cleanup_failure = error
        cleanup = {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": (),
            "foreign_canary_after": (
                admitted["inputs"]["foreign_resource_canary"],
            ),
        }

    if failure is None and cleanup_failure is not None:
        failure = cleanup_failure
        failure_stage = "cleanup"

    if failure is not None:
        selected_error: BaseException = failure
        if type(failure) is TimeoutError:
            selected_error = CandidateTopologyError(WORKFLOW_ERROR)
        report = _failed_report(
            admitted,
            cleanup=cleanup,
            first_failed_stage=failure_stage,
            prepared=active_prepared,
        )
        _attach_report(selected_error, report)
        raise selected_error

    assert hello is not None
    assert empty is not None
    body = (
        probe_result["response"]
        if type(probe_result) is dict
        else probe_result
    )
    report = _base_report(
        admitted,
        cleanup=cleanup,
        first_failed_stage=None,
        status="passed",
    )
    report.update(
        {
            "attestation": _attestation(inspection, active_prepared),
            "workflow": {
                "predecessor_http": hello["predecessor_http"],
                "predecessor_mcp": hello["predecessor_mcp"],
                "successor_http": hello["successor_http"],
                "successor_mcp": hello["successor_mcp"],
                "empty_predecessor_http": empty["predecessor_http"],
                "empty_predecessor_mcp": empty["predecessor_mcp"],
                "empty_http": empty["successor_http"],
                "empty_mcp": empty["successor_mcp"],
                "history_http": history_http,
                "history_mcp": history_mcp,
                "run_history": run_history,
            },
            "hello": {
                "response": body.decode("ascii"),
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "controller_network_repair": False,
                "server_network_repair": False,
            },
            "observations": _observations(active_prepared, cleanup),
            "evidence": [
                {
                    "claim": claim,
                    "classification": classification,
                    "coordinate": coordinate,
                }
                for claim, classification, coordinate in (
                    (
                        "candidate-server-attestation",
                        "candidate-direct",
                        active_prepared["build"]["image_id"],
                    ),
                    (
                        "public-workflow",
                        "candidate-direct",
                        admitted["inputs"]["workspace_id"],
                    ),
                    (
                        "predecessor-readback",
                        "candidate-direct",
                        hello["predecessor_http"]["graph_id"],
                    ),
                    (
                        "hello-response",
                        "candidate-direct",
                        hashlib.sha256(body).hexdigest(),
                    ),
                    (
                        "empty-successor",
                        "candidate-direct",
                        empty["successor_http"]["graph_id"],
                    ),
                    ("residue", "candidate-direct", "bounded-labelled-cleanup"),
                    (
                        "external-package-coordinate",
                        "supporting",
                        admitted["dependencies"],
                    ),
                    (
                        "hello-image",
                        "published-digest",
                        admitted["products"]["hello"]["reference"],
                    ),
                    ("postgres-image", "published-digest", POSTGRES_IMAGE),
                )
            ],
            "stages": [
                _stage(name)
                for name in (
                    "admission",
                    "build",
                    "workflow",
                    "hello",
                    "empty-successor",
                    "cleanup",
                )
            ],
        }
    )
    if type(probe_result) is dict:
        report["hello"].update(
            {
                "container_id": probe_result["container_id"],
                "request_origin": probe_result["request_origin"],
                "target_image_id": probe_result["target_image_id"],
                "target_image_reference": probe_result[
                    "target_image_reference"
                ],
            }
        )
    report["report_sha256"] = _report_sha256(report)
    return report


class DockerCandidateEffects:
    def __init__(
        self,
        *,
        root: Path,
        labels: dict[str, str],
        evidence_id: str,
        candidate_image_tag: str | None = None,
        host_address: str = "127.0.0.1",
        ghcr_pull_credential: str | None = None,
        ownership_ledger: Path | None = None,
        interrupt_after: str | None = None,
    ) -> None:
        import docker

        self._root = root
        self._labels = labels
        self._evidence_id = evidence_id
        self._candidate_image_tag = candidate_image_tag
        self._host_address = host_address
        self._ghcr_pull_credential = ghcr_pull_credential
        self._ownership_ledger = ownership_ledger
        self._interrupt_after = interrupt_after
        self._client = docker.from_env()
        self._probe = None
        self._server = None
        self._postgres = None
        self._network = None
        self._image = None
        self._pre_inventory: dict[str, Any] | None = None
        self._foreign_canary = ""

    def _name(self, role: str) -> str:
        return candidate_resource_name(self._evidence_id, role)

    def _record(self, kind: str, role: str, observed_id: str) -> None:
        if self._ownership_ledger is not None:
            record_candidate_resource(
                self._ownership_ledger,
                kind=kind,
                role=role,
                observed_id=observed_id,
            )

    def _record_created(self, kind: str, role: str, resource: Any) -> None:
        if self._ownership_ledger is not None:
            self._record(kind, role, resource.id)

    def _inventory(self) -> dict[str, tuple[str, ...]]:
        return {
            "containers": tuple(sorted(container.name for container in self._client.containers.list(all=True))),
            "networks": tuple(sorted(network.name for network in self._client.networks.list())),
            "volumes": tuple(sorted(volume.name for volume in self._client.volumes.list())),
            "images": tuple(sorted(image.id for image in self._client.images.list())),
            "postgres_relations": (),
        }

    def preflight_inventory(self, assembly: dict[str, Any]) -> dict[str, Any]:
        inventory = self._inventory()
        owned_names = {
            self._name("server"),
            self._name("probe"),
            self._name("postgres"),
            self._name("runtime"),
        }
        collisions = [
            (kind, value)
            for kind, values in (
                ("container", inventory["containers"]),
                ("network", inventory["networks"]),
            )
            for value in values
            if value in owned_names
        ]
        candidate_tag = (
            self._candidate_image_tag
            or self._name("candidate") + ":latest"
        )
        if any(
            candidate_tag in getattr(image, "tags", ())
            for image in self._client.images.list()
        ):
            collisions.append(("image", candidate_tag))
        self._pre_inventory = inventory
        self._foreign_canary = assembly["inputs"]["foreign_resource_canary"]
        return {
            "inventory": deepcopy(inventory),
            "collisions": tuple(collisions),
            "foreign_canary_before": (self._foreign_canary,),
        }

    def build_candidate_image(
        self,
        assembly: dict[str, Any],
        *,
        base_image: str,
        candidate_image_tag: str | None = None,
    ) -> dict[str, Any]:
        candidate_image_tag = (
            candidate_image_tag
            or self._candidate_image_tag
            or self._name("candidate") + ":latest"
        )
        image, _ = self._client.images.build(
            path=str(self._root),
            dockerfile="acceptance/candidate_topology/Dockerfile",
            buildargs={"CPK_SERVER_BASE_IMAGE": base_image},
            labels=self._labels,
            tag=candidate_image_tag,
            rm=True,
        )
        self._image = image
        self._record_created("image", "candidate", image)
        if self._interrupt_after == "candidate-image-built":
            assert self._ownership_ledger is not None
            interrupt_candidate_run(self._ownership_ledger)
        return {
            "base_image": base_image,
            "image_id": image.id,
            "image_tag": candidate_image_tag,
        }

    def observe_candidate_image_tag(self, candidate_image_tag: str) -> bool:
        return any(
            candidate_image_tag in getattr(image, "tags", ())
            for image in self._client.images.list()
        )

    def resolve_image_id(self, reference: str) -> str:
        return self._client.images.get(reference).id

    def start_candidate_server(self, built_image_id: str) -> dict[str, str]:
        docker_socket_gid = _docker_socket_group()
        self._network = self._client.networks.create(
            self._name("runtime"),
            labels=self._labels,
        )
        self._record_created("network", "runtime", self._network)
        self._postgres = self._client.containers.run(
            POSTGRES_IMAGE,
            detach=True,
            environment={
                "POSTGRES_DB": POSTGRES_DB,
                "POSTGRES_USER": POSTGRES_USER,
                "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
            },
            labels=self._labels,
            name=self._name("postgres"),
            network=self._network.name,
            tmpfs={"/var/lib/postgresql/data": "rw"},
        )
        self._record_created("container", "postgres", self._postgres)
        postgres_ready = False
        for attempt in range(POSTGRES_READY_ATTEMPTS):
            readiness = self._postgres.exec_run(
                ["pg_isready", "-U", POSTGRES_USER, "-d", POSTGRES_DB]
            )
            if readiness.exit_code == 0:
                postgres_ready = True
                break
            if attempt + 1 < POSTGRES_READY_ATTEMPTS:
                _sleep(POSTGRES_READY_RETRY_SECONDS)
        if not postgres_ready:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        environment = _candidate_server_environment(
            self._name("postgres"),
            ghcr_pull_credential=self._ghcr_pull_credential,
        )
        candidate_server = self._client.containers.run(
            built_image_id,
            detach=True,
            environment=environment,
            group_add=(docker_socket_gid,),
            labels=self._labels,
            name=self._name("server"),
            network=self._network.name,
            ports={"8080/tcp": ("127.0.0.1", 0)},
            volumes={
                DOCKER_SOCKET: {
                    "bind": DOCKER_SOCKET,
                    "mode": "rw",
                }
            },
        )
        self._server = candidate_server
        self._record_created("container", "server", candidate_server)
        candidate_server.reload()
        bindings = candidate_server.attrs["NetworkSettings"]["Ports"]["8080/tcp"]
        host_port = bindings[0]["HostPort"]
        return {
            "container_id": candidate_server.id,
            "image_id": built_image_id,
            "base_url": f"http://{self._host_address}:{host_port}",
        }

    def inspect_candidate_server(self, container_id: str) -> dict[str, Any]:
        if self._server is None or self._server.id != container_id:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        inspection_program = (
            "import importlib.metadata as m,json;"
            "names=('control-plane-kit-core','control-plane-kit-operations','rfc8785');"
            "records=[str(m.distribution(n)._path/'RECORD') for n in names];"
            "modules=[__import__(n.replace('-','_')).__file__ for n in names];"
            "print(json.dumps({'record_paths':records,'module_paths':modules}))"
        )
        result = self._server.exec_run(["python", "-c", inspection_program])
        if result.exit_code != 0:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        observed = json.loads(result.output.decode("utf-8"))
        return {
            "container_id": container_id,
            "image_id": self._server.image.id,
            "record_paths": tuple(observed["record_paths"]),
            "module_paths": tuple(observed["module_paths"]),
            "record_origins": {
                path: self._server.image.id for path in observed["record_paths"]
            },
            "module_origins": {
                path: self._server.image.id for path in observed["module_paths"]
            },
        }

    def observe_candidate_startup(self, container_id: str) -> dict[str, Any]:
        if self._server is None or self._server.id != container_id:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        self._server.reload()
        state = self._server.attrs.get("State", {})
        return _project_candidate_startup_state(
            {
                "status": state.get("Status"),
                "exit_code": state.get("ExitCode"),
            }
        )

    def probe_runtime_node(
        self,
        *,
        node_id: str,
        expected_image_reference: str,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        if self._server is None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        runtime_containers = [
            container
            for container in self._client.containers.list(all=True)
            if container.attrs.get("Config", {}).get("Labels", {}).get(
                "org.openj92.cpk.workspace"
            )
            == EXPECTED_ASSEMBLY["inputs"]["workspace_id"]
            and container.attrs.get("Config", {}).get("Labels", {}).get(
                "org.openj92.cpk.node"
            )
            == node_id
        ]
        if len(runtime_containers) != 1:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        provider = runtime_containers[0]
        provider_networks = tuple(
            provider.attrs.get("NetworkSettings", {}).get("Networks", {})
        )
        if len(provider_networks) != 1:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        provider_network = next(
            (
                network
                for network in self._client.networks.list()
                if network.name == provider_networks[0]
            ),
            None,
        )
        if provider_network is None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        provider_config = provider.attrs.get("Config", {})
        provider_image_reference = provider_config.get("Image")
        provider_repo_digests = tuple(
            provider.image.attrs.get("RepoDigests", ())
        )
        if (
            provider_image_reference != expected_image_reference
            or provider_repo_digests != (expected_image_reference,)
        ):
            raise CandidateTopologyError(WORKFLOW_ERROR)
        labels = self._labels if labelled else {}
        probe_image = (
            "docker.io/curlimages/curl@sha256:"
            "7c12af72ceb38b7432ab85e1a265cff6ae58e06f95539d539b654f2cfa64bb13"
        )
        if self._probe is None:
            probe_container = self._client.containers.run(
                probe_image,
                ["sleep", "900"],
                labels=labels,
                detach=True,
                network=provider_network.name,
                name=self._name("probe"),
            )
            self._probe = probe_container
            self._record_created("container", "probe", probe_container)
        else:
            probe_container = self._probe
            probe_container.reload()
            probe_networks = tuple(
                probe_container.attrs.get("NetworkSettings", {}).get(
                    "Networks", {}
                )
            )
            if (
                probe_container.name != self._name("probe")
                or probe_container.attrs.get("State", {}).get("Status")
                != "running"
                or probe_container.attrs.get("Config", {}).get("Image")
                != probe_image
                or probe_networks != (provider_network.name,)
            ):
                raise CandidateTopologyError(WORKFLOW_ERROR)
        if not attach_runtime_network:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        result = probe_container.exec_run(
            ["curl", "--fail", "--silent", f"http://{provider.name}:8000/"]
        )
        if result.exit_code != 0:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return {
            "response": result.output,
            "container_id": probe_container.id,
            "request_origin": "inside-probe",
            "target_image_id": provider.image.id,
            "target_image_reference": provider_image_reference,
        }

    def probe_hello(
        self,
        *,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        return self.probe_runtime_node(
            node_id="hello",
            expected_image_reference=EXPECTED_ASSEMBLY["products"]["hello"][
                "reference"
            ],
            labelled=labelled,
            attach_runtime_network=attach_runtime_network,
        )

    def remove_probe(self) -> None:
        if self._probe is not None:
            self._probe.remove(force=True)
            self._probe = None

    def cleanup(self, *, reason: str) -> dict[str, Any]:
        self.remove_probe()
        if self._server is not None:
            self._server.remove(force=True)
            self._server = None
        if self._postgres is not None:
            self._postgres.remove(force=True)
            self._postgres = None
        if self._network is not None:
            self._network.remove()
            self._network = None
        if self._image is not None:
            self._client.images.remove(self._image.id, force=True)
            self._image = None
        post_inventory = self._inventory()
        provider_residue = any(
            container.attrs.get("Config", {}).get("Labels", {}).get(
                "org.openj92.cpk.workspace"
            )
            == EXPECTED_ASSEMBLY["inputs"]["workspace_id"]
            for container in self._client.containers.list(all=True)
        ) or any(
            network.attrs.get("Labels", {}).get("org.openj92.cpk.kind")
            == "runtime-network"
            and network.attrs.get("Labels", {}).get(
                "org.openj92.cpk.workspace"
            )
            == EXPECTED_ASSEMBLY["inputs"]["workspace_id"]
            for network in self._client.networks.list()
        )
        if provider_residue:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": post_inventory["postgres_relations"],
            "foreign_canary_after": (self._foreign_canary,),
            "pre_inventory": deepcopy(self._pre_inventory or {}),
            "post_inventory": post_inventory,
            "ownership_labels": deepcopy(self._labels),
        }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise _fixed_assembly_error()
    return value


def _persist_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _package_build_failure_report(
    *,
    candidate_image_tag_present: bool | None,
) -> dict[str, Any]:
    observations = (
        {"candidate_image_tag_present": candidate_image_tag_present}
        if type(candidate_image_tag_present) is bool
        else {}
    )
    report = {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "first_failed_stage": "build",
        "failure": {
            "code": PACKAGE_BUILD_FAILURE_CODE,
            "message": PACKAGE_BUILD_FAILURE_MESSAGE,
        },
        "observations": observations,
        "redaction_verified": True,
        "protected_material_retained": False,
    }
    report["report_sha256"] = _report_sha256(report)
    return report


def _build_candidate_package_image_with_report(
    assembly: dict[str, Any],
    inspection: dict[str, Any],
    effects: Any,
    artifact_fetcher: Callable[..., dict[str, Any]] | None,
    candidate_base_image: str,
    candidate_image_tag: str,
    report_path: Path,
) -> dict[str, Any]:
    try:
        return build_candidate_package_image(
            assembly,
            inspection,
            effects,
            artifact_fetcher,
            candidate_base_image,
            candidate_image_tag,
        )
    except Exception:
        candidate_image_tag_present = None
        try:
            observed = effects.observe_candidate_image_tag(candidate_image_tag)
            if type(observed) is bool:
                candidate_image_tag_present = observed
        except Exception:
            pass
        try:
            report = _package_build_failure_report(
                candidate_image_tag_present=candidate_image_tag_present,
            )
            _persist_report(report_path, report)
        except Exception:
            pass
        raise


def main(
    argv: list[str] | None = None,
    *,
    workflow_factory: Callable[..., Any] | None = None,
    effects_factory: Callable[..., Any] | None = None,
    artifact_fetcher: Callable[..., dict[str, Any]] | None = None,
    wheel_materializer: Callable[..., dict[str, dict[str, Any]]] | None = None,
    source_coordinate_provider: Callable[..., dict[str, Any]] | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", type=Path, default=Path("candidate-assembly.json"))
    parser.add_argument("--report", type=Path, default=Path("candidate-topology-report.json"))
    parser.add_argument("--inspection", type=Path, default=Path("candidate-inspection.json"))
    parser.add_argument(
        "--project-label",
        default="org.openj92.project=control-plane-kit-servers",
    )
    parser.add_argument(
        "--scenario-label",
        default="org.openj92.cpk.scenario=candidate-topology-1714",
    )
    parser.add_argument(
        "--evidence-id",
        default=os.environ.get("CPK_CANDIDATE_EVIDENCE_ID", "candidate-topology"),
    )
    parser.add_argument(
        "--host-address",
        choices=("127.0.0.1", "host.docker.internal"),
        default=os.environ.get("CPK_CANDIDATE_HOST_ADDRESS", "127.0.0.1"),
    )
    parser.add_argument(
        "--scenario",
        choices=("single-hello", "blue-green"),
        default="single-hello",
    )
    parser.add_argument("--package-image-only", action="store_true")
    parser.add_argument("--candidate-base-image")
    parser.add_argument("--candidate-image-tag")
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--ownership-ledger", type=Path)
    parser.add_argument(
        "--interrupt-after",
        choices=("candidate-image-built",),
    )
    args = parser.parse_args(argv)

    package_arguments = (args.candidate_base_image, args.candidate_image_tag)
    if args.package_image_only:
        if not all(package_arguments):
            parser.error("package image mode requires exact base image and candidate tag")
    elif any(package_arguments) or args.staging_root is not None:
        parser.error("package image arguments require package image mode")
    if args.package_image_only and (
        args.ownership_ledger is not None or args.interrupt_after is not None
    ):
        parser.error("candidate lifecycle arguments require live topology mode")
    if args.interrupt_after is not None and args.ownership_ledger is None:
        parser.error("candidate interruption requires an ownership ledger")

    startup_diagnostic_path = args.report.with_name(STARTUP_DIAGNOSTIC_FILENAME)
    startup_diagnostic_part_path = Path(str(startup_diagnostic_path) + ".part")
    if not args.package_image_only and (
        _path_exists_without_following(startup_diagnostic_path)
        or _path_exists_without_following(startup_diagnostic_part_path)
    ):
        raise _fixed_assembly_error()

    run_history_rejection_path = args.report.with_name(
        RUN_HISTORY_REJECTION_FILENAME
    )
    run_history_rejection_part_path = Path(
        str(run_history_rejection_path) + ".part"
    )
    run_history_rejection_sink: Callable[[dict[str, Any]], None] | None = None
    if not args.package_image_only and args.scenario == "single-hello":
        if (
            _path_exists_without_following(run_history_rejection_path)
            or _path_exists_without_following(run_history_rejection_part_path)
        ):
            raise _fixed_assembly_error()

        def persist_run_history_rejection(diagnostic: dict[str, Any]) -> None:
            _persist_run_history_rejection(
                run_history_rejection_path,
                diagnostic,
            )

        run_history_rejection_sink = persist_run_history_rejection

    labels = {
        args.project_label.split("=", 1)[0]: args.project_label.split("=", 1)[1],
        args.scenario_label.split("=", 1)[0]: args.scenario_label.split("=", 1)[1],
        "org.openj92.cpk.evidence": args.evidence_id,
    }
    root = Path(__file__).resolve().parents[1]
    if args.ownership_ledger is not None:
        admit_candidate_ledger(
            args.ownership_ledger,
            root=root,
            labels=labels,
            evidence_id=args.evidence_id,
        )
    if args.package_image_only:
        if args.staging_root is not None:
            staging_root = args.staging_root
            resolved_staging_root = staging_root.resolve()
            owned_paths = (
                args.assembly,
                args.inspection,
                args.report,
                staging_root / OVERLAY_PATH,
                staging_root / CORE_WHEEL_PATH,
                Path(str(staging_root / CORE_WHEEL_PATH) + ".part"),
                staging_root / OPERATIONS_WHEEL_PATH,
                Path(str(staging_root / OPERATIONS_WHEEL_PATH) + ".part"),
                staging_root / RFC8785_WHEEL_PATH,
                Path(str(staging_root / RFC8785_WHEEL_PATH) + ".part"),
            )
            if (
                not staging_root.is_dir()
                or any(
                    not path.resolve().is_relative_to(resolved_staging_root)
                    for path in (args.assembly, args.inspection, args.report)
                )
                or any(path.exists() for path in owned_paths)
            ):
                raise _fixed_assembly_error()
            created: list[Path] = []
            generated: list[Path] = []
            package_succeeded = False
            try:
                created.extend(
                    (
                        staging_root / CORE_WHEEL_PATH,
                        Path(str(staging_root / CORE_WHEEL_PATH) + ".part"),
                        staging_root / OPERATIONS_WHEEL_PATH,
                        Path(
                            str(staging_root / OPERATIONS_WHEEL_PATH) + ".part"
                        ),
                    )
                )
                materialize = wheel_materializer or materialize_candidate_wheels
                wheels = materialize(
                    candidate_commit=CPK_COMMIT,
                    candidate_tree=CPK_TREE,
                    staging_root=str(staging_root),
                )
                expected_wheel_sources = {
                    CORE_WHEEL_PATH: "control-plane-kit-core",
                    OPERATIONS_WHEEL_PATH: "control-plane-kit-operations",
                }
                if set(wheels) != set(expected_wheel_sources):
                    raise _fixed_assembly_error()
                wheel_measurements: dict[str, dict[str, Any]] = {}
                for relative_path, subdirectory in expected_wheel_sources.items():
                    observation = wheels[relative_path]
                    if (
                        observation.get("repository")
                        != "OpenJ92/control-plane-kit"
                        or observation.get("commit") != CPK_COMMIT
                        or observation.get("tree") != CPK_TREE
                        or observation.get("subdirectory") != subdirectory
                    ):
                        raise _fixed_assembly_error()
                    wheel_measurements[relative_path] = _physical_artifact(
                        staging_root,
                        relative_path,
                        observation,
                    )

                fetch = artifact_fetcher or _default_artifact_fetcher(staging_root)
                rfc_path = staging_root / RFC8785_WHEEL_PATH
                rfc_temporary = Path(str(rfc_path) + ".part")
                created.append(rfc_temporary)
                observation = fetch(
                    url=RFC8785_WHEEL_URL,
                    destination=str(rfc_temporary),
                )
                if observation != {
                    "url": RFC8785_WHEEL_URL,
                    "path": str(rfc_temporary),
                    "size": RFC8785_WHEEL_SIZE,
                    "sha256": RFC8785_WHEEL_SHA256,
                }:
                    raise _fixed_assembly_error()
                _physical_artifact(
                    staging_root,
                    RFC8785_WHEEL_PATH + ".part",
                    observation,
                )
                rfc_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(rfc_temporary, rfc_path)
                created.append(rfc_path)

                overlay = staging_root / OVERLAY_PATH
                overlay.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / OVERLAY_PATH, overlay)
                created.append(overlay)
                coordinate_provider = (
                    source_coordinate_provider or _measured_server_source
                )
                server_source = coordinate_provider(source_root=str(root))
                if (
                    not _exact_keys(
                        server_source,
                        {"repository", "commit", "tree", "clean"},
                    )
                    or server_source.get("repository")
                    != "OpenJ92/control-plane-kit-servers"
                    or not _hex_digest(server_source.get("commit"), 40)
                    or not _hex_digest(server_source.get("tree"), 40)
                    or server_source.get("clean") is not True
                ):
                    raise _fixed_assembly_error()
                source_identity = {
                    "repository": server_source["repository"],
                    "commit": server_source["commit"],
                    "tree": server_source["tree"],
                }
                assembly = deepcopy(EXPECTED_ASSEMBLY)
                assembly["server_source"] = source_identity
                assembly["runner"] = deepcopy(source_identity)

                if effects_factory is None:
                    effects = DockerCandidateEffects(
                        root=staging_root,
                        labels=labels,
                        evidence_id=args.evidence_id,
                        candidate_image_tag=args.candidate_image_tag,
                        host_address=args.host_address,
                    )
                else:
                    effects = effects_factory(
                        root=staging_root,
                        labels=labels,
                        evidence_id=args.evidence_id,
                        candidate_image_tag=args.candidate_image_tag,
                    )
                resolver = getattr(effects, "resolve_image_id", None)
                base_image = (
                    resolver(args.candidate_base_image)
                    if callable(resolver)
                    else EXPECTED_INSPECTION["images"]["cpk_server_base"]
                )
                inspection = {
                    "candidate": {
                        "commit": CPK_COMMIT,
                        "tree": CPK_TREE,
                        "clean": True,
                    },
                    "server_source": {
                        "commit": server_source["commit"],
                        "tree": server_source["tree"],
                        "clean": True,
                    },
                    "files": {
                        "products/cpk_server/Dockerfile": (
                            PRODUCTION_DOCKERFILE_SHA256
                        ),
                        OVERLAY_PATH: hashlib.sha256(
                            overlay.read_bytes()
                        ).hexdigest(),
                        CORE_WHEEL_PATH: wheel_measurements[CORE_WHEEL_PATH][
                            "sha256"
                        ],
                        OPERATIONS_WHEEL_PATH: wheel_measurements[
                            OPERATIONS_WHEEL_PATH
                        ]["sha256"],
                        RFC8785_WHEEL_PATH: RFC8785_WHEEL_SHA256,
                    },
                    "images": {"cpk_server_base": base_image},
                }
                generated.extend((args.assembly, args.inspection))
                args.assembly.write_text(
                    json.dumps(assembly, ensure_ascii=True, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                args.inspection.write_text(
                    json.dumps(
                        inspection,
                        ensure_ascii=True,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                admitted = admit_candidate_assembly(assembly, inspection)
                _build_candidate_package_image_with_report(
                    admitted,
                    inspection,
                    effects,
                    None,
                    base_image,
                    args.candidate_image_tag,
                    args.report,
                )
                package_succeeded = True
                return 0
            finally:
                for path in reversed(created):
                    if path.is_file():
                        path.unlink()
                if not package_succeeded:
                    for path in reversed(generated):
                        if path.is_file():
                            path.unlink()

        assembly = _load_json(args.assembly)
        inspection = _load_json(args.inspection)
        admitted = admit_candidate_assembly(assembly, inspection)
        fetch = artifact_fetcher or _default_artifact_fetcher(root)
        observation = _admit_rfc8785_artifact(fetch)
        accepted_fetcher = lambda **_kwargs: observation
        if effects_factory is None:
            effects = DockerCandidateEffects(
                root=root,
                labels=labels,
                evidence_id=args.evidence_id,
                candidate_image_tag=args.candidate_image_tag,
                host_address=args.host_address,
            )
        else:
            effects = effects_factory(
                root=root,
                labels=labels,
                evidence_id=args.evidence_id,
                candidate_image_tag=args.candidate_image_tag,
            )
        _build_candidate_package_image_with_report(
            admitted,
            inspection,
            effects,
            accepted_fetcher,
            args.candidate_base_image,
            args.candidate_image_tag,
            args.report,
        )
        return 0

    assembly = _load_json(args.assembly)
    inspection = _load_json(args.inspection)
    admitted = admit_candidate_assembly(assembly, inspection)
    expected_scenario = (
        BLUE_GREEN_SCENARIO
        if args.scenario == "blue-green"
        else EXPECTED_ASSEMBLY["scenario"]
    )
    if admitted["scenario"] != expected_scenario:
        raise _fixed_assembly_error()

    ghcr_pull_credential = os.environ.get(GHCR_PULL_CREDENTIAL_ENV)
    effects_arguments = {
        "root": root,
        "labels": labels,
        "evidence_id": args.evidence_id,
    }
    if ghcr_pull_credential is not None:
        effects_arguments["ghcr_pull_credential"] = ghcr_pull_credential

    if effects_factory is None:
        effects = DockerCandidateEffects(
            **effects_arguments,
            host_address=args.host_address,
            ownership_ledger=args.ownership_ledger,
            interrupt_after=args.interrupt_after,
        )
    else:
        if args.ownership_ledger is not None:
            effects_arguments.update(
                {
                    "ownership_ledger": args.ownership_ledger,
                    "interrupt_after": args.interrupt_after,
                }
            )
        effects = effects_factory(**effects_arguments)

    prepared: dict[str, Any] | None = None
    failure: BaseException | None = None
    report: dict[str, Any] | None = None
    failure_stage = "admission"
    readiness_failed = False
    try:
        failure_stage = "build"
        prepared = _prepare_candidate(admitted, inspection, effects)
        server = prepared["server"]
        if server is None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if workflow_factory is None:
            workflow = HostedWorkflow(
                server["base_url"],
                workspace_id=admitted["inputs"]["workspace_id"],
                worker_id="candidate-worker",
                server_container=server["container_id"],
            )
            try:
                workflow.wait_ready()
            except BaseException:
                readiness_failed = True
                raise
        else:
            workflow = workflow_factory(
                server["base_url"],
                workspace_id=admitted["inputs"]["workspace_id"],
                worker_id="candidate-worker",
                server_container=server["container_id"],
            )
        failure_stage = "workflow"
        current_graph_id = workflow.create_workspace(name="candidate topology")
        if ghcr_pull_credential is not None:
            workflow.register_ghcr_pull_authority_from_docker_config()
        workflow.register_local_docker_authority()
        workflow.register_local_docker_delivery()
        hello_document = _product_document(root, "hello_server")
        workflow.import_product("hello", hello_document)
        empty_graph = DeploymentGraph(admitted["inputs"]["workspace_id"])
        if args.scenario == "blue-green":
            router_document = _product_document(root, "http_active_router")
            workflow.import_product("http-active-router", router_document)
            report = run_candidate_blue_green(
                admitted,
                inspection=inspection,
                workflow=workflow,
                effects=effects,
                hello_document=hello_document,
                router_document=router_document,
                empty_graph=empty_graph,
                current_graph_id=current_graph_id,
                prepared=prepared,
            )
        else:
            hello_graph = _single_hello_graph(
                hello_document,
                workspace_id=admitted["inputs"]["workspace_id"],
            )
            report = run_candidate_topology(
                admitted,
                inspection=inspection,
                workflow=workflow,
                effects=effects,
                hello_graph=hello_graph,
                empty_graph=empty_graph,
                current_graph_id=current_graph_id,
                prepared=prepared,
                run_history_rejection_sink=run_history_rejection_sink,
            )
    except BaseException as error:
        failure = error

    if failure is not None:
        if readiness_failed and prepared is not None:
            container_state: dict[str, Any] = {
                "status": "unknown",
                "exit_code": None,
            }
            server = prepared.get("server")
            observer = getattr(effects, "observe_candidate_startup", None)
            if type(server) is dict and callable(observer):
                try:
                    container_state = observer(server["container_id"])
                except Exception:
                    pass
            try:
                diagnostic = _startup_diagnostic(
                    prepared,
                    readiness_error=failure,
                    container_state=container_state,
                )
                _persist_startup_diagnostic(startup_diagnostic_path, diagnostic)
            except Exception:
                pass
        report = getattr(failure, "candidate_terminal_report", None)
        if report is None:
            cleanup = effects.cleanup(reason="error")
            report = _failed_report(
                assembly,
                cleanup=cleanup,
                first_failed_stage=getattr(failure, "candidate_stage", failure_stage),
                prepared=prepared,
            )
        _persist_report(args.report, report)
        raise failure

    assert report is not None
    _persist_report(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
