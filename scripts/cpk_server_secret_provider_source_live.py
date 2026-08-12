"""Source-live cpk-server acceptance against a real durable secrets provider."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import docker
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt
import psycopg

from control_plane_kit_core.algebra import (
    DeploymentTopology,
    DockerRuntime,
    SocketConnection,
)
from control_plane_kit_core.delegation_authority import DelegationAuthorityBinding
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.gateway_delegation import (
    DelegatedGatewayProbeGrant,
    GatewayProbeAccessPath,
    GatewayProbeCommandKind,
    GatewayProbeRequest,
)
from control_plane_kit_core.products import (
    ProductDescriptorCodec,
    ProductInstanceConfiguration,
    instantiate_product,
)
from control_plane_kit_core.public_ingress import PublicIngressLifecycle
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.runtime_effects import GatewayTargetId
from control_plane_kit_core.topology import DeploymentGraph, compile_topology
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.verification import VerificationContract, VerificationPolicy
from control_plane_kit_interpreters.timing import verification_attempts

from cpk_server_hosted_activity import (
    AUTHORIZATION,
    GATEWAY_PROBE_KEY_ID,
    LOCAL_DOCKER_AUTHORITY_REF,
    GATEWAY_PROBE_ISSUER,
    HostedWorkflow,
    _assert_activity_mentions,
    _assert_gateway_probe_succeeded,
    _assert_no_node_containers,
    _assert_no_runtime_networks,
    _assert_public_gateway_authenticated_http_probe,
    _assert_public_gateway_unreachable,
    _assert_runtime_activity_mentions,
    _assert_secret_absent_from_activity,
    _bootstrap_workspace,
    _clock,
    _disconnect_runtime_networks,
    _events_for_run,
    _http,
    _mcp_read,
    _mcp_tool,
    _product_document,
    _public_gateway_ingress_graph,
    _public_gateway_overlay,
    _single_hello_graph,
    _single_docker_container,
    _sync_runtime_networks,
    _with_public_environment,
    _wait_public_gateway_ready,
)
from cpk_server_source_live_abort import (
    ExactOwnedIngressResource,
    SourceLiveAbortError,
    SourceLiveCheckpoint,
    compensate_abort,
    read_checkpoint,
    record_checkpoint,
)


PROVIDER_ID = "control-plane-kit"
PROVIDER_ENDPOINT_REFERENCE = "source-live-secrets"
PROVIDER_CREDENTIAL_REFERENCE = "secret://bootstrap/provider/client-token"
WRONG_PROVIDER_CREDENTIAL_REFERENCE = "secret://bootstrap/provider/wrong-token"
POSTGRES_PASSWORD_REFERENCE = "secret://control-plane-kit/postgres/password"
POSTGRES_INTENT = "postgres.password"
APPLICATION_TOKEN_INTENT = "application.control-token"
CLOUDFLARE_API_TOKEN_REFERENCE = (
    "secret://control-plane-kit/cloudflare/openj92/api-token"
)
CLOUDFLARE_GENERATED_REFERENCE_PREFIX = (
    "secret://control-plane-kit/cloudflare/openj92/generated-source-live"
)
GATEWAY_SIGNING_KEY_REFERENCE = (
    "secret://control-plane-kit/gateway/source-live-signing-key"
)
GATEWAY_VERIFIER_KEY_REFERENCE = (
    "secret://control-plane-kit/gateway/source-live-rotation-key-a"
)
GHCR_PULL_CREDENTIAL_REFERENCE = (
    "secret://control-plane-kit/oci/ghcr-source-live-credential"
)
CLOUDFLARE_API_TOKEN_INTENT = "cloudflare.api-token"
CLOUDFLARE_TUNNEL_TOKEN_INTENT = "cloudflare.tunnel-token"
GATEWAY_SIGNING_KEY_INTENT = "gateway.probe-signing-key"
OCI_PULL_CREDENTIAL_INTENT = "oci.pull-credential"
WORKER_AUTHORIZATION = "Bearer worker-present"
NO_SECRET_WORKER_AUTHORIZATION = "Bearer worker-no-secret"
SUCCESS_WORKSPACE = "workspace-secret-provider-live"
REVOKED_BEFORE_USE_WORKSPACE = "workspace-secret-revoked-before-use"
CONCURRENT_WORKSPACES = (
    "workspace-secret-concurrent-a",
    "workspace-secret-concurrent-b",
    "workspace-secret-concurrent-c",
)
PROVIDER_BASE_URL = "http://cpk-secrets:8081"
CONTAINER_RESTART_TIMEOUT_SECONDS = 30
CONTAINER_RESTART_STABILITY_SECONDS = 1.0
GATEWAY_VERIFIER_WORKSPACE = "workspace-gateway-key-rotation"
GATEWAY_BOOTSTRAP_WORKSPACE = "workspace-gateway-key-bootstrap"
GATEWAY_VERIFIER_ISSUER = "cpk-source-live-rotation"
GATEWAY_VERIFIER_KEY_ID = "source-live-rotation-key-a"
PUBLIC_GATEWAY_PROBE_POLICY = VerificationPolicy(
    timeout_seconds=5,
    interval_seconds=2,
    maximum_attempts=5,
)


@dataclass(frozen=True)
class PreparedRun:
    run_id: str
    plan_id: str
    current_graph_id: str
    desired_graph_id: str


@dataclass(frozen=True)
class CloudflareInventorySnapshot:
    dns_record_count: int
    dns_record_digest: str
    active_tunnel_count: int
    active_tunnel_digest: str

    def __post_init__(self) -> None:
        for count in (self.dns_record_count, self.active_tunnel_count):
            if type(count) is not int or count < 0 or count > 100_000:
                raise RuntimeError("protected Cloudflare inventory count was invalid")
        for digest in (self.dns_record_digest, self.active_tunnel_digest):
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise RuntimeError("protected Cloudflare inventory digest was invalid")

    def descriptor(self) -> dict[str, object]:
        return {
            "dns_record_count": self.dns_record_count,
            "dns_record_digest": self.dns_record_digest,
            "active_tunnel_count": self.active_tunnel_count,
            "active_tunnel_digest": self.active_tunnel_digest,
        }


@dataclass(frozen=True)
class ExactFailedDockerNodeEffect:
    workspace_id: str
    run_id: str
    plan_id: str
    desired_graph_id: str
    activity_id: str
    runtime_id: str
    node_id: str
    container_name: str

    def __post_init__(self) -> None:
        for name in (
            "workspace_id",
            "run_id",
            "plan_id",
            "desired_graph_id",
            "activity_id",
            "runtime_id",
            "node_id",
            "container_name",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", value)
                is None
            ):
                raise RuntimeError("failed connector evidence is uncertain")

    def expected_labels(self) -> dict[str, str]:
        return {
            "org.openj92.cpk.kind": "container",
            "org.openj92.cpk.workspace": self.workspace_id,
            "org.openj92.cpk.runtime": self.runtime_id,
            "org.openj92.cpk.node": self.node_id,
            "org.openj92.cpk.plan": self.plan_id,
            "org.openj92.cpk.desired-graph": self.desired_graph_id,
        }

    def bounded_descriptor(self) -> dict[str, str]:
        return {
            "workspace_id": self.workspace_id,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "desired_graph_id": self.desired_graph_id,
            "activity_id": self.activity_id,
            "runtime_id": self.runtime_id,
            "node_id": self.node_id,
            "container_name": self.container_name,
        }


@dataclass(frozen=True)
class ProviderVersionReceipt:
    version_id: str
    version_number: int


class SourceLiveGatewayDenialError(RuntimeError):
    """Bounded source-live gateway denial witness failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(repr=False)
class PostgresTransactionWitness:
    """Detect target database IO after accounting for its own measurements."""

    snapshot: Callable[[], int]
    measurement_overhead: int
    _last_snapshot: int

    @classmethod
    def calibrate(
        cls,
        snapshot: Callable[[], int],
    ) -> "PostgresTransactionWitness":
        first = snapshot()
        second = snapshot()
        third = snapshot()
        first_delta = second - first
        second_delta = third - second
        if first_delta < 1 or first_delta != second_delta:
            raise SourceLiveGatewayDenialError("postgres-witness-unstable")
        return cls(snapshot, first_delta, third)

    def assert_no_target_io(self, action: Callable[[], None]) -> None:
        action()
        current = self.snapshot()
        observed_delta = current - self._last_snapshot
        self._last_snapshot = current
        if observed_delta != self.measurement_overhead:
            raise SourceLiveGatewayDenialError("postgres-target-io-observed")

    def synchronize(self) -> None:
        self._last_snapshot = self.snapshot()

    def __repr__(self) -> str:
        return "PostgresTransactionWitness(<bounded>)"


def main() -> int:
    base_url = _required_env("CPK_HOSTED_ACTIVITY_BASE_URL").rstrip("/")
    server_container = _required_env("CPK_HOSTED_ACTIVITY_SERVER_CONTAINER")
    provider_container = _required_env("CPK_SECRET_PROVIDER_CONTAINER")
    servers_repo = Path(_required_env("CPK_HOSTED_ACTIVITY_SERVERS_REPO"))
    operations_database_url = _required_env("CPK_OPERATIONS_DATABASE_URL")
    provider_token_file = Path(_required_env("CPK_SECRET_PROVIDER_TOKEN_FILE"))
    bootstrap_dir = Path(_required_env("CPK_SECRET_PROVIDER_BOOTSTRAP_DIR"))
    if os.environ.get("CPK_SECRET_PROVIDER_SOURCE_LIVE_MODE") == "abort-cleanup":
        return _run_cloudflare_abort_cleanup(
            base_url=base_url,
            server_container=server_container,
            operations_database_url=operations_database_url,
            provider_container=provider_container,
            provider_token_file=provider_token_file,
            bootstrap_dir=bootstrap_dir,
        )
    if (
        os.environ.get("CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO")
        == "gateway-delegation-bootstrap"
    ):
        _run_gateway_delegation_bootstrap(
            base_url=base_url,
            server_container=server_container,
            provider_container=provider_container,
            servers_repo=servers_repo,
            provider_token_file=provider_token_file,
            bootstrap_dir=bootstrap_dir,
        )
        print("cpk-server gateway delegation bootstrap source-live acceptance passed")
        return 0
    if (
        os.environ.get("CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO")
        == "gateway-verifier-projection"
    ):
        _run_gateway_verifier_projection(
            base_url=base_url,
            server_container=server_container,
            provider_container=provider_container,
            servers_repo=servers_repo,
            operations_database_url=operations_database_url,
            provider_token_file=provider_token_file,
            bootstrap_dir=bootstrap_dir,
        )
        print("cpk-server gateway verifier projection source-live acceptance passed")
        return 0
    if (
        os.environ.get("CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO")
        == "cloudflare-tunnel-custody"
    ):
        _run_cloudflare_tunnel_custody(
            base_url=base_url,
            server_container=server_container,
            provider_container=provider_container,
            servers_repo=servers_repo,
            operations_database_url=operations_database_url,
            provider_token_file=provider_token_file,
            bootstrap_dir=bootstrap_dir,
        )
        print("cpk-server Cloudflare generated-secret custody acceptance passed")
        return 0

    cpk_server_document = _product_document(servers_repo, "cpk_server")
    postgres_document = _product_document(servers_repo, "postgres_server")
    success = _workflow(
        base_url,
        server_container,
        workspace_id=SUCCESS_WORKSPACE,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    success.wait_ready()
    current_graph_id = _bootstrap_workspace(
        success,
        name="Secret provider source-live success",
        product_documents={"postgres": postgres_document},
        register_runtime_authority=True,
        register_runtime_delivery=False,
    )
    _register_provider_and_reference(success)
    _assert_provider_metadata_is_secret_free(success)
    _provider_write_secret(
        workspace_id=SUCCESS_WORKSPACE,
        value_file=bootstrap_dir / "postgres-password",
        provider_token_file=provider_token_file,
        correlation_id="source-live-bootstrap-write-a",
    )

    _restart_provider(provider_container)
    _restart_cpk_server(
        server_container,
        success,
        ready_policy=_verification_policy(cpk_server_document, "ready"),
    )
    deployed_a = success.run_approved_transition(
        title="Secret provider source-live deploy A",
        graph=_postgres_graph(
            postgres_document,
            SUCCESS_WORKSPACE,
            node_ids=("postgres-a",),
        ),
        current_graph_id=current_graph_id,
    )
    _assert_activity_mentions(success, deployed_a.run_id, "postgres-a")
    _assert_provider_and_operations_correlation(
        provider_container=provider_container,
        operations_database_url=operations_database_url,
        workspace_id=SUCCESS_WORKSPACE,
    )
    first_resolution = _latest_successful_resolution(
        provider_container,
        SUCCESS_WORKSPACE,
    )
    version_a = first_resolution["version_id"]

    version_b = _provider_rotate_secret(
        workspace_id=SUCCESS_WORKSPACE,
        value_file=bootstrap_dir / "postgres-password-v2",
        provider_token_file=provider_token_file,
        correlation_id="source-live-rotate-b",
    )
    if version_b == version_a:
        raise RuntimeError("secret rotation did not create a new version")
    replayed_version = _provider_resolve_metadata(
        workspace_id=SUCCESS_WORKSPACE,
        provider_token_file=provider_token_file,
        caller_subject=first_resolution["caller_subject"],
        correlation_id=first_resolution["correlation_id"],
    )
    if replayed_version != version_a:
        raise RuntimeError("exact provider correlation did not remain pinned")

    deployed_b = success.run_approved_transition(
        title="Secret provider source-live deploy B",
        graph=_postgres_graph(
            postgres_document,
            SUCCESS_WORKSPACE,
            node_ids=("postgres-a", "postgres-b"),
        ),
        current_graph_id=deployed_a.current_graph_id,
        expected_desired_graph_id=deployed_a.desired_graph_id,
    )
    _assert_activity_mentions(success, deployed_b.run_id, "postgres-b")
    _assert_run_resolved_version(
        provider_container=provider_container,
        operations_database_url=operations_database_url,
        workspace_id=SUCCESS_WORKSPACE,
        run_id=deployed_b.run_id,
        expected_version_id=version_b,
    )
    _assert_provider_version_history(
        provider_container,
        workspace_id=SUCCESS_WORKSPACE,
        expected_versions={version_a, version_b},
    )
    _assert_activity_is_secret_free(success)
    _disconnect_runtime_networks(
        success.server_container,
        workspace_id=SUCCESS_WORKSPACE,
    )
    removed = success.run_approved_transition(
        title="Secret provider source-live teardown",
        graph=DeploymentGraph(SUCCESS_WORKSPACE),
        current_graph_id=deployed_b.current_graph_id,
        expected_desired_graph_id=deployed_b.desired_graph_id,
        sync_runtime_networks=False,
    )
    _assert_activity_mentions(success, removed.run_id, "postgres-a")
    _assert_activity_mentions(success, removed.run_id, "postgres-b")
    _assert_no_node_containers(SUCCESS_WORKSPACE, "postgres-a")
    _assert_no_node_containers(SUCCESS_WORKSPACE, "postgres-b")

    _assert_resolution_revoke_race(
        provider_container=provider_container,
        operations_database_url=operations_database_url,
        workspace_id=SUCCESS_WORKSPACE,
        provider_token_file=provider_token_file,
        first_resolution=first_resolution,
    )
    _run_revoked_before_use(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        provider_token_file=provider_token_file,
        value_file=bootstrap_dir / "postgres-revoked",
    )
    _run_concurrent_workspace_uses(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        operations_database_url=operations_database_url,
        provider_token_file=provider_token_file,
        bootstrap_dir=bootstrap_dir,
    )

    _run_denial_matrix(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
    )
    print("cpk-server durable secret-provider source-live acceptance passed")
    return 0


def _run_gateway_delegation_bootstrap(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    servers_repo: Path,
    provider_token_file: Path,
    bootstrap_dir: Path,
) -> None:
    cpk_server_document = _product_document(servers_repo, "cpk_server")
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=GATEWAY_BOOTSTRAP_WORKSPACE,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    workflow.wait_ready()
    _bootstrap_workspace(
        workflow,
        name="Gateway delegation bootstrap source-live",
        product_documents={},
        register_runtime_authority=False,
        register_runtime_delivery=False,
    )
    private_key_file = bootstrap_dir / "gateway-rotation-key-a.pem"
    public_key_file = bootstrap_dir / "gateway-rotation-key-a-public.pem"
    _provider_write_secret(
        workspace_id=GATEWAY_BOOTSTRAP_WORKSPACE,
        reference=GATEWAY_VERIFIER_KEY_REFERENCE,
        intent=GATEWAY_SIGNING_KEY_INTENT,
        value_file=private_key_file,
        provider_token_file=provider_token_file,
        correlation_id="gateway-delegation-bootstrap-write",
    )
    arguments = {
        "provider_id": PROVIDER_ID,
        "provider_display_name": "Ephemeral hosted acceptance custody",
        "provider_endpoint_reference": PROVIDER_ENDPOINT_REFERENCE,
        "provider_credential_reference": PROVIDER_CREDENTIAL_REFERENCE,
        "private_key_reference": GATEWAY_VERIFIER_KEY_REFERENCE,
        "issuer": GATEWAY_VERIFIER_ISSUER,
        "key_id": GATEWAY_VERIFIER_KEY_ID,
        "public_key_pem": public_key_file.read_text(encoding="ascii"),
        "admitted_at": "2026-08-04T10:00:00Z",
        "activated_at": "2026-08-04T10:00:01Z",
        "metadata": {"acceptance": "ephemeral-hosted-source-live"},
    }
    admitted = workflow.admit_gateway_delegation_key(**arguments)
    _assert_gateway_bootstrap_key(admitted)

    _restart_provider(provider_container)
    _restart_cpk_server(
        server_container,
        workflow,
        ready_policy=_verification_policy(cpk_server_document, "ready"),
    )
    replayed = workflow.admit_gateway_delegation_key(**arguments)
    _assert_gateway_bootstrap_key(replayed)
    if replayed["registration_id"] != admitted["registration_id"]:
        raise RuntimeError("delegation bootstrap replay changed key identity")
    verifier = _gateway_verifier_configuration(workflow)
    _assert_verifier_key_ids(verifier, {GATEWAY_VERIFIER_KEY_ID})
    _assert_secret_absent_from_activity(
        workflow,
        private_key_file.read_text(encoding="ascii"),
    )


def _assert_gateway_bootstrap_key(value: dict[str, Any]) -> None:
    expected = {
        "workspace_id": GATEWAY_BOOTSTRAP_WORKSPACE,
        "purpose": "gateway-probe",
        "issuer": GATEWAY_VERIFIER_ISSUER,
        "key_id": GATEWAY_VERIFIER_KEY_ID,
        "algorithm": "ed25519",
        "private_key_reference": GATEWAY_VERIFIER_KEY_REFERENCE,
        "status": "active",
    }
    mismatches = {
        key: (value.get(key), expected_value)
        for key, expected_value in expected.items()
        if value.get(key) != expected_value
    }
    if mismatches:
        raise RuntimeError(
            "gateway delegation bootstrap key did not match: "
            f"{sorted(mismatches)}"
        )



def _owned_cloudflare_epoch_evidence(
    operations_database_url: str,
    *,
    workspace_id: str,
) -> tuple[tuple[int, str, str, str, str], ...]:
    query = """
        SELECT
          resource.epoch,
          resource.status,
          resource.tunnel_id,
          resource.dns_record_id,
          generated.metadata->>'provider_version_id'
        FROM cpk_cloudflare_ingress_resources AS resource
        JOIN cpk_generated_ingress_secret_references AS generated
          ON generated.workspace_id = resource.workspace_id
         AND generated.source_run_id = resource.source_run_id
         AND generated.source_activity_id = resource.source_activity_id
         AND generated.source_event_id = resource.source_event_id
        WHERE resource.workspace_id = %s
        ORDER BY resource.epoch
    """
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (workspace_id,))
            rows = cursor.fetchall()
    return tuple(
        (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
        )
        for row in rows
    )


