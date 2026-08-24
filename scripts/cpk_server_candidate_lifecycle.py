from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


LEDGER_SCHEMA = "cpk.candidate-run-ledger.v1"
INTERRUPTION_EXIT = 86
LIFECYCLE_ERROR = "candidate lifecycle evidence is invalid"
RESOURCE_ROLES = (
    ("container", "server"),
    ("container", "probe"),
    ("container", "postgres"),
    ("network", "runtime"),
    ("image", "candidate"),
    ("path", "core-wheel"),
    ("path", "operations-wheel"),
    ("path", "rfc8785-wheel"),
)
TOP_LEVEL_KEYS = {
    "schema",
    "scenario",
    "evidence_id",
    "ownership_labels",
    "phase",
    "classification",
    "resources",
    "ledger_sha256",
}
RESOURCE_KEYS = {
    "kind",
    "role",
    "coordinate",
    "observed_id",
    "disposition",
}
LABEL_KEYS = {
    "org.openj92.project",
    "org.openj92.cpk.scenario",
    "org.openj92.cpk.evidence",
}
PHASES = {
    "declared",
    "candidate-image-built",
    "interruption-requested",
    "success-requested",
    "contained",
    "passed",
}
CLASSIFICATIONS = {
    "incomplete",
    "interrupted",
    "interrupted-contained",
    "failed-contained",
    "passed",
}
STATE_PAIRS = {
    ("declared", "incomplete"),
    ("candidate-image-built", "incomplete"),
    ("interruption-requested", "interrupted"),
    ("success-requested", "incomplete"),
    ("contained", "interrupted-contained"),
    ("contained", "failed-contained"),
    ("passed", "passed"),
}
TERMINAL_CLASSIFICATIONS = {
    "interrupted-contained",
    "failed-contained",
    "passed",
}
TERMINAL_PHASES = {
    "interrupted-contained": "contained",
    "failed-contained": "contained",
    "passed": "passed",
}
PRETERMINAL_STATES = {
    "interrupted-contained": {("interruption-requested", "interrupted")},
    "failed-contained": {
        ("declared", "incomplete"),
        ("candidate-image-built", "incomplete"),
    },
    "passed": {("success-requested", "incomplete")},
}
DISPOSITIONS = {"declared", "created", "removed", "absent"}
EVIDENCE_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
DOCKER_ID_PATTERN = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")


class CandidateLifecycleError(RuntimeError):
    pass


def candidate_resource_name(evidence_id: str, role: str) -> str:
    if not EVIDENCE_PATTERN.fullmatch(evidence_id) or role not in {
        item[1] for item in RESOURCE_ROLES
    }:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    digest = hashlib.sha256(evidence_id.encode("ascii")).hexdigest()[:12]
    return f"cpk-{digest}-{role}"


