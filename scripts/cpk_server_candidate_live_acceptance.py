"""Typed transition execution for candidate live acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import json
import re
from typing import Any, Protocol

from control_plane_kit_core.topology import DeploymentGraph


PROGRAM_ERROR = "candidate transition program is invalid"
WORKFLOW_ERROR = "candidate topology workflow failed"
_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_NAME_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_IMAGE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9.-]*(?::[0-9]+)?"
    r"(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[0-9a-f]{64}\Z"
)
_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IPV4_PATTERN = re.compile(r"(?:^|[^0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::[0-9]+)?(?:$|[^0-9])")
_HOSTNAME_PATTERN = re.compile(
    r"(?:^|[^A-Za-z0-9-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?:$|[^A-Za-z0-9-])"
)
_HTTP_PATH_PATTERN = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*\Z")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]+Z?\Z")
_PROTECTED_TEXT = (
    "access_key",
    "api-key",
    "api_key",
    "authorization:",
    "bearer ",
    "buildkit",
    "client_secret",
    "containerd",
    "credential",
    "docker daemon",
    "dockerd",
    "docker.sock",
    "exception",
    "password",
    "private key",
    "provider error",
    "provider message",
    "raw provider",
    "session_cookie",
    "secret://",
    "token=",
    "traceback",
)


class CandidateTransitionProgramError(ValueError):
    """Raised when a typed candidate transition program is malformed."""


class CandidateTopologyError(RuntimeError):
    """Raised for bounded candidate transition or evidence failure."""


class CandidateWorkflowPort(Protocol):
    def start_session(self, title: str) -> str: ...

    def set_desired_graph(
        self,
        *,
        session_id: str,
        graph: DeploymentGraph,
        title: str,
        expected_desired_graph_id: str | None,
    ) -> str: ...

    def plan_transition(
        self,
        *,
        session_id: str,
        title: str,
        current_graph_id: str,
        desired_graph_id: str,
    ) -> str: ...

    def request_approval(
        self,
        *,
        session_id: str,
        title: str,
        plan_id: str,
    ) -> dict[str, object]: ...

    def assert_approval_visible(self, approval_id: str, plan_id: str) -> None: ...

    def approve(
        self,
        *,
        session_id: str,
        title: str,
        approval: CandidateApprovalProjection,
    ) -> None: ...

    def admit(
        self,
        *,
        session_id: str,
        title: str,
        plan_id: str,
        approval_id: str,
    ) -> str: ...

    def claim(self, *, title: str, request_id: str) -> str: ...

    def start_run(self, *, title: str, run_id: str) -> None: ...

    def execute_to_completion(
        self,
        run_id: str,
        *,
        sync_runtime_networks: bool,
    ) -> None: ...

    def read_current_graph_http(self) -> dict[str, Any]: ...

    def read_current_graph_mcp(self) -> dict[str, Any]: ...

    def advance_current_graph(
        self,
        *,
        title: str,
        run_id: str,
        plan_id: str,
        current_graph_id: str,
        desired_graph_id: str,
    ) -> str: ...

    def read_activity_http(self) -> dict[str, Any]: ...

    def read_activity_mcp(self) -> dict[str, Any]: ...


class CandidateProbePort(Protocol):
    def probe_runtime_node(
        self,
        *,
        node_id: str,
        expected_image_reference: str,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]: ...

    def remove_probe(self) -> None: ...


def _reject_protected_text(value: str) -> None:
    lowered = value.lower()
    try:
        ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        is_ip_address = False
    else:
        is_ip_address = True
    if (
        "://" in lowered
        or any(token in lowered for token in _PROTECTED_TEXT)
        or _IPV4_PATTERN.search(value) is not None
        or _HOSTNAME_PATTERN.search(value) is not None
        or is_ip_address
        or value.startswith("/")
    ):
        raise CandidateTopologyError(WORKFLOW_ERROR)


def _closed_object(value: Any, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return value


def _safe_text(value: Any) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 65536:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _reject_protected_text(value)
    return value


def _safe_identity(value: Any) -> str:
    value = _safe_text(value)
    if _IDENTITY_PATTERN.fullmatch(value) is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return value


def _safe_sequence(value: Any) -> list[Any] | tuple[Any, ...]:
    if type(value) not in {list, tuple}:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return value


def _validate_protocol(value: Any) -> None:
    value = _closed_object(value, frozenset(("application", "transport")))
    _safe_identity(value["application"])
    _safe_identity(value["transport"])


def _validate_lifecycle(value: Any) -> None:
    value = _closed_object(value, frozenset(("compute", "data", "ownership")))
    _safe_identity(value["compute"])
    if _safe_sequence(value["data"]):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["ownership"])


def _validate_check(value: Any) -> None:
    value = _closed_object(
        value,
        frozenset(
            (
                "check_id",
                "expected_statuses",
                "kind",
                "path",
                "policy",
                "provider_socket",
            )
        ),
    )
    _safe_identity(value["check_id"])
    statuses = _safe_sequence(value["expected_statuses"])
    if not statuses or any(type(status) is not int for status in statuses):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["kind"])
    if type(value["path"]) is not str or _HTTP_PATH_PATTERN.fullmatch(value["path"]) is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    policy = _closed_object(
        value["policy"],
        frozenset(
            (
                "interval_seconds",
                "maximum_attempts",
                "maximum_evidence_bytes",
                "timeout_seconds",
            )
        ),
    )
    if any(type(item) not in {int, float} or item <= 0 for item in policy.values()):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["provider_socket"])


def _validate_node(value: Any) -> None:
    value = _closed_object(
        value,
        frozenset(
            (
                "block_family",
                "block_spec",
                "configuration_artifacts",
                "endpoints",
                "environment_bindings",
                "kind",
                "lifecycle",
                "metadata",
                "node_id",
                "providers",
                "requirements",
                "runtime_id",
                "secret_deliveries",
            )
        ),
    )
    _safe_identity(value["block_family"])
    block = _closed_object(
        value["block_spec"],
        frozenset(
            (
                "capabilities",
                "display_name",
                "health_path",
                "metadata",
                "role_id",
                "variant",
                "verification",
            )
        ),
    )
    for capability in _safe_sequence(block["capabilities"]):
        _safe_identity(capability)
    _safe_identity(block["display_name"])
    if block["health_path"] is not None:
        if type(block["health_path"]) is not str or _HTTP_PATH_PATTERN.fullmatch(block["health_path"]) is None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
    _closed_object(block["metadata"], frozenset())
    _safe_identity(block["role_id"])
    _safe_identity(block["variant"])
    verification = _closed_object(block["verification"], frozenset(("checks",)))
    for check in _safe_sequence(verification["checks"]):
        _validate_check(check)
    if _safe_sequence(value["configuration_artifacts"]):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    if type(value["endpoints"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, endpoint in value["endpoints"].items():
        _safe_identity(key)
        endpoint = _closed_object(endpoint, frozenset(("address", "protocol", "scope")))
        if endpoint["address"] != "<redacted>":
            raise CandidateTopologyError(WORKFLOW_ERROR)
        _validate_protocol(endpoint["protocol"])
        _safe_identity(endpoint["scope"])
    for binding in _safe_sequence(value["environment_bindings"]):
        if type(binding) is not dict or frozenset(binding) not in {
            frozenset(("kind", "name", "value")),
            frozenset(("edge_id", "kind", "name", "value")),
        }:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if "edge_id" in binding:
            _safe_identity(binding["edge_id"])
        _safe_identity(binding["kind"])
        _safe_identity(binding["name"])
        if binding["value"] != "<redacted>":
            raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["kind"])
    _validate_lifecycle(value["lifecycle"])
    metadata = _closed_object(
        value["metadata"],
        frozenset(
            (
                "block_family",
                "capabilities",
                "display_name",
                "oci_image",
                "product_descriptor_digest",
                "product_identity",
            )
        ),
    )
    _safe_identity(metadata["block_family"])
    for capability in _safe_sequence(metadata["capabilities"]):
        capability = _closed_object(
            capability,
            frozenset(("description", "label", "name", "route_set")),
        )
        _safe_text(capability["description"])
        _safe_identity(capability["label"])
        _safe_identity(capability["name"])
        _safe_identity(capability["route_set"])
    _safe_identity(metadata["display_name"])
    if type(metadata["oci_image"]) is not str or _IMAGE_PATTERN.fullmatch(metadata["oci_image"]) is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    if type(metadata["product_descriptor_digest"]) is not str or _DIGEST_PATTERN.fullmatch(metadata["product_descriptor_digest"]) is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_text(metadata["product_identity"])
    _safe_identity(value["node_id"])
    if type(value["providers"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, provider in value["providers"].items():
        _safe_identity(key)
        provider = _closed_object(provider, frozenset(("protocol",)))
        _validate_protocol(provider["protocol"])
    if type(value["requirements"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, requirement in value["requirements"].items():
        _safe_identity(key)
        requirement = _closed_object(
            requirement,
            frozenset(("binding", "env_bindings", "protocol", "required")),
        )
        _safe_identity(requirement["binding"])
        for name in _safe_sequence(requirement["env_bindings"]):
            _safe_identity(name)
        _validate_protocol(requirement["protocol"])
        if type(requirement["required"]) is not bool:
            raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["runtime_id"])
    if value["secret_deliveries"] != "<redacted>":
        raise CandidateTopologyError(WORKFLOW_ERROR)


def _validate_graph_readback(value: Any) -> None:
    compact_keys = frozenset(("activity", "graph_id"))
    if type(value) is dict and frozenset(value) == compact_keys:
        _safe_identity(value["graph_id"])
        for event in _safe_sequence(value["activity"]):
            _safe_identity(event)
        return
    value = _closed_object(
        value,
        frozenset(
            (
                "assigned",
                "authored_graph_id",
                "graph_descriptor",
                "graph_id",
                "graph_name",
                "pointer",
                "realized_projection_id",
                "version",
            )
        ),
    )
    if type(value["assigned"]) is not bool or type(value["version"]) is not int:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key in ("authored_graph_id", "graph_id", "graph_name", "realized_projection_id"):
        _safe_identity(value[key])
    if value["pointer"] != "current":
        raise CandidateTopologyError(WORKFLOW_ERROR)
    descriptor = _closed_object(
        value["graph_descriptor"],
        frozenset(("edges", "name", "nodes", "public_ingresses", "runtimes")),
    )
    _safe_identity(descriptor["name"])
    if _safe_sequence(descriptor["public_ingresses"]):
        raise CandidateTopologyError(WORKFLOW_ERROR)
    if type(descriptor["nodes"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, node in descriptor["nodes"].items():
        _safe_identity(key)
        _validate_node(node)
    if type(descriptor["edges"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, edge in descriptor["edges"].items():
        _safe_identity(key)
        edge = _closed_object(
            edge,
            frozenset(("binding", "consumer", "edge_id", "env_assignments", "protocol", "provider")),
        )
        _safe_identity(edge["binding"])
        for party, party_keys in (
            (edge["consumer"], frozenset(("requirement", "role"))),
            (edge["provider"], frozenset(("role", "socket"))),
        ):
            party = _closed_object(party, party_keys)
            for item in party.values():
                _safe_identity(item)
        _safe_identity(edge["edge_id"])
        if edge["env_assignments"] != "<redacted>":
            raise CandidateTopologyError(WORKFLOW_ERROR)
        _validate_protocol(edge["protocol"])
    if type(descriptor["runtimes"]) is not dict:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    for key, runtime in descriptor["runtimes"].items():
        _safe_identity(key)
        runtime = _closed_object(
            runtime,
            frozenset(("authority_ref", "children", "kind", "lifecycle", "metadata")),
        )
        if runtime["authority_ref"] is not None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        for child in _safe_sequence(runtime["children"]):
            _safe_identity(child)
        _safe_identity(runtime["kind"])
        _validate_lifecycle(runtime["lifecycle"])
        metadata = _closed_object(runtime["metadata"], frozenset(("network_name",)))
        _safe_identity(metadata["network_name"])


def _validate_activity_history(value: Any) -> None:
    if type(value) is dict and frozenset(value) == frozenset(("events",)):
        for event in _safe_sequence(value["events"]):
            _safe_identity(event)
        return
    value = _closed_object(
        value,
        frozenset(("items", "kind", "limit", "next_cursor", "workspace_id")),
    )
    if type(value["limit"]) is not int or value["limit"] < 1 or value["next_cursor"] is not None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    _safe_identity(value["kind"])
    _safe_identity(value["workspace_id"])
    for item in _safe_sequence(value["items"]):
        item = _closed_object(
            item,
            frozenset(("actor_id", "closed_at", "created_at", "metadata", "session_id", "status", "title", "workspace_id")),
        )
        for key in ("actor_id", "session_id", "status", "title", "workspace_id"):
            _safe_identity(item[key])
        if type(item["created_at"]) is not str or _TIMESTAMP_PATTERN.fullmatch(item["created_at"]) is None:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if item["closed_at"] is not None and (
            type(item["closed_at"]) is not str
            or _TIMESTAMP_PATTERN.fullmatch(item["closed_at"]) is None
        ):
            raise CandidateTopologyError(WORKFLOW_ERROR)
        _closed_object(item["metadata"], frozenset())


@dataclass(frozen=True)
class _FrozenObject:
    values: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class _FrozenArray:
    values: tuple[Any, ...]
    source: str


def _freeze_json(value: Any, *, depth: int, items: list[int]) -> Any:
    if depth > 16:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    items[0] += 1
    if items[0] > 32768:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    if value is None or type(value) in {bool, int, float}:
        return value
    if type(value) is str:
        if len(value.encode("utf-8")) > 65536:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        _reject_protected_text(value)
        return value
    if type(value) is dict:
        if not all(type(key) is str and key for key in value):
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return _FrozenObject(
            tuple(
                (key, _freeze_json(value[key], depth=depth + 1, items=items))
                for key in sorted(value)
            )
        )
    if type(value) in {list, tuple}:
        return _FrozenArray(
            tuple(
                _freeze_json(item, depth=depth + 1, items=items)
                for item in value
            ),
            "tuple" if type(value) is tuple else "list",
        )
    raise CandidateTopologyError(WORKFLOW_ERROR)


def _thaw_json(value: Any) -> Any:
    if type(value) is _FrozenObject:
        return {key: _thaw_json(item) for key, item in value.values}
    if type(value) is _FrozenArray:
        items = tuple(_thaw_json(item) for item in value.values)
        return items if value.source == "tuple" else list(items)
    return value


@dataclass(frozen=True)
class _CandidateClosedProjection:
    _value: _FrozenObject

    @classmethod
    def _admit_validated(cls, value: Any) -> _CandidateClosedProjection:
        frozen = _freeze_json(value, depth=0, items=[0])
        if type(frozen) is not _FrozenObject:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        document = _thaw_json(frozen)
        canonical = json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if len(canonical) > 524288:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return cls(frozen)

    def to_document(self) -> dict[str, Any]:
        return _thaw_json(self._value)


@dataclass(frozen=True)
class CandidateGraphReadbackProjection(_CandidateClosedProjection):
    @classmethod
    def admit(cls, value: Any) -> CandidateGraphReadbackProjection:
        _validate_graph_readback(value)
        return cls._admit_validated(value)


@dataclass(frozen=True)
class CandidateActivityHistoryProjection(_CandidateClosedProjection):
    @classmethod
    def admit(cls, value: Any) -> CandidateActivityHistoryProjection:
        _validate_activity_history(value)
        return cls._admit_validated(value)


@dataclass(frozen=True)
class CandidateApprovalProjection:
    request_id: str
    required_scope: str
    max_risk: str
    destructive: bool
    plan_id: str

    @classmethod
    def admit(
        cls,
        value: Any,
        *,
        expected_plan_id: str,
    ) -> CandidateApprovalProjection:
        value = _closed_object(
            value,
            frozenset(
                (
                    "destructive",
                    "max_risk",
                    "plan_id",
                    "request_id",
                    "required_scope",
                )
            ),
        )
        request_id = _safe_identity(value["request_id"])
        plan_id = _safe_identity(value["plan_id"])
        if plan_id != expected_plan_id:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if value["required_scope"] not in {
            "plan:approve",
            "plan:approve-destructive",
        }:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if value["max_risk"] not in {"low", "moderate", "high", "destructive"}:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        if type(value["destructive"]) is not bool:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return cls(
            request_id=request_id,
            required_scope=value["required_scope"],
            max_risk=value["max_risk"],
            destructive=value["destructive"],
            plan_id=plan_id,
        )

    def __getitem__(self, key: str) -> object:
        if key not in {
            "request_id",
            "required_scope",
            "max_risk",
            "destructive",
            "plan_id",
        }:
            raise KeyError(key)
        return getattr(self, key)

    def to_document(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "required_scope": self.required_scope,
            "max_risk": self.max_risk,
            "destructive": self.destructive,
            "plan_id": self.plan_id,
        }


def _identity(value: Any) -> str:
    if type(value) is not str or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise CandidateTopologyError(WORKFLOW_ERROR)
    return value


@dataclass(frozen=True)
class CandidateProbeSpec:
    node_id: str
    image_reference: str
    expected_response: bytes

    def __post_init__(self) -> None:
        if (
            type(self.node_id) is not str
            or _NAME_PATTERN.fullmatch(self.node_id) is None
            or type(self.image_reference) is not str
            or _IMAGE_PATTERN.fullmatch(self.image_reference) is None
            or type(self.expected_response) is not bytes
            or not self.expected_response
            or len(self.expected_response) > 512
        ):
            raise CandidateTransitionProgramError(PROGRAM_ERROR)
        try:
            response = self.expected_response.decode("ascii")
        except UnicodeDecodeError:
            raise CandidateTransitionProgramError(PROGRAM_ERROR) from None
        try:
            _reject_protected_text(response)
        except CandidateTopologyError:
            raise CandidateTransitionProgramError(PROGRAM_ERROR) from None


@dataclass(frozen=True)
class CandidateTransitionSpec:
    stage: str
    graph: DeploymentGraph
    probe: CandidateProbeSpec | None


@dataclass(frozen=True)
class CandidateTransitionProgram:
    transitions: tuple[CandidateTransitionSpec, ...]

    def __post_init__(self) -> None:
        transitions = self.transitions
        if type(transitions) is not tuple or len(transitions) < 2:
            raise CandidateTransitionProgramError(PROGRAM_ERROR)
        stages: list[str] = []
        for transition in transitions:
            if (
                type(transition) is not CandidateTransitionSpec
                or type(transition.stage) is not str
                or _NAME_PATTERN.fullmatch(transition.stage) is None
                or type(transition.graph) is not DeploymentGraph
                or (
                    transition.probe is not None
                    and type(transition.probe) is not CandidateProbeSpec
                )
            ):
                raise CandidateTransitionProgramError(PROGRAM_ERROR)
            stages.append(transition.stage)
        if len(set(stages)) != len(stages):
            raise CandidateTransitionProgramError(PROGRAM_ERROR)
        unprobed = tuple(
            index
            for index, transition in enumerate(transitions)
            if transition.probe is None
        )
        if unprobed != (len(transitions) - 1,):
            raise CandidateTransitionProgramError(PROGRAM_ERROR)


@dataclass(frozen=True)
class CandidateProbeEvidence:
    node_id: str
    image_reference: str
    response: bytes
    container_id: str
    request_origin: str
    target_image_id: str
    target_image_reference: str

    @classmethod
    def admit(
        cls,
        spec: CandidateProbeSpec,
        value: Any,
    ) -> CandidateProbeEvidence:
        expected_keys = {
            "response",
            "container_id",
            "request_origin",
            "target_image_id",
            "target_image_reference",
        }
        if type(value) is not dict or set(value) != expected_keys:
            raise CandidateTopologyError(WORKFLOW_ERROR)
        response = value["response"]
        container_id = value["container_id"]
        request_origin = value["request_origin"]
        target_image_id = value["target_image_id"]
        target_image_reference = value["target_image_reference"]
        if (
            type(response) is not bytes
            or response != spec.expected_response
            or type(container_id) is not str
            or _IDENTITY_PATTERN.fullmatch(container_id) is None
            or request_origin != "inside-probe"
            or type(target_image_id) is not str
            or _IMAGE_ID_PATTERN.fullmatch(target_image_id) is None
            or target_image_reference != spec.image_reference
        ):
            raise CandidateTopologyError(WORKFLOW_ERROR)
        return cls(
            node_id=spec.node_id,
            image_reference=spec.image_reference,
            response=response,
            container_id=container_id,
            request_origin=request_origin,
            target_image_id=target_image_id,
            target_image_reference=target_image_reference,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "image_reference": self.image_reference,
            "response": self.response.decode("ascii"),
            "response_sha256": hashlib.sha256(self.response).hexdigest(),
            "container_id": self.container_id,
            "request_origin": self.request_origin,
            "target_image_id": self.target_image_id,
            "target_image_reference": self.target_image_reference,
        }


@dataclass(frozen=True)
class CandidateTransitionEvidence:
    stage: str
    current_graph_id: str
    plan_id: str
    run_id: str
    desired_graph_id: str
    advanced_graph_id: str
    predecessor_http: CandidateGraphReadbackProjection
    predecessor_mcp: CandidateGraphReadbackProjection
    successor_http: CandidateGraphReadbackProjection
    successor_mcp: CandidateGraphReadbackProjection
    probe: CandidateProbeEvidence | None

    def transition_document(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "desired_graph_id": self.desired_graph_id,
            "advanced_graph_id": self.advanced_graph_id,
            "predecessor_http": self.predecessor_http.to_document(),
            "predecessor_mcp": self.predecessor_mcp.to_document(),
            "successor_http": self.successor_http.to_document(),
            "successor_mcp": self.successor_mcp.to_document(),
        }

    def to_document(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "current_graph_id": self.current_graph_id,
            **self.transition_document(),
            "probe": None if self.probe is None else self.probe.to_document(),
        }


@dataclass(frozen=True)
class CandidateScenarioEvidence:
    transitions: tuple[CandidateTransitionEvidence, ...]
    history_http: CandidateActivityHistoryProjection
    history_mcp: CandidateActivityHistoryProjection

    def to_document(self) -> dict[str, Any]:
        return {
            "transitions": [
                transition.to_document() for transition in self.transitions
            ],
            "history_http": self.history_http.to_document(),
            "history_mcp": self.history_mcp.to_document(),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_document(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def _mark_stage(error: BaseException, stage: str, boundary: str) -> None:
    setattr(error, "candidate_transition_stage", stage)
    setattr(error, "candidate_transition_boundary", boundary)


def execute_candidate_transitions(
    workflow: CandidateWorkflowPort,
    effects: CandidateProbePort,
    program: CandidateTransitionProgram,
    *,
    current_graph_id: str,
) -> CandidateScenarioEvidence:
    if type(program) is not CandidateTransitionProgram:
        raise CandidateTransitionProgramError(PROGRAM_ERROR)
    active_graph_id = _identity(current_graph_id)
    expected_desired_graph_id: str | None = None
    evidence: list[CandidateTransitionEvidence] = []

    for spec in program.transitions:
        boundary = "workflow"
        try:
            if spec.probe is None:
                boundary = "probe-removal"
                effects.remove_probe()
                boundary = "workflow"
            session_id = _identity(workflow.start_session(spec.stage))
            desired_graph_id = _identity(
                workflow.set_desired_graph(
                    session_id=session_id,
                    graph=spec.graph,
                    title=spec.stage,
                    expected_desired_graph_id=expected_desired_graph_id,
                )
            )
            plan_id = _identity(
                workflow.plan_transition(
                    session_id=session_id,
                    title=spec.stage,
                    current_graph_id=active_graph_id,
                    desired_graph_id=desired_graph_id,
                )
            )
            approval = CandidateApprovalProjection.admit(
                workflow.request_approval(
                    session_id=session_id,
                    title=spec.stage,
                    plan_id=plan_id,
                ),
                expected_plan_id=plan_id,
            )
            approval_id = approval.request_id
            workflow.assert_approval_visible(approval_id, plan_id)
            workflow.approve(
                session_id=session_id,
                title=spec.stage,
                approval=approval,
            )
            request_id = _identity(
                workflow.admit(
                    session_id=session_id,
                    title=spec.stage,
                    plan_id=plan_id,
                    approval_id=approval_id,
                )
            )
            run_id = _identity(
                workflow.claim(title=spec.stage, request_id=request_id)
            )
            workflow.start_run(title=spec.stage, run_id=run_id)
            workflow.execute_to_completion(
                run_id,
                sync_runtime_networks=False,
            )
            predecessor_http = CandidateGraphReadbackProjection.admit(
                workflow.read_current_graph_http()
            )
            predecessor_mcp = CandidateGraphReadbackProjection.admit(
                workflow.read_current_graph_mcp()
            )
            if predecessor_http.to_document() != predecessor_mcp.to_document():
                raise CandidateTopologyError(WORKFLOW_ERROR)
            if predecessor_http.to_document().get("graph_id") != active_graph_id:
                raise CandidateTopologyError(WORKFLOW_ERROR)
            advanced_graph_id = _identity(
                workflow.advance_current_graph(
                    title=spec.stage,
                    run_id=run_id,
                    plan_id=plan_id,
                    current_graph_id=active_graph_id,
                    desired_graph_id=desired_graph_id,
                )
            )
            if advanced_graph_id != desired_graph_id:
                raise CandidateTopologyError(WORKFLOW_ERROR)
            successor_http = CandidateGraphReadbackProjection.admit(
                workflow.read_current_graph_http()
            )
            successor_mcp = CandidateGraphReadbackProjection.admit(
                workflow.read_current_graph_mcp()
            )
            if successor_http.to_document() != successor_mcp.to_document():
                raise CandidateTopologyError(WORKFLOW_ERROR)
            if successor_http.to_document().get("graph_id") != advanced_graph_id:
                raise CandidateTopologyError(WORKFLOW_ERROR)
            probe_evidence = None
            if spec.probe is not None:
                boundary = "probe"
                probe_evidence = CandidateProbeEvidence.admit(
                    spec.probe,
                    effects.probe_runtime_node(
                        node_id=spec.probe.node_id,
                        expected_image_reference=spec.probe.image_reference,
                        labelled=True,
                        attach_runtime_network=True,
                    ),
                )
            evidence.append(
                CandidateTransitionEvidence(
                    stage=spec.stage,
                    current_graph_id=active_graph_id,
                    plan_id=plan_id,
                    run_id=run_id,
                    desired_graph_id=desired_graph_id,
                    advanced_graph_id=advanced_graph_id,
                    predecessor_http=predecessor_http,
                    predecessor_mcp=predecessor_mcp,
                    successor_http=successor_http,
                    successor_mcp=successor_mcp,
                    probe=probe_evidence,
                )
            )
            active_graph_id = advanced_graph_id
            expected_desired_graph_id = desired_graph_id
        except BaseException as error:
            _mark_stage(error, spec.stage, boundary)
            raise

    try:
        history_http = CandidateActivityHistoryProjection.admit(
            workflow.read_activity_http()
        )
        history_mcp = CandidateActivityHistoryProjection.admit(
            workflow.read_activity_mcp()
        )
        if history_http.to_document() != history_mcp.to_document():
            raise CandidateTopologyError(WORKFLOW_ERROR)
    except BaseException as error:
        _mark_stage(error, program.transitions[-1].stage, "history")
        raise
    return CandidateScenarioEvidence(
        transitions=tuple(evidence),
        history_http=history_http,
        history_mcp=history_mcp,
    )
