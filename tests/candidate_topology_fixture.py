"""Test support for the candidate-direct topology contract."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SERVER_BASELINE_COMMIT = "43e9f359ca828c83fe4994ed1b62e1be54277ddd"
SERVER_BASELINE_TREE = "ec259176eba3ce2f777d38c68fcc14e0a0e80cd3"
CANDIDATE_COMMIT = "4fb75b7b6c1a16ec3b8c1d78dec6ad1a4ad1b40a"
CANDIDATE_TREE = "6a405e4ab7e707ff7374205ca2ef4726d6225b86"
SNAPSHOT_MANIFEST_SHA256 = (
    "2cf09911ac9dcaa4e8ae86f8eefa60f191955d0e1f1f115f763aba78a831a48c"
)
INTERPRETERS_COMMIT = "4c1a265075f2fa30e0290e7ea0e1996d32b70319"
INTERPRETERS_TREE = "8cd60f5f640df38488efcd6c555675f292f37324"
SECRETS_COMMIT = "96e86dc3248d578780d64d5d7fc5d6359631d1d6"
SECRETS_TREE = "b1740225a93410349a9e9199c539e330b408abae"
PRODUCTION_DOCKERFILE_SHA256 = (
    "7a95cf122c7bb7c5bd911c5bbe95c3c5da81f757aa8fb7d0fa014eb36a51d5eb"
)
POSTGRES_IMAGE = (
    "docker.io/library/postgres@sha256:"
    "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)
HELLO_IMAGE = (
    "ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:"
    "e2288b23844b1f0b7526d2798cbc1eaf6e9f536399173a043e7957f0e7730cbf"
)
HELLO_DESCRIPTOR_SHA256 = (
    "57ac661ca3f73ad4fa488df34390240e95da58e302bffb17c2197eeac29c2a24"
)
HELLO_RESPONSE = b"Hello, world!\n"
HELLO_RESPONSE_SHA256 = hashlib.sha256(HELLO_RESPONSE).hexdigest()
HELLO_LOCAL_IMAGE_ID = "sha256:" + "2" * 64

RUNNER_COMMIT = "fc46e42d7143698ad6c7ab86d67c66a3f059ab68"
RUNNER_TREE = "eeab26c68610d176078adbd68a319c806a8cd436"
OVERLAY_SHA256 = "c" * 64
CORE_WHEEL_PATH = "dist/control_plane_kit_core.whl"
OPERATIONS_WHEEL_PATH = "dist/control_plane_kit_operations.whl"
CORE_WHEEL_BYTES = (
    b"control-plane-kit-core candidate wheel\n"
    + CANDIDATE_COMMIT.encode("ascii")
    + b"\n"
    + CANDIDATE_TREE.encode("ascii")
    + b"\n"
)
OPERATIONS_WHEEL_BYTES = (
    b"control-plane-kit-operations candidate wheel\n"
    + CANDIDATE_COMMIT.encode("ascii")
    + b"\n"
    + CANDIDATE_TREE.encode("ascii")
    + b"\n"
)
CORE_WHEEL_SHA256 = "d" * 64
OPERATIONS_WHEEL_SHA256 = "e" * 64
STAGED_OVERLAY_SHA256 = (
    "87a1009c3d81c4fd9b861534f560712d15960faa3ceb715ef4e4353a38d98fdf"
)
STAGED_CORE_WHEEL_SHA256 = hashlib.sha256(CORE_WHEEL_BYTES).hexdigest()
STAGED_OPERATIONS_WHEEL_SHA256 = hashlib.sha256(
    OPERATIONS_WHEEL_BYTES
).hexdigest()
MEASURED_SERVER_COMMIT = "0123456789abcdef" * 2 + "01234567"
MEASURED_SERVER_TREE = "89abcdef01234567" * 2 + "89abcdef"
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
RFC8785_WHEEL_BYTES = base64.b64decode(
    """
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
    """
)
CANDIDATE_WHEEL_SOURCES = {
    CORE_WHEEL_PATH: {
        "repository": "OpenJ92/control-plane-kit",
        "commit": CANDIDATE_COMMIT,
        "tree": CANDIDATE_TREE,
        "subdirectory": "control-plane-kit-core",
        "sha256": STAGED_CORE_WHEEL_SHA256,
        "size": len(CORE_WHEEL_BYTES),
    },
    OPERATIONS_WHEEL_PATH: {
        "repository": "OpenJ92/control-plane-kit",
        "commit": CANDIDATE_COMMIT,
        "tree": CANDIDATE_TREE,
        "subdirectory": "control-plane-kit-operations",
        "sha256": STAGED_OPERATIONS_WHEEL_SHA256,
        "size": len(OPERATIONS_WHEEL_BYTES),
    },
}
CPK_SERVER_BASE_IMAGE = "sha256:" + "9" * 64
CANDIDATE_IMAGE_ID = "sha256:" + "f" * 64
INSTALLED_RECORD_PATHS = (
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_core-0.1.0.dist-info/RECORD",
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_operations-0.1.0.dist-info/RECORD",
    "/usr/local/lib/python3.12/site-packages/rfc8785-0.1.4.dist-info/RECORD",
)
INSTALLED_MODULE_PATHS = (
    "/usr/local/lib/python3.12/site-packages/control_plane_kit_core/__init__.py",
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_operations/__init__.py",
    "/usr/local/lib/python3.12/site-packages/rfc8785/__init__.py",
)
WORKSPACE_ID = "candidate-topology-1714"
FOREIGN_RESOURCE_CANARY = "foreign-resource-1714"
FOREIGN_INVENTORY = {
    "containers": ("foreign-container-1714",),
    "networks": ("foreign-network-1714",),
    "volumes": (),
    "images": ("sha256:" + "3" * 64, "sha256:" + "8" * 64),
    "postgres_relations": (),
}

CANDIDATE_LABELS = {
    "org.openj92.project": "control-plane-kit-servers",
    "org.openj92.cpk.scenario": "candidate-topology-1714",
    "org.openj92.cpk.evidence": "candidate-topology-hardening",
}
DOCKER_SOCKET_GID = 987
POSTGRES_DB = "cpk"
POSTGRES_USER = "candidate"
POSTGRES_PASSWORD = "candidate-password-not-for-output"
POSTGRES_DATA_PATH = "/var/lib/postgresql/data"
POSTGRES_READY_ATTEMPTS = 15
POSTGRES_READY_RETRY_SECONDS = 1.0
POSTGRES_BOOTSTRAP_ENVIRONMENT = {
    "POSTGRES_DB": POSTGRES_DB,
    "POSTGRES_USER": POSTGRES_USER,
    "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
}
POSTGRES_DSN_ENVIRONMENT = {
    "CPK_WORKPLACE_DATABASE_URL": (
        "postgresql://candidate:candidate-password-not-for-output@"
        "candidate-postgres:5432/cpk"
    ),
    "CPK_ACTIVITY_HISTORY_DATABASE_URL": (
        "postgresql://candidate:candidate-password-not-for-output@"
        "candidate-postgres:5432/cpk"
    ),
    "CPK_OBSERVER_STATE_DATABASE_URL": (
        "postgresql://candidate:candidate-password-not-for-output@"
        "candidate-postgres:5432/cpk"
    ),
    "CPK_GRAPH_TOPOLOGY_DATABASE_URL": (
        "postgresql://candidate:candidate-password-not-for-output@"
        "candidate-postgres:5432/cpk"
    ),
}
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
CANDIDATE_SERVER_ENVIRONMENT = {
    "CPK_SERVER_MODE": "execution-capable",
    "CPK_CONTROL_AUTH_VERIFIER": "static-development",
    "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(
        [
            {
                "credential": "present",
                "subject_id": "hosted-operator",
                "kind": "operator",
                "workspace_grants": {WORKSPACE_ID: list(OPERATOR_SCOPES)},
            },
            {
                "credential": "manager-present",
                "subject_id": "manager-a",
                "kind": "operator",
                "workspace_grants": {WORKSPACE_ID: list(APPROVER_SCOPES)},
            },
            {
                "credential": "worker-present",
                "subject_id": "candidate-worker",
                "kind": "worker",
                "workspace_grants": {WORKSPACE_ID: list(WORKER_SCOPES)},
            },
        ],
        separators=(",", ":"),
        sort_keys=True,
    ),
    "CPK_PORT": "8080",
    "CPK_RUNTIME_INTERPRETERS": "docker",
    "CPK_INGRESS_INTERPRETERS": "none",
    "CPK_PRODUCT_MATERIAL_RESOLVER": "none",
    **POSTGRES_DSN_ENVIRONMENT,
}
CURL_IMAGE = (
    "docker.io/curlimages/curl@sha256:"
    "7c12af72ceb38b7432ab85e1a265cff6ae58e06f95539d539b654f2cfa64bb13"
)


def exact_assembly() -> dict[str, Any]:
    return {
        "schema": "cpk.candidate-assembly.v1",
        "scenario": "candidate.topology.single-hello.v1",
        "acceptance_level": "source-built-candidate",
        "candidate": {
            "repository": "OpenJ92/control-plane-kit",
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
        },
        "server_source": {
            "repository": "OpenJ92/control-plane-kit-servers",
            "commit": RUNNER_COMMIT,
            "tree": RUNNER_TREE,
        },
        "runner": {
            "repository": "OpenJ92/control-plane-kit-servers",
            "commit": RUNNER_COMMIT,
            "tree": RUNNER_TREE,
        },
        "dependencies": {
            "control_plane_kit_interpreters": {
                "repository": "OpenJ92/control-plane-kit-interpreters",
                "commit": INTERPRETERS_COMMIT,
                "tree": INTERPRETERS_TREE,
            },
            "control_plane_kit_secrets": {
                "repository": "OpenJ92/control-plane-kit-secrets",
                "commit": SECRETS_COMMIT,
                "tree": SECRETS_TREE,
            },
        },
        "products": {
            "cpk_server": {
                "classification": "source-built-candidate",
                "source_commit": CANDIDATE_COMMIT,
                "source_tree": CANDIDATE_TREE,
                "dockerfile_sha256": PRODUCTION_DOCKERFILE_SHA256,
            },
            "hello": {
                "classification": "published-digest",
                "reference": HELLO_IMAGE,
                "descriptor_sha256": HELLO_DESCRIPTOR_SHA256,
            },
        },
        "inputs": {
            "workspace_id": WORKSPACE_ID,
            "foreign_resource_canary": FOREIGN_RESOURCE_CANARY,
        },
    }


def exact_inspection() -> dict[str, Any]:
    return {
        "candidate": {
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
            "clean": True,
        },
        "server_source": {
            "commit": RUNNER_COMMIT,
            "tree": RUNNER_TREE,
            "clean": True,
        },
        "files": {
            "products/cpk_server/Dockerfile": PRODUCTION_DOCKERFILE_SHA256,
            "acceptance/candidate_topology/Dockerfile": OVERLAY_SHA256,
            "dist/control_plane_kit_core.whl": CORE_WHEEL_SHA256,
            "dist/control_plane_kit_operations.whl": OPERATIONS_WHEEL_SHA256,
            RFC8785_WHEEL_PATH: RFC8785_WHEEL_SHA256,
        },
        "images": {"cpk_server_base": CPK_SERVER_BASE_IMAGE},
    }


def package_staging_assembly(
    *,
    source_commit: str = MEASURED_SERVER_COMMIT,
    source_tree: str = MEASURED_SERVER_TREE,
) -> dict[str, Any]:
    assembly = exact_assembly()
    source = {
        "repository": "OpenJ92/control-plane-kit-servers",
        "commit": source_commit,
        "tree": source_tree,
    }
    assembly["server_source"] = source
    assembly["runner"] = deepcopy(source)
    return assembly


def package_staging_inspection(
    *,
    source_commit: str = MEASURED_SERVER_COMMIT,
    source_tree: str = MEASURED_SERVER_TREE,
) -> dict[str, Any]:
    return {
        "candidate": {
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
            "clean": True,
        },
        "server_source": {
            "commit": source_commit,
            "tree": source_tree,
            "clean": True,
        },
        "files": {
            "products/cpk_server/Dockerfile": PRODUCTION_DOCKERFILE_SHA256,
            "acceptance/candidate_topology/Dockerfile": STAGED_OVERLAY_SHA256,
            CORE_WHEEL_PATH: STAGED_CORE_WHEEL_SHA256,
            OPERATIONS_WHEEL_PATH: STAGED_OPERATIONS_WHEEL_SHA256,
            RFC8785_WHEEL_PATH: RFC8785_WHEEL_SHA256,
        },
        "images": {"cpk_server_base": CPK_SERVER_BASE_IMAGE},
    }


def changed(document: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    result = deepcopy(document)
    owner: dict[str, Any] = result
    for part in path[:-1]:
        owner = owner[part]
    owner[path[-1]] = value
    return result


def canonical_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def canonical_report_sha256(document: dict[str, Any]) -> str:
    projected = deepcopy(document)
    projected.pop("report_sha256", None)
    return canonical_sha256(projected)


@dataclass
class RecordingHostedWorkflow:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    workspace_id: str = WORKSPACE_ID
    current_graph_id: str = "graph-predecessor"
    activity: tuple[str, ...] = ()
    active_transition: str = "hello"
    graphs: dict[str, Any] = field(default_factory=dict)
    desired_predecessors: dict[str, str | None] = field(default_factory=dict)
    fail_at: str | None = None

    def create_workspace(self, *, name: str, actor_id: str = "operator-a") -> str:
        self.ledger.append(("create-workspace", self.workspace_id))
        return self.current_graph_id

    def import_product(self, label: str, product_document: Any) -> None:
        self.ledger.append(
            (
                "import-product",
                {
                    "label": label,
                    "content_digest": product_document.content_digest,
                    "document_sha256": hashlib.sha256(
                        product_document.content
                    ).hexdigest(),
                },
            )
        )

    def register_local_docker_authority(self) -> None:
        self.ledger.append(("register-runtime-authority", self.workspace_id))

    def register_ghcr_pull_authority_from_docker_config(self) -> None:
        self.ledger.append(("register-ghcr-secret-provider", self.workspace_id))
        self.ledger.append(("register-ghcr-secret-reference", self.workspace_id))
        self.ledger.append(("register-ghcr-pull-authority", self.workspace_id))

    def register_local_docker_delivery(self) -> None:
        self.ledger.append(("register-runtime-delivery", self.workspace_id))

    def start_session(self, title: str) -> str:
        if self.fail_at == "workflow":
            raise RuntimeError("protected-workflow-failure")
        self.active_transition = "empty" if "empty" in title.lower() else "hello"
        self.ledger.append(("plan", self.active_transition))
        return f"session-{self.active_transition}"

    def set_desired_graph(self, **kwargs: Any) -> str:
        self.graphs[self.active_transition] = kwargs["graph"]
        self.desired_predecessors[self.active_transition] = kwargs[
            "expected_desired_graph_id"
        ]
        self.ledger.append(("desired", self.active_transition))
        return f"graph-{self.active_transition}"

    def plan_transition(self, **kwargs: Any) -> str:
        self.ledger.append(("plan", self.active_transition))
        return f"plan-{self.active_transition}"

    def request_approval(self, **kwargs: Any) -> dict[str, object]:
        self.ledger.append(("request-approval", self.active_transition))
        return {
            "request_id": f"approval-{self.active_transition}",
            "required_scope": "plan:approve-destructive",
            "max_risk": "destructive",
            "destructive": True,
            "plan_id": f"plan-{self.active_transition}",
        }

    def assert_approval_visible(self, approval_id: str, plan_id: str) -> None:
        self.ledger.append(("approval-visible", self.active_transition))

    def approve(self, **kwargs: Any) -> None:
        self.ledger.append(("approve", self.active_transition))

    def admit(self, **kwargs: Any) -> str:
        self.ledger.append(("admit", self.active_transition))
        return f"request-{self.active_transition}"

    def claim(self, **kwargs: Any) -> str:
        self.ledger.append(("claim", self.active_transition))
        return f"run-{self.active_transition}"

    def start_run(self, **kwargs: Any) -> None:
        self.ledger.append(("start", self.active_transition))

    def execute_to_completion(self, run_id: str, *, sync_runtime_networks: bool) -> None:
        self.ledger.append(
            ("execute", (self.active_transition, sync_runtime_networks))
        )
        self.activity = (
            *self.activity,
            f"{self.active_transition}-effect-attempt-complete",
        )

    def read_current_graph_http(self) -> dict[str, Any]:
        self.ledger.append((f"{self._graph_phase()}-http", self.current_graph_id))
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def read_current_graph_mcp(self) -> dict[str, Any]:
        self.ledger.append((f"{self._graph_phase()}-mcp", self.current_graph_id))
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def advance_current_graph(self, **kwargs: Any) -> str:
        self.current_graph_id = kwargs["desired_graph_id"]
        self.ledger.append((f"advance-{self.active_transition}", self.current_graph_id))
        return self.current_graph_id

    def read_activity_http(self) -> dict[str, Any]:
        self.ledger.append(("history-http", self.activity))
        return {"events": self.activity}

    def read_activity_mcp(self) -> dict[str, Any]:
        self.ledger.append(("history-mcp", self.activity))
        return {"events": self.activity}

    def _graph_phase(self) -> str:
        if self.active_transition == "empty" and self.current_graph_id == "graph-hello":
            return "empty-predecessor"
        if self.current_graph_id == "graph-predecessor":
            return "hello-predecessor"
        return f"{self.active_transition}-successor"


@dataclass
class RecordingCandidateEffects:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    foreign_canary_before: tuple[str, ...] = (FOREIGN_RESOURCE_CANARY,)

    def build_candidate_image(
        self,
        assembly: dict[str, Any],
        *,
        base_image: str,
        candidate_image_tag: str | None = None,
    ) -> dict[str, Any]:
        build_identity = (canonical_sha256(assembly), base_image)
        if candidate_image_tag is not None:
            build_identity = (*build_identity, candidate_image_tag)
        self.ledger.append(("build", build_identity))
        return {
            "base_image": base_image,
            "image_id": CANDIDATE_IMAGE_ID,
            "image_tag": candidate_image_tag,
            "record_paths": INSTALLED_RECORD_PATHS,
            "module_paths": INSTALLED_MODULE_PATHS,
        }

    def probe_hello(self, *, labelled: bool, attach_runtime_network: bool) -> bytes:
        self.ledger.append(("probe", (labelled, attach_runtime_network)))
        return HELLO_RESPONSE

    def probe_runtime_node(
        self,
        *,
        node_id: str,
        expected_image_reference: str,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        if node_id != "hello" or expected_image_reference != HELLO_IMAGE:
            raise RuntimeError("candidate probe coordinate is invalid")
        observed = self.probe_hello(
            labelled=labelled,
            attach_runtime_network=attach_runtime_network,
        )
        if type(observed) is dict:
            return observed
        return {
            "response": observed,
            "container_id": "candidate-consumer-probe",
            "request_origin": "inside-probe",
            "target_image_id": HELLO_LOCAL_IMAGE_ID,
            "target_image_reference": HELLO_IMAGE,
        }

    def remove_probe(self) -> None:
        self.ledger.append(("remove-probe", None))

    def cleanup(self, *, reason: str) -> dict[str, Any]:
        self.ledger.append(("cleanup", reason))
        return {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": (),
            "foreign_canary_after": self.foreign_canary_before,
        }


@dataclass
class HardenedRecordingCandidateEffects(RecordingCandidateEffects):
    collision: bool = False
    fail_at: str | None = None
    wrong_hello: bool = False
    build_context: str | None = None
    build_error: BaseException = field(
        default_factory=lambda: RuntimeError("protected-build-failure")
    )
    observation_error: BaseException | None = None
    startup_observation: dict[str, Any] = field(
        default_factory=lambda: {"status": "running", "exit_code": None}
    )
    startup_observation_error: Exception | None = None
    pre_inventory: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: deepcopy(FOREIGN_INVENTORY)
    )

    def preflight_inventory(self, assembly: dict[str, Any]) -> dict[str, Any]:
        observed = {
            "inventory": deepcopy(self.pre_inventory),
            "collisions": (
                (("container", "candidate-owned-name"),)
                if self.collision
                else ()
            ),
            "foreign_canary_before": (
                assembly["inputs"]["foreign_resource_canary"],
            ),
        }
        self.ledger.append(("preflight-inventory", deepcopy(observed)))
        return observed

    def build_candidate_image(
        self,
        assembly: dict[str, Any],
        *,
        base_image: str,
        candidate_image_tag: str | None = None,
    ) -> dict[str, Any]:
        build_identity = (canonical_sha256(assembly), base_image)
        if candidate_image_tag is not None:
            build_identity = (*build_identity, candidate_image_tag)
        if self.fail_at == "build":
            self.ledger.append(("build", build_identity))
            raise self.build_error
        if self.build_context is not None:
            root = Path(self.build_context)
            observed_files = {}
            for relative_path in (
                "acceptance/candidate_topology/Dockerfile",
                CORE_WHEEL_PATH,
                OPERATIONS_WHEEL_PATH,
                RFC8785_WHEEL_PATH,
            ):
                path = root / relative_path
                observed_files[relative_path] = (
                    {
                        "exists": True,
                        "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    if path.is_file()
                    else {"exists": False}
                )
            self.ledger.append(
                (
                    "build-context",
                    {"root": str(root), "files": observed_files},
                )
            )
        self.ledger.append(("build", build_identity))
        return {
            "base_image": base_image,
            "image_id": CANDIDATE_IMAGE_ID,
            "image_tag": candidate_image_tag,
        }

    def observe_candidate_image_tag(self, candidate_image_tag: str) -> bool:
        self.ledger.append(("observe-candidate-image-tag", candidate_image_tag))
        if self.observation_error is not None:
            raise self.observation_error
        return False

    def start_candidate_server(self, built_image_id: str) -> dict[str, str]:
        self.ledger.append(("start-candidate-server", built_image_id))
        return {
            "container_id": "candidate-server-container",
            "image_id": built_image_id,
            "base_url": "http://candidate-server-container:8080",
        }

    def inspect_candidate_server(self, container_id: str) -> dict[str, Any]:
        self.ledger.append(("inspect-candidate-server", container_id))
        return {
            "container_id": container_id,
            "image_id": CANDIDATE_IMAGE_ID,
            "record_paths": INSTALLED_RECORD_PATHS,
            "module_paths": INSTALLED_MODULE_PATHS,
            "record_origins": {
                path: CANDIDATE_IMAGE_ID for path in INSTALLED_RECORD_PATHS
            },
            "module_origins": {
                path: CANDIDATE_IMAGE_ID for path in INSTALLED_MODULE_PATHS
            },
        }

    def observe_candidate_startup(self, container_id: str) -> dict[str, Any]:
        self.ledger.append(("observe-candidate-startup", container_id))
        if self.startup_observation_error is not None:
            raise self.startup_observation_error
        return deepcopy(self.startup_observation)

    def probe_hello(
        self,
        *,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        if self.fail_at == "probe":
            raise RuntimeError("protected-probe-failure")
        self.ledger.append(
            (
                "probe-request",
                {
                    "container_id": "candidate-consumer-probe",
                    "labelled": labelled,
                    "attach_runtime_network": attach_runtime_network,
                    "request_origin": "inside-probe",
                    "target_image_id": HELLO_LOCAL_IMAGE_ID,
                    "target_image_reference": HELLO_IMAGE,
                },
            )
        )
        response = b"Wrong response\n" if self.wrong_hello else HELLO_RESPONSE
        return {
            "response": response,
            "container_id": "candidate-consumer-probe",
            "request_origin": "inside-probe",
            "target_image_id": HELLO_LOCAL_IMAGE_ID,
            "target_image_reference": HELLO_IMAGE,
        }

    def cleanup(self, *, reason: str) -> dict[str, Any]:
        observed = super().cleanup(reason=reason)
        return {
            **observed,
            "pre_inventory": deepcopy(self.pre_inventory),
            "post_inventory": deepcopy(self.pre_inventory),
            "ownership_labels": {
                "org.openj92.project": "control-plane-kit-servers",
                "org.openj92.cpk.scenario": "candidate-topology-1714",
            },
        }



@dataclass
class RecordingHostedWorkflowFactory:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    fail_at: str | None = None
    instances: list[RecordingHostedWorkflow] = field(default_factory=list)

    def __call__(self, base_url: str, **kwargs: Any) -> RecordingHostedWorkflow:
        self.ledger.append(
            (
                "workflow-target",
                {
                    "base_url": base_url,
                    "workspace_id": kwargs["workspace_id"],
                    "server_container": kwargs["server_container"],
                },
            )
        )
        workflow = RecordingHostedWorkflow(
            ledger=self.ledger,
            workspace_id=kwargs["workspace_id"],
            fail_at=self.fail_at,
        )
        self.instances.append(workflow)
        return workflow


@dataclass
class RecordingCandidateEffectsFactory:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    collision: bool = False
    fail_at: str | None = None
    wrong_hello: bool = False
    build_error: BaseException | None = None
    startup_observation: dict[str, Any] = field(
        default_factory=lambda: {"status": "running", "exit_code": None}
    )
    startup_observation_error: Exception | None = None
    instances: list[HardenedRecordingCandidateEffects] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> HardenedRecordingCandidateEffects:
        self.ledger.append(("effects-factory", dict(kwargs)))
        effect_arguments = {
            "ledger": self.ledger,
            "collision": self.collision,
            "fail_at": self.fail_at,
            "wrong_hello": self.wrong_hello,
            "build_context": kwargs.get("root"),
            "startup_observation": deepcopy(self.startup_observation),
            "startup_observation_error": self.startup_observation_error,
        }
        if self.build_error is not None:
            effect_arguments["build_error"] = self.build_error
        effects = HardenedRecordingCandidateEffects(**effect_arguments)
        self.instances.append(effects)
        return effects


@dataclass
class RecordingArtifactFetcher:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    artifact_bytes: bytes = RFC8785_WHEEL_BYTES
    write_artifact: bool = False

    def __call__(self, *, url: str, destination: str) -> dict[str, Any]:
        if self.write_artifact:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.artifact_bytes)
        observation = {
            "url": url,
            "path": destination,
            "size": len(self.artifact_bytes),
            "sha256": hashlib.sha256(self.artifact_bytes).hexdigest(),
        }
        self.ledger.append(("fetch-artifact", deepcopy(observation)))
        return observation


@dataclass
class RecordingServerSourceCoordinate:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    commit: str = MEASURED_SERVER_COMMIT
    tree: str = MEASURED_SERVER_TREE

    def __call__(self, *, source_root: str) -> dict[str, Any]:
        observation = {
            "repository": "OpenJ92/control-plane-kit-servers",
            "commit": self.commit,
            "tree": self.tree,
            "clean": True,
        }
        self.ledger.append(
            (
                "measure-server-source",
                {"source_root": str(source_root), "observation": observation},
            )
        )
        return deepcopy(observation)


@dataclass
class RecordingCandidateWheelMaterializer:
    ledger: list[tuple[str, Any]] = field(default_factory=list)

    def __call__(
        self,
        *,
        candidate_commit: str,
        candidate_tree: str,
        staging_root: str,
    ) -> dict[str, dict[str, Any]]:
        request = {
            "candidate_commit": candidate_commit,
            "candidate_tree": candidate_tree,
            "staging_root": staging_root,
        }
        self.ledger.append(("materialize-candidate-wheels", deepcopy(request)))
        root = Path(staging_root)
        for relative_path, content in (
            (CORE_WHEEL_PATH, CORE_WHEEL_BYTES),
            (OPERATIONS_WHEEL_PATH, OPERATIONS_WHEEL_BYTES),
        ):
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".part")
            temporary.write_bytes(content)
            temporary.replace(destination)
        return deepcopy(CANDIDATE_WHEEL_SOURCES)


@dataclass
class RecordingDockerImage:
    id: str
    tags: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    removed: bool = False

    @property
    def attrs(self) -> dict[str, Any]:
        return {
            "Config": {"Labels": dict(self.labels)},
            "RepoDigests": list(self.tags),
        }


@dataclass
class RecordingDockerContainer:
    client: "RecordingDockerClient"
    image_reference: str
    name: str
    identifier: str
    labels: dict[str, str]
    environment: dict[str, str] = field(default_factory=dict)
    network: str | None = None
    command: Any = None
    ports: dict[str, Any] = field(default_factory=dict)
    volumes: dict[str, Any] = field(default_factory=dict)
    group_add: tuple[str, ...] = ()
    state_status: Any = "running"
    state_exit_code: Any = 0
    removed: bool = False

    @property
    def id(self) -> str:
        return self.identifier

    @property
    def image(self) -> RecordingDockerImage:
        image = self.client.image_for(self.image_reference)
        if image is None:
            image = RecordingDockerImage(self.image_reference)
        return image

    @property
    def attrs(self) -> dict[str, Any]:
        return {
            "Config": {
                "Image": self.image_reference,
                "Labels": dict(self.labels),
            },
            "NetworkSettings": {
                "Ports": {"8080/tcp": [{"HostPort": "49171"}]},
                "Networks": {
                    name: {} for name in (() if self.network is None else (self.network,))
                },
            },
            "State": {
                "Status": self.state_status,
                "ExitCode": self.state_exit_code,
            },
        }

    def reload(self) -> None:
        self.client.ledger.append(("container-reload", self.name))

    def exec_run(self, command: Any) -> Any:
        frozen = tuple(command) if type(command) is list else command
        self.client.ledger.append(("container-exec", (self.name, frozen)))
        rendered = " ".join(command) if type(command) is list else str(command)
        if "pg_isready" in rendered:
            exit_code = (
                self.client.postgres_readiness.pop(0)
                if self.client.postgres_readiness
                else 0
            )
            output = b"accepting connections\n" if exit_code == 0 else b"no response\n"
            return SimpleNamespace(exit_code=exit_code, output=output)
        if "importlib.metadata" in rendered:
            return SimpleNamespace(
                exit_code=0,
                output=json.dumps(
                    {
                        "record_paths": INSTALLED_RECORD_PATHS,
                        "module_paths": INSTALLED_MODULE_PATHS,
                    }
                ).encode("utf-8"),
            )
        if "curl" in rendered:
            return SimpleNamespace(exit_code=0, output=HELLO_RESPONSE)
        return SimpleNamespace(exit_code=0, output=b"")

    def remove(self, *, force: bool = False) -> None:
        self.removed = True
        self.client.ledger.append(("container-remove", (self.name, force)))


@dataclass
class RecordingDockerNetwork:
    client: "RecordingDockerClient"
    name: str
    labels: dict[str, str]
    removed: bool = False
    connections: list[str] = field(default_factory=list)

    @property
    def attrs(self) -> dict[str, Any]:
        return {"Labels": dict(self.labels)}

    def connect(self, container: RecordingDockerContainer) -> None:
        self.connections.append(container.name)
        container.network = self.name
        self.client.ledger.append(("network-connect", (self.name, container.name)))

    def remove(self) -> None:
        self.removed = True
        self.client.ledger.append(("network-remove", self.name))


class RecordingDockerContainers:
    def __init__(self, client: "RecordingDockerClient") -> None:
        self.client = client
        self.values: list[RecordingDockerContainer] = []

    def list(self, *, all: bool = False, filters: Any = None) -> list[Any]:
        values = [value for value in self.values if not value.removed]
        return self.client.filtered(values, filters)

    def run(self, image: str, command: Any = None, **kwargs: Any) -> Any:
        name = kwargs["name"]
        recorded = {
            "image": image,
            "command": command,
            "name": name,
            **{key: value for key, value in kwargs.items()},
        }
        container = RecordingDockerContainer(
            client=self.client,
            image_reference=image,
            name=name,
            identifier=f"sha256:{hashlib.sha256(name.encode('ascii')).hexdigest()}",
            labels=dict(kwargs.get("labels") or {}),
            environment=dict(kwargs.get("environment") or {}),
            network=kwargs.get("network"),
            command=command,
            ports=dict(kwargs.get("ports") or {}),
            volumes=dict(kwargs.get("volumes") or {}),
            group_add=tuple(str(value) for value in kwargs.get("group_add") or ()),
            state_status=(
                self.client.candidate_state_status
                if image == CANDIDATE_IMAGE_ID
                else "running"
            ),
            state_exit_code=(
                self.client.candidate_state_exit_code
                if image == CANDIDATE_IMAGE_ID
                else 0
            ),
        )
        self.values.append(container)
        self.client.container_runs.append(recorded)
        self.client.ledger.append(
            (
                "container-run",
                {
                    "image": image,
                    "command": command,
                    "name": name,
                    **{
                        key: value
                        for key, value in kwargs.items()
                        if key != "environment"
                    },
                    "environment_keys": tuple(
                        sorted((kwargs.get("environment") or {}).keys())
                    ),
                },
            )
        )
        return container


class RecordingDockerNetworks:
    def __init__(self, client: "RecordingDockerClient") -> None:
        self.client = client
        self.values: list[RecordingDockerNetwork] = []

    def list(self, *, filters: Any = None) -> list[Any]:
        values = [value for value in self.values if not value.removed]
        return self.client.filtered(values, filters)

    def create(self, name: str, **kwargs: Any) -> RecordingDockerNetwork:
        network = RecordingDockerNetwork(
            client=self.client,
            name=name,
            labels=dict(kwargs.get("labels") or {}),
        )
        self.values.append(network)
        self.client.ledger.append(("network-create", {"name": name, **kwargs}))
        return network


class RecordingDockerImages:
    def __init__(self, client: "RecordingDockerClient") -> None:
        self.client = client
        self.values: list[RecordingDockerImage] = [
            RecordingDockerImage(CPK_SERVER_BASE_IMAGE),
            RecordingDockerImage("sha256:" + "8" * 64, ("foreign-image:stable",)),
        ]

    def list(self, *, filters: Any = None) -> list[RecordingDockerImage]:
        values = [value for value in self.values if not value.removed]
        return self.client.filtered(values, filters)

    def build(self, **kwargs: Any) -> tuple[RecordingDockerImage, tuple[Any, ...]]:
        image = RecordingDockerImage(
            CANDIDATE_IMAGE_ID,
            (kwargs["tag"],),
            labels=dict(kwargs.get("labels") or {}),
        )
        self.values.append(image)
        self.client.ledger.append(("image-build", dict(kwargs)))
        return image, ()

    def remove(self, image_id: str, *, force: bool = False) -> None:
        image = self.client.image_for(image_id)
        if image is not None:
            image.removed = True
        self.client.ledger.append(("image-remove", (image_id, force)))


class RecordingDockerVolumes:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def list(self) -> list[Any]:
        return list(self.values)


class RecordingDockerClient:
    def __init__(self) -> None:
        self.ledger: list[tuple[str, Any]] = []
        self.container_runs: list[dict[str, Any]] = []
        self.postgres_readiness: list[int] = []
        self.candidate_state_status = "running"
        self.candidate_state_exit_code: Any = 0
        self.containers = RecordingDockerContainers(self)
        self.networks = RecordingDockerNetworks(self)
        self.images = RecordingDockerImages(self)
        self.volumes = RecordingDockerVolumes()

    def image_for(self, reference: str) -> RecordingDockerImage | None:
        return next(
            (
                image
                for image in self.images.values
                if image.id == reference or reference in image.tags
            ),
            None,
        )

    def filtered(self, values: list[Any], filters: Any) -> list[Any]:
        if not filters or "label" not in filters:
            return list(values)
        expected = {}
        for item in filters["label"]:
            key, value = item.split("=", 1)
            expected[key] = value
        return [
            value
            for value in values
            if all(
                value.labels.get(key) == expected_value
                for key, expected_value in expected.items()
            )
        ]

    def seed_foreign_canary(self) -> None:
        self.containers.values.append(
            RecordingDockerContainer(
                client=self,
                image_reference="sha256:" + "8" * 64,
                name="foreign-container-1714",
                identifier="sha256:" + "7" * 64,
                labels={"org.openj92.foreign": "true"},
            )
        )
        self.networks.values.append(
            RecordingDockerNetwork(
                client=self,
                name="foreign-network-1714",
                labels={"org.openj92.foreign": "true"},
            )
        )
        self.images.values.append(
            RecordingDockerImage(
                "sha256:" + "3" * 64,
                ("foreign-build-1714:latest",),
                labels={"org.openj92.foreign": "true"},
            )
        )

    def seed_hello_runtime(self) -> tuple[Any, Any]:
        self.images.values.append(
            RecordingDockerImage(
                HELLO_LOCAL_IMAGE_ID,
                (HELLO_IMAGE,),
                labels={"org.openj92.cpk.product": "hello"},
            )
        )
        network = RecordingDockerNetwork(
            client=self,
            name="cpk-runtime-candidate-topology-1714",
            labels={
                "org.openj92.cpk.workspace": WORKSPACE_ID,
                "org.openj92.cpk.kind": "runtime-network",
            },
        )
        container = RecordingDockerContainer(
            client=self,
            image_reference=HELLO_IMAGE,
            name="cpk-runtime-candidate-topology-1714-hello",
            identifier="sha256:" + "6" * 64,
            labels={
                "org.openj92.cpk.workspace": WORKSPACE_ID,
                "org.openj92.cpk.node": "hello",
            },
            network=network.name,
        )
        self.networks.values.append(network)
        self.containers.values.append(container)
        return container, network

    def seed_foreign_workspace_runtime(self) -> RecordingDockerNetwork:
        network = RecordingDockerNetwork(
            client=self,
            name="cpk-runtime-foreign-workspace-1714",
            labels={
                "org.openj92.cpk.workspace": "foreign-workspace-1714",
                "org.openj92.cpk.kind": "runtime-network",
            },
        )
        self.networks.values.append(network)
        return network
