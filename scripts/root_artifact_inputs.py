"""Closed qualification inputs for the two current root product artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
LIMIT = 65536
ROLES = {"cpk-server": "10001", "secrets-server": "10006"}


class RootArtifactError(ValueError):
    def __init__(self):
        super().__init__("current root artifact input is invalid")


def require(condition):
    if not condition:
        raise RootArtifactError()


def revision(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def identity(value):
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def reference_for(role, value):
    return type(role) is str and role in ROLES and type(value) is str and re.fullmatch(
        r"ghcr\.io/openj92/control-plane-kit-servers/" + re.escape(role) + r"@sha256:[0-9a-f]{64}",
        value) is not None


def select_root_artifacts(environment):
    require(type(environment) is dict)
    mode = environment.get("CPK_ROOT_ARTIFACT_MODE", "source-built")
    cpk = environment.get("CPK_ROOT_CPK_IMAGE", "")
    secrets = environment.get("CPK_ROOT_SECRETS_IMAGE", "")
    source = environment.get("CPK_ROOT_SOURCE_REVISION", "")
    require(mode in ("source-built", "published-digest"))
    if mode == "source-built":
        require(cpk == secrets == source == "")
        return None
    require(reference_for("cpk-server", cpk) and reference_for("secrets-server", secrets)
            and revision(source))
    return {"mode": mode, "source_revision": source,
            "images": {"cpk-server": cpk, "secrets-server": secrets}}


def qualify_root_artifact(*, role, reference, source_revision, image_attrs, expected_execution_id=None):
    require(reference_for(role, reference) and revision(source_revision))
    require(type(image_attrs) is dict)
    config = image_attrs.get("Config")
    require(type(config) is dict and config.get("User") == ROLES[role])
    labels = config.get("Labels")
    require(type(labels) is dict and labels.get("org.opencontainers.image.revision") == source_revision)
    require(image_attrs.get("Os") == "linux" and image_attrs.get("Architecture") == "amd64")
    digests = image_attrs.get("RepoDigests")
    require(type(digests) is list and reference in digests)
    execution = image_attrs.get("Id")
    require(identity(execution))
    if expected_execution_id is not None:
        require(identity(expected_execution_id) and execution == expected_execution_id)
    return {"role": role, "reference": reference, "source_revision": source_revision,
            "execution_id": execution, "platform": "linux/amd64"}


def require_root_artifact_execution(*, proof, observed_image_id):
    require(type(proof) is dict and identity(proof.get("execution_id")))
    require(identity(observed_image_id) and observed_image_id == proof["execution_id"])


def require_root_artifact_process_uid(*, role, pid1_status):
    require(type(role) is str and role in ROLES)
    require(type(pid1_status) is str and len(pid1_status) <= LIMIT and pid1_status.isascii())
    rows = [line for line in pid1_status.splitlines() if line.startswith("Uid:")]
    require(len(rows) == 1)
    number = r"(0|[1-9][0-9]*)"
    row = re.fullmatch(r"Uid:[ \t]+" + r"[ \t]+".join([number] * 4), rows[0])
    require(row is not None)
    effective = row.group(2)
    require(effective == ROLES[role])
    return effective


def expected_provenance(role, upstreams):
    require(type(role) is str and role in ROLES and type(upstreams) is dict)
    selected = {
        "control-plane-kit-core": ("control-plane-kit", "control_plane_kit_core_commit", "control-plane-kit-core"),
        "control-plane-kit-server-sdk": ("control-plane-kit-server-sdk", "control_plane_kit_server_sdk_commit", None),
    }
    if role == "cpk-server":
        selected.update({
            "control-plane-kit-operations": ("control-plane-kit", "control_plane_kit_operations_commit", "control-plane-kit-operations"),
            "control-plane-kit-interpreters": ("control-plane-kit-interpreters", "control_plane_kit_interpreters_commit", None),
        })
    else:
        selected["control-plane-kit-secrets"] = ("control-plane-kit-secrets", "control_plane_kit_secrets_commit", None)
    result = {}
    for name, (repository, key, subdirectory) in selected.items():
        commit = upstreams.get(key)
        require(revision(commit))
        result[name] = {"url": f"https://github.com/OpenJ92/{repository}/archive/{commit}.zip"}
        if subdirectory is not None:
            result[name]["subdirectory"] = subdirectory
    return result


def require_root_artifact_provenance(*, role, installed, upstreams):
    expected = expected_provenance(role, upstreams)
    require(type(installed) is dict and set(installed) == set(expected))
    for name, wanted in expected.items():
        actual = installed[name]
        require(type(actual) is dict and set(actual) <= {"url", "subdirectory", "archive_info"})
        require({key: value for key, value in actual.items() if key != "archive_info"} == wanted)
        if "archive_info" in actual:
            require(type(actual["archive_info"]) is dict)


def read_json(stream):
    raw = stream.read(LIMIT + 1)
    require(len(raw) <= LIMIT)
    return json.loads(raw)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        require(bool(args))
        action = args[0]
        if action == "admit":
            require(len(args) in (4, 5))
            _, role, reference, source, *prior = args
            selected = select_root_artifacts(dict(os.environ))
            require(selected is not None and selected["images"].get(role) == reference
                    and selected["source_revision"] == source)
            attrs = read_json(sys.stdin.buffer)
            if type(attrs) is list:
                require(len(attrs) == 1)
                attrs = attrs[0]
            proof = qualify_root_artifact(role=role, reference=reference,
                source_revision=source, image_attrs=attrs,
                expected_execution_id=prior[0] if prior else None)
            print(proof["execution_id"])
        elif action == "execution":
            require(len(args) == 3)
            require_root_artifact_execution(proof={"execution_id": args[1]}, observed_image_id=args[2])
        elif action == "process-uid":
            require(len(args) == 3)
            with Path(args[2]).open("rb") as stream:
                raw = stream.read(LIMIT + 1)
            require(len(raw) <= LIMIT)
            effective = require_root_artifact_process_uid(role=args[1], pid1_status=raw.decode("ascii"))
            print(f"root_artifact_process_uid role={args[1]} pid=1 effective_uid={effective}")
        elif action == "provenance":
            require(len(args) == 3)
            with Path(args[2]).open("rb") as stream:
                installed = read_json(stream)
            upstreams = json.loads((ROOT / "coordinates/server-products.json").read_text())["upstreams"]
            require_root_artifact_provenance(role=args[1], installed=installed, upstreams=upstreams)
            public = {name: {key: value for key, value in metadata.items()
                             if key in ("url", "subdirectory")}
                      for name, metadata in installed.items()}
            print(json.dumps({"root_artifact_dependencies": args[1], "installed": public}, sort_keys=True))
        else:
            raise RootArtifactError()
    except (RootArtifactError, ValueError, TypeError, KeyError, OSError):
        print("current root artifact input is invalid", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
