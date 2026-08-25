"""Typed transition execution for candidate live acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
_PROTECTED_TEXT = (
    "authorization:",
    "bearer ",
    "credential",
    "docker.sock",
    "exception",
    "password",
    "raw provider",
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

    def set_desired_graph(self, **kwargs: Any) -> str: ...

    def plan_transition(self, **kwargs: Any) -> str: ...

    def request_approval(self, **kwargs: Any) -> dict[str, Any]: ...

    def assert_approval_visible(self, approval_id: str, plan_id: str) -> None: ...

    def approve(self, **kwargs: Any) -> None: ...

    def admit(self, **kwargs: Any) -> str: ...

    def claim(self, **kwargs: Any) -> str: ...

    def start_run(self, **kwargs: Any) -> None: ...

    def execute_to_completion(
        self,
        run_id: str,
        *,
        sync_runtime_networks: bool,
    ) -> None: ...

    def read_current_graph_http(self) -> dict[str, Any]: ...

    def read_current_graph_mcp(self) -> dict[str, Any]: ...

    def advance_current_graph(self, **kwargs: Any) -> str: ...

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
    if (
        "://" in lowered
        or any(token in lowered for token in _PROTECTED_TEXT)
        or _IPV4_PATTERN.search(value) is not None
    ):
        raise CandidateTopologyError(WORKFLOW_ERROR)


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
class CandidatePublicProjection:
    _value: _FrozenObject

    @classmethod
    def admit(cls, value: Any) -> CandidatePublicProjection:
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
    predecessor_http: CandidatePublicProjection
    predecessor_mcp: CandidatePublicProjection
    successor_http: CandidatePublicProjection
    successor_mcp: CandidatePublicProjection
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
    history_http: CandidatePublicProjection
    history_mcp: CandidatePublicProjection

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
            approval = workflow.request_approval(
                session_id=session_id,
                title=spec.stage,
                plan_id=plan_id,
            )
            if type(approval) is not dict or "request_id" not in approval:
                raise CandidateTopologyError(WORKFLOW_ERROR)
            approval_id = _identity(approval["request_id"])
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
            predecessor_http = CandidatePublicProjection.admit(
                workflow.read_current_graph_http()
            )
            predecessor_mcp = CandidatePublicProjection.admit(
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
            successor_http = CandidatePublicProjection.admit(
                workflow.read_current_graph_http()
            )
            successor_mcp = CandidatePublicProjection.admit(
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
        history_http = CandidatePublicProjection.admit(
            workflow.read_activity_http()
        )
        history_mcp = CandidatePublicProjection.admit(
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