def _assert_owned_cloudflare_epoch_states(
    operations_database_url: str,
    *,
    workspace_id: str,
    expected_statuses: tuple[str, ...],
) -> None:
    evidence = _owned_cloudflare_epoch_evidence(
        operations_database_url,
        workspace_id=workspace_id,
    )
    if tuple(row[0] for row in evidence) != tuple(
        range(1, len(expected_statuses) + 1)
    ):
        raise RuntimeError("owned ingress allocation epochs were not monotonic")
    if tuple(row[1] for row in evidence) != expected_statuses:
        raise RuntimeError("owned ingress lifecycle state did not match graph truth")
    for column, label in ((2, "tunnel"), (4, "token version")):
        identities = [row[column] for row in evidence]
        if len(set(identities)) != len(identities):
            raise RuntimeError(f"public ingress recreation reused {label} identity")
    dns_identities = {row[3] for row in evidence}
    if len(dns_identities) != len(evidence):
        raise RuntimeError("public ingress recreation reused DNS identity")


def _assert_removed_ingress_token_versions_revoked(
    provider_container: str,
    operations_database_url: str,
    *,
    workspace_id: str,
    expected_count: int,
) -> None:
    evidence = _owned_cloudflare_epoch_evidence(
        operations_database_url,
        workspace_id=workspace_id,
    )
    removed_versions = {
        row[4] for row in evidence if row[1] == "removed"
    }
    if len(removed_versions) != expected_count:
        raise RuntimeError("removed ingress token-version evidence was incomplete")
    revoked_versions = {
        row["version_id"]
        for row in _provider_audit_rows(provider_container, workspace_id)
        if row["outcome"] == "revoked"
        and row["intent"] == CLOUDFLARE_TUNNEL_TOKEN_INTENT
        and row["version_id"]
    }
    if not removed_versions.issubset(revoked_versions):
        raise RuntimeError("removed ingress token version remained active")


def _run_gateway_verifier_projection(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    servers_repo: Path,
    operations_database_url: str,
    provider_token_file: Path,
    bootstrap_dir: Path,
) -> None:
    workspace_id = GATEWAY_VERIFIER_WORKSPACE
    cpk_server_document = _product_document(servers_repo, "cpk_server")
    gateway_document = _source_live_gateway_document(servers_repo)
    hello_document = _product_document(servers_repo, "hello_server")
    postgres_document = _product_document(servers_repo, "postgres_server")
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=workspace_id,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    workflow.wait_ready()
    current_graph_id = _bootstrap_workspace(
        workflow,
        name="Gateway verifier projection source-live",
        product_documents={
            "gateway": gateway_document,
            "hello": hello_document,
            "postgres": postgres_document,
        },
        register_runtime_authority=True,
        register_runtime_delivery=False,
    )
    provider_registration_id = _register_gateway_verifier_provider(workflow)
    key_a_receipt: ProviderVersionReceipt | None = None
    for reference, value_file, correlation in (
        (
            POSTGRES_PASSWORD_REFERENCE,
            bootstrap_dir / "postgres-password",
            "gateway-rotation-postgres-bootstrap",
        ),
        (
            GATEWAY_VERIFIER_KEY_REFERENCE,
            bootstrap_dir / "gateway-rotation-key-a.pem",
            "gateway-rotation-key-a-bootstrap",
        ),
        (
            GHCR_PULL_CREDENTIAL_REFERENCE,
            bootstrap_dir / "ghcr-pull-credential.json",
            "gateway-rotation-ghcr-pull-bootstrap",
        ),
    ):
        intent = {
            POSTGRES_PASSWORD_REFERENCE: POSTGRES_INTENT,
            GATEWAY_VERIFIER_KEY_REFERENCE: GATEWAY_SIGNING_KEY_INTENT,
            GHCR_PULL_CREDENTIAL_REFERENCE: OCI_PULL_CREDENTIAL_INTENT,
        }[reference]
        receipt = _provider_write_secret(
            workspace_id=workspace_id,
            reference=reference,
            intent=intent,
            value_file=value_file,
            provider_token_file=provider_token_file,
            correlation_id=correlation,
        )
        if reference == GATEWAY_VERIFIER_KEY_REFERENCE:
            key_a_receipt = receipt
    if key_a_receipt is None:
        raise RuntimeError("initial gateway key custody receipt was not recorded")
    _register_gateway_verifier_references(
        workflow,
        provider_registration_id=provider_registration_id,
        initial_key_receipt=key_a_receipt,
    )
    workflow.register_ghcr_pull_authority(
        credential_reference=GHCR_PULL_CREDENTIAL_REFERENCE,
    )

    _register_delegation_key(
        workflow,
        key_id=GATEWAY_VERIFIER_KEY_ID,
        private_key_reference=GATEWAY_VERIFIER_KEY_REFERENCE,
        public_key_file=bootstrap_dir / "gateway-rotation-key-a-public.pem",
        admitted_at="2026-08-01T10:01:00Z",
    )
    _activate_delegation_key(
        workflow,
        GATEWAY_VERIFIER_KEY_ID,
        activated_at="2026-08-01T10:02:00Z",
    )
    verifier_a = _gateway_verifier_configuration(workflow)
    _assert_verifier_key_ids(verifier_a, {GATEWAY_VERIFIER_KEY_ID})
    graph_a = _gateway_verifier_graph(
        gateway_document,
        hello_document,
        postgres_document,
        workspace_id=workspace_id,
    )
    deployed_a = workflow.run_approved_transition(
        title="Gateway key A deploy",
        graph=graph_a,
        current_graph_id=current_graph_id,
        sync_runtime_networks=True,
    )
    _assert_initial_gateway_transition_evidence(workflow, deployed_a)
    _wait_private_gateway_ready(gateway_document, workspace_id=workspace_id)
    _assert_gateway_probe_key(
        workflow.request_gateway_probe_http(
            request_id=f"{workspace_id}:gateway-probe:key-a-http",
            expected_current_graph_id=deployed_a.current_graph_id,
            gateway_node_id="gateway",
            kind="http-status",
            target_id="hello.internal",
            path="/",
        ),
        GATEWAY_VERIFIER_KEY_ID,
    )
    _assert_gateway_probe_key(
        workflow.request_gateway_probe_mcp(
            request_id=f"{workspace_id}:gateway-probe:key-a-postgres",
            expected_current_graph_id=deployed_a.current_graph_id,
            gateway_node_id="gateway",
            kind="postgres-select-one",
            target_id="postgres.postgres",
        ),
        GATEWAY_VERIFIER_KEY_ID,
    )
    _assert_live_gateway_denial_matrix(
        workspace_id=workspace_id,
        key_id=GATEWAY_VERIFIER_KEY_ID,
        private_key_file=bootstrap_dir / "gateway-rotation-key-a.pem",
        postgres_password_file=bootstrap_dir / "postgres-password",
    )
    return



def _register_gateway_verifier_provider(
    workflow: HostedWorkflow,
) -> str:
    all_references = _gateway_verifier_reference_definitions()
    allowed_reference_prefixes = [value[0] for value in all_references]
    allowed_intents = [
        POSTGRES_INTENT,
        GATEWAY_SIGNING_KEY_INTENT,
        OCI_PULL_CREDENTIAL_INTENT,
    ]
    provider = _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/secret-providers",
        {
            "provider_id": PROVIDER_ID,
            "provider_kind": "control-plane-kit-secrets",
            "display_name": "Source-live gateway verifier custody",
            "endpoint_reference": PROVIDER_ENDPOINT_REFERENCE,
            "credential_reference": PROVIDER_CREDENTIAL_REFERENCE,
            "allowed_reference_prefixes": allowed_reference_prefixes,
            "allowed_intents": allowed_intents,
            "admitted_at": "2026-08-01T10:00:00Z",
            "metadata": {"acceptance": "source-live-gateway-verifier"},
            "idempotency_key": f"{workflow.workspace_id}:secret-provider",
        },
    )
    return str(provider["registration_id"])


def _register_gateway_verifier_references(
    workflow: HostedWorkflow,
    *,
    provider_registration_id: str,
    initial_key_receipt: ProviderVersionReceipt,
) -> dict[str, str]:
    registrations: dict[str, str] = {}
    for reference, intent, label in _gateway_verifier_reference_definitions():
        metadata: dict[str, object] = {
            "acceptance": "source-live-gateway-verifier"
        }
        if reference == GATEWAY_VERIFIER_KEY_REFERENCE:
            metadata.update(
                {
                    "provider_version_id": initial_key_receipt.version_id,
                    "provider_version_number": initial_key_receipt.version_number,
                }
            )
        registered = _http(
            workflow.base_url,
            "POST",
            f"/workspaces/{workflow.workspace_id}/secret-references",
            {
                "reference": reference,
                "provider_registration_id": provider_registration_id,
                "allowed_intents": [intent],
                "admitted_at": "2026-08-01T10:00:30Z",
                "metadata": metadata,
                "idempotency_key": (
                    f"{workflow.workspace_id}:secret-reference:{label}"
                ),
            },
        )
        registrations[reference] = str(registered["registration_id"])
    return registrations


def _gateway_verifier_reference_definitions() -> tuple[tuple[str, str, str], ...]:
    return (
        (POSTGRES_PASSWORD_REFERENCE, POSTGRES_INTENT, "postgres-password"),
        (
            GATEWAY_VERIFIER_KEY_REFERENCE,
            GATEWAY_SIGNING_KEY_INTENT,
            "gateway-rotation-key-a",
        ),
        (
            GHCR_PULL_CREDENTIAL_REFERENCE,
            OCI_PULL_CREDENTIAL_INTENT,
            "ghcr-pull-credential",
        ),
    )


def _register_delegation_key(
    workflow: HostedWorkflow,
    *,
    key_id: str,
    private_key_reference: str,
    public_key_file: Path,
    admitted_at: str,
    issuer: str = GATEWAY_VERIFIER_ISSUER,
) -> None:
    _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/delegation-keys",
        {
            "purpose": "gateway-probe",
            "issuer": issuer,
            "key_id": key_id,
            "algorithm": "ed25519",
            "public_key_pem": public_key_file.read_text(encoding="utf-8"),
            "private_key_reference": private_key_reference,
            "admitted_at": admitted_at,
            "idempotency_key": f"{workflow.workspace_id}:delegation-key:{key_id}",
        },
    )


def _activate_delegation_key(
    workflow: HostedWorkflow,
    key_id: str,
    *,
    activated_at: str,
    issuer: str = GATEWAY_VERIFIER_ISSUER,
) -> None:
    _delegation_key_lifecycle_command(
        workflow,
        key_id,
        action="activate",
        evidence_name="activated_at",
        evidence_value=activated_at,
        issuer=issuer,
    )


def _retire_delegation_key(
    workflow: HostedWorkflow,
    key_id: str,
    *,
    retired_at: str,
    issuer: str = GATEWAY_VERIFIER_ISSUER,
) -> None:
    _delegation_key_lifecycle_command(
        workflow,
        key_id,
        action="retire",
        evidence_name="retired_at",
        evidence_value=retired_at,
        issuer=issuer,
    )


def _revoke_delegation_key(
    workflow: HostedWorkflow,
    key_id: str,
    *,
    revoked_at: str,
    issuer: str = GATEWAY_VERIFIER_ISSUER,
) -> None:
    _delegation_key_lifecycle_command(
        workflow,
        key_id,
        action="revoke",
        evidence_name="revoked_at",
        evidence_value=revoked_at,
        issuer=issuer,
    )


def _delegation_key_lifecycle_command(
    workflow: HostedWorkflow,
    key_id: str,
    *,
    action: str,
    evidence_name: str,
    evidence_value: str,
    issuer: str,
) -> None:
    encoded_issuer = quote(issuer, safe="")
    _http(
        workflow.base_url,
        "POST",
        (
            f"/workspaces/{workflow.workspace_id}/delegation-keys/"
            f"{encoded_issuer}/{key_id}/{action}"
        ),
        {
            "purpose": "gateway-probe",
            evidence_name: evidence_value,
            "idempotency_key": (
                f"{workflow.workspace_id}:delegation-key:{key_id}:{action}"
            ),
        },
    )


def _gateway_verifier_configuration(workflow: HostedWorkflow) -> dict[str, Any]:
    response = _http(
        workflow.base_url,
        "GET",
        (
            f"/workspaces/{workflow.workspace_id}/gateways/gateway/"
            "verifier-configuration"
        ),
    )
    configuration = response.get("gateway_verifier_configuration")
    if not isinstance(configuration, dict):
        raise RuntimeError("gateway verifier configuration read was malformed")
    return configuration


def _assert_verifier_key_ids(
    configuration: dict[str, Any],
    expected: set[str],
) -> None:
    public_keys = configuration.get("public_keys")
    if not isinstance(public_keys, list):
        raise RuntimeError("gateway verifier public key set was malformed")
    observed = {
        str(item.get("key_id"))
        for item in public_keys
        if isinstance(item, dict)
    }
    if observed != expected:
        raise RuntimeError(
            f"gateway verifier key set mismatch: expected={expected}, observed={observed}"
        )
    rendered = json.dumps(configuration, separators=(",", ":"), sort_keys=True)
    if "private_key" in rendered.lower() or "secret://" in rendered:
        raise RuntimeError("gateway verifier configuration exposed private metadata")


def _assert_delegation_key_statuses(
    workflow: HostedWorkflow,
    expected: dict[str, str],
) -> None:
    response = _http(
        workflow.base_url,
        "GET",
        f"/workspaces/{workflow.workspace_id}/delegation-keys",
    )
    items = response.get("items")
    if not isinstance(items, list):
        raise RuntimeError("delegation key read model was malformed")
    observed = {
        str(item.get("key_id")): str(item.get("status"))
        for item in items
        if isinstance(item, dict)
    }
    if observed != expected:
        raise RuntimeError(
            f"delegation key status mismatch: expected={expected}, observed={observed}"
        )


