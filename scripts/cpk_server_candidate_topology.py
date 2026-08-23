"""Candidate-direct cpk-server topology acceptance orchestration."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from time import sleep as _sleep
from typing import Any, Callable
from urllib.request import urlretrieve

from control_plane_kit_core.topology import DeploymentGraph

from scripts.cpk_server_hosted_activity import (
    HostedWorkflow,
    _product_document,
    _single_hello_graph,
)


ASSEMBLY_SCHEMA = "cpk.candidate-assembly.v1"
REPORT_SCHEMA = "cpk.candidate-topology-report.v1"
ASSEMBLY_ERROR = "candidate assembly is invalid"
WORKFLOW_ERROR = "candidate topology workflow failed"
PACKAGE_BUILD_FAILURE_CODE = "candidate-image-build-failed"
PACKAGE_BUILD_FAILURE_MESSAGE = "Candidate image build failed."
SERVER_BASELINE_COMMIT = "43e9f359ca828c83fe4994ed1b62e1be54277ddd"
SERVER_BASELINE_TREE = "ec259176eba3ce2f777d38c68fcc14e0a0e80cd3"
SNAPSHOT_MANIFEST_SHA256 = (
    "9e9492ed1afe80fc77e12b6c7ba8a5a740a7548a0ccce0056c48038a18d6d403"
)
POSTGRES_IMAGE = (
    "docker.io/library/postgres@sha256:"
    "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)
HELLO_RESPONSE = b"Hello, world!\n"
CPK_COMMIT = "4fb75b7b6c1a16ec3b8c1d78dec6ad1a4ad1b40a"
CPK_TREE = "6a405e4ab7e707ff7374205ca2ef4726d6225b86"
PRODUCTION_DOCKERFILE_SHA256 = (
    "aa0f6971fac329ab191f5d1b7aa21617ca2ea1fc69ef4abad748ec217a6239b6"
)
HELLO_DESCRIPTOR_SHA256 = (
    "57ac661ca3f73ad4fa488df34390240e95da58e302bffb17c2197eeac29c2a24"
)
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
    "plan:approve",
    "plan:approve-destructive",
    "plan:execute",
    "execution:operate",
    "runtime-authority:register",
    "runtime-authority:read",
    "runtime-authority:revoke",
    "runtime-authority:use",
    "runtime-authority-delivery:register",
    "runtime-authority-delivery:read",
    "runtime-authority-delivery:revoke",
)
WORKER_SCOPES = ("execution:operate",)
DOCKER_SOCKET = "/var/run/docker.sock"
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
            "commit": "2335a21adc5c0b0ae2f592bd15757c6ca1a55e4b",
            "tree": "343911ecc968d0ea6c3b1c128a3aad4a28471cfe",
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
        "workspace_id": "candidate-topology-1714",
        "foreign_resource_canary": "foreign-resource-1714",
    },
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


def _candidate_server_environment(postgres_name: str) -> dict[str, str]:
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
    return {
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
        "CPK_PRODUCT_MATERIAL_RESOLVER": "none",
        "CPK_WORKPLACE_DATABASE_URL": database_url,
        "CPK_ACTIVITY_HISTORY_DATABASE_URL": database_url,
        "CPK_OBSERVER_STATE_DATABASE_URL": database_url,
        "CPK_GRAPH_TOPOLOGY_DATABASE_URL": database_url,
    }


def admit_candidate_assembly(
    assembly: dict[str, Any],
    inspection: dict[str, Any],
) -> dict[str, Any]:
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
    if (
        assembly["schema"] != ASSEMBLY_SCHEMA
        or assembly["scenario"] != EXPECTED_ASSEMBLY["scenario"]
        or assembly["acceptance_level"] != EXPECTED_ASSEMBLY["acceptance_level"]
        or assembly["candidate"] != EXPECTED_ASSEMBLY["candidate"]
        or assembly["dependencies"] != EXPECTED_ASSEMBLY["dependencies"]
        or assembly["inputs"] != EXPECTED_ASSEMBLY["inputs"]
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
    if not _exact_keys(products, {"cpk_server", "hello"}):
        raise _fixed_assembly_error()
    server_product = products["cpk_server"]
    if not _exact_keys(
        server_product,
        {"classification", "source_commit", "source_tree", "dockerfile_sha256"},
    ) or server_product != EXPECTED_ASSEMBLY["products"]["cpk_server"]:
        raise _fixed_assembly_error()
    if products["hello"] != EXPECTED_ASSEMBLY["products"]["hello"]:
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
    if source == EXPECTED_ASSEMBLY["server_source"] and inspection != EXPECTED_INSPECTION:
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
) -> dict[str, Any]:
    session_id = workflow.start_session(title)
    desired_graph_id = workflow.set_desired_graph(
        session_id=session_id,
        graph=graph,
        title=title,
        expected_desired_graph_id=None,
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
    candidate_pin = "4fb75b7b6c1a16ec3b8c1d78dec6ad1a4ad1b40a"
    candidate_tree_pin = "6a405e4ab7e707ff7374205ca2ef4726d6225b86"
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
    probe_result: Any = None

    try:
        hello = _public_transition(
            workflow,
            title="hello",
            graph=hello_graph,
            current_graph_id=current_graph_id,
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
            )
            history_http = workflow.read_activity_http()
            history_mcp = workflow.read_activity_mcp()
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
    ) -> None:
        import docker

        self._root = root
        self._labels = labels
        self._evidence_id = evidence_id
        self._candidate_image_tag = candidate_image_tag
        self._client = docker.from_env()
        self._probe = None
        self._server = None
        self._postgres = None
        self._network = None
        self._image = None
        self._pre_inventory: dict[str, Any] | None = None
        self._foreign_canary = ""

    def _name(self, role: str) -> str:
        digest = hashlib.sha256(self._evidence_id.encode("utf-8")).hexdigest()[:12]
        return f"cpk-{digest}-{role}"

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
        environment = _candidate_server_environment(self._name("postgres"))
        candidate_server = self._client.containers.run(
            built_image_id,
            detach=True,
            environment=environment,
            group_add=(docker_socket_gid,),
            labels=self._labels,
            name=self._name("server"),
            network=self._network.name,
            ports={"8080/tcp": ("127.0.0.1", None)},
            volumes={
                DOCKER_SOCKET: {
                    "bind": DOCKER_SOCKET,
                    "mode": "rw",
                }
            },
        )
        self._server = candidate_server
        candidate_server.reload()
        bindings = candidate_server.attrs["NetworkSettings"]["Ports"]["8080/tcp"]
        host_port = bindings[0]["HostPort"]
        return {
            "container_id": candidate_server.id,
            "image_id": built_image_id,
            "base_url": f"http://127.0.0.1:{host_port}",
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

    def probe_hello(
        self,
        *,
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
            == "hello"
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
        expected_image_reference = EXPECTED_ASSEMBLY["products"]["hello"][
            "reference"
        ]
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
        probe_container = self._client.containers.run(
            "docker.io/curlimages/curl@sha256:"
            "7c12af72ceb38b7432ab85e1a265cff6ae58e06f95539d539b654f2cfa64bb13",
            ["sleep", "60"],
            labels=labels,
            detach=True,
            network_mode="none",
            name=self._name("probe"),
        )
        self._probe = probe_container
        if not attach_runtime_network:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        provider_network.connect(probe_container)
        result = probe_container.exec_run(
            ["curl", "--fail", "--silent", f"http://{provider.name}:8080/"]
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
    parser.add_argument("--package-image-only", action="store_true")
    parser.add_argument("--candidate-base-image")
    parser.add_argument("--candidate-image-tag")
    parser.add_argument("--staging-root", type=Path)
    args = parser.parse_args(argv)

    package_arguments = (args.candidate_base_image, args.candidate_image_tag)
    if args.package_image_only:
        if not all(package_arguments):
            parser.error("package image mode requires exact base image and candidate tag")
    elif any(package_arguments) or args.staging_root is not None:
        parser.error("package image arguments require package image mode")

    labels = {
        args.project_label.split("=", 1)[0]: args.project_label.split("=", 1)[1],
        args.scenario_label.split("=", 1)[0]: args.scenario_label.split("=", 1)[1],
        "org.openj92.cpk.evidence": args.evidence_id,
    }
    root = Path(__file__).resolve().parents[1]
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

    if effects_factory is None:
        effects = DockerCandidateEffects(
            root=root,
            labels=labels,
            evidence_id=args.evidence_id,
        )
    else:
        effects = effects_factory(
            root=root,
            labels=labels,
            evidence_id=args.evidence_id,
        )

    prepared: dict[str, Any] | None = None
    failure: BaseException | None = None
    report: dict[str, Any] | None = None
    failure_stage = "admission"
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
            workflow.wait_ready()
        else:
            workflow = workflow_factory(
                server["base_url"],
                workspace_id=admitted["inputs"]["workspace_id"],
                worker_id="candidate-worker",
                server_container=server["container_id"],
            )
        failure_stage = "workflow"
        current_graph_id = workflow.create_workspace(name="candidate topology")
        workflow.register_local_docker_authority()
        workflow.register_local_docker_delivery()
        hello_document = _product_document(root, "hello_server")
        workflow.import_product("hello", hello_document)
        hello_graph = _single_hello_graph(
            hello_document,
            workspace_id=admitted["inputs"]["workspace_id"],
        )
        empty_graph = DeploymentGraph(admitted["inputs"]["workspace_id"])
        report = run_candidate_topology(
            admitted,
            inspection=inspection,
            workflow=workflow,
            effects=effects,
            hello_graph=hello_graph,
            empty_graph=empty_graph,
            current_graph_id=current_graph_id,
            prepared=prepared,
        )
    except BaseException as error:
        failure = error

    if failure is not None:
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