def _canonical_sha256(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _with_hash(ledger: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(ledger)
    value.pop("ledger_sha256", None)
    value["ledger_sha256"] = _canonical_sha256(value)
    return value


def _atomic_write(path: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    value = _with_hash(ledger)
    temporary = Path(str(path) + ".part")
    if temporary.exists() or temporary.is_symlink():
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    try:
        with temporary.open("x", encoding="ascii") as stream:
            stream.write(
                json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary.is_file() and not temporary.is_symlink():
            temporary.unlink()
        raise
    return value


def _resource_coordinates(
    root: Path,
    evidence_id: str,
) -> tuple[dict[str, Any], ...]:
    tag = candidate_resource_name(evidence_id, "candidate") + ":latest"
    coordinates = {
        ("container", "server"): candidate_resource_name(evidence_id, "server"),
        ("container", "probe"): candidate_resource_name(evidence_id, "probe"),
        ("container", "postgres"): candidate_resource_name(evidence_id, "postgres"),
        ("network", "runtime"): candidate_resource_name(evidence_id, "runtime"),
        ("image", "candidate"): tag,
        ("path", "core-wheel"): str(root / "dist/control_plane_kit_core.whl"),
        ("path", "operations-wheel"): str(
            root / "dist/control_plane_kit_operations.whl"
        ),
        ("path", "rfc8785-wheel"): str(
            root / "dist/rfc8785-0.1.4-py3-none-any.whl"
        ),
    }
    return tuple(
        {
            "kind": kind,
            "role": role,
            "coordinate": coordinates[(kind, role)],
            "observed_id": None,
            "disposition": "declared",
        }
        for kind, role in RESOURCE_ROLES
    )


def _validate(ledger: Any) -> dict[str, Any]:
    if type(ledger) is not dict or set(ledger) != TOP_LEVEL_KEYS:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    evidence_id = ledger.get("evidence_id")
    scenario = ledger.get("scenario")
    labels = ledger.get("ownership_labels")
    if (
        type(evidence_id) is not str
        or not EVIDENCE_PATTERN.fullmatch(evidence_id)
        or type(scenario) is not str
        or not EVIDENCE_PATTERN.fullmatch(scenario)
        or type(labels) is not dict
        or set(labels) != LABEL_KEYS
        or labels["org.openj92.project"] != "control-plane-kit-servers"
        or labels["org.openj92.cpk.scenario"] != scenario
        or labels["org.openj92.cpk.evidence"] != evidence_id
        or ledger.get("phase") not in PHASES
        or ledger.get("classification") not in CLASSIFICATIONS
        or (ledger.get("phase"), ledger.get("classification")) not in STATE_PAIRS
    ):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    resources = ledger.get("resources")
    if type(resources) is not list or len(resources) != len(RESOURCE_ROLES):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    identities = []
    for resource in resources:
        if type(resource) is not dict or set(resource) != RESOURCE_KEYS:
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        identity = (resource.get("kind"), resource.get("role"))
        identities.append(identity)
        observed_id = resource.get("observed_id")
        if (
            identity not in RESOURCE_ROLES
            or type(resource.get("coordinate")) is not str
            or not resource["coordinate"]
            or (
                observed_id is not None
                and (
                    type(observed_id) is not str
                    or not DOCKER_ID_PATTERN.fullmatch(observed_id)
                )
            )
            or resource.get("disposition") not in DISPOSITIONS
            or (resource["kind"] == "path" and observed_id is not None)
        ):
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
    if tuple(identities) != RESOURCE_ROLES:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    core_path = Path(resources[5]["coordinate"])
    if core_path.name != "control_plane_kit_core.whl" or core_path.parent.name != "dist":
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    expected_coordinates = _resource_coordinates(core_path.parent.parent, evidence_id)
    if any(
        (observed["kind"], observed["role"], observed["coordinate"])
        != (expected["kind"], expected["role"], expected["coordinate"])
        for observed, expected in zip(resources, expected_coordinates, strict=True)
    ):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    expected_hash = ledger.get("ledger_sha256")
    unhashed = deepcopy(ledger)
    unhashed.pop("ledger_sha256")
    if (
        type(expected_hash) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or _canonical_sha256(unhashed) != expected_hash
    ):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    return deepcopy(ledger)


def load_candidate_ledger(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CandidateLifecycleError(LIFECYCLE_ERROR) from None
    return _validate(value)


def admit_candidate_ledger(
    path: Path,
    *,
    root: Path,
    labels: dict[str, str],
    evidence_id: str,
) -> dict[str, Any]:
    ledger = load_candidate_ledger(path)
    if (
        ledger["evidence_id"] != evidence_id
        or ledger["ownership_labels"] != labels
        or ledger["resources"]
        != list(_resource_coordinates(root.resolve(), evidence_id))
    ):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    return ledger


def _not_found_type(not_found_error: Any) -> Any:
    if not_found_error is not None:
        return not_found_error
    import docker

    return docker.errors.NotFound


def _manager(client: Any, kind: str) -> Any:
    if kind == "container":
        return client.containers
    if kind == "network":
        return client.networks
    if kind == "image":
        return client.images
    raise CandidateLifecycleError(LIFECYCLE_ERROR)


def declare_candidate_ledger(
    path: Path,
    *,
    root: Path,
    labels: dict[str, str],
    evidence_id: str,
    client: Any,
    not_found_error: Any = None,
) -> dict[str, Any]:
    if path.exists() or path.is_symlink() or Path(str(path) + ".part").exists():
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    if type(labels) is not dict or set(labels) != LABEL_KEYS:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    scenario = labels.get("org.openj92.cpk.scenario")
    if labels.get("org.openj92.cpk.evidence") != evidence_id:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    resources = _resource_coordinates(root.resolve(), evidence_id)
    not_found = _not_found_type(not_found_error)
    for resource in resources:
        if resource["kind"] == "path":
            coordinate = Path(resource["coordinate"])
            if coordinate.exists() or coordinate.is_symlink():
                raise CandidateLifecycleError(LIFECYCLE_ERROR)
            continue
        try:
            _manager(client, resource["kind"]).get(resource["coordinate"])
        except not_found:
            continue
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    ledger = {
        "schema": LEDGER_SCHEMA,
        "scenario": scenario,
        "evidence_id": evidence_id,
        "ownership_labels": deepcopy(labels),
        "phase": "declared",
        "classification": "incomplete",
        "resources": list(resources),
    }
    return _atomic_write(path, ledger)


def _rewrite(path: Path, transform: Any) -> dict[str, Any]:
    ledger = load_candidate_ledger(path)
    transform(ledger)
    return _atomic_write(path, ledger)


def record_candidate_resource(
    path: Path,
    *,
    kind: str,
    role: str,
    observed_id: str,
) -> dict[str, Any]:
    if not DOCKER_ID_PATTERN.fullmatch(observed_id):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)

    def transform(ledger: dict[str, Any]) -> None:
        if (
            ledger["classification"] != "incomplete"
            or ledger["phase"] not in {"declared", "candidate-image-built"}
        ):
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        matches = [
            row
            for row in ledger["resources"]
            if (row["kind"], row["role"]) == (kind, role)
        ]
        if len(matches) != 1:
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        row = matches[0]
        if row["observed_id"] not in (None, observed_id):
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        row["observed_id"] = observed_id
        row["disposition"] = "created"
        if (kind, role) == ("image", "candidate"):
            ledger["phase"] = "candidate-image-built"

    return _rewrite(path, transform)


def interrupt_candidate_run(path: Path) -> None:
    def transform(ledger: dict[str, Any]) -> None:
        if (
            ledger["phase"] != "candidate-image-built"
            or ledger["classification"] != "incomplete"
        ):
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        ledger["phase"] = "interruption-requested"
        ledger["classification"] = "interrupted"

    _rewrite(path, transform)
    os._exit(INTERRUPTION_EXIT)


def mark_candidate_success(path: Path) -> dict[str, Any]:
    def transform(ledger: dict[str, Any]) -> None:
        docker_resources = tuple(
            row for row in ledger["resources"] if row["kind"] != "path"
        )
        if (
            (ledger["phase"], ledger["classification"])
            != ("candidate-image-built", "incomplete")
            or any(
                row["observed_id"] is None or row["disposition"] != "created"
                for row in docker_resources
            )
        ):
            raise CandidateLifecycleError(LIFECYCLE_ERROR)
        ledger["phase"] = "success-requested"

    return _rewrite(path, transform)


def _resource_labels(resource: Any, kind: str) -> dict[str, str]:
    attrs = getattr(resource, "attrs", {})
    if kind == "container":
        labels = attrs.get("Config", {}).get("Labels", {})
    elif kind == "network":
        labels = attrs.get("Labels", {})
    else:
        labels = attrs.get("Config", {}).get("Labels", {})
    return labels if type(labels) is dict else {}


def _exact_resource(
    ledger: dict[str, Any],
    row: dict[str, Any],
    client: Any,
    not_found: Any,
) -> Any | None:
    try:
        resource = _manager(client, row["kind"]).get(row["coordinate"])
    except not_found:
        return None
    labels = _resource_labels(resource, row["kind"])
    if any(
        labels.get(key) != value
        for key, value in ledger["ownership_labels"].items()
    ):
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    observed_id = row["observed_id"]
    if observed_id is not None and getattr(resource, "id", None) != observed_id:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    return resource


def cleanup_candidate_ledger(
    path: Path,
    *,
    client: Any,
    classification: str,
    not_found_error: Any = None,
) -> dict[str, Any]:
    if classification not in TERMINAL_CLASSIFICATIONS:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    not_found = _not_found_type(not_found_error)
    ledger = load_candidate_ledger(path)
    state = (ledger["phase"], ledger["classification"])
    if ledger["classification"] in TERMINAL_CLASSIFICATIONS:
        if (
            ledger["classification"] == classification
            and ledger["phase"] == TERMINAL_PHASES[classification]
            and all(
                row["disposition"] in {"removed", "absent"}
                for row in ledger["resources"]
            )
        ):
            return ledger
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    if state not in PRETERMINAL_STATES[classification]:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    for index, row in enumerate(ledger["resources"]):
        if row["kind"] == "path":
            owned_path = Path(row["coordinate"])
            if owned_path.is_symlink() or (
                owned_path.exists() and not owned_path.is_file()
            ):
                raise CandidateLifecycleError(LIFECYCLE_ERROR)
            if owned_path.is_file():
                owned_path.unlink()
                disposition = "removed"
            else:
                disposition = "absent"
        else:
            resource = _exact_resource(ledger, row, client, not_found)
            if resource is None:
                disposition = "absent"
            else:
                if row["kind"] == "image":
                    client.images.remove(row["coordinate"], force=True)
                elif row["kind"] == "container":
                    resource.remove(force=True)
                else:
                    resource.remove()
                disposition = "removed"
        ledger["resources"][index]["disposition"] = disposition
        ledger = _atomic_write(path, ledger)
    ledger["phase"] = "passed" if classification == "passed" else "contained"
    ledger["classification"] = classification
    return _atomic_write(path, ledger)


def _parse_label(value: str) -> tuple[str, str]:
    key, separator, item = value.partition("=")
    if not separator or not key or not item:
        raise CandidateLifecycleError(LIFECYCLE_ERROR)
    return key, item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    declare = subparsers.add_parser("declare")
    declare.add_argument("--ledger", type=Path, required=True)
    declare.add_argument("--root", type=Path, required=True)
    declare.add_argument("--evidence-id", required=True)
    declare.add_argument("--project-label", required=True)
    declare.add_argument("--scenario-label", required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--ledger", type=Path, required=True)
    cleanup.add_argument(
        "--classification",
        choices=("interrupted-contained", "failed-contained", "passed"),
        required=True,
    )
    success = subparsers.add_parser("success")
    success.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "success":
        mark_candidate_success(args.ledger)
        return 0

    import docker

    client = docker.from_env()
    if args.command == "declare":
        labels = dict(
            (
                _parse_label(args.project_label),
                _parse_label(args.scenario_label),
                ("org.openj92.cpk.evidence", args.evidence_id),
            )
        )
        declare_candidate_ledger(
            args.ledger,
            root=args.root,
            labels=labels,
            evidence_id=args.evidence_id,
            client=client,
        )
        return 0
    cleanup_candidate_ledger(
        args.ledger,
        client=client,
        classification=args.classification,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