def _gateway_verifier_graph(
    gateway_document: Any,
    hello_document: Any,
    postgres_document: Any,
    *,
    workspace_id: str,
) -> DeploymentGraph:
    gateway_product = gateway_document.product
    gateway = instantiate_product(
        gateway_product,
        "gateway",
        ProductInstanceConfiguration.from_contract(gateway_product.runtime_contract),
    )
    hello_product = hello_document.product
    hello = instantiate_product(
        hello_product,
        "hello",
        _with_public_environment(
            ProductInstanceConfiguration.from_contract(hello_product.runtime_contract),
            {"HELLO_MESSAGE": "Hello through rotating gateway keys"},
        ),
    )
    postgres_product = postgres_document.product
    postgres = instantiate_product(
        postgres_product,
        "postgres",
        ProductInstanceConfiguration.from_contract(postgres_product.runtime_contract),
    )
    postgres = replace(
        postgres,
        spec=replace(postgres.spec, verification=VerificationContract()),
    )
    return compile_topology(
        DeploymentTopology(
            workspace_id,
            DockerRuntime(
                runtime_id="docker",
                network_name=f"control-plane-kit-{workspace_id}-docker",
                authority_ref=RuntimeAuthorityReference(LOCAL_DOCKER_AUTHORITY_REF),
                children=(
                    gateway,
                    hello,
                    postgres,
                    SocketConnection("hello", "internal", "gateway", "target-http"),
                    SocketConnection(
                        "postgres",
                        "postgres",
                        "gateway",
                        "target-postgres",
                    ),
                ),
            ),
            delegation_authorities=(
                DelegationAuthorityBinding(
                    delegate_node_id="gateway",
                    purpose=DelegationKeyPurpose.GATEWAY_PROBE,
                    issuer=GATEWAY_VERIFIER_ISSUER,
                ),
            ),
        )
    )



def _assert_gateway_probe_key(result: dict[str, Any], expected_key_id: str) -> None:
    _assert_gateway_probe_succeeded(result, target_id=str(result["gateway_probe"]["target_id"]))
    grant = result.get("gateway_probe", {}).get("grant")
    if not isinstance(grant, dict) or grant.get("key_id") != expected_key_id:
        raise RuntimeError("gateway probe did not use the expected active signing key")


def _assert_public_gateway_probe(
    request: Callable[[str], dict[str, Any]],
    *,
    request_id_prefix: str,
    expected_key_id: str,
) -> None:
    for attempt in verification_attempts(PUBLIC_GATEWAY_PROBE_POLICY):
        result = request(f"{request_id_prefix}:attempt-{attempt}")
        probe = result.get("gateway_probe")
        evidence = probe.get("evidence") if isinstance(probe, dict) else None
        transient_readiness = (
            isinstance(probe, dict)
            and probe.get("status") == "failed"
            and (
                probe.get("result_code")
                == "gateway-endpoint-unresolved-endpoint"
                or (
                    probe.get("result_code") == "gateway-transport-failed"
                    and isinstance(evidence, dict)
                    and evidence.get("http_status") == 530
                )
            )
        )
        if (
            transient_readiness
            and attempt < PUBLIC_GATEWAY_PROBE_POLICY.maximum_attempts
        ):
            continue
        if not isinstance(probe, dict) or probe.get("status") != "succeeded":
            raise RuntimeError("public gateway probe did not succeed")
        _assert_gateway_probe_key(result, expected_key_id)
        return


def _assert_public_gateway_probe_pair(
    workflow: HostedWorkflow,
    *,
    current_graph_id: str,
    expected_key_id: str,
    request_prefix: str,
) -> None:
    _assert_public_gateway_probe(
        lambda request_id: workflow.request_gateway_probe_http(
            request_id=request_id,
            expected_current_graph_id=current_graph_id,
            gateway_node_id="gateway",
            kind="http-status",
            target_id="hello.internal",
            path="/",
            access_path=GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS,
        ),
        request_id_prefix=f"{request_prefix}:http",
        expected_key_id=expected_key_id,
    )
    _assert_public_gateway_probe(
        lambda request_id: workflow.request_gateway_probe_mcp(
            request_id=request_id,
            expected_current_graph_id=current_graph_id,
            gateway_node_id="gateway",
            kind="http-status",
            target_id="hello.internal",
            path="/",
            access_path=GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS,
        ),
        request_id_prefix=f"{request_prefix}:mcp",
        expected_key_id=expected_key_id,
    )


def _assert_initial_gateway_transition_evidence(
    workflow: HostedWorkflow,
    transition: Any,
) -> None:
    expected_node_ids = {"gateway", "hello", "postgres"}
    desired = workflow.read_desired_graph()
    graph_descriptor = desired.get("graph_descriptor")
    if not isinstance(graph_descriptor, dict):
        raise RuntimeError("desired graph readback omitted its graph descriptor")
    nodes = graph_descriptor.get("nodes")
    if not isinstance(nodes, dict):
        raise RuntimeError("desired graph readback omitted its node map")
    desired_node_ids = set(nodes)
    if not expected_node_ids <= desired_node_ids:
        raise RuntimeError(
            "desired graph readback lost gateway rotation nodes: "
            f"expected={sorted(expected_node_ids)}, observed={sorted(desired_node_ids)}"
        )

    detail = workflow.read_plan_detail(transition.plan_id)
    plan = detail.get("plan")
    payload = plan.get("payload") if isinstance(plan, dict) else None
    activities = payload.get("activities") if isinstance(payload, dict) else None
    if not isinstance(activities, list):
        raise RuntimeError("plan detail omitted its activity plan")
    start_activity_ids = {
        str(target.get("node_id")): str(activity.get("activity_id"))
        for activity in activities
        if isinstance(activity, dict)
        for operation in (activity.get("operation"),)
        if isinstance(operation, dict) and operation.get("kind") == "start-node"
        for target in (operation.get("target"),)
        if isinstance(target, dict) and target.get("kind") == "node"
    }
    started_node_ids = set(start_activity_ids)
    if not expected_node_ids <= started_node_ids:
        raise RuntimeError(
            "initial gateway plan omitted required start-node activities: "
            f"expected={sorted(expected_node_ids)}, observed={sorted(started_node_ids)}, "
            f"plan_id={transition.plan_id}"
        )

    events = _events_for_run(workflow.read_activity(limit=200), transition.run_id)
    succeeded_activity_ids = {
        str(event.get("activity_id"))
        for event in events
        if event.get("event_type") == "step_succeeded"
    }
    missing_success = {
        node_id: activity_id
        for node_id, activity_id in start_activity_ids.items()
        if node_id in expected_node_ids and activity_id not in succeeded_activity_ids
    }
    if missing_success:
        gateway_events = [
            event
            for event in events
            if event.get("activity_id") in start_activity_ids.values()
        ]
        raise RuntimeError(
            "initial gateway run omitted exact start-node success evidence: "
            f"missing={missing_success}, events={gateway_events}"
        )


def _runtime_node_identities(
    workspace_id: str,
    node_ids: tuple[str, ...],
) -> dict[str, str]:
    return {
        node_id: str(_single_docker_container(workspace_id, node_id).id)
        for node_id in node_ids
    }


def _assert_public_overlay_transition_evidence(
    workflow: HostedWorkflow,
    transition: Any,
    *,
    expected_ingress_operations: set[str],
    expected_connector_operations: set[str],
    stable_workload_nodes: set[str],
) -> None:
    detail = workflow.read_plan_detail(transition.plan_id)
    plan = detail.get("plan")
    payload = plan.get("payload") if isinstance(plan, dict) else None
    activities = payload.get("activities") if isinstance(payload, dict) else None
    if not isinstance(activities, list):
        raise RuntimeError("public overlay plan detail omitted its activity plan")

    observed_ingress_operations: set[str] = set()
    observed_connector_operations: set[str] = set()
    forbidden_workload_mutations: list[tuple[str, str]] = []
    planned_activity_ids: set[str] = set()
    mutation_kinds = {
        "start-node",
        "stop-node",
        "remove-node-resource",
        "reconcile-node",
    }
    for activity in activities:
        if not isinstance(activity, dict):
            raise RuntimeError("public overlay plan contained malformed activity")
        activity_id = activity.get("activity_id")
        operation = activity.get("operation")
        if not isinstance(activity_id, str) or not isinstance(operation, dict):
            raise RuntimeError("public overlay plan contained malformed operation")
        planned_activity_ids.add(activity_id)
        kind = operation.get("kind")
        target = operation.get("target")
        if not isinstance(kind, str) or not isinstance(target, dict):
            raise RuntimeError("public overlay plan operation omitted its target")
        if target.get("kind") == "public-ingress":
            observed_ingress_operations.add(kind)
        node_id = target.get("node_id")
        if node_id == "cloudflared-gateway":
            observed_connector_operations.add(kind)
        if node_id in stable_workload_nodes and kind in mutation_kinds:
            forbidden_workload_mutations.append((kind, str(node_id)))

    if observed_ingress_operations != expected_ingress_operations:
        raise RuntimeError("public overlay plan had unexpected ingress operations")
    if observed_connector_operations != expected_connector_operations:
        raise RuntimeError("public overlay plan had unexpected connector operations")
    if forbidden_workload_mutations:
        raise RuntimeError("public overlay plan mutated stable workload nodes")

    events = _events_for_run(workflow.read_activity(limit=200), transition.run_id)
    succeeded_activity_ids = {
        str(event.get("activity_id"))
        for event in events
        if event.get("event_type") == "step_succeeded"
    }
    if planned_activity_ids - succeeded_activity_ids:
        raise RuntimeError("public overlay run omitted planned success evidence")


def _assert_runtime_node_identities(
    workspace_id: str,
    expected: dict[str, str],
) -> None:
    if _runtime_node_identities(workspace_id, tuple(expected)) != expected:
        raise RuntimeError("public access overlay changed workload container identities")


def _assert_named_public_gateway_probes_unavailable(
    workflow: HostedWorkflow,
    *,
    current_graph_id: str,
) -> None:
    calls = (
        lambda: workflow.request_gateway_probe_http(
            request_id=f"{workflow.workspace_id}:gateway-probe:public-off:http",
            expected_current_graph_id=current_graph_id,
            gateway_node_id="gateway",
            kind="http-status",
            target_id="hello.internal",
            path="/",
            access_path=GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS,
        ),
        lambda: workflow.request_gateway_probe_mcp(
            request_id=f"{workflow.workspace_id}:gateway-probe:public-off:mcp",
            expected_current_graph_id=current_graph_id,
            gateway_node_id="gateway",
            kind="http-status",
            target_id="hello.internal",
            path="/",
            access_path=GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS,
        ),
    )
    for call in calls:
        try:
            call()
        except RuntimeError as error:
            if "gateway control node has no named public ingress" not in str(error):
                raise RuntimeError(
                    "public gateway probe failed for an unexpected reason"
                ) from None
        else:
            raise RuntimeError("public gateway probe succeeded while overlay was off")


