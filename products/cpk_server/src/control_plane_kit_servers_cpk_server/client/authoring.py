"""Pure, bounded receiver-control authoring for desired deployment graphs.

The Operations service owns accepted receiver identities.  This module only
selects those accepted facts, allocates explicitly introduced identities, and
materializes product-owned configuration values into a caller supplied graph.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from pathlib import Path
from typing import Callable
from uuid import uuid4

import control_plane_kit_core as core
from control_plane_kit_core.configuration import (
    ConfigurationArtifact,
    ConfigurationMediaType,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.receiver_configuration import (
    ReceiverNodeControlConfiguration,
    ReceiverNodeControlConfigurationCodec,
)
from control_plane_kit_core.topology import DeploymentGraph, Node
from control_plane_kit_core.topology.codec import DEFAULT_GRAPH_CODEC
from control_plane_kit_core.wrapper_configuration import (
    NodeControlVerificationConfiguration,
    WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    ARTIFACT_ID as GATEWAY_ROUTES_ARTIFACT_ID,
    CONFIGURATION_PATH as GATEWAY_ROUTES_PATH,
    GatewayHealthRelayConfiguration,
    GatewayHealthTargetBinding,
    gateway_health_relay_configuration_artifact,
)


_ERROR = "receiver graph could not be authored"
_GATEWAY_TARGET_IDENTITY = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_RECEIVER_ID = re.compile(r"[0-9a-f]{32}\Z")
_INPUT_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    LookupError,
    RecursionError,
    OverflowError,
)


class ReceiverAuthoringError(ValueError):
    """Fixed public refusal without leaking rejected candidate material."""


def _graph_reference(
    role: core.NodeControlGraphReferenceRole, value: object
) -> str:
    if type(value) is not str:
        raise ValueError
    core.NodeControlGraphReference(role, value)
    return value


def _opaque_coordinate(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > 512
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError
    return value


def _gateway_target_identity(value: object) -> str:
    if type(value) is not str or _GATEWAY_TARGET_IDENTITY.fullmatch(value) is None:
        raise ValueError
    return value


@dataclass(frozen=True, slots=True)
class ReceiverScope:
    node_id: str
    provider_socket_name: str

    def __post_init__(self) -> None:
        roles = core.NodeControlGraphReferenceRole
        _graph_reference(roles.NODE, self.node_id)
        _graph_reference(roles.PROVIDER_SOCKET, self.provider_socket_name)


@dataclass(frozen=True, slots=True)
class ReceiverIntroduction:
    scope: ReceiverScope
    artifact_id: str
    target_path: str

    def __post_init__(self) -> None:
        if type(self.scope) is not ReceiverScope:
            raise ValueError
        # ConfigurationArtifact remains the source of truth for slot grammar.
        ConfigurationArtifact(
            self.artifact_id,
            self.target_path,
            ConfigurationMediaType.JSON,
            "{}",
        )


@dataclass(frozen=True, slots=True)
class PendingReceiverContinuation:
    draft_id: str
    expected_head_revision: int
    scopes: tuple[ReceiverScope, ...]

    def __post_init__(self) -> None:
        _opaque_coordinate(self.draft_id)
        if type(self.expected_head_revision) is not int or self.expected_head_revision < 0:
            raise ValueError
        if (
            type(self.scopes) is not tuple
            or not self.scopes
            or not all(type(scope) is ReceiverScope for scope in self.scopes)
            or len(set(self.scopes)) != len(self.scopes)
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class GatewayHealthTargetIntent:
    target_id: str
    target_scope: ReceiverScope
    origin: str

    def __post_init__(self) -> None:
        _gateway_target_identity(self.target_id)
        if type(self.target_scope) is not ReceiverScope or type(self.origin) is not str:
            raise ValueError


@dataclass(frozen=True, slots=True)
class GatewayHealthRoutes:
    gateway_scope: ReceiverScope
    targets: tuple[GatewayHealthTargetIntent, ...]

    def __post_init__(self) -> None:
        if (
            type(self.gateway_scope) is not ReceiverScope
            or type(self.targets) is not tuple
            or not all(type(target) is GatewayHealthTargetIntent for target in self.targets)
            or len({target.target_id for target in self.targets}) != len(self.targets)
            or len({target.target_scope for target in self.targets}) != len(self.targets)
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class AuthoredDesiredGraph:
    path: Path
    introductions: tuple[ReceiverIntroduction, ...] = ()
    pending: PendingReceiverContinuation | None = None
    gateway_health_replacements: tuple[GatewayHealthRoutes, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or type(self.introductions) is not tuple
            or not all(type(value) is ReceiverIntroduction for value in self.introductions)
            or len({value.scope for value in self.introductions}) != len(self.introductions)
            or (self.pending is not None and type(self.pending) is not PendingReceiverContinuation)
            or type(self.gateway_health_replacements) is not tuple
            or not all(
                type(value) is GatewayHealthRoutes
                for value in self.gateway_health_replacements
            )
            or len(
                {value.gateway_scope for value in self.gateway_health_replacements}
            )
            != len(self.gateway_health_replacements)
        ):
            raise ValueError


def _reference(role: core.NodeControlGraphReferenceRole, value: str):
    return core.NodeControlGraphReference(role, value)


def _surface(graph: DeploymentGraph, scope: ReceiverScope):
    node = graph.node(scope.node_id)
    surfaces = tuple(
        value
        for value in node.block_spec.control_surfaces
        if value.provider_socket_name.value == scope.provider_socket_name
    )
    if len(surfaces) != 1:
        raise ValueError
    node.provider_socket(scope.provider_socket_name)
    profile = (
        core.WorkloadNodeControlSurfaceDeclarationProfile.V2
        if surfaces[0].health_reads
        else core.WorkloadNodeControlSurfaceDeclarationProfile.V1
    )
    declaration = core.WorkloadNodeControlSurfaceDeclaration(surfaces[0], profile=profile)
    return node, declaration


def _target(
    *, workspace_id: str, node: Node, scope: ReceiverScope, receiver_id: str
) -> core.NodeControlReceiverTarget:
    if _RECEIVER_ID.fullmatch(receiver_id) is None:
        raise ValueError
    roles = core.NodeControlGraphReferenceRole
    return core.NodeControlReceiverTarget(
        _reference(roles.WORKSPACE, workspace_id),
        _reference(roles.RUNTIME, node.runtime_id),
        _reference(roles.NODE, scope.node_id),
        _reference(roles.PROVIDER_SOCKET, scope.provider_socket_name),
        receiver_id,
    )


def _current_receivers(context: object) -> dict[ReceiverScope, dict]:
    if type(context) is not dict or context.get("profile") != "receiver-authoring-context.v1":
        raise ValueError
    current = context.get("current")
    if type(current) is not dict or type(current.get("receivers")) is not list:
        raise ValueError
    expectation = context.get("expectation")
    if (
        type(expectation) is not dict
        or set(expectation)
        != {
            "current_graph_id",
            "current_realized_projection_id",
            "desired_graph_id",
            "desired_realized_projection_id",
            "desired_graph_revision",
        }
        or current.get("graph_id") != expectation["current_graph_id"]
        or current.get("realized_projection_id")
        != expectation["current_realized_projection_id"]
    ):
        raise ValueError
    result = {}
    for entry in current["receivers"]:
        if type(entry) is not dict or type(entry.get("binding")) is not dict:
            raise ValueError
        binding = entry["binding"]
        if (
            entry.get("lifecycle") != "current"
            or binding.get("graph_id") != current.get("graph_id")
            or binding.get("realized_projection_id")
            != current.get("realized_projection_id")
        ):
            raise ValueError
        scope = ReceiverScope(binding["node_id"], binding["provider_socket_name"])
        if scope in result:
            raise ValueError
        result[scope] = entry
    return result


def _pending_receivers(
    context: object, continuation: PendingReceiverContinuation | None
) -> dict[ReceiverScope, dict]:
    if continuation is None:
        return {}
    if type(context) is not dict:
        raise ValueError
    pending = context.get("pending_draft")
    if (
        type(pending) is not dict
        or pending.get("draft_id") != continuation.draft_id
        or pending.get("head_revision") != continuation.expected_head_revision
        or type(pending.get("receivers")) is not list
    ):
        raise ValueError
    selected = set(continuation.scopes)
    result = {}
    for entry in pending["receivers"]:
        if type(entry) is not dict or type(entry.get("binding")) is not dict:
            raise ValueError
        binding = entry["binding"]
        scope = ReceiverScope(binding["node_id"], binding["provider_socket_name"])
        if scope in selected:
            if (
                entry.get("lifecycle") != "pending"
                or binding.get("graph_id") != pending.get("graph_id")
                or binding.get("realized_projection_id")
                != pending.get("realized_projection_id")
            ):
                raise ValueError
            if scope in result:
                raise ValueError
            result[scope] = entry
    if set(result) != selected:
        raise ValueError
    return result


def _selected_existing(
    graph: DeploymentGraph,
    workspace_id: str,
    scope: ReceiverScope,
    entry: dict,
) -> tuple[
    core.NodeControlReceiverTarget,
    core.WorkloadNodeControlSurfaceDeclaration,
    ConfigurationArtifact,
]:
    node, declaration = _surface(graph, scope)
    binding = entry["binding"]
    if (
        binding.get("workspace_id") != workspace_id
        or binding.get("runtime_id") != node.runtime_id
        or binding.get("node_id") != scope.node_id
        or binding.get("provider_socket_name") != scope.provider_socket_name
        or binding.get("declaration_identity") != declaration.identity().value
    ):
        raise ValueError
    artifact = ConfigurationArtifact.from_descriptor(entry["configuration_artifact"])
    if binding.get("selected_configuration_digest") != artifact.content_digest:
        raise ValueError
    configured = ReceiverNodeControlConfigurationCodec().decode_bytes(
        artifact.content.encode("utf-8")
    )
    expected = _target(
        workspace_id=workspace_id,
        node=node,
        scope=scope,
        receiver_id=binding["receiver_id"],
    )
    if configured.target != expected or configured.declaration != declaration:
        raise ValueError
    return expected, declaration, artifact


def _verifiers(
    raw: object, declaration: core.WorkloadNodeControlSurfaceDeclaration
) -> tuple[NodeControlVerificationConfiguration, ...]:
    if type(raw) is not dict or set(raw) != {"workload_verifier_configuration"}:
        raise ValueError
    document = raw["workload_verifier_configuration"]
    if type(document) is not dict or set(document) != {"verifiers"}:
        raise ValueError
    purposes = {core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ}
    if declaration.surface.variables:
        purposes.add(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL)
    if declaration.surface.health_reads:
        purposes.add(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
    admitted = []
    entries = document["verifiers"]
    if type(entries) is not list or not 1 <= len(entries) <= 3:
        raise ValueError
    for entry in entries:
        if (
            type(entry) is not dict
            or set(entry) != {"purpose", "issuer", "public_keys"}
            or type(entry["public_keys"]) is not list
            or not 1 <= len(entry["public_keys"]) <= 16
        ):
            raise ValueError
        purpose = core.DelegationKeyPurpose(entry["purpose"])
        if purpose not in purposes:
            continue
        keys = []
        for key in entry["public_keys"]:
            if (
                type(key) is not dict
                or set(key) != {"key_id", "algorithm", "public_key_pem"}
                or not all(type(key[name]) is str for name in key)
            ):
                raise ValueError
            keys.append(
                core.DelegationPublicKey(
                    key["key_id"],
                    core.DelegationKeyAlgorithm(key["algorithm"]),
                    key["public_key_pem"],
                )
            )
        admitted.append(
            NodeControlVerificationConfiguration(purpose, entry["issuer"], tuple(keys))
        )
    return tuple(admitted)


def _install_wrapper(
    graph: DeploymentGraph,
    introduction: ReceiverIntroduction,
    target: core.NodeControlReceiverTarget,
    declaration: core.WorkloadNodeControlSurfaceDeclaration,
    verifiers: tuple[NodeControlVerificationConfiguration, ...],
) -> DeploymentGraph:
    node = graph.node(introduction.scope.node_id)
    if any(
        artifact.artifact_id == introduction.artifact_id
        or artifact.target_path == introduction.target_path
        for artifact in node.configuration_artifacts
    ):
        raise ValueError
    if any(
        binding.name == WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
        for binding in node.public_environment + node.socket_environment
    ):
        raise ValueError
    configuration = ReceiverNodeControlConfiguration(target, declaration, verifiers)
    content = ReceiverNodeControlConfigurationCodec().encode_bytes(configuration)
    artifact = ConfigurationArtifact(
        introduction.artifact_id,
        introduction.target_path,
        ConfigurationMediaType.JSON,
        content.decode("utf-8"),
    )
    updated = replace(
        node,
        configuration_artifacts=(*node.configuration_artifacts, artifact),
        public_environment=(
            *node.public_environment,
            PublicStaticEnvironmentBinding(
                WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT,
                introduction.target_path,
            ),
        ),
    )
    return graph.update_node(updated)


def _install_selected_wrapper(
    graph: DeploymentGraph,
    scope: ReceiverScope,
    artifact: ConfigurationArtifact,
) -> DeploymentGraph:
    node, declaration = _surface(graph, scope)
    configured = ReceiverNodeControlConfigurationCodec().decode_bytes(
        artifact.content.encode("utf-8")
    )
    if configured.declaration != declaration:
        raise ValueError
    collisions = tuple(
        item
        for item in node.configuration_artifacts
        if item.artifact_id == artifact.artifact_id
        or item.target_path == artifact.target_path
    )
    if len(collisions) > 1 or (
        collisions
        and (
            collisions[0].artifact_id != artifact.artifact_id
            or collisions[0].target_path != artifact.target_path
        )
    ):
        raise ValueError
    bindings = tuple(
        item
        for item in node.public_environment + node.socket_environment
        if item.name == WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
    )
    if (
        len(bindings) > 1
        or bool(collisions) != bool(bindings)
        or (bindings and bindings[0].value != artifact.target_path)
    ):
        raise ValueError
    artifacts = (
        tuple(
            artifact if item == collisions[0] else item
            for item in node.configuration_artifacts
        )
        if collisions
        else (*node.configuration_artifacts, artifact)
    )
    public_environment = node.public_environment
    if not bindings:
        public_environment = (
            *public_environment,
            PublicStaticEnvironmentBinding(
                WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT,
                artifact.target_path,
            ),
        )
    return graph.update_node(
        replace(
            node,
            configuration_artifacts=artifacts,
            public_environment=public_environment,
        )
    )


def _replace_routes(
    graph: DeploymentGraph,
    routes: GatewayHealthRoutes,
    assignments: dict[
        ReceiverScope,
        tuple[core.NodeControlReceiverTarget, core.WorkloadNodeControlSurfaceDeclaration],
    ],
) -> DeploymentGraph:
    gateway_node, _ = _surface(graph, routes.gateway_scope)
    transit = gateway_node.block_spec.gateway_transit
    if (
        transit is None
        or transit.provider_socket_name != routes.gateway_scope.provider_socket_name
        or transit.protocol is not core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2
        or routes.gateway_scope not in assignments
    ):
        raise ValueError
    bindings = []
    for intent in routes.targets:
        if intent.target_scope not in assignments:
            raise ValueError
        target, declaration = assignments[intent.target_scope]
        bindings.append(
            GatewayHealthTargetBinding(
                intent.target_id, target, declaration, intent.origin
            )
        )
    artifact = gateway_health_relay_configuration_artifact(
        GatewayHealthRelayConfiguration(assignments[routes.gateway_scope][0], tuple(bindings))
    )
    collisions = tuple(
        item
        for item in gateway_node.configuration_artifacts
        if item.artifact_id == GATEWAY_ROUTES_ARTIFACT_ID
        or item.target_path == GATEWAY_ROUTES_PATH
    )
    if len(collisions) != 1 or (
        collisions[0].artifact_id != GATEWAY_ROUTES_ARTIFACT_ID
        or collisions[0].target_path != GATEWAY_ROUTES_PATH
    ):
        raise ValueError
    updated = replace(
        gateway_node,
        configuration_artifacts=tuple(
            artifact if item == collisions[0] else item
            for item in gateway_node.configuration_artifacts
        ),
    )
    return graph.update_node(updated)


def author_receiver_graph(
    graph: DeploymentGraph,
    *,
    workspace_id: str,
    context: object,
    verifier_configuration: object,
    introductions: tuple[ReceiverIntroduction, ...] = (),
    pending: PendingReceiverContinuation | None = None,
    gateway_health_replacements: tuple[GatewayHealthRoutes, ...] = (),
    receiver_identity_factory: Callable[[], str] = lambda: uuid4().hex,
) -> DeploymentGraph:
    """Return one fully materialized graph or a fixed, candidate-free refusal."""
    try:
        if type(graph) is not DeploymentGraph:
            raise ValueError
        _graph_reference(core.NodeControlGraphReferenceRole.WORKSPACE, workspace_id)
        if (
            type(introductions) is not tuple
            or not all(type(item) is ReceiverIntroduction for item in introductions)
            or len({item.scope for item in introductions}) != len(introductions)
            or pending is not None and type(pending) is not PendingReceiverContinuation
            or type(gateway_health_replacements) is not tuple
            or not all(type(item) is GatewayHealthRoutes for item in gateway_health_replacements)
            or len({item.gateway_scope for item in gateway_health_replacements})
            != len(gateway_health_replacements)
            or not callable(receiver_identity_factory)
        ):
            raise ValueError
        if context.get("workspace_id") != workspace_id:
            raise ValueError
        current = _current_receivers(context)
        pending_entries = _pending_receivers(context, pending)
        introduced_scopes = {item.scope for item in introductions}
        if (
            introduced_scopes & (set(current) | set(pending_entries))
            or set(current) & set(pending_entries)
        ):
            raise ValueError

        required = {
            scope
            for replacement in gateway_health_replacements
            for scope in (
                replacement.gateway_scope,
                *(target.target_scope for target in replacement.targets),
            )
        }
        required |= introduced_scopes
        required |= set(pending_entries)
        required |= {
            ReceiverScope(node.node_id, surface.provider_socket_name.value)
            for node in graph.nodes.values()
            for surface in node.block_spec.control_surfaces
        }
        assignments = {}
        selected_artifacts = {}
        for scope in required - introduced_scopes:
            entry = pending_entries.get(scope, current.get(scope))
            if entry is None:
                raise ValueError
            target, declaration, artifact = _selected_existing(
                graph, workspace_id, scope, entry
            )
            assignments[scope] = (target, declaration)
            selected_artifacts[scope] = artifact

        pending_installations = []
        for introduction in introductions:
            node, declaration = _surface(graph, introduction.scope)
            if node.block_spec.gateway_transit is not None:
                raise ValueError
            receiver_id = receiver_identity_factory()
            if type(receiver_id) is not str or _RECEIVER_ID.fullmatch(receiver_id) is None:
                raise ValueError
            target = _target(
                workspace_id=workspace_id,
                node=node,
                scope=introduction.scope,
                receiver_id=receiver_id,
            )
            selected_verifiers = _verifiers(verifier_configuration, declaration)
            assignments[introduction.scope] = (target, declaration)
            pending_installations.append(
                (introduction, target, declaration, selected_verifiers)
            )

        result = graph
        for replacement in gateway_health_replacements:
            result = _replace_routes(result, replacement, assignments)

        for scope, artifact in selected_artifacts.items():
            result = _install_selected_wrapper(result, scope, artifact)
        for introduction, target, declaration, selected_verifiers in pending_installations:
            result = _install_wrapper(
                result, introduction, target, declaration, selected_verifiers
            )

        # Make Core's public codec the final authority for graph validity.
        encoded = DEFAULT_GRAPH_CODEC.encode(result)
        return DEFAULT_GRAPH_CODEC.decode(encoded)
    except _INPUT_ERRORS:
        failure = ReceiverAuthoringError(_ERROR)
    raise failure from None


__all__ = (
    "AuthoredDesiredGraph",
    "GatewayHealthRoutes",
    "GatewayHealthTargetIntent",
    "PendingReceiverContinuation",
    "ReceiverAuthoringError",
    "ReceiverIntroduction",
    "ReceiverScope",
    "author_receiver_graph",
)
