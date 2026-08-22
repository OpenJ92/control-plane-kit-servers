"""Test support for the candidate-direct topology contract."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from types import SimpleNamespace
from typing import Any


SERVER_BASELINE_COMMIT = "43e9f359ca828c83fe4994ed1b62e1be54277ddd"
SERVER_BASELINE_TREE = "ec259176eba3ce2f777d38c68fcc14e0a0e80cd3"
CANDIDATE_COMMIT = "4fb75b7b6c1a16ec3b8c1d78dec6ad1a4ad1b40a"
CANDIDATE_TREE = "6a405e4ab7e707ff7374205ca2ef4726d6225b86"
SNAPSHOT_MANIFEST_SHA256 = (
    "9e9492ed1afe80fc77e12b6c7ba8a5a740a7548a0ccce0056c48038a18d6d403"
)
INTERPRETERS_COMMIT = "2335a21adc5c0b0ae2f592bd15757c6ca1a55e4b"
INTERPRETERS_TREE = "343911ecc968d0ea6c3b1c128a3aad4a28471cfe"
SECRETS_COMMIT = "96e86dc3248d578780d64d5d7fc5d6359631d1d6"
SECRETS_TREE = "b1740225a93410349a9e9199c539e330b408abae"
PRODUCTION_DOCKERFILE_SHA256 = (
    "aa0f6971fac329ab191f5d1b7aa21617ca2ea1fc69ef4abad748ec217a6239b6"
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

RUNNER_COMMIT = "fc46e42d7143698ad6c7ab86d67c66a3f059ab68"
RUNNER_TREE = "eeab26c68610d176078adbd68a319c806a8cd436"
OVERLAY_SHA256 = "c" * 64
CORE_WHEEL_SHA256 = "d" * 64
OPERATIONS_WHEEL_SHA256 = "e" * 64
CPK_SERVER_BASE_IMAGE = "sha256:" + "9" * 64
CANDIDATE_IMAGE_ID = "sha256:" + "f" * 64
INSTALLED_RECORD_PATHS = (
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_core-0.1.0.dist-info/RECORD",
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_operations-0.1.0.dist-info/RECORD",
)
INSTALLED_MODULE_PATHS = (
    "/usr/local/lib/python3.12/site-packages/control_plane_kit_core/__init__.py",
    "/usr/local/lib/python3.12/site-packages/"
    "control_plane_kit_operations/__init__.py",
)
WORKSPACE_ID = "candidate-topology-1714"
FOREIGN_RESOURCE_CANARY = "foreign-resource-1714"
FOREIGN_INVENTORY = {
    "containers": ("foreign-container-1714",),
    "networks": ("foreign-network-1714",),
    "volumes": (),
    "images": ("sha256:" + "3" * 64, "sha256:" + "8" * 64),
    "build_residue": ("foreign-build-1714:latest",),
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
CANDIDATE_SERVER_ENVIRONMENT = {
    "CPK_SERVER_MODE": "execution-capable",
    "CPK_CONTROL_AUTH_VERIFIER": "static-development",
    "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(
        [
            {
                "credential": "operator-token-not-for-output",
                "subject_id": "operator-a",
                "kind": "operator",
                "workspace_grants": {WORKSPACE_ID: ["admin:*"]},
            },
            {
                "credential": "worker-token-not-for-output",
                "subject_id": "candidate-worker",
                "kind": "worker",
                "workspace_grants": {WORKSPACE_ID: ["execution:operate"]},
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
    "7f6d731c246d5d5e5350599f6e85c67c013a006f54d6d8e6dff1117e7f6c91b8"
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
        self.ledger.append(("desired", self.active_transition))
        return f"graph-{self.active_transition}"

    def plan_transition(self, **kwargs: Any) -> str:
        self.ledger.append(("plan", self.active_transition))
        return f"plan-{self.active_transition}"

    def request_approval(self, **kwargs: Any) -> dict[str, str]:
        self.ledger.append(("request-approval", self.active_transition))
        return {"request_id": f"approval-{self.active_transition}"}

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
    ) -> dict[str, Any]:
        self.ledger.append(("build", (canonical_sha256(assembly), base_image)))
        return {
            "base_image": base_image,
            "image_id": CANDIDATE_IMAGE_ID,
            "record_paths": INSTALLED_RECORD_PATHS,
            "module_paths": INSTALLED_MODULE_PATHS,
        }

    def probe_hello(self, *, labelled: bool, attach_runtime_network: bool) -> bytes:
        self.ledger.append(("probe", (labelled, attach_runtime_network)))
        return HELLO_RESPONSE

    def remove_probe(self) -> None:
        self.ledger.append(("remove-probe", None))

    def cleanup(self, *, reason: str) -> dict[str, Any]:
        self.ledger.append(("cleanup", reason))
        return {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "build_residue": (),
            "postgres_relations": (),
            "foreign_canary_after": self.foreign_canary_before,
        }


@dataclass
class HardenedRecordingCandidateEffects(RecordingCandidateEffects):
    collision: bool = False
    fail_at: str | None = None
    wrong_hello: bool = False
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
    ) -> dict[str, Any]:
        if self.fail_at == "build":
            raise RuntimeError("protected-build-failure")
        self.ledger.append(("build", (canonical_sha256(assembly), base_image)))
        return {
            "base_image": base_image,
            "image_id": CANDIDATE_IMAGE_ID,
        }

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
                    "target_image_id": CANDIDATE_IMAGE_ID,
                },
            )
        )
        response = b"Wrong response\n" if self.wrong_hello else HELLO_RESPONSE
        return {
            "response": response,
            "container_id": "candidate-consumer-probe",
            "request_origin": "inside-probe",
            "target_image_id": CANDIDATE_IMAGE_ID,
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
    instances: list[HardenedRecordingCandidateEffects] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> HardenedRecordingCandidateEffects:
        self.ledger.append(("effects-factory", dict(kwargs)))
        effects = HardenedRecordingCandidateEffects(
            ledger=self.ledger,
            collision=self.collision,
            fail_at=self.fail_at,
            wrong_hello=self.wrong_hello,
        )
        self.instances.append(effects)
        return effects


@dataclass
class RecordingDockerImage:
    id: str
    tags: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    removed: bool = False

    @property
    def attrs(self) -> dict[str, Any]:
        return {"Config": {"Labels": dict(self.labels)}}


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
            "Config": {"Labels": dict(self.labels)},
            "NetworkSettings": {
                "Ports": {"8080/tcp": [{"HostPort": "49171"}]},
                "Networks": {
                    name: {} for name in (() if self.network is None else (self.network,))
                },
            },
        }

    def reload(self) -> None:
        self.client.ledger.append(("container-reload", self.name))

    def exec_run(self, command: Any) -> Any:
        frozen = tuple(command) if type(command) is list else command
        self.client.ledger.append(("container-exec", (self.name, frozen)))
        rendered = " ".join(command) if type(command) is list else str(command)
        if "pg_isready" in rendered:
            return SimpleNamespace(exit_code=0, output=b"accepting connections\n")
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