def _direct_gateway_capability(
    *,
    workspace_id: str,
    key_id: str,
    private_key_file: Path,
    expires_in: int,
    jti: str,
    request: GatewayProbeRequest | None = None,
    grant_changes: dict[str, object] | None = None,
    signing_private_key: Ed25519PrivateKey | None = None,
    inbound_request: GatewayProbeRequest | None = None,
) -> tuple[str, GatewayProbeRequest]:
    request = request or GatewayProbeRequest(
        GatewayProbeCommandKind.HTTP_STATUS,
        GatewayTargetId("hello.internal"),
        "/",
    )
    now = int(time.time())
    grant = DelegatedGatewayProbeGrant(
        issuer=GATEWAY_VERIFIER_ISSUER,
        key_id=key_id,
        audience=f"gateway:{workspace_id}:gateway",
        workspace_id=workspace_id,
        operation_id=f"diagnostic:{jti}",
        request_id=f"diagnostic:{jti}",
        gateway_node_id="gateway",
        probe_kind=request.kind,
        target_id=request.target_id,
        request_digest=request.canonical_digest(),
        issued_at=now,
        expires_at=now + expires_in,
        jti=jti,
    )
    if grant_changes:
        grant = replace(grant, **grant_changes)
    private_key = signing_private_key or serialization.load_pem_private_key(
        private_key_file.read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("gateway diagnostic key was not Ed25519")
    token = jwt.encode(
        {
            "iss": grant.issuer,
            "aud": grant.audience,
            "iat": grant.issued_at,
            "exp": grant.expires_at,
            "jti": grant.jti,
            "gateway_probe": grant.descriptor(),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": grant.key_id, "typ": "CPK-GATEWAY-PROBE+JWT"},
    )
    return token, inbound_request or request


def _assert_direct_gateway_rejected(
    capability: tuple[str, GatewayProbeRequest],
) -> None:
    token, probe = capability
    status = _direct_gateway_status(
        authorization=f"CPK-Gateway {token}",
        body=_gateway_request_body(probe),
    )
    if status not in {400, 401, 403, 409}:
        raise RuntimeError(f"invalid gateway capability was not rejected: {status}")


def _direct_gateway_status(
    *,
    authorization: str | None,
    body: bytes,
) -> int:
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    request = Request(
        "http://gateway:8000/cpk/probes",
        method="POST",
        headers=headers,
        data=body,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status
    except HTTPError as error:
        return error.code


def _gateway_request_body(request: GatewayProbeRequest) -> bytes:
    return json.dumps(
        request.descriptor(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _source_live_gateway_document(servers_repo: Path) -> Any:
    execution_reference = _required_env("CPK_SOURCE_LIVE_GATEWAY_IMAGE")
    source_commit = _required_env("CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT")
    match = re.fullmatch(
        r"(?P<registry>[a-z0-9.-]+(?:\:[0-9]+)?)/"
        r"(?P<repository>[a-z0-9._/-]+)@"
        r"(?P<digest>sha256:[0-9a-f]{64})",
        execution_reference,
    )
    if match is None:
        raise RuntimeError("source-live gateway image must be an immutable digest")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise RuntimeError("source-live gateway source commit must be canonical")

    descriptor_path = (
        servers_repo / "products" / "cpk_local_gateway" / "product.cpk.json"
    )
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    image = descriptor["product"]["image"]
    image.update(
        {
            "registry": match.group("registry"),
            "repository": match.group("repository"),
            "digest": match.group("digest"),
            "tag": "source-live",
        }
    )
    provenance = image.get("provenance")
    if isinstance(provenance, dict):
        provenance["source-commit"] = source_commit
    return ProductDescriptorCodec().decode_document(
        json.dumps(descriptor, separators=(",", ":")).encode("ascii")
    )


def _assert_live_gateway_denial_matrix(
    *,
    workspace_id: str,
    key_id: str,
    private_key_file: Path,
    postgres_password_file: Path,
) -> None:
    trusted_private_key = serialization.load_pem_private_key(
        private_key_file.read_bytes(), password=None
    )
    if not isinstance(trusted_private_key, Ed25519PrivateKey):
        raise RuntimeError("gateway diagnostic key was not Ed25519")
    forged_private_key = Ed25519PrivateKey.generate()
    witness = _postgres_transaction_witness(postgres_password_file)
    requests = (
        GatewayProbeRequest(
            GatewayProbeCommandKind.HTTP_STATUS,
            GatewayTargetId("hello.internal"),
            "/",
        ),
        GatewayProbeRequest(
            GatewayProbeCommandKind.POSTGRES_SELECT_ONE,
            GatewayTargetId("postgres.postgres"),
        ),
    )
    for probe in requests:
        suffix = probe.kind.value
        base = _direct_gateway_capability(
            workspace_id=workspace_id,
            key_id=key_id,
            private_key_file=private_key_file,
            expires_in=60,
            jti=f"denial-base-{suffix}",
            request=probe,
        )
        alternate = (
            GatewayProbeRequest(
                GatewayProbeCommandKind.POSTGRES_SELECT_ONE,
                GatewayTargetId("postgres.postgres"),
            )
            if probe.kind is GatewayProbeCommandKind.HTTP_STATUS
            else GatewayProbeRequest(
                GatewayProbeCommandKind.HTTP_STATUS,
                GatewayTargetId("hello.internal"),
                "/",
            )
        )
        cases: tuple[tuple[str, str | None, bytes], ...] = (
            ("missing", None, _gateway_request_body(probe)),
            ("malformed", "CPK-Gateway malformed", _gateway_request_body(probe)),
            (
                "forged",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-forged-{suffix}",
                    request=probe,
                    signing_private_key=forged_private_key,
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-issuer",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-issuer-{suffix}",
                    request=probe,
                    grant_changes={"issuer": "cpk-source-live-other"},
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-key",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-key-{suffix}",
                    request=probe,
                    grant_changes={"key_id": "unknown-key"},
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-audience",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-audience-{suffix}",
                    request=probe,
                    grant_changes={"audience": "gateway:other:gateway"},
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-workspace",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-workspace-{suffix}",
                    request=probe,
                    grant_changes={"workspace_id": "workspace-other"},
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-gateway",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-gateway-{suffix}",
                    request=probe,
                    grant_changes={"gateway_node_id": "gateway-other"},
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "wrong-request",
                f"CPK-Gateway {base[0]}",
                _gateway_request_body(alternate),
            ),
            (
                "malformed-body",
                f"CPK-Gateway {base[0]}",
                b'{"kind":"unsupported"}',
            ),
            (
                "expired",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-expired-{suffix}",
                    request=probe,
                    grant_changes={
                        "issued_at": int(time.time()) - 80,
                        "expires_at": int(time.time()) - 20,
                    },
                )[0],
                _gateway_request_body(probe),
            ),
            (
                "not-yet-valid",
                "CPK-Gateway "
                + _direct_gateway_capability(
                    workspace_id=workspace_id,
                    key_id=key_id,
                    private_key_file=private_key_file,
                    expires_in=60,
                    jti=f"denial-future-{suffix}",
                    request=probe,
                    grant_changes={
                        "issued_at": int(time.time()) + 20,
                        "expires_at": int(time.time()) + 80,
                    },
                )[0],
                _gateway_request_body(probe),
            ),
        )
        for label, authorization, body in cases:
            _assert_no_gateway_target_io(
                lambda authorization=authorization, body=body, label=label: (
                    _assert_direct_gateway_status_rejected(
                        authorization=authorization,
                        body=body,
                        label=label,
                    )
                ),
                postgres_witness=witness,
            )

        replay = _direct_gateway_capability(
            workspace_id=workspace_id,
            key_id=key_id,
            private_key_file=private_key_file,
            expires_in=60,
            jti=f"denial-replay-{suffix}",
            request=probe,
            signing_private_key=trusted_private_key,
        )
        first_status = _direct_gateway_status(
            authorization=f"CPK-Gateway {replay[0]}",
            body=_gateway_request_body(replay[1]),
        )
        if first_status != 200:
            raise RuntimeError("diagnostic replay seed request did not succeed")
        witness.synchronize()
        _assert_no_gateway_target_io(
            lambda: _assert_direct_gateway_status_rejected(
                authorization=f"CPK-Gateway {replay[0]}",
                body=_gateway_request_body(replay[1]),
                label="replayed",
            ),
            postgres_witness=witness,
        )


def _assert_direct_gateway_status_rejected(
    *,
    authorization: str | None,
    body: bytes,
    label: str,
) -> None:
    status = _direct_gateway_status(authorization=authorization, body=body)
    if status not in {400, 401, 403, 409}:
        raise RuntimeError(f"gateway denial case {label} returned {status}")


def _postgres_transaction_witness(password_file: Path) -> PostgresTransactionWitness:
    def snapshot() -> int:
        password = password_file.read_text(encoding="utf-8").strip()
        with psycopg.connect(
            host="postgres",
            port=5432,
            dbname="cpk",
            user="cpk",
            password=password,
            connect_timeout=5,
            autocommit=True,
        ) as connection:
            connection.execute("SELECT pg_stat_force_next_flush()")
            row = connection.execute(
                "SELECT xact_commit + xact_rollback "
                "FROM pg_stat_database WHERE datname = current_database()"
            ).fetchone()
        if row is None or type(row[0]) is not int:
            raise SourceLiveGatewayDenialError("postgres-witness-malformed")
        return row[0]

    return PostgresTransactionWitness.calibrate(snapshot)


def _assert_no_gateway_target_io(
    action: Callable[[], None],
    *,
    postgres_witness: PostgresTransactionWitness,
) -> None:
    hello_before = _hello_request_count()
    postgres_witness.assert_no_target_io(action)
    if _hello_request_count() != hello_before:
        raise SourceLiveGatewayDenialError("hello-target-io-observed")


def _hello_request_count() -> int:
    with urlopen("http://hello:8000/observations/requests", timeout=5) as response:
        payload = json.loads(response.read(16_384))
    requests = payload.get("requests")
    if not isinstance(requests, list):
        raise RuntimeError("hello observation payload was malformed")
    return len(requests)


def _wait_private_gateway_ready(
    gateway_document: Any,
    *,
    workspace_id: str = GATEWAY_VERIFIER_WORKSPACE,
) -> None:
    policy = _verification_policy(gateway_document, "ready")
    last_error = "gateway did not answer"
    for attempt in range(1, policy.maximum_attempts + 1):
        if attempt > 1:
            time.sleep(policy.interval_seconds)
        try:
            with urlopen(
                "http://gateway:8000/health/ready",
                timeout=policy.timeout_seconds,
            ) as response:
                payload = json.loads(response.read(16_384))
            if response.status == 200 and payload.get("status") == "ready":
                return
            last_error = f"status={response.status}, payload={payload}"
        except Exception as error:
            try:
                gateway_addresses = sorted(
                    {
                        address[4][0]
                        for address in socket.getaddrinfo(
                            "gateway",
                            8000,
                            type=socket.SOCK_STREAM,
                        )
                    }
                )
            except OSError as resolution_error:
                gateway_addresses = [
                    f"resolution-error:{type(resolution_error).__name__}:"
                    f"{resolution_error}"
                ]
            last_error = (
                f"{type(error).__name__}:{error}; "
                f"gateway_addresses={gateway_addresses}"
            )
    raise RuntimeError(
        "private gateway did not become ready under descriptor policy: "
        f"{last_error}; gateway_container="
        f"{json.dumps(_gateway_container_diagnostics(workspace_id), sort_keys=True)}; "
        "runtime_networks="
        f"{_runtime_network_diagnostics(workspace_id)}"
    )


def _gateway_container_diagnostics(workspace_id: str) -> dict[str, Any]:
    try:
        container = _single_docker_container(workspace_id, "gateway")
        container.reload()
        return _bounded_container_state(container)
    except Exception as error:
        return {
            "status": "unavailable",
            "failure_type": type(error).__name__,
        }


def _runtime_network_diagnostics(workspace_id: str) -> list[dict[str, object]]:
    client = docker.from_env()
    label_filters = [
        f"org.openj92.cpk.workspace={workspace_id}",
        "org.openj92.cpk.kind=runtime-network",
    ]
    diagnostics: list[dict[str, object]] = []
    for network in client.networks.list(filters={"label": label_filters}):
        network.reload()
        endpoints = []
        for container_id in sorted((network.attrs.get("Containers") or {}).keys()):
            container = client.containers.get(container_id)
            attachment = (
                (container.attrs.get("NetworkSettings") or {})
                .get("Networks", {})
                .get(network.name, {})
            )
            endpoints.append(
                {
                    "container": container.name,
                    "aliases": sorted(attachment.get("Aliases") or ()),
                    "ipv4": str(attachment.get("IPAddress") or ""),
                }
            )
        diagnostics.append(
            {
                "network": network.name,
                "endpoints": endpoints,
            }
        )
    return diagnostics


def _run_cloudflare_tunnel_custody(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    servers_repo: Path,
    operations_database_url: str,
    provider_token_file: Path,
    bootstrap_dir: Path,
) -> None:
    workspace_id = _required_env("CPK_HOSTED_ACTIVITY_WORKSPACE_ID")
    provider_container = _required_env("CPK_SECRET_PROVIDER_CONTAINER")
    public_hostname = _required_env("CPK_PUBLIC_GATEWAY_HOSTNAME")
    gateway_document = _product_document(servers_repo, "cpk_local_gateway")
    hello_document = _product_document(servers_repo, "hello_server")
    cloudflared_document = _product_document(servers_repo, "cloudflared_connector")
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=workspace_id,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    workflow.wait_ready()
    current_graph_id = _bootstrap_workspace(
        workflow,
        name="Cloudflare generated-secret custody source-live",
        product_documents={
            "gateway": gateway_document,
            "hello": hello_document,
            "cloudflared": cloudflared_document,
        },
        register_runtime_authority=True,
        register_runtime_delivery=False,
    )
    provider_registration_id = _register_cloudflare_provider_and_references(workflow)
    _assert_provider_metadata_is_secret_free(workflow)
    _provider_write_secret(
        workspace_id=workspace_id,
        reference=CLOUDFLARE_API_TOKEN_REFERENCE,
        intent=CLOUDFLARE_API_TOKEN_INTENT,
        value_file=bootstrap_dir / "cloudflare-api-token",
        provider_token_file=provider_token_file,
        correlation_id="source-live-cloudflare-api-bootstrap",
    )
    _provider_write_secret(
        workspace_id=workspace_id,
        reference=GATEWAY_SIGNING_KEY_REFERENCE,
        intent=GATEWAY_SIGNING_KEY_INTENT,
        value_file=bootstrap_dir / "gateway-private-key.pem",
        provider_token_file=provider_token_file,
        correlation_id="source-live-gateway-signing-bootstrap",
    )
    _provider_write_secret(
        workspace_id=workspace_id,
        reference=GHCR_PULL_CREDENTIAL_REFERENCE,
        intent=OCI_PULL_CREDENTIAL_INTENT,
        value_file=bootstrap_dir / "ghcr-pull-credential.json",
        provider_token_file=provider_token_file,
        correlation_id="source-live-ghcr-pull-bootstrap",
    )
    workflow.register_ghcr_pull_authority(
        credential_reference=GHCR_PULL_CREDENTIAL_REFERENCE,
    )
    _register_delegation_key(
        workflow,
        key_id=GATEWAY_PROBE_KEY_ID,
        private_key_reference=GATEWAY_SIGNING_KEY_REFERENCE,
        public_key_file=bootstrap_dir / "gateway-public-key.pem",
        admitted_at=_clock(),
        issuer=GATEWAY_PROBE_ISSUER,
    )
    _activate_delegation_key(
        workflow,
        GATEWAY_PROBE_KEY_ID,
        activated_at=_clock(),
        issuer=GATEWAY_PROBE_ISSUER,
    )
    workflow.register_provider_backed_cloudflare_ingress_authority(
        api_token_ref=CLOUDFLARE_API_TOKEN_REFERENCE,
        generated_secret_provider_registration_id=provider_registration_id,
        generated_secret_reference_prefix=CLOUDFLARE_GENERATED_REFERENCE_PREFIX,
        allowed_hostname_pattern="cpk-sec1203-*.openj92.dev",
    )

    public_graph = _public_gateway_ingress_graph(
        gateway_document,
        hello_document,
        cloudflared_document,
        workspace_id=workspace_id,
        authority_ref=RuntimeAuthorityReference(LOCAL_DOCKER_AUTHORITY_REF),
        public_hostname=public_hostname,
        lifecycle=PublicIngressLifecycle.EPHEMERAL,
    )
    private_graph = _single_hello_graph(
        hello_document,
        workspace_id=workspace_id,
        authority_ref=RuntimeAuthorityReference(LOCAL_DOCKER_AUTHORITY_REF),
        message="Hello through public ingress",
    )
    _record_source_live_cloudflare_inventory(
        bootstrap_dir / "cloudflare-api-token"
    )
    _checkpoint_cloudflare_phase(
        workflow,
        phase="prepared",
        current_graph_id=current_graph_id,
        desired_graph_id=current_graph_id,
    )

    public_on = workflow.run_approved_transition(
        title="Cloudflare custody public overlay on",
        graph=public_graph,
        current_graph_id=current_graph_id,
        sync_runtime_networks=False,
    )
    _checkpoint_cloudflare_phase(
        workflow,
        phase="public-on-committed",
        result=public_on,
    )
    _assert_public_overlay_transition_evidence(
        workflow,
        public_on,
        expected_ingress_operations={
            "allocate-public-ingress",
            "wait-for-public-ingress-ready",
        },
        expected_connector_operations={"start-node", "wait-for-healthy"},
        stable_workload_nodes=set(),
    )
    _assert_activity_mentions(workflow, public_on.run_id, "gateway")
    _assert_activity_mentions(workflow, public_on.run_id, "hello")
    _assert_activity_mentions(workflow, public_on.run_id, "cloudflared-gateway")
    _wait_public_gateway_ready(public_hostname)
    _assert_public_gateway_authenticated_http_probe(
        public_hostname,
        workspace_id=workspace_id,
    )
    _assert_public_gateway_probe_pair(
        workflow,
        current_graph_id=public_on.current_graph_id,
        expected_key_id=GATEWAY_PROBE_KEY_ID,
        request_prefix=f"{workspace_id}:gateway-probe:public-on",
    )
    workload_identities = _runtime_node_identities(
        workspace_id,
        ("gateway", "hello"),
    )
    _sync_runtime_networks(server_container, workspace_id=workspace_id)
    private_probe = workflow.request_gateway_probe_http(
        request_id=f"{workspace_id}:gateway-probe:first",
        expected_current_graph_id=public_on.current_graph_id,
        gateway_node_id="gateway",
        kind="http-status",
        target_id="hello.internal",
        path="/",
    )
    _assert_gateway_probe_succeeded(private_probe, target_id="hello.internal")

    public_off = workflow.run_approved_transition(
        title="Cloudflare custody public overlay off",
        graph=private_graph,
        current_graph_id=public_on.current_graph_id,
        expected_desired_graph_id=public_on.desired_graph_id,
        sync_runtime_networks=False,
    )
    _checkpoint_cloudflare_phase(
        workflow,
        phase="public-off-committed",
        result=public_off,
    )
    _assert_public_overlay_transition_evidence(
        workflow,
        public_off,
        expected_ingress_operations={"remove-public-ingress"},
        expected_connector_operations={"stop-node", "remove-node-resource"},
        stable_workload_nodes={"gateway", "hello"},
    )
    _assert_activity_mentions(workflow, public_off.run_id, "cloudflared-gateway")
    _assert_public_gateway_unreachable(public_hostname)
    _assert_runtime_node_identities(workspace_id, workload_identities)
    _assert_named_public_gateway_probes_unavailable(
        workflow,
        current_graph_id=public_off.current_graph_id,
    )
    _assert_owned_cloudflare_epoch_states(
        operations_database_url,
        workspace_id=workspace_id,
        expected_statuses=("removed",),
    )
    _assert_removed_ingress_token_versions_revoked(
        provider_container,
        operations_database_url,
        workspace_id=workspace_id,
        expected_count=1,
    )
    _assert_owned_cloudflare_resources_removed(
        operations_database_url,
        workspace_id=workspace_id,
        api_token_file=bootstrap_dir / "cloudflare-api-token",
        expected_minimum=1,
    )

    public_on_again = workflow.run_approved_transition(
        title="Cloudflare custody public overlay on again",
        graph=public_graph,
        current_graph_id=public_off.current_graph_id,
        expected_desired_graph_id=public_off.desired_graph_id,
        sync_runtime_networks=False,
    )
    _checkpoint_cloudflare_phase(
        workflow,
        phase="public-on-again-committed",
        result=public_on_again,
    )
    _assert_public_overlay_transition_evidence(
        workflow,
        public_on_again,
        expected_ingress_operations={
            "allocate-public-ingress",
            "wait-for-public-ingress-ready",
        },
        expected_connector_operations={"start-node", "wait-for-healthy"},
        stable_workload_nodes={"gateway", "hello"},
    )
    _assert_activity_mentions(workflow, public_on_again.run_id, "gateway")
    _assert_activity_mentions(workflow, public_on_again.run_id, "cloudflared-gateway")
    _wait_public_gateway_ready(public_hostname)
    _assert_public_gateway_authenticated_http_probe(
        public_hostname,
        workspace_id=workspace_id,
    )
    _assert_runtime_node_identities(workspace_id, workload_identities)
    _assert_owned_cloudflare_epoch_states(
        operations_database_url,
        workspace_id=workspace_id,
        expected_statuses=("removed", "active"),
    )
    _disconnect_runtime_networks(server_container, workspace_id=workspace_id)
    removed = workflow.run_approved_transition(
        title="Cloudflare custody final teardown",
        graph=DeploymentGraph(workspace_id),
        current_graph_id=public_on_again.current_graph_id,
        expected_desired_graph_id=public_on_again.desired_graph_id,
        sync_runtime_networks=False,
    )
    _checkpoint_cloudflare_phase(
        workflow,
        phase="final-teardown-committed",
        result=removed,
    )
    _assert_public_overlay_transition_evidence(
        workflow,
        removed,
        expected_ingress_operations={"remove-public-ingress"},
        expected_connector_operations={"stop-node", "remove-node-resource"},
        stable_workload_nodes=set(),
    )
    _assert_activity_mentions(workflow, removed.run_id, "cloudflared-gateway")
    _assert_public_gateway_unreachable(public_hostname)
    _assert_no_runtime_networks(workspace_id)
    _assert_owned_cloudflare_epoch_states(
        operations_database_url,
        workspace_id=workspace_id,
        expected_statuses=("removed", "removed"),
    )
    _assert_removed_ingress_token_versions_revoked(
        provider_container,
        operations_database_url,
        workspace_id=workspace_id,
        expected_count=2,
    )
    _assert_owned_cloudflare_resources_removed(
        operations_database_url,
        workspace_id=workspace_id,
        api_token_file=bootstrap_dir / "cloudflare-api-token",
        expected_minimum=2,
    )
    _assert_cloudflare_provider_correlation(
        provider_container=provider_container,
        operations_database_url=operations_database_url,
        workspace_id=workspace_id,
    )
    _assert_activity_is_secret_free(workflow)
    _assert_secret_absent_from_activity(
        workflow,
        (bootstrap_dir / "cloudflare-api-token").read_text(encoding="utf-8"),
    )
    _assert_source_live_cloudflare_inventory_unchanged(
        bootstrap_dir / "cloudflare-api-token"
    )


def _checkpoint_cloudflare_phase(
    workflow: HostedWorkflow,
    *,
    phase: str,
    result: PreparedRun | None = None,
    current_graph_id: str | None = None,
    desired_graph_id: str | None = None,
) -> None:
    state_file = os.environ.get("CPK_SOURCE_LIVE_STATE_FILE")
    if not state_file:
        return
    if result is not None:
        current_graph_id = result.current_graph_id
        desired_graph_id = result.desired_graph_id
    if current_graph_id is None or desired_graph_id is None:
        raise RuntimeError("source-live checkpoint graph identity is unavailable")
    record_checkpoint(
        Path(state_file),
        SourceLiveCheckpoint(
            workspace_id=workflow.workspace_id,
            phase=phase,
            current_graph_id=current_graph_id,
            desired_graph_id=desired_graph_id,
        ),
        fail_after_phase=os.environ.get("CPK_SOURCE_LIVE_FAIL_AFTER_PHASE"),
    )


def _run_cloudflare_abort_cleanup(
    *,
    base_url: str,
    server_container: str,
    operations_database_url: str,
    provider_container: str,
    provider_token_file: Path,
    bootstrap_dir: Path,
) -> int:
    checkpoint = read_checkpoint(
        Path(_required_env("CPK_SOURCE_LIVE_STATE_FILE"))
    )
    workspace_id = _required_env("CPK_HOSTED_ACTIVITY_WORKSPACE_ID")
    if checkpoint.workspace_id != workspace_id:
        raise RuntimeError("source-live checkpoint workspace changed")
    active_resources = _load_exact_owned_ingress_resources(
        operations_database_url,
        workspace_id=workspace_id,
    )
    resources = active_resources or _load_all_exact_owned_ingress_resources(
        operations_database_url,
        workspace_id=workspace_id,
    )
    if not resources and checkpoint.phase != "prepared":
        raise RuntimeError("source-live exact Cloudflare evidence was unavailable")
    failed_connector_effects: dict[str, ExactFailedDockerNodeEffect] = {}
    uncertain_connector_runs: set[str] = set()
    for source_run_id in sorted(
        {resource.source_run_id for resource in active_resources}
    ):
        try:
            effect = _load_exact_connector_run_evidence(
                operations_database_url,
                workspace_id=workspace_id,
                source_run_id=source_run_id,
                connector_node_id="cloudflared-gateway",
                accepted_graph_id=checkpoint.current_graph_id,
            )
            if effect is not None:
                failed_connector_effects[source_run_id] = effect
        except Exception:
            uncertain_connector_runs.add(source_run_id)
    emergency_resources = tuple(
        resource
        for resource in active_resources
        if resource.source_run_id in failed_connector_effects
    )
    _print_bounded_abort_snapshot(
        checkpoint,
        resources,
        failed_connector_effects=failed_connector_effects,
        uncertain_connector_runs=uncertain_connector_runs,
    )
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=workspace_id,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )

    def authoritative_cleanup() -> None:
        workflow.wait_ready()
        current_graph_id = workflow.read_current_graph_id()
        workspace = workflow.read_workspace().get("workspace")
        if not isinstance(workspace, dict):
            raise RuntimeError("abort cleanup workspace readback was unavailable")
        desired_graph_id = workspace.get("desired_graph_id")
        if not isinstance(desired_graph_id, str) or not desired_graph_id:
            raise RuntimeError("abort cleanup desired graph was unavailable")
        _disconnect_runtime_networks(
            server_container,
            workspace_id=workspace_id,
        )
        workflow.run_approved_transition(
            title=f"Source-live abort cleanup {checkpoint.phase}",
            graph=DeploymentGraph(workspace_id),
            current_graph_id=current_graph_id,
            expected_desired_graph_id=desired_graph_id,
            sync_runtime_networks=False,
        )

    def verify_authoritative_absence() -> None:
        if uncertain_connector_runs:
            raise RuntimeError("failed connector absence is uncertain")
        _assert_no_node_containers(workspace_id, "cloudflared-gateway")
        _assert_failed_connectors_absent(
            emergency_resources,
            failed_connector_effects=failed_connector_effects,
            uncertain_connector_runs=set(),
        )
        _assert_abort_generated_secret_versions_revoked(
            resources,
            provider_container=provider_container,
            workspace_id=workspace_id,
        )
        _assert_owned_cloudflare_resources_removed(
            operations_database_url,
            workspace_id=workspace_id,
            api_token_file=bootstrap_dir / "cloudflare-api-token",
            expected_minimum=0 if checkpoint.phase == "prepared" else 1,
        )

    def verify_emergency_absence() -> None:
        _assert_no_node_containers(workspace_id, "cloudflared-gateway")
        _assert_abort_generated_secret_versions_revoked(
            resources,
            provider_container=provider_container,
            workspace_id=workspace_id,
        )
        verification_arguments = {
            "api_token_file": bootstrap_dir / "cloudflare-api-token",
            "failed_connector_effects": failed_connector_effects,
            "uncertain_connector_runs": uncertain_connector_runs,
        }
        if active_resources == resources:
            _assert_abort_resources_physically_absent(
                resources,
                connector_resources=emergency_resources,
                **verification_arguments,
            )
        else:
            _assert_abort_resources_physically_absent(
                resources,
                connector_resources=active_resources,
                **verification_arguments,
            )

    report = compensate_abort(
        authoritative_cleanup=authoritative_cleanup,
        verify_authoritative_absence=verify_authoritative_absence,
        verify_emergency_absence=verify_emergency_absence,
        resources=resources,
        emergency_resources=emergency_resources,
        emergency_compensators={
            "cloudflare": lambda resource: _emergency_compensate_cloudflare(
                resource,
                workspace_id=workspace_id,
                provider_token_file=provider_token_file,
                api_token_file=bootstrap_dir / "cloudflare-api-token",
                failed_connector_effect=failed_connector_effects.get(
                    resource.source_run_id
                ),
                connector_required=resource in active_resources,
            )
        },
    )
    _assert_source_live_cloudflare_inventory_unchanged(
        bootstrap_dir / "cloudflare-api-token"
    )
    print(
        json.dumps(
            {
                "abort_cleanup": "completed",
                "authoritative": report.authoritative,
                "emergency_attempted": report.emergency_attempted,
                "resource_count": report.resource_count,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if report.authoritative else 2


def _load_exact_owned_ingress_resources(
    operations_database_url: str,
    *,
    workspace_id: str,
) -> tuple[ExactOwnedIngressResource, ...]:
    query = """
        SELECT
          resource.provider_kind,
          resource.ingress_id,
          resource.epoch,
          resource.tunnel_id,
          resource.dns_record_id,
          resource.hostname,
          resource.zone_id,
          resource.source_run_id,
          left(generated.secret_ref, 257),
          left(generated.metadata->>'provider_version_id', 256),
          left(generated.metadata->>'provider_version_number', 11)
        FROM cpk_cloudflare_ingress_resources AS resource
        JOIN cpk_generated_ingress_secret_references AS generated
          ON generated.workspace_id = resource.workspace_id
         AND generated.source_run_id = resource.source_run_id
         AND generated.source_activity_id = resource.source_activity_id
         AND generated.source_event_id = resource.source_event_id
        WHERE resource.workspace_id = %s
          AND resource.status <> 'removed'
        ORDER BY resource.ingress_id, resource.epoch
    """
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (workspace_id,))
            rows = cursor.fetchall()
    return _decode_exact_owned_ingress_resources(tuple(rows))


def _load_all_exact_owned_ingress_resources(
    operations_database_url: str,
    *,
    workspace_id: str,
) -> tuple[ExactOwnedIngressResource, ...]:
    query = """
        SELECT
          resource.provider_kind,
          resource.ingress_id,
          resource.epoch,
          resource.tunnel_id,
          resource.dns_record_id,
          resource.hostname,
          resource.zone_id,
          resource.source_run_id,
          left(generated.secret_ref, 257),
          left(generated.metadata->>'provider_version_id', 256),
          left(generated.metadata->>'provider_version_number', 11)
        FROM cpk_cloudflare_ingress_resources AS resource
        JOIN cpk_generated_ingress_secret_references AS generated
          ON generated.workspace_id = resource.workspace_id
         AND generated.source_run_id = resource.source_run_id
         AND generated.source_activity_id = resource.source_activity_id
         AND generated.source_event_id = resource.source_event_id
        WHERE resource.workspace_id = %s
        ORDER BY resource.ingress_id, resource.epoch
    """
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (workspace_id,))
            rows = cursor.fetchall()
    return _decode_exact_owned_ingress_resources(tuple(rows))


def _decode_exact_owned_ingress_resources(
    rows: tuple[tuple[Any, ...], ...],
) -> tuple[ExactOwnedIngressResource, ...]:
    resources: list[ExactOwnedIngressResource] = []
    identities: set[tuple[str, int]] = set()
    for row in rows:
        if (
            len(row) != 11
            or row[0] != "cloudflare"
            or type(row[2]) is not int
            or type(row[10]) is not str
            or any(
                type(row[index]) is not str
                for index in (*range(0, 2), *range(3, 10))
            )
        ):
            raise RuntimeError("owned ingress evidence is uncertain")
        identity = (row[1], row[2])
        if identity in identities:
            raise RuntimeError("owned ingress evidence is uncertain")
        identities.add(identity)
        provider_version_number = _decode_provider_version_number(row[10])
        if provider_version_number is None:
            raise RuntimeError("owned ingress evidence is uncertain")
        invalid_resource = False
        try:
            resource = ExactOwnedIngressResource(
                provider_kind=row[0],
                ingress_id=row[1],
                epoch=row[2],
                public_provider_coordinates={
                    "tunnel_id": row[3],
                    "dns_record_id": row[4],
                    "hostname": row[5],
                    "zone_id": row[6],
                },
                source_run_id=row[7],
                secret_reference=row[8],
                provider_version_id=row[9],
                provider_version_number=provider_version_number,
            )
        except (SourceLiveAbortError, TypeError, ValueError):
            invalid_resource = True
        if invalid_resource:
            raise RuntimeError("owned ingress evidence is uncertain")
        resources.append(resource)
    return tuple(resources)


def _decode_provider_version_number(candidate: str) -> int | None:
    if re.fullmatch(r"[1-9][0-9]{0,9}", candidate) is None:
        return None
    decoded = int(candidate)
    return decoded if decoded <= 2_147_483_647 else None


def _load_exact_failed_connector_effect(
    operations_database_url: str,
    *,
    workspace_id: str,
    source_run_id: str,
    connector_node_id: str,
) -> ExactFailedDockerNodeEffect:
    rows = _load_connector_run_rows(
        operations_database_url,
        source_run_id=source_run_id,
    )
    return _decode_exact_failed_connector_effect(
        expected_workspace_id=workspace_id,
        expected_run_id=source_run_id,
        connector_node_id=connector_node_id,
        rows=rows,
    )


def _load_exact_connector_run_evidence(
    operations_database_url: str,
    *,
    workspace_id: str,
    source_run_id: str,
    connector_node_id: str,
    accepted_graph_id: str,
) -> ExactFailedDockerNodeEffect | None:
    rows = _load_connector_run_rows(
        operations_database_url,
        source_run_id=source_run_id,
    )
    return _decode_exact_connector_run_evidence(
        expected_workspace_id=workspace_id,
        expected_run_id=source_run_id,
        connector_node_id=connector_node_id,
        accepted_graph_id=accepted_graph_id,
        rows=rows,
    )


def _decode_exact_connector_run_evidence(
    *,
    expected_workspace_id: str,
    expected_run_id: str,
    connector_node_id: str,
    accepted_graph_id: str,
    rows: tuple[tuple[Any, ...], ...],
) -> ExactFailedDockerNodeEffect | None:
    if not rows or any(len(row) != 7 for row in rows):
        raise RuntimeError("connector run evidence is uncertain")
    identity = rows[0][:6]
    if any(row[:6] != identity for row in rows):
        raise RuntimeError("connector run evidence is uncertain")
    run_id, run_status, row_workspace_id, plan_id, desired_graph_id, payload = (
        identity
    )
    if run_status == "succeeded":
        if (
            run_id != expected_run_id
            or row_workspace_id != expected_workspace_id
            or desired_graph_id != accepted_graph_id
            or type(plan_id) is not str
            or not plan_id
            or type(payload) is not dict
        ):
            raise RuntimeError("connector run evidence is uncertain")
        return None
    if run_status != "failed":
        raise RuntimeError("connector run evidence is uncertain")
    return _decode_exact_failed_connector_effect(
        expected_workspace_id=expected_workspace_id,
        expected_run_id=expected_run_id,
        connector_node_id=connector_node_id,
        rows=rows,
    )


def _load_connector_run_rows(
    operations_database_url: str,
    *,
    source_run_id: str,
) -> tuple[tuple[Any, ...], ...]:
    query = """
        SELECT
          run.run_id,
          run.status,
          request.workspace_id,
          plan.plan_id,
          plan.desired_graph_id,
          plan.payload,
          event.payload
        FROM cpk_activity_runs AS run
        JOIN cpk_execution_requests AS request
          ON request.request_id = run.request_id
         AND request.plan_id = run.plan_id
        JOIN cpk_activity_plans AS plan
          ON plan.plan_id = run.plan_id
        LEFT JOIN cpk_activity_events AS event
          ON event.run_id = run.run_id
         AND event.event_type = 'step_succeeded'
        WHERE run.run_id = %s
        ORDER BY event.ordinal
    """
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (source_run_id,))
            return tuple(cursor.fetchall())


def _decode_exact_failed_connector_effect(
    *,
    expected_workspace_id: str,
    expected_run_id: str,
    connector_node_id: str,
    rows: tuple[tuple[Any, ...], ...],
) -> ExactFailedDockerNodeEffect:
    if not rows or any(len(row) != 7 for row in rows):
        raise RuntimeError("failed connector evidence is uncertain")
    identity = rows[0][:6]
    if any(row[:6] != identity for row in rows):
        raise RuntimeError("failed connector evidence is uncertain")
    run_id, run_status, workspace_id, plan_id, desired_graph_id, plan_payload = identity
    if (
        run_id != expected_run_id
        or run_status != "failed"
        or workspace_id != expected_workspace_id
        or not isinstance(plan_payload, dict)
    ):
        raise RuntimeError("failed connector evidence is uncertain")
    activities = plan_payload.get("activities")
    if not isinstance(activities, list):
        raise RuntimeError("failed connector evidence is uncertain")
    matching_activities = []
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        operation = activity.get("operation")
        target = operation.get("target") if isinstance(operation, dict) else None
        if (
            isinstance(target, dict)
            and operation.get("kind") == "start-node"
            and target.get("kind") == "node"
            and target.get("node_id") == connector_node_id
        ):
            matching_activities.append(activity)
    if len(matching_activities) != 1:
        raise RuntimeError("failed connector evidence is uncertain")
    activity_id = matching_activities[0].get("activity_id")
    matching_events = []
    for row in rows:
        event_payload = row[6]
        if (
            isinstance(event_payload, dict)
            and event_payload.get("activity_id") == activity_id
        ):
            matching_events.append(event_payload)
    if len(matching_events) != 1:
        raise RuntimeError("failed connector evidence is uncertain")
    evidence = matching_events[0].get("evidence")
    if not isinstance(evidence, dict) or evidence.get("node_id") != connector_node_id:
        raise RuntimeError("failed connector evidence is uncertain")
    try:
        return ExactFailedDockerNodeEffect(
            workspace_id=workspace_id,
            run_id=run_id,
            plan_id=plan_id,
            desired_graph_id=desired_graph_id,
            activity_id=activity_id,
            runtime_id=evidence["runtime_id"],
            node_id=evidence["node_id"],
            container_name=evidence["container"],
        )
    except (KeyError, TypeError, RuntimeError):
        raise RuntimeError("failed connector evidence is uncertain") from None


def _print_bounded_abort_snapshot(
    checkpoint: SourceLiveCheckpoint,
    resources: tuple[ExactOwnedIngressResource, ...],
    *,
    failed_connector_effects: dict[str, ExactFailedDockerNodeEffect],
    uncertain_connector_runs: set[str],
) -> None:
    print(
        json.dumps(
            {
                "abort_phase": checkpoint.phase,
                "workspace_id": checkpoint.workspace_id,
                "current_graph_id": checkpoint.current_graph_id,
                "desired_graph_id": checkpoint.desired_graph_id,
                "owned_resource_count": len(resources),
                "failed_connector_count": len(failed_connector_effects),
                "uncertain_connector_count": len(uncertain_connector_runs),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _emergency_compensate_cloudflare(
    resource: ExactOwnedIngressResource,
    *,
    workspace_id: str,
    provider_token_file: Path,
    api_token_file: Path,
    failed_connector_effect: ExactFailedDockerNodeEffect | None,
    connector_required: bool = True,
) -> tuple[str, ...]:
    failed: list[str] = []
    coordinates = resource.public_provider_coordinates
    try:
        _provider_revoke_exact_version(
            workspace_id=workspace_id,
            reference=resource.secret_reference,
            version_id=resource.provider_version_id,
            version_number=resource.provider_version_number,
            provider_token_file=provider_token_file,
            correlation_id=(
                f"source-live-abort:{resource.ingress_id}:{resource.epoch}"
            ),
        )
    except Exception:
        failed.append("custody")

    if failed_connector_effect is None and connector_required:
        failed.append("connector-evidence")
    elif failed_connector_effect is not None:
        try:
            _stop_remove_exact_failed_connector(failed_connector_effect)
        except Exception:
            failed.append("connector")

    try:
        from control_plane_kit_core.secrets import SecretReference, SecretValue
        from control_plane_kit_interpreters.cloudflare import (
            CloudflareApiClient,
            CloudflareZoneAuthority,
        )

        authority = CloudflareZoneAuthority(
            account_id=_required_env("OPENJ92_CLOUDFLARE_ACCOUNT_ID"),
            zone_id=coordinates["zone_id"],
            zone_name=_required_env("OPENJ92_CLOUDFLARE_ZONE"),
            api_token_ref=SecretReference(CLOUDFLARE_API_TOKEN_REFERENCE),
            allowed_hostname_pattern=coordinates["hostname"],
        )
        client = CloudflareApiClient(
            authority,
            api_token=SecretValue(
                api_token_file.read_text(encoding="utf-8").strip()
            ),
        )
    except Exception:
        return tuple((*failed, "dns", "connections", "tunnel"))

    try:
        client.delete_dns_record(coordinates["dns_record_id"])
    except Exception:
        failed.append("dns")
    try:
        client.delete_tunnel_connections(coordinates["tunnel_id"])
    except Exception:
        failed.append("connections")
    try:
        client.delete_tunnel(coordinates["tunnel_id"])
    except Exception:
        failed.append("tunnel")
    return tuple(failed)


def _stop_remove_exact_failed_connector(
    effect: ExactFailedDockerNodeEffect,
) -> None:
    client = docker.from_env()
    try:
        try:
            container = client.containers.get(effect.container_name)
        except docker.errors.NotFound:
            return
        container.reload()
        labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        if (
            container.name != effect.container_name
            or not isinstance(labels, dict)
            or any(
                labels.get(key) != value
                for key, value in effect.expected_labels().items()
            )
        ):
            raise RuntimeError("failed connector ownership is uncertain")
        if container.status == "running":
            container.stop(timeout=10)
        container.remove()
    finally:
        client.close()


def _assert_exact_failed_connector_absent(
    effect: ExactFailedDockerNodeEffect,
) -> None:
    client = docker.from_env()
    try:
        try:
            client.containers.get(effect.container_name)
        except docker.errors.NotFound:
            return
        raise RuntimeError("exact failed connector remains present")
    finally:
        client.close()


def _provider_revoke_exact_version(
    *,
    workspace_id: str,
    reference: str,
    version_id: str,
    version_number: int,
    provider_token_file: Path,
    correlation_id: str,
) -> None:
    suffix = f"/versions/{quote(version_id, safe='')}/revoke"
    status, payload = _provider_request(
        method="POST",
        path=_provider_secret_path(
            workspace_id,
            reference=reference,
            suffix=suffix,
        ),
        provider_token_file=provider_token_file,
        payload={
            "version_number": version_number,
            "caller_subject": "source-live-abort-compensator",
            "correlation_id": correlation_id,
        },
    )
    if status != 200 or payload.get("outcome") != "revoked":
        raise RuntimeError("provider exact version revocation failed")


def _assert_abort_resources_physically_absent(
    resources: tuple[ExactOwnedIngressResource, ...],
    *,
    api_token_file: Path,
    failed_connector_effects: dict[str, ExactFailedDockerNodeEffect],
    uncertain_connector_runs: set[str],
    connector_resources: tuple[ExactOwnedIngressResource, ...] | None = None,
) -> None:
    if connector_resources is None:
        connector_resources = resources
    _assert_failed_connectors_absent(
        connector_resources,
        failed_connector_effects=failed_connector_effects,
        uncertain_connector_runs=uncertain_connector_runs,
    )
    for resource in resources:
        if resource.provider_kind != "cloudflare":
            raise RuntimeError("abort resource provider is unsupported")
        coordinates = resource.public_provider_coordinates
        _assert_cloudflare_resource_absent(
            "/zones/"
            f"{coordinates['zone_id']}/dns_records/{coordinates['dns_record_id']}",
            api_token_file,
        )
        _assert_cloudflare_tunnel_deleted(
            account_id=_required_env("OPENJ92_CLOUDFLARE_ACCOUNT_ID"),
            tunnel_id=coordinates["tunnel_id"],
            api_token_file=api_token_file,
        )


def _assert_failed_connectors_absent(
    resources: tuple[ExactOwnedIngressResource, ...],
    *,
    failed_connector_effects: dict[str, ExactFailedDockerNodeEffect],
    uncertain_connector_runs: set[str],
) -> None:
    expected_run_ids = {resource.source_run_id for resource in resources}
    if uncertain_connector_runs or set(failed_connector_effects) != expected_run_ids:
        raise RuntimeError("failed connector absence is uncertain")
    for source_run_id in sorted(expected_run_ids):
        _assert_exact_failed_connector_absent(
            failed_connector_effects[source_run_id]
        )


def _assert_abort_generated_secret_versions_revoked(
    resources: tuple[ExactOwnedIngressResource, ...],
    *,
    provider_container: str,
    workspace_id: str,
) -> None:
    audit_rows = _provider_audit_rows(provider_container, workspace_id)
    revoked_version_ids = {
        row["version_id"]
        for row in audit_rows
        if row["outcome"] == "revoked" and row["version_id"]
    }
    expected_version_ids = {
        resource.provider_version_id for resource in resources
    }
    if not expected_version_ids.issubset(revoked_version_ids):
        raise RuntimeError("generated ingress secret revocation evidence is incomplete")


def _register_cloudflare_provider_and_references(
    workflow: HostedWorkflow,
) -> str:
    provider = _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/secret-providers",
        {
            "provider_id": PROVIDER_ID,
            "provider_kind": "control-plane-kit-secrets",
            "display_name": "Source-live durable Cloudflare custody",
            "endpoint_reference": PROVIDER_ENDPOINT_REFERENCE,
            "credential_reference": PROVIDER_CREDENTIAL_REFERENCE,
            "allowed_reference_prefixes": [
                CLOUDFLARE_API_TOKEN_REFERENCE,
                CLOUDFLARE_GENERATED_REFERENCE_PREFIX,
                GATEWAY_SIGNING_KEY_REFERENCE,
                GHCR_PULL_CREDENTIAL_REFERENCE,
            ],
            "allowed_intents": [
                CLOUDFLARE_API_TOKEN_INTENT,
                CLOUDFLARE_TUNNEL_TOKEN_INTENT,
                GATEWAY_SIGNING_KEY_INTENT,
                OCI_PULL_CREDENTIAL_INTENT,
            ],
            "admitted_at": _clock(),
            "metadata": {"acceptance": "source-live-cloudflare-custody"},
            "idempotency_key": (
                f"{workflow.workspace_id}:secret-provider:cloudflare-custody"
            ),
        },
    )
    provider_registration_id = str(provider["registration_id"])
    for label, reference, intent in (
        (
            "cloudflare-api-token",
            CLOUDFLARE_API_TOKEN_REFERENCE,
            CLOUDFLARE_API_TOKEN_INTENT,
        ),
        (
            "gateway-signing-key",
            GATEWAY_SIGNING_KEY_REFERENCE,
            GATEWAY_SIGNING_KEY_INTENT,
        ),
        (
            "ghcr-pull-credential",
            GHCR_PULL_CREDENTIAL_REFERENCE,
            OCI_PULL_CREDENTIAL_INTENT,
        ),
    ):
        _http(
            workflow.base_url,
            "POST",
            f"/workspaces/{workflow.workspace_id}/secret-references",
            {
                "reference": reference,
                "provider_registration_id": provider_registration_id,
                "allowed_intents": [intent],
                "admitted_at": _clock(),
                "metadata": {"acceptance": "source-live-cloudflare-custody"},
                "idempotency_key": (
                    f"{workflow.workspace_id}:secret-reference:{label}"
                ),
            },
        )
    return provider_registration_id


def _run_denial_matrix(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    postgres_document: Any,
) -> None:
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-denied-scope",
        worker_id="hosted-worker-no-secret",
        worker_authorization=NO_SECRET_WORKER_AUTHORIZATION,
        expected_provider_io=False,
    )

    source = _workflow(
        base_url,
        server_container,
        workspace_id="workspace-secret-wrong-source",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    _bootstrap_workspace(
        source,
        name="Wrong workspace source",
        product_documents={},
        register_runtime_authority=False,
        register_runtime_delivery=False,
    )
    _register_provider_and_reference(source)
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-wrong-target",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        register_provider=False,
        expected_provider_io=False,
    )

    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-wrong-intent",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        reference_intents=(APPLICATION_TOKEN_INTENT,),
        provider_intents=(APPLICATION_TOKEN_INTENT, POSTGRES_INTENT),
        expected_provider_io=False,
    )
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-revoked-provider",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        revoke_provider=True,
        expected_provider_io=False,
    )
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-revoked-reference",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        revoke_reference=True,
        expected_provider_io=False,
    )
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-missing",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        expected_provider_io=True,
    )
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-wrong-credential",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        credential_reference=WRONG_PROVIDER_CREDENTIAL_REFERENCE,
        expected_provider_io=True,
    )
    _run_denied_case(
        base_url=base_url,
        server_container=server_container,
        provider_container=provider_container,
        postgres_document=postgres_document,
        workspace_id="workspace-secret-unavailable",
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
        stop_provider=True,
        expected_provider_io=False,
    )


