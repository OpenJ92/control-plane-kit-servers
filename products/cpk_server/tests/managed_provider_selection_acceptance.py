"""Actual public management grants select fixed transports without contacting Docker."""
from dataclasses import replace
import json
from unittest.mock import patch

from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_interpreters.docker.sdk import DockerSdkClient, DockerUnixSocketClientConfig
from control_plane_kit_operations.managed_runtime_assignments import ManagedRuntimeSelectionService

from receiver_acceptance_operations import utc_now


def managed_provider_selection_acceptance(client, invoke, schema, authority):
    from control_plane_kit_servers_cpk_server.managed_health_placement import (
        DockerRuntimeCapabilityBinding, DockerRuntimeClientSelector, DockerRuntimePolicyBinding,
    )

    workspace, runtime, reference = "workspace-b", "docker", "managed-local"
    capability, other_capability = authority.capability_policy.capabilities
    config = DockerUnixSocketClientConfig("/var/run/synthetic-management-never-opened.sock", 5.0)
    other_config = DockerUnixSocketClientConfig("/var/run/synthetic-other-management-never-opened.sock", 5.0)
    administrator = authority.administration_policy.administrators[0]
    invoke(client, "http", "command.workspace-permission.grant", {
        "target": administrator.descriptor(), "scopes": [PolicyScope.RUNTIME_AUTHORITY_REGISTER.value,
            PolicyScope.RUNTIME_AUTHORITY_REVOKE.value],
        "expected_revision": 0, "idempotency_key": "management-runtime-authority-permission"})
    registration = {
        "authority_ref": reference, "runtime_kind": "docker", "authority": {"kind": "local-docker-socket"},
        "admitted_at": utc_now(), "idempotency_key": "management-runtime-registration"}
    registered = invoke(client, "http", "command.runtime-authority.register", registration)
    # Read the actual registered value for this library boundary; no history is seeded.
    with schema.unit_of_work() as uow:
        runtime_authority = uow.stores.runtime_authorities.get(workspace, RuntimeAuthorityReference(reference))
    assert runtime_authority.registration_id == registered["registration_id"]

    with patch.object(DockerSdkClient, "from_authority") as sdk, \
            patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
        selector = DockerRuntimeClientSelector((), capability_policy=authority.capability_policy,
            capability_bindings=(DockerRuntimeCapabilityBinding(capability, config),
                DockerRuntimeCapabilityBinding(other_capability, other_config)),
            unit_of_work_factory=schema.unit_of_work)

        def select(**changes):
            return selector.select(**{ "workspace_id": workspace, "runtime_id": runtime,
                "authority": runtime_authority, **changes})

        def require_selected(expected_config):
            selected = select()
            assert type(selected) is DockerRuntimePolicyBinding
            assert (selected.workspace_id, selected.runtime_id, selected.authority_ref) == (
                workspace, runtime, runtime_authority.authority_ref)
            assert selected.local_client_config is expected_config
            assert expected_config.socket_path not in repr(selected)

        assert select() is None
        grant = {"runtime_id": runtime, "authority_ref": reference,
            "registration_id": registered["registration_id"], "capability_id": capability.capability_id,
            "expected_revision": 0, "idempotency_key": "management-grant"}
        invoke(client, "http", "command.managed-runtime-access.grant", grant)
        require_selected(config)
        # Capture the owner's actual selected value, not a reconstructed permission
        # history or a claim that this fixture has admitted an execution attempt.
        original = ManagedRuntimeSelectionService(schema.unit_of_work,
            capability_policy=authority.capability_policy).select(
                workspace_id=workspace, runtime_id=runtime, authority=runtime_authority)
        assert select(workspace_id="workspace-a") is None
        assert select(runtime_id="unassigned-runtime") is None
        # Unknown registration is input refusal, not a simulated successful incarnation.
        assert select(authority=replace(runtime_authority, registration_id="unregistered-identity")) is None
        invoke(client, "http", "command.runtime-authority.register", {
            **registration, "authority_ref": "other-managed-local", "idempotency_key": "other-runtime-registration"})
        with schema.unit_of_work() as uow:
            other_authority = uow.stores.runtime_authorities.get(workspace,
                RuntimeAuthorityReference("other-managed-local"))
        assert select(authority=other_authority) is None
        record = invoke(client, "mcp", "read.managed-runtime-assignment", {
            "runtime_id": runtime, "authority_ref": reference})
        assert record["registration_id"] == registered["registration_id"]
        assert record["capability_id"] == capability.capability_id and record["status"] == "active"
        assert config.socket_path not in json.dumps(record)
        revoked = invoke(client, "mcp", "command.managed-runtime-access.revoke", {
            "runtime_id": runtime, "authority_ref": reference,
            "expected_revision": record["revision"], "idempotency_key": "management-revoke"})
        assert select() is None
        invoke(client, "http", "command.managed-runtime-access.grant", {
            **grant, "expected_revision": revoked["receipt"]["resulting_assignment"]["revision"],
            "capability_id": other_capability.capability_id,
            "idempotency_key": "management-regrant"})
        require_selected(other_config)
        mapped = selector.bind_admitted(original, workspace_id=workspace, runtime_id=runtime,
            authority=runtime_authority)
        assert mapped.local_client_config is config
        assert mapped.managed_target is original
        invoke(client, "mcp", "command.runtime-authority.revoke", {
            "authority_ref": reference, "idempotency_key": "management-runtime-revoke"})
        # The retained input still says active; the owner must observe current revocation.
        assert select() is None
        # The selected owner retains deterministic registration IDs. This is a
        # bounded refusal/no-revival check, never successful reincarnation proof.
        invoke(client, "http", "command.runtime-authority.register", {
            **registration, "idempotency_key": "management-reregister-refused"}, status=500)
        assert select() is None
        record = invoke(client, "http", "read.managed-runtime-assignment", {
            "runtime_id": runtime, "authority_ref": reference})
        assert record["status"] == "revoked" and record["registration_id"] == registered["registration_id"]
        sdk.assert_not_called()
        constructor.assert_not_called()
        ambient.assert_not_called()