def _run_revoked_before_use(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    postgres_document: Any,
    provider_token_file: Path,
    value_file: Path,
) -> None:
    workspace_id = REVOKED_BEFORE_USE_WORKSPACE
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=workspace_id,
        worker_id="hosted-worker",
        worker_authorization=WORKER_AUTHORIZATION,
    )
    current_graph_id = _bootstrap_workspace(
        workflow,
        name="Secret provider revoked before use",
        product_documents={"postgres": postgres_document},
        register_runtime_authority=True,
        register_runtime_delivery=False,
    )
    _register_provider_and_reference(workflow)
    _provider_write_secret(
        workspace_id=workspace_id,
        value_file=value_file,
        provider_token_file=provider_token_file,
        correlation_id=f"{workspace_id}:write",
    )
    runtime_only = workflow.run_approved_transition(
        title="Create empty runtime before revoked use",
        graph=_postgres_graph(postgres_document, workspace_id, node_ids=()),
        current_graph_id=current_graph_id,
    )
    before = _workspace_runtime_resources(workspace_id)
    _provider_revoke_secret(
        workspace_id=workspace_id,
        provider_token_file=provider_token_file,
        correlation_id=f"{workspace_id}:revoke",
    )
    prepared = _prepare_run(
        workflow,
        title="Reject revoked secret before Postgres mutation",
        graph=_postgres_graph(postgres_document, workspace_id),
        current_graph_id=runtime_only.current_graph_id,
        expected_desired_graph_id=runtime_only.desired_graph_id,
    )
    terminal = _execute_until_terminal(workflow, prepared.run_id)
    if terminal.get("coordinator_status") not in {
        "failed",
        "unsupported",
        "uncertain",
        "blocked",
    }:
        raise RuntimeError("revoked provider secret did not stop node realization")
    after = _workspace_runtime_resources(workspace_id)
    if after != before:
        raise RuntimeError("revoked secret use mutated Docker resources")
    _assert_no_node_containers(workspace_id, "postgres")
    rows = _provider_audit_rows(provider_container, workspace_id)
    if not any(
        row["outcome"] == "revoked" and row["intent"] == POSTGRES_INTENT
        for row in rows
    ):
        raise RuntimeError("revoked use did not produce bounded provider audit evidence")
    _disconnect_runtime_networks(server_container, workspace_id=workspace_id)
    cleaned = workflow.run_approved_transition(
        title="Remove empty runtime after revoked use",
        graph=DeploymentGraph(workspace_id),
        current_graph_id=runtime_only.current_graph_id,
        expected_desired_graph_id=prepared.desired_graph_id,
        sync_runtime_networks=False,
    )
    _assert_runtime_activity_mentions(workflow, cleaned.run_id, "docker")


def _run_concurrent_workspace_uses(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    postgres_document: Any,
    operations_database_url: str,
    provider_token_file: Path,
    bootstrap_dir: Path,
) -> None:
    workflows: dict[str, HostedWorkflow] = {}
    current_graph_ids: dict[str, str] = {}
    for index, workspace_id in enumerate(CONCURRENT_WORKSPACES, start=1):
        workflow = _workflow(
            base_url,
            server_container,
            workspace_id=workspace_id,
            worker_id="hosted-worker",
            worker_authorization=WORKER_AUTHORIZATION,
        )
        workflows[workspace_id] = workflow
        current_graph_ids[workspace_id] = _bootstrap_workspace(
            workflow,
            name=f"Concurrent secret workspace {index}",
            product_documents={"postgres": postgres_document},
            register_runtime_authority=True,
            register_runtime_delivery=False,
        )
        _register_provider_and_reference(workflow)
        _provider_write_secret(
            workspace_id=workspace_id,
            value_file=bootstrap_dir / f"postgres-concurrent-{index}",
            provider_token_file=provider_token_file,
            correlation_id=f"{workspace_id}:write",
        )

    def deploy(workspace_id: str):
        return workflows[workspace_id].run_approved_transition(
            title=f"Concurrent provider deployment {workspace_id}",
            graph=_postgres_graph(postgres_document, workspace_id),
            current_graph_id=current_graph_ids[workspace_id],
        )

    with ThreadPoolExecutor(max_workers=len(CONCURRENT_WORKSPACES)) as executor:
        futures = {
            workspace_id: executor.submit(deploy, workspace_id)
            for workspace_id in CONCURRENT_WORKSPACES
        }
        deployed = {
            workspace_id: future.result()
            for workspace_id, future in futures.items()
        }

    versions: set[str] = set()
    for workspace_id, transition in deployed.items():
        _assert_activity_mentions(
            workflows[workspace_id],
            transition.run_id,
            "postgres",
        )
        _assert_provider_and_operations_correlation(
            provider_container=provider_container,
            operations_database_url=operations_database_url,
            workspace_id=workspace_id,
        )
        resolved = _latest_successful_resolution(provider_container, workspace_id)
        versions.add(resolved["version_id"])
    if len(versions) != len(CONCURRENT_WORKSPACES):
        raise RuntimeError("concurrent workspaces did not preserve version isolation")

    for workspace_id, transition in deployed.items():
        workflow = workflows[workspace_id]
        _disconnect_runtime_networks(server_container, workspace_id=workspace_id)
        removed = workflow.run_approved_transition(
            title=f"Concurrent provider teardown {workspace_id}",
            graph=DeploymentGraph(workspace_id),
            current_graph_id=transition.current_graph_id,
            expected_desired_graph_id=transition.desired_graph_id,
            sync_runtime_networks=False,
        )
        _assert_activity_mentions(workflow, removed.run_id, "postgres")
        _assert_no_node_containers(workspace_id, "postgres")
        _assert_activity_is_secret_free(workflow)


def _assert_resolution_revoke_race(
    *,
    provider_container: str,
    operations_database_url: str,
    workspace_id: str,
    provider_token_file: Path,
    first_resolution: dict[str, str],
) -> None:
    operations_correlations = _operations_correlations(
        operations_database_url,
        workspace_id=workspace_id,
    )
    correlation_id = first_resolution["correlation_id"]
    if correlation_id not in operations_correlations:
        raise RuntimeError("race correlation was not admitted by operations")
    barrier = threading.Barrier(2)

    def replay() -> tuple[int, dict[str, Any]]:
        barrier.wait()
        return _provider_request(
            method="POST",
            path=_provider_secret_path(workspace_id, suffix="/resolve"),
            provider_token_file=provider_token_file,
            payload={
                "intent": POSTGRES_INTENT,
                "caller_subject": first_resolution["caller_subject"],
                "correlation_id": correlation_id,
            },
        )

    def revoke() -> tuple[int, dict[str, Any]]:
        barrier.wait()
        return _provider_request(
            method="POST",
            path=_provider_secret_path(workspace_id, suffix="/revoke"),
            provider_token_file=provider_token_file,
            payload={
                "caller_subject": "source-live-race",
                "correlation_id": f"{workspace_id}:race-revoke",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        replay_future = executor.submit(replay)
        revoke_future = executor.submit(revoke)
        replay_status, replay_payload = replay_future.result()
        revoke_status, _ = revoke_future.result()

    if revoke_status != 200:
        raise RuntimeError("provider revoke race did not complete")
    if replay_status == 200:
        metadata = replay_payload.get("metadata", {})
        if metadata.get("version_id") != first_resolution["version_id"]:
            raise RuntimeError("winning replay changed its pinned version")
    elif replay_status == 409:
        detail = replay_payload.get("detail", {})
        if detail.get("code") != "secret-revoked":
            raise RuntimeError("losing replay did not fail as revoked")
    else:
        raise RuntimeError("provider resolve/revoke race had an invalid outcome")
    rows = _provider_audit_rows(provider_container, workspace_id)
    matching = [row for row in rows if row["correlation_id"] == correlation_id]
    if not matching or matching[-1]["outcome"] not in {"resolved", "revoked"}:
        raise RuntimeError("provider race audit did not preserve transaction outcome")


def _run_denied_case(
    *,
    base_url: str,
    server_container: str,
    provider_container: str,
    postgres_document: Any,
    workspace_id: str,
    worker_id: str,
    worker_authorization: str,
    register_provider: bool = True,
    provider_intents: tuple[str, ...] = (POSTGRES_INTENT,),
    reference_intents: tuple[str, ...] = (POSTGRES_INTENT,),
    credential_reference: str = PROVIDER_CREDENTIAL_REFERENCE,
    revoke_provider: bool = False,
    revoke_reference: bool = False,
    stop_provider: bool = False,
    expected_provider_io: bool,
) -> None:
    workflow = _workflow(
        base_url,
        server_container,
        workspace_id=workspace_id,
        worker_id=worker_id,
        worker_authorization=worker_authorization,
    )
    current_graph_id = _bootstrap_workspace(
        workflow,
        name=f"Secret provider denied case {workspace_id}",
        product_documents={"postgres": postgres_document},
        register_runtime_authority=True,
        register_runtime_delivery=False,
    )
    provider_registration_id = None
    reference_registration_id = None
    if register_provider:
        provider_registration_id, reference_registration_id = (
            _register_provider_and_reference(
                workflow,
                provider_intents=provider_intents,
                reference_intents=reference_intents,
                credential_reference=credential_reference,
            )
        )
    if revoke_provider:
        if provider_registration_id is None:
            raise RuntimeError("provider revocation requires a registration")
        _revoke_provider(workflow)
    if revoke_reference:
        if reference_registration_id is None:
            raise RuntimeError("reference revocation requires a registration")
        _revoke_reference(workflow, reference_registration_id)

    audit_before = _provider_audit_count(provider_container, workspace_id)
    if stop_provider:
        docker.from_env().containers.get(provider_container).stop(timeout=10)
    try:
        prepared = _prepare_run(
            workflow,
            title=f"Denied secret use {workspace_id}",
            graph=_postgres_graph(postgres_document, workspace_id),
            current_graph_id=current_graph_id,
        )
        terminal = _execute_until_terminal(workflow, prepared.run_id)
        if terminal.get("coordinator_status") not in {
            "failed",
            "unsupported",
            "uncertain",
            "blocked",
        }:
            raise RuntimeError(
                f"secret denial did not stop execution for {workspace_id}: {terminal}"
            )
    finally:
        if stop_provider:
            docker.from_env().containers.get(provider_container).start()
            _wait_provider_ready()

    _assert_no_node_containers(workspace_id, "postgres")
    audit_after = _provider_audit_count(provider_container, workspace_id)
    if expected_provider_io:
        if audit_after <= audit_before and credential_reference == PROVIDER_CREDENTIAL_REFERENCE:
            raise RuntimeError(
                f"expected bounded provider IO was not audited for {workspace_id}"
            )
    elif audit_after != audit_before:
        raise RuntimeError(
            f"denied secret use reached provider IO for {workspace_id}"
        )


def _workflow(
    base_url: str,
    server_container: str,
    *,
    workspace_id: str,
    worker_id: str,
    worker_authorization: str,
) -> HostedWorkflow:
    return HostedWorkflow(
        base_url,
        workspace_id=workspace_id,
        worker_id=worker_id,
        server_container=server_container,
        worker_authorization=worker_authorization,
    )


def _register_provider_and_reference(
    workflow: HostedWorkflow,
    *,
    provider_intents: tuple[str, ...] = (POSTGRES_INTENT,),
    reference_intents: tuple[str, ...] = (POSTGRES_INTENT,),
    credential_reference: str = PROVIDER_CREDENTIAL_REFERENCE,
) -> tuple[str, str]:
    provider = _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/secret-providers",
        {
            "provider_id": PROVIDER_ID,
            "provider_kind": "control-plane-kit-secrets",
            "display_name": "Source-live durable secrets",
            "endpoint_reference": PROVIDER_ENDPOINT_REFERENCE,
            "credential_reference": credential_reference,
            "allowed_reference_prefixes": [POSTGRES_PASSWORD_REFERENCE],
            "allowed_intents": list(provider_intents),
            "admitted_at": _clock(),
            "metadata": {"acceptance": "source-live"},
            "idempotency_key": f"{workflow.workspace_id}:secret-provider",
        },
    )
    provider_registration_id = str(provider["registration_id"])
    reference = _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/secret-references",
        {
            "reference": POSTGRES_PASSWORD_REFERENCE,
            "provider_registration_id": provider_registration_id,
            "allowed_intents": list(reference_intents),
            "admitted_at": _clock(),
            "metadata": {"acceptance": "source-live"},
            "idempotency_key": f"{workflow.workspace_id}:secret-reference",
        },
    )
    return provider_registration_id, str(reference["registration_id"])


def _revoke_provider(workflow: HostedWorkflow) -> None:
    _http(
        workflow.base_url,
        "POST",
        f"/workspaces/{workflow.workspace_id}/secret-providers/{PROVIDER_ID}/revoke",
        {
            "revoked_at": _clock(),
            "idempotency_key": f"{workflow.workspace_id}:secret-provider:revoke",
        },
    )


def _revoke_reference(workflow: HostedWorkflow, registration_id: str) -> None:
    _http(
        workflow.base_url,
        "POST",
        (
            f"/workspaces/{workflow.workspace_id}/secret-references/"
            f"{registration_id}/revoke"
        ),
        {
            "revoked_at": _clock(),
            "idempotency_key": f"{workflow.workspace_id}:secret-reference:revoke",
        },
    )


def _assert_provider_metadata_is_secret_free(workflow: HostedWorkflow) -> None:
    providers = _mcp_read(
        workflow.base_url,
        "read.secret-providers",
        {"workspace_id": workflow.workspace_id, "limit": 10, "offset": 0},
    )
    references = _mcp_read(
        workflow.base_url,
        "read.secret-references",
        {"workspace_id": workflow.workspace_id, "limit": 10, "offset": 0},
    )
    rendered = json.dumps(
        {"providers": providers, "references": references},
        separators=(",", ":"),
        sort_keys=True,
    ).lower()
    for forbidden_key in (
        "value_base64",
        "ciphertext",
        "private_key",
        "access_token",
    ):
        if forbidden_key in rendered:
            raise RuntimeError("secret provider metadata exposed secret material")


def _postgres_graph(
    postgres_document: Any,
    workspace_id: str,
    *,
    node_ids: tuple[str, ...] = ("postgres",),
) -> DeploymentGraph:
    product = postgres_document.product
    postgres_nodes = tuple(
        instantiate_product(
            product,
            node_id,
            ProductInstanceConfiguration.from_contract(product.runtime_contract),
        )
        for node_id in node_ids
    )
    return compile_topology(
        DeploymentTopology(
            workspace_id,
            DockerRuntime(
                runtime_id="docker",
                network_name=f"control-plane-kit-{workspace_id}-docker",
                authority_ref=RuntimeAuthorityReference(LOCAL_DOCKER_AUTHORITY_REF),
                children=postgres_nodes,
            ),
        )
    )


def _prepare_run(
    workflow: HostedWorkflow,
    *,
    title: str,
    graph: DeploymentGraph,
    current_graph_id: str,
    expected_desired_graph_id: str | None = None,
) -> PreparedRun:
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
    approval_id = str(approval["request_id"])
    workflow.assert_approval_visible(approval_id, plan_id)
    workflow.approve(session_id=session_id, title=title, approval=approval)
    request_id = workflow.admit(
        session_id=session_id,
        title=title,
        plan_id=plan_id,
        approval_id=approval_id,
    )
    run_id = workflow.claim(title=title, request_id=request_id)
    workflow.start_run(title=title, run_id=run_id)
    return PreparedRun(
        run_id=run_id,
        plan_id=plan_id,
        current_graph_id=current_graph_id,
        desired_graph_id=desired_graph_id,
    )


def _execute_until_terminal(
    workflow: HostedWorkflow,
    run_id: str,
) -> dict[str, Any]:
    for attempt in range(40):
        _sync_runtime_networks(
            workflow.server_container,
            workspace_id=workflow.workspace_id,
        )
        result = _mcp_tool(
            workflow.base_url,
            "command.deployment.execute",
            {
                "workspace_id": workflow.workspace_id,
                "run_id": run_id,
                "worker_id": workflow.worker_id,
                "actor_scopes": [PolicyScope.EXECUTION_OPERATE.value],
                "idempotency_key": (
                    f"{workflow.workspace_id}:denied-execute:{attempt}"
                ),
                "max_effects": 1,
            },
            timeout=60,
            authorization=workflow.worker_authorization,
        )
        if result["coordinator_status"] in {
            "completed",
            "failed",
            "unsupported",
            "uncertain",
            "blocked",
        }:
            return result
    raise RuntimeError("denied source-live run did not reach a terminal state")


def _restart_provider(container_id: str) -> None:
    _restart_container(container_id)
    _wait_provider_ready()


def _restart_cpk_server(
    container_id: str,
    workflow: HostedWorkflow,
    *,
    ready_policy: VerificationPolicy,
) -> None:
    _restart_container(container_id)
    workflow.wait_ready(policy=ready_policy)
    if workflow.read_current_graph_id() == "":
        raise RuntimeError("cpk-server restart did not restore workspace state")


def _restart_container(container_id: str) -> None:
    container = docker.from_env().containers.get(container_id)
    container.reload()
    previous_started_at = str(container.attrs["State"]["StartedAt"])
    container.stop(timeout=10)
    container.reload()
    if container.attrs["State"]["Running"]:
        raise RuntimeError("container did not stop before restart")
    container.start()
    deadline = time.monotonic() + CONTAINER_RESTART_TIMEOUT_SECONDS
    stable_since: float | None = None
    while (now := time.monotonic()) < deadline:
        container.reload()
        state = container.attrs["State"]
        crossed_restart_boundary = str(state["StartedAt"]) != previous_started_at
        if crossed_restart_boundary and state["Running"]:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= CONTAINER_RESTART_STABILITY_SECONDS:
                return
        elif crossed_restart_boundary:
            if state.get("Status") in {"dead", "exited"}:
                raise RuntimeError(
                    "container exited before restart stability: "
                    + json.dumps(
                        _bounded_container_state(container),
                        sort_keys=True,
                        separators=(",", ": "),
                    )
                )
            stable_since = None
        else:
            stable_since = None
        time.sleep(0.25)
    raise RuntimeError(
        "container did not reach stable running state after restart: "
        + json.dumps(
            _bounded_container_state(container),
            sort_keys=True,
            separators=(",", ": "),
        )
    )


def _bounded_container_state(container: Any) -> dict[str, Any]:
    state = container.attrs.get("State", {})
    health = state.get("Health")
    health_status = health.get("Status") if isinstance(health, dict) else None
    networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
    network_names = sorted(str(name) for name in networks)
    network_addresses = {
        str(name): str(material.get("IPAddress", ""))
        for name, material in sorted(networks.items())
        if isinstance(material, dict)
    }
    return {
        "container_id": str(container.id)[:12],
        "container_name": str(container.name),
        "image_id": str(container.image.id),
        "status": str(state.get("Status", "unknown")),
        "running": state.get("Running") is True,
        "restarting": state.get("Restarting") is True,
        "paused": state.get("Paused") is True,
        "dead": state.get("Dead") is True,
        "oom_killed": state.get("OOMKilled") is True,
        "exit_code": state.get("ExitCode"),
        "health_status": health_status,
        "started_at": str(state.get("StartedAt", "")),
        "finished_at": str(state.get("FinishedAt", "")),
        "network_names": network_names,
        "network_addresses": network_addresses,
    }


def _verification_policy(
    product_document: Any,
    check_id: str,
) -> VerificationPolicy:
    for check in product_document.product.runtime_contract.verification.checks:
        if check.check_id == check_id:
            return check.policy
    raise RuntimeError(f"product verification check is missing: {check_id}")


def _wait_provider_ready() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen("http://cpk-secrets:8081/health/ready", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("secret provider did not become ready")


def _provider_write_secret(
    *,
    workspace_id: str,
    reference: str = POSTGRES_PASSWORD_REFERENCE,
    intent: str = POSTGRES_INTENT,
    value_file: Path,
    provider_token_file: Path,
    correlation_id: str,
) -> ProviderVersionReceipt:
    status, payload = _provider_request(
        method="POST",
        path=_provider_secret_path(workspace_id, reference=reference),
        provider_token_file=provider_token_file,
        payload={
            "value_base64": base64.b64encode(value_file.read_bytes()).decode("ascii"),
            "intent": intent,
            "labels": {"intent": intent},
            "caller_subject": "source-live-bootstrap",
            "correlation_id": correlation_id,
        },
    )
    if status != 200 or payload.get("outcome") != "stored":
        raise RuntimeError("provider fixture write failed")
    return _provider_version_receipt(payload)


def _provider_rotate_secret(
    *,
    workspace_id: str,
    value_file: Path,
    provider_token_file: Path,
    correlation_id: str,
) -> str:
    status, payload = _provider_request(
        method="POST",
        path=_provider_secret_path(workspace_id, suffix="/rotate"),
        provider_token_file=provider_token_file,
        payload={
            "value_base64": base64.b64encode(value_file.read_bytes()).decode("ascii"),
            "intent": POSTGRES_INTENT,
            "labels": {"intent": POSTGRES_INTENT},
            "caller_subject": "source-live-rotation",
            "correlation_id": correlation_id,
        },
    )
    if status != 200 or payload.get("outcome") != "rotated":
        raise RuntimeError("provider fixture rotation failed")
    return _metadata_version(payload)


def _provider_revoke_secret(
    *,
    workspace_id: str,
    reference: str = POSTGRES_PASSWORD_REFERENCE,
    provider_token_file: Path,
    correlation_id: str,
) -> None:
    status, payload = _provider_request(
        method="POST",
        path=_provider_secret_path(
            workspace_id,
            reference=reference,
            suffix="/revoke",
        ),
        provider_token_file=provider_token_file,
        payload={
            "caller_subject": "source-live-revocation",
            "correlation_id": correlation_id,
        },
    )
    if status != 200 or payload.get("outcome") != "revoked":
        raise RuntimeError("provider fixture revocation failed")


def _provider_resolve_metadata(
    *,
    workspace_id: str,
    reference: str = POSTGRES_PASSWORD_REFERENCE,
    intent: str = POSTGRES_INTENT,
    provider_token_file: Path,
    caller_subject: str,
    correlation_id: str,
) -> str:
    status, payload = _provider_request(
        method="POST",
        path=_provider_secret_path(
            workspace_id,
            reference=reference,
            suffix="/resolve",
        ),
        provider_token_file=provider_token_file,
        payload={
            "intent": intent,
            "caller_subject": caller_subject,
            "correlation_id": correlation_id,
        },
    )
    if status != 200 or payload.get("outcome") != "resolved":
        raise RuntimeError("provider correlation replay failed")
    payload.pop("value_base64", None)
    return _metadata_version(payload)


def _provider_request(
    *,
    method: str,
    path: str,
    provider_token_file: Path,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    request = Request(
        f"{PROVIDER_BASE_URL}{path}",
        method=method,
        headers={
            "Authorization": (
                f"Bearer {provider_token_file.read_text(encoding='utf-8').strip()}"
            ),
            "Content-Type": "application/json",
        },
        data=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        ),
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            decoded = json.loads(response.read())
    except HTTPError as error:
        status = error.code
        decoded = json.loads(error.read())
    if not isinstance(decoded, dict):
        raise RuntimeError("provider response was malformed")
    return status, decoded


def _provider_secret_path(
    workspace_id: str,
    *,
    reference: str = POSTGRES_PASSWORD_REFERENCE,
    suffix: str = "",
) -> str:
    encoded = base64.urlsafe_b64encode(reference.encode("utf-8"))
    secret_id = f"cpk1_{encoded.rstrip(b'=').decode('ascii')}"
    return f"/v1/workspaces/{workspace_id}/secrets/{secret_id}{suffix}"


def _metadata_version(payload: dict[str, Any]) -> str:
    return _provider_version_receipt(payload).version_id


def _provider_version_receipt(payload: dict[str, Any]) -> ProviderVersionReceipt:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("provider response omitted secret metadata")
    version_id = metadata.get("version_id")
    if not isinstance(version_id, str) or not version_id:
        raise RuntimeError("provider response omitted secret version identity")
    version_number = metadata.get("version_number")
    if type(version_number) is not int or version_number < 1:
        raise RuntimeError("provider response omitted secret version number")
    return ProviderVersionReceipt(version_id, version_number)


def _workspace_runtime_resources(workspace_id: str) -> tuple[tuple[str, ...], ...]:
    client = docker.from_env()
    label = f"org.openj92.cpk.workspace={workspace_id}"
    return (
        tuple(
            sorted(
                container.id
                for container in client.containers.list(
                    all=True,
                    filters={"label": label},
                )
            )
        ),
        tuple(
            sorted(
                network.id
                for network in client.networks.list(filters={"label": label})
            )
        ),
        tuple(
            sorted(
                volume.id
                for volume in client.volumes.list(filters={"label": label})
            )
        ),
    )


def _assert_owned_cloudflare_resources_removed(
    operations_database_url: str,
    *,
    workspace_id: str,
    api_token_file: Path,
    expected_minimum: int,
) -> None:
    query = """
        SELECT tunnel_id, dns_record_id, tunnel_name, hostname, zone_id, status
        FROM cpk_cloudflare_ingress_resources
        WHERE workspace_id = %s
        ORDER BY epoch
    """
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (workspace_id,))
            resources = cursor.fetchall()
    if len(resources) < expected_minimum:
        raise RuntimeError("operations omitted owned Cloudflare resource evidence")
    tunnel_ids = {str(row[0]) for row in resources}
    if len(tunnel_ids) != len(resources):
        raise RuntimeError("Cloudflare recreation reused a prior tunnel identity")
    for tunnel_id, dns_record_id, _name, hostname, zone_id, status in resources:
        if status != "removed":
            raise RuntimeError("owned Cloudflare resource was not durably removed")
        if hostname != _required_env("CPK_PUBLIC_GATEWAY_HOSTNAME"):
            raise RuntimeError("owned Cloudflare evidence changed the test hostname")
        _assert_cloudflare_resource_absent(
            f"/zones/{zone_id}/dns_records/{dns_record_id}",
            api_token_file,
        )
        _assert_cloudflare_tunnel_deleted(
            account_id=_required_env("OPENJ92_CLOUDFLARE_ACCOUNT_ID"),
            tunnel_id=str(tunnel_id),
            api_token_file=api_token_file,
        )


def _assert_cloudflare_resource_absent(
    path: str,
    api_token_file: Path,
) -> None:
    request = Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method="GET",
        headers={
            "Authorization": (
                f"Bearer {api_token_file.read_text(encoding='utf-8').strip()}"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
    if status != 404:
        raise RuntimeError(
            f"owned Cloudflare resource remained after teardown: status={status}"
        )


def _assert_cloudflare_tunnel_deleted(
    *,
    account_id: str,
    tunnel_id: str,
    api_token_file: Path,
) -> None:
    base_path = f"/accounts/{account_id}/cfd_tunnel"
    exact_status, exact_payload = _cloudflare_api_get_json(
        f"{base_path}/{tunnel_id}",
        api_token_file,
    )
    active_status, active_payload = _cloudflare_api_get_json(
        f"{base_path}?is_deleted=false&uuid={tunnel_id}&per_page=1",
        api_token_file,
    )
    _validate_cloudflare_tunnel_deletion(
        tunnel_id=tunnel_id,
        exact_status=exact_status,
        exact_payload=exact_payload,
        active_status=active_status,
        active_payload=active_payload,
    )


def _cloudflare_api_get_json(
    path: str,
    api_token_file: Path,
) -> tuple[int, dict[str, object] | None]:
    request = Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method="GET",
        headers={
            "Authorization": (
                f"Bearer {api_token_file.read_text(encoding='utf-8').strip()}"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read(65_537)
    except HTTPError as error:
        status = error.code
        body = error.read(65_537)
    if len(body) > 65_536:
        raise RuntimeError("Cloudflare deletion response exceeded evidence limit")
    if status == 404:
        return status, None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Cloudflare deletion response was malformed") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Cloudflare deletion response was malformed")
    return status, payload


def _cloudflare_inventory_snapshot(
    api_token_file: Path,
) -> CloudflareInventorySnapshot:
    zone_id = _required_env("OPENJ92_CLOUDFLARE_ZONE_ID")
    account_id = _required_env("OPENJ92_CLOUDFLARE_ACCOUNT_ID")
    dns_records = _cloudflare_bounded_inventory(
        f"/zones/{zone_id}/dns_records",
        api_token_file,
        fields=("id", "type", "name", "content", "proxied", "ttl"),
    )
    active_tunnels = _cloudflare_bounded_inventory(
        f"/accounts/{account_id}/cfd_tunnel",
        api_token_file,
        fields=("id", "name", "config_src", "deleted_at"),
        query="is_deleted=false",
    )
    return CloudflareInventorySnapshot(
        dns_record_count=len(dns_records),
        dns_record_digest=_bounded_inventory_digest(dns_records),
        active_tunnel_count=len(active_tunnels),
        active_tunnel_digest=_bounded_inventory_digest(active_tunnels),
    )


def _cloudflare_bounded_inventory(
    path: str,
    api_token_file: Path,
    *,
    fields: tuple[str, ...],
    query: str = "",
) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for page in range(1, 21):
        separator = "&" if query else ""
        status, payload = _cloudflare_api_get_json(
            f"{path}?{query}{separator}per_page=100&page={page}",
            api_token_file,
        )
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("protected Cloudflare inventory read was unavailable")
        result = payload.get("result")
        if not isinstance(result, list) or len(result) > 100:
            raise RuntimeError("protected Cloudflare inventory response was malformed")
        for value in result:
            if not isinstance(value, dict):
                raise RuntimeError("protected Cloudflare inventory item was malformed")
            records.append({field: value.get(field) for field in fields})
            if len(records) > 100_000:
                raise RuntimeError("protected Cloudflare inventory exceeded evidence limit")
        result_info = payload.get("result_info")
        total_pages = (
            result_info.get("total_pages")
            if isinstance(result_info, dict)
            else None
        )
        if type(total_pages) is int and total_pages > 20:
            raise RuntimeError("protected Cloudflare inventory exceeded page limit")
        if not result or (type(total_pages) is int and page >= total_pages):
            break
    else:
        raise RuntimeError("protected Cloudflare inventory exceeded page limit")
    return tuple(sorted(records, key=lambda item: json.dumps(item, sort_keys=True)))


def _bounded_inventory_digest(records: tuple[dict[str, object], ...]) -> str:
    encoded = json.dumps(
        records,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_protected_cloudflare_inventory_unchanged(
    before: CloudflareInventorySnapshot,
    after: CloudflareInventorySnapshot,
) -> None:
    if after != before:
        raise RuntimeError("protected Cloudflare inventory changed")


def _record_protected_cloudflare_inventory(
    path: Path,
    api_token_file: Path,
) -> None:
    snapshot = _cloudflare_inventory_snapshot(api_token_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(snapshot.descriptor(), separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def _record_source_live_cloudflare_inventory(api_token_file: Path) -> None:
    value = os.environ.get("CPK_SOURCE_LIVE_CLOUDFLARE_INVENTORY_FILE")
    if value:
        _record_protected_cloudflare_inventory(Path(value), api_token_file)


def _assert_source_live_cloudflare_inventory_unchanged(
    api_token_file: Path,
) -> None:
    value = os.environ.get("CPK_SOURCE_LIVE_CLOUDFLARE_INVENTORY_FILE")
    if value:
        _assert_protected_cloudflare_inventory_unchanged(
            Path(value),
            api_token_file,
        )


def _assert_protected_cloudflare_inventory_unchanged(
    path: Path,
    api_token_file: Path,
) -> None:
    try:
        before = CloudflareInventorySnapshot(**json.loads(path.read_text("utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("protected Cloudflare inventory baseline was unavailable") from error
    after = _cloudflare_inventory_snapshot(api_token_file)
    _require_protected_cloudflare_inventory_unchanged(before, after)


def _validate_cloudflare_tunnel_deletion(
    *,
    tunnel_id: str,
    exact_status: int,
    exact_payload: dict[str, object] | None,
    active_status: int,
    active_payload: dict[str, object] | None,
) -> None:
    if exact_status == 404:
        pass
    elif exact_status == 200:
        result = (
            exact_payload.get("result")
            if isinstance(exact_payload, dict)
            and exact_payload.get("success") is True
            else None
        )
        if (
            not isinstance(result, dict)
            or result.get("id") != tunnel_id
            or not isinstance(result.get("deleted_at"), str)
            or not result["deleted_at"].strip()
        ):
            raise RuntimeError(
                "Cloudflare tunnel tombstone did not match owned deletion"
            )
    else:
        raise RuntimeError(
            f"Cloudflare tunnel deletion could not be verified: status={exact_status}"
        )

    active_results = (
        active_payload.get("result")
        if active_status == 200
        and isinstance(active_payload, dict)
        and active_payload.get("success") is True
        else None
    )
    if not isinstance(active_results, list) or not all(
        isinstance(candidate, dict) for candidate in active_results
    ):
        raise RuntimeError("Cloudflare active tunnel inventory was malformed")
    if any(candidate.get("id") == tunnel_id for candidate in active_results):
        raise RuntimeError("owned Cloudflare tunnel remained active after teardown")


def _assert_cloudflare_provider_correlation(
    *,
    provider_container: str,
    operations_database_url: str,
    workspace_id: str,
) -> None:
    provider_rows = _provider_audit_rows(provider_container, workspace_id)
    for intent in (
        CLOUDFLARE_API_TOKEN_INTENT,
        CLOUDFLARE_TUNNEL_TOKEN_INTENT,
        OCI_PULL_CREDENTIAL_INTENT,
    ):
        resolved = [
            row
            for row in provider_rows
            if row["outcome"] == "resolved" and row["intent"] == intent
        ]
        if not resolved:
            raise RuntimeError(f"provider omitted successful {intent} resolution audit")
        operation_correlations = _operations_correlations(
            operations_database_url,
            workspace_id=workspace_id,
            intent=intent,
        )
        if not {row["correlation_id"] for row in resolved}.issubset(
            operation_correlations
        ):
            raise RuntimeError(f"operations/provider {intent} correlation diverged")

    stored_tunnel_versions = {
        row["version_id"]
        for row in provider_rows
        if row["outcome"] == "stored"
        and row["intent"] == CLOUDFLARE_TUNNEL_TOKEN_INTENT
        and row["version_id"]
    }
    revoked_tunnel_versions = {
        row["version_id"]
        for row in provider_rows
        if row["outcome"] == "revoked"
        and row["intent"] == CLOUDFLARE_TUNNEL_TOKEN_INTENT
        and row["version_id"]
    }
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT metadata->>'provider_version_id'
                FROM cpk_generated_ingress_secret_references
                WHERE workspace_id = %s
                  AND purpose = 'cloudflared-tunnel-token'
                ORDER BY recorded_at
                """,
                (workspace_id,),
            )
            recorded_versions = {str(row[0]) for row in cursor.fetchall()}
    if len(recorded_versions) < 2 or recorded_versions != stored_tunnel_versions:
        raise RuntimeError("generated tunnel custody/version evidence diverged")
    if not recorded_versions.issubset(revoked_tunnel_versions):
        raise RuntimeError("teardown did not revoke every generated tunnel token")


def _provider_audit_rows(
    provider_container: str,
    workspace_id: str,
) -> list[dict[str, str]]:
    script = (
        "import json,sqlite3,sys;"
        "c=sqlite3.connect('/var/lib/cpk-secrets/secrets.sqlite3');"
        "rows=c.execute("
        "\"SELECT correlation_id,outcome,intent,caller_subject,"
        "version_id,secret_id,code "
        "FROM audit_records WHERE workspace_id=? ORDER BY rowid\","
        "(sys.argv[1],)).fetchall();"
        "print(json.dumps([dict(zip("
        "('correlation_id','outcome','intent','caller_subject',"
        "'version_id','secret_id','code'),r)) for r in rows]))"
    )
    result = docker.from_env().containers.get(provider_container).exec_run(
        ["python", "-c", script, workspace_id]
    )
    if result.exit_code != 0:
        raise RuntimeError("provider audit evidence was unavailable")
    decoded = json.loads(result.output.decode("utf-8"))
    if not isinstance(decoded, list):
        raise RuntimeError("provider audit evidence was malformed")
    return decoded


def _provider_audit_count(provider_container: str, workspace_id: str) -> int:
    return len(_provider_audit_rows(provider_container, workspace_id))


def _latest_successful_resolution(
    provider_container: str,
    workspace_id: str,
    *,
    intent: str = POSTGRES_INTENT,
) -> dict[str, str]:
    rows = [
        row
        for row in _provider_audit_rows(provider_container, workspace_id)
        if row["outcome"] == "resolved"
        and row["intent"] == intent
        and row["version_id"]
    ]
    if not rows:
        raise RuntimeError(f"provider had no successful {intent} resolution")
    return rows[-1]


def _assert_provider_version_history(
    provider_container: str,
    *,
    workspace_id: str,
    expected_versions: set[str],
) -> None:
    script = (
        "import json,sqlite3,sys;"
        "c=sqlite3.connect('/var/lib/cpk-secrets/secrets.sqlite3');"
        "rows=c.execute("
        "\"SELECT version_id,status FROM secret_versions "
        "WHERE workspace_id=? ORDER BY version_number\","
        "(sys.argv[1],)).fetchall();"
        "print(json.dumps(rows))"
    )
    result = docker.from_env().containers.get(provider_container).exec_run(
        ["python", "-c", script, workspace_id]
    )
    if result.exit_code != 0:
        raise RuntimeError("provider version history was unavailable")
    rows = json.loads(result.output.decode("utf-8"))
    versions = {str(row[0]) for row in rows}
    if not expected_versions.issubset(versions):
        raise RuntimeError("provider did not retain rotated version history")


def _assert_provider_version_revoked(
    provider_container: str,
    *,
    workspace_id: str,
    expected_version_id: str,
) -> None:
    script = (
        "import json,sqlite3,sys;"
        "c=sqlite3.connect('/var/lib/cpk-secrets/secrets.sqlite3');"
        "rows=c.execute("
        "\"SELECT version_id,status FROM secret_versions "
        "WHERE workspace_id=? AND version_id=?\","
        "(sys.argv[1],sys.argv[2])).fetchall();"
        "print(json.dumps(rows))"
    )
    result = docker.from_env().containers.get(provider_container).exec_run(
        ["python", "-c", script, workspace_id, expected_version_id]
    )
    if result.exit_code != 0:
        raise RuntimeError("exact provider version status was unavailable")
    rows = json.loads(result.output.decode("utf-8"))
    if rows != [[expected_version_id, "revoked"]]:
        raise RuntimeError("exact old provider version was not revoked")


def _operations_correlations(
    operations_database_url: str,
    *,
    workspace_id: str,
    intent: str = POSTGRES_INTENT,
    run_id: str | None = None,
) -> set[str]:
    query = """
        SELECT correlation_id
        FROM cpk_secret_use_authorizations
        WHERE workspace_id = %s AND use_intent = %s
    """
    parameters: list[str] = [workspace_id, intent]
    if run_id is not None:
        query += " AND run_id = %s"
        parameters.append(run_id)
    with psycopg.connect(operations_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(parameters))
            return {str(row[0]) for row in cursor.fetchall()}


def _assert_provider_and_operations_correlation(
    *,
    provider_container: str,
    operations_database_url: str,
    workspace_id: str,
    intent: str = POSTGRES_INTENT,
) -> None:
    provider_rows = [
        row
        for row in _provider_audit_rows(provider_container, workspace_id)
        if row["outcome"] == "resolved" and row["intent"] == intent
    ]
    if not provider_rows:
        raise RuntimeError(f"provider did not audit successful {intent} resolution")
    operations_correlations = _operations_correlations(
        operations_database_url,
        workspace_id=workspace_id,
        intent=intent,
    )
    provider_correlations = {row["correlation_id"] for row in provider_rows}
    if not provider_correlations.issubset(operations_correlations):
        raise RuntimeError("operations/provider secret-use correlation diverged")


def _assert_run_resolved_version(
    *,
    provider_container: str,
    operations_database_url: str,
    workspace_id: str,
    run_id: str,
    expected_version_id: str,
) -> None:
    correlations = _operations_correlations(
        operations_database_url,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    rows = [
        row
        for row in _provider_audit_rows(provider_container, workspace_id)
        if row["correlation_id"] in correlations
        and row["outcome"] == "resolved"
        and row["intent"] == POSTGRES_INTENT
    ]
    if not rows or expected_version_id not in {row["version_id"] for row in rows}:
        raise RuntimeError("runtime effect did not resolve the expected provider version")


def _assert_activity_is_secret_free(workflow: HostedWorkflow) -> None:
    rendered = json.dumps(
        workflow.read_activity(limit=400),
        separators=(",", ":"),
        sort_keys=True,
    ).lower()
    for forbidden_key in (
        "value_base64",
        "ciphertext",
        "private_key",
        "access_token",
    ):
        if forbidden_key in rendered:
            raise RuntimeError("activity readback exposed secret material")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
