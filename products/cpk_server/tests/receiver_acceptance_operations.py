"""Public Operations driver for the #1912 receiver-acceptance witness.

This module deliberately imports only installed product packages.  It creates
an isolated Operations schema, composes the real public command services, and
drives every durable transition through ``CpkServerOperationsApplication``.
Graph construction, provider state, key material, signing, gateway transport,
and SDK behavior remain explicit injected ports owned by the calling witness.

No successful event, attempt, current pointer, acceptance, or retirement fact
is inserted directly here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

import psycopg
from psycopg import sql
from control_plane_kit_core.operations.lifecycle import ActivityEventKind, FailureCategory
from control_plane_kit_servers_cpk_server.operations_application import (
    OperationsApplicationFactory as SharedOperationsApplicationFactory,
    OperationsEffectPorts as SharedOperationsEffectPorts,
    OperationsIdFactories,
)

from control_plane_kit_core.identity import (
    AuthenticatedPrincipal,
    PrincipalIdentity,
    PrincipalKind,
    WorkspaceGrant,
)
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.admission import ExecutionAdmissionCommandService
from control_plane_kit_operations.advancement import CurrentGraphAdvancementCommandService
from control_plane_kit_operations.approvals import ApprovalCommandService
from control_plane_kit_operations.coordinator import (
    ActivityExecutionDispatcher,
    ExecutionCoordinator,
    RuntimeInterpreterDispatcher,
)
from control_plane_kit_operations.cpk_server import (
    CpkServerOperationsApplication,
    cpk_server_services,
)
from control_plane_kit_operations.delegation_signing_keys import (
    DelegationSigningKeyRegistrationService,
)
from control_plane_kit_operations.desired_topology_drafts import DesiredTopologyDraftCommandService
from control_plane_kit_operations.effect_attempt_fold_interpreter import (
    EffectAttemptFoldService,
)
from control_plane_kit_operations.effect_attempt_reconciliation_interpreter import (
    EffectAttemptReconciliationService,
)
from control_plane_kit_operations.effect_attempt_start_interpreter import (
    EffectAttemptStartService,
)
from control_plane_kit_operations.health_signing_authority import (
    HealthSigningAuthorityReloadService,
)
from control_plane_kit_operations.ingress_authorities import (
    IngressAuthorityProviderKind,
    IngressAuthorityRegistrationService,
)
from control_plane_kit_operations.ingress_realization import IngressRealizationAdapter
from control_plane_kit_operations.lifecycle import RunLifecycleCommandService
from control_plane_kit_operations.planning import (
    ActivityPlanningCommandService,
    DesiredGraphCommandService,
)
from control_plane_kit_operations.postgres import PostgresUnitOfWork, install_schema
from control_plane_kit_operations.products import (
    ImagePullAuthorityRegistrationService,
    ProductRegistrationService,
)
from control_plane_kit_operations.runtime_authorities import (
    RuntimeAuthorityRegistrationService,
)
from control_plane_kit_operations.secret_providers import (
    SecretProviderRegistrationService,
    SecretUseAuthorizationService,
)
from control_plane_kit_operations.workflows import OperationCommandService
from control_plane_kit_operations.workspaces import WorkspaceCommandService


_SCHEMA = re.compile(r"cpk_1912_[a-z0-9_]{1,48}\Z")
_REGISTRATION_ROUTES = frozenset(
    {
        "command.product.import",
        "command.image-pull-authority.register",
        "command.runtime-authority.register",
        "command.runtime-authority-delivery.register",
        "command.ingress-authority.register",
        "command.secret-provider.register",
        "command.secret-reference.register",
        "command.delegation-key.register",
        "command.delegation-key.activate",
    }
)


def utc_now() -> str:
    value = datetime.now(timezone.utc)
    return value.isoformat(
        timespec="microseconds" if value.microsecond else "seconds"
    ).replace("+00:00", "Z")


@dataclass(frozen=True)
class RouteRequest:
    surface: str
    route_id: str
    service_role: ControlPlaneServiceRole
    path_parameters: Mapping[str, str]
    payload: Mapping[str, object]
    principal: AuthenticatedPrincipal


def witness_principal(
    workspace_id: str,
    *,
    subject_id: str,
    kind: PrincipalKind,
    scopes: Sequence[PolicyScope],
) -> AuthenticatedPrincipal:
    """Create one explicit test principal without bypassing route policy."""

    return AuthenticatedPrincipal(
        PrincipalIdentity("urn:cpk:test:receiver-acceptance", subject_id, kind),
        (WorkspaceGrant(workspace_id, tuple(scopes)),),
    )


class IsolatedOperationsSchema:
    """Exact disposable schema backed by the smoke test's existing Postgres."""

    def __init__(self, database_url: str, schema: str) -> None:
        if not isinstance(database_url, str) or not database_url:
            raise ValueError("database URL is required")
        if not isinstance(schema, str) or _SCHEMA.fullmatch(schema) is None:
            raise ValueError("receiver-acceptance schema identity is invalid")
        self.database_url = database_url
        self.schema = schema
        self._created = False

    def connect(self):
        # The restricted schema grammar makes this libpq option one closed token.
        return psycopg.connect(
            self.database_url,
            options=f"-csearch_path={self.schema}",
        )

    def unit_of_work(self) -> PostgresUnitOfWork:
        return PostgresUnitOfWork(self.connect)

    def create(self) -> "IsolatedOperationsSchema":
        if self._created:
            raise RuntimeError("receiver-acceptance schema was already created")
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
            )
        self._created = True
        try:
            with self.connect() as connection:
                install_schema(connection)
                connection.commit()
        except BaseException:
            self.drop()
            raise
        return self

    def drop(self) -> None:
        if not self._created:
            return
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )
            row = connection.execute(
                "SELECT to_regnamespace(%s)",
                (self.schema,),
            ).fetchone()
            if row != (None,):
                raise RuntimeError("receiver-acceptance schema still exists after drop")
        self._created = False

    def __enter__(self) -> "IsolatedOperationsSchema":
        return self.create()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.drop()


@dataclass(frozen=True)
class OperationsEffectPorts:
    """Named external ports; none may write Operations durable truth."""

    runtime_interpreters: Mapping[RuntimeKind, object]
    ingress_interpreters: Mapping[IngressAuthorityProviderKind, object]
    managed_health: object
    health_receiver_decoders: object
    runtime_observer: object | None = None
    secret_metadata_reader: object | None = None


class _RefuseUnexpectedRecovery:
    """Positive witness has no authority to manufacture recovery evidence."""

    def observe(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("receiver-acceptance witness entered recovery")


class ObservedEffectStart:
    """Test-only error observation; the real owner receives and returns exact values."""
    def __init__(self, service, observer):
        self.service, self.observer = service, observer

    def execute(self, command):
        try:
            return self.service.execute(command)
        except Exception as error:
            try:
                self.observer(error)
            except Exception:
                raise error  # Preserve the original owner error if diagnostics fail.
            raise

    def execute_health(self, command):
        return self.service.execute_health(command)


@dataclass(frozen=True)
class OperationsApplicationFactory:
    """Test configuration of the shared production assembly; no copied owners."""
    unit_of_work_factory: Callable[[], PostgresUnitOfWork]
    ports: OperationsEffectPorts
    id_factory: Callable[[], str]
    clock: Callable[[], str] = utc_now
    start_failure_observer: Callable[[Exception], None] | None = None

    def __call__(self) -> CpkServerOperationsApplication:
        ports = self.ports
        decoration = None
        if self.start_failure_observer is not None:
            decoration = lambda service: ObservedEffectStart(service, self.start_failure_observer)
        return SharedOperationsApplicationFactory(self.unit_of_work_factory,
            SharedOperationsEffectPorts(ports.runtime_interpreters, ports.ingress_interpreters,
                ports.managed_health, ports.health_receiver_decoders,
                ports.runtime_observer or _RefuseUnexpectedRecovery(),
                secret_metadata_reader=ports.secret_metadata_reader),
            OperationsIdFactories(*(self.id_factory for _ in range(5))),
            clock=self.clock, start_service_decorator=decoration)()


class OperationsSequenceError(RuntimeError):
    """The public sequence stopped without inventing a successful transition."""


class CoordinatorStopped(OperationsSequenceError):
    """Only an actual execution response, not an arbitrary fixture failure."""

    def __init__(self, label, run_id, execution):
        super().__init__(f"{label} stopped with coordinator status {execution.get('coordinator_status')!r}")
        self.run_id = run_id
        self.execution = dict(execution)


def execution_failure_codes(events, plan=None):
    """Bounded public classifications only, never messages or event payloads."""
    def code(value):
        return value if type(value) is str and re.fullmatch(r"[a-z][a-z0-9.-]{0,95}", value) else None
    def identity(value):
        return value if type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", value) else None
    activities = (plan or {}).get("payload", {}).get("activities", [])
    rows = []
    for event in events[-32:]:
        if not isinstance(event, Mapping):
            continue
        try:
            kind = ActivityEventKind(event.get("event_type"))
        except (TypeError, ValueError):
            continue
        failure = event.get("failure")
        if not isinstance(failure, Mapping):
            continue
        try:
            category = FailureCategory(failure.get("category")).value
        except (TypeError, ValueError):
            category = None
        matches = [value for value in activities if value.get("activity_id") == event.get("activity_id")]
        operation = matches[0].get("operation", {}) if len(matches) == 1 else {}
        target = operation.get("target", {})
        details = failure.get("details")
        details = details if isinstance(details, Mapping) else {}
        outcome = details.get("effect_outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        rows.append({"event_type": kind.value, "activity_id": identity(event.get("activity_id")),
            "operation": code(operation.get("kind")), "node_id": identity(target.get("node_id")),
            "failure_category": category,
            "failure_code": code(failure.get("code")),
            "runtime_failure_code": code(outcome.get("runtime_failure_code"))})
    return {"receiver_execution_failure": "observed", "event_count": len(events),
        "events_truncated": len(events) > 32,
        "failures": rows}


def graph_descriptor(value: Mapping[str, object] | DeploymentGraph) -> dict[str, object]:
    """Copy an authored graph through Core's public descriptor boundary."""

    if type(value) is DeploymentGraph:
        return dict(DEFAULT_GRAPH_CODEC.encode(value))
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("desired graph must be authored Core graph truth")


def _registration_identity(
    result: Mapping[str, object],
    *,
    workspace_id: str,
    identity_key: str = "registration_id",
) -> str:
    """Require the common first-admission result without guessing store state."""

    identity = result.get(identity_key)
    if (
        not isinstance(identity, str)
        or not identity
        or result.get("workspace_id") != workspace_id
    ):
        raise OperationsSequenceError("public registration result is malformed")
    return identity


async def register_material(
    driver: "PublicOperationsDriver",
    material: object,
) -> dict[str, object]:
    """Admit #1912 authored material through public registration routes only."""

    documents = getattr(material, "documents", None)
    public_keys = getattr(material, "public", None)
    if (
        driver.workspace_id != getattr(material, "workspace_id", "workspace-a")
        or not isinstance(documents, Mapping)
        or set(documents) != {"gateway", "api", "connector"}
        or not isinstance(public_keys, Mapping)
        or set(public_keys) != {"transit", "workload"}
    ):
        raise ValueError("receiver-acceptance authored material is incomplete")

    admitted_at = utc_now()
    registrations: dict[str, object] = {"products": {}}
    product_results = registrations["products"]
    assert isinstance(product_results, dict)
    for name in ("gateway", "api", "connector"):
        document = documents[name]
        content = getattr(document, "content", None)
        if not isinstance(content, bytes):
            raise ValueError(f"{name} product document has no encoded content")
        descriptor = json.loads(content)
        if not isinstance(descriptor, dict):
            raise ValueError(f"{name} product document is not an object")
        result = await driver.register(
            "command.product.import",
            {
                "descriptor_document": descriptor,
                "imported_at": admitted_at,
                "idempotency_key": f"receiver-acceptance-product-{name}",
            },
        )
        _registration_identity(result, workspace_id=driver.workspace_id)
        if result.get("status") != "active":
            raise OperationsSequenceError(f"{name} product was not activated")
        product_results[name] = result

    runtime = await driver.register(
        "command.runtime-authority.register",
        {
            "authority_ref": "local-docker",
            "runtime_kind": "docker",
            "authority": {"kind": "local-docker-socket"},
            "admitted_at": admitted_at,
            "idempotency_key": "receiver-acceptance-runtime-local-docker",
        },
    )
    _registration_identity(runtime, workspace_id=driver.workspace_id)
    if (
        runtime.get("authority_ref") != "local-docker"
        or runtime.get("runtime_kind") != "docker"
        or runtime.get("authority") != {"kind": "local-docker-socket"}
        or runtime.get("status") != "active"
    ):
        raise OperationsSequenceError("local Docker runtime authority differs")
    registrations["runtime"] = runtime

    provider_specs = {
        "health": {
            "provider_id": "health-secrets",
            "display_name": "Receiver acceptance health key custody",
            "endpoint_reference": "health-secrets",
            "credential_reference": "secret://bootstrap/health-secrets/client-token",
            "allowed_reference_prefixes": ["secret://health-secrets/keys"],
            "allowed_intents": [
                "gateway.node-health-read-transit-signing-key",
                "workload.node-health-read-signing-key",
            ],
        },
        "cloudflare": {
            "provider_id": "cloudflare",
            "display_name": "Receiver acceptance Cloudflare custody",
            "endpoint_reference": "cloudflare-secrets",
            "credential_reference": "secret://bootstrap/cloudflare-secrets/client-token",
            "allowed_reference_prefixes": ["secret://cloudflare/ingress"],
            "allowed_intents": ["cloudflare.api-token"],
        },
        "generated": {
            "provider_id": "generated",
            "display_name": "Receiver acceptance generated ingress custody",
            "endpoint_reference": "generated-secrets",
            "credential_reference": "secret://bootstrap/generated-secrets/client-token",
            "allowed_reference_prefixes": ["secret://generated/ingress"],
            "allowed_intents": ["cloudflare.tunnel-token"],
        },
    }
    providers: dict[str, dict[str, object]] = {}
    provider_ids: dict[str, str] = {}
    for name, spec in provider_specs.items():
        result = await driver.register(
            "command.secret-provider.register",
            {
                **spec,
                "provider_kind": "control-plane-kit-secrets",
                "admitted_at": admitted_at,
                "metadata": {"acceptance": "receiver-acceptance-1912"},
                "idempotency_key": f"receiver-acceptance-provider-{name}",
            },
        )
        provider_ids[name] = _registration_identity(
            result, workspace_id=driver.workspace_id
        )
        if (
            result.get("provider_id") != spec["provider_id"]
            or result.get("allowed_reference_prefixes")
            != sorted(spec["allowed_reference_prefixes"])
            or result.get("allowed_intents") != sorted(spec["allowed_intents"])
            or result.get("status") != "active"
        ):
            raise OperationsSequenceError(f"{name} secret provider differs")
        providers[name] = result
    registrations["providers"] = providers

    reference_specs = {
        "transit": "secret://health-secrets/keys/transit",
        "workload": "secret://health-secrets/keys/workload",
    }
    references: dict[str, dict[str, object]] = {}
    keys: dict[str, dict[str, object]] = {}
    activations: dict[str, dict[str, object]] = {}
    purposes = {
        "transit": "gateway-node-health-read-transit",
        "workload": "workload-node-health-read",
    }
    signing_intents = {
        "transit": "gateway.node-health-read-transit-signing-key",
        "workload": "workload.node-health-read-signing-key",
    }
    for family in ("transit", "workload"):
        reference = reference_specs[family]
        reference_result = await driver.register(
            "command.secret-reference.register",
            {
                "reference": reference,
                "provider_registration_id": provider_ids["health"],
                "allowed_intents": [signing_intents[family]],
                "admitted_at": admitted_at,
                "metadata": {"acceptance": "receiver-acceptance-1912"},
                "idempotency_key": f"receiver-acceptance-reference-{family}",
            },
        )
        _registration_identity(reference_result, workspace_id=driver.workspace_id)
        if (
            reference_result.get("reference_id") != reference
            or reference_result.get("provider_registration_id")
            != provider_ids["health"]
            or reference_result.get("allowed_intents")
            != [signing_intents[family]]
            or reference_result.get("status") != "active"
        ):
            raise OperationsSequenceError(f"{family} secret reference differs")
        references[family] = reference_result

        public_key = public_keys[family]
        expected_key_id = f"health-{family}"
        if getattr(public_key, "key_id", None) != expected_key_id:
            raise ValueError(f"{family} delegation key identity is invalid")
        algorithm = getattr(getattr(public_key, "algorithm", None), "value", None)
        public_key_pem = getattr(public_key, "public_key_pem", None)
        if algorithm != "ed25519" or not isinstance(public_key_pem, str):
            raise ValueError(f"{family} delegation public key is invalid")
        key_result = await driver.register(
            "command.delegation-key.register",
            {
                "purpose": purposes[family],
                "issuer": "cpk-server",
                "key_id": expected_key_id,
                "algorithm": algorithm,
                "public_key_pem": public_key_pem,
                "private_key_reference": reference,
                "admitted_at": admitted_at,
                "idempotency_key": f"receiver-acceptance-key-{family}",
            },
        )
        _registration_identity(key_result, workspace_id=driver.workspace_id)
        if (
            key_result.get("purpose") != purposes[family]
            or key_result.get("issuer") != "cpk-server"
            or key_result.get("key_id") != expected_key_id
            or key_result.get("private_key_reference") != reference
            or key_result.get("status") != "verify-only"
        ):
            raise OperationsSequenceError(f"{family} delegation key differs")
        keys[family] = key_result
        activation = await driver.register(
            "command.delegation-key.activate",
            {
                "purpose": purposes[family],
                "issuer": "cpk-server",
                "key_id": expected_key_id,
                "activated_at": admitted_at,
                "idempotency_key": f"receiver-acceptance-key-{family}-activate",
            },
        )
        _registration_identity(
            activation,
            workspace_id=driver.workspace_id,
        )
        if (
            activation.get("registration_id") != key_result.get("registration_id")
            or activation.get("purpose") != purposes[family]
            or activation.get("key_id") != expected_key_id
            or activation.get("status") != "active"
        ):
            raise OperationsSequenceError(f"{family} delegation key was not activated")
        activations[family] = activation
    registrations["references"] = references
    registrations["keys"] = keys
    registrations["activations"] = activations

    cloudflare_reference = await driver.register(
        "command.secret-reference.register",
        {
            "reference": "secret://cloudflare/ingress/api-token",
            "provider_registration_id": provider_ids["cloudflare"],
            "allowed_intents": ["cloudflare.api-token"],
            "admitted_at": admitted_at,
            "metadata": {"acceptance": "receiver-acceptance-1912"},
            "idempotency_key": "receiver-acceptance-reference-cloudflare-api-token",
        },
    )
    _registration_identity(cloudflare_reference, workspace_id=driver.workspace_id)
    if (
        cloudflare_reference.get("reference_id")
        != "secret://cloudflare/ingress/api-token"
        or cloudflare_reference.get("provider_registration_id")
        != provider_ids["cloudflare"]
        or cloudflare_reference.get("allowed_intents")
        != ["cloudflare.api-token"]
        or cloudflare_reference.get("status") != "active"
    ):
        raise OperationsSequenceError("Cloudflare API secret reference differs")
    registrations["cloudflare_reference"] = cloudflare_reference

    ingress = await driver.register(
        "command.ingress-authority.register",
        {
            "authority_ref": "zone",
            "authority": {
                "provider_kind": "cloudflare",
                "account_id": "account-1912",
                "zone_id": "zone-1912",
                "zone_name": "example.invalid",
                "api_token_ref": "secret://cloudflare/ingress/api-token",
                "allowed_hostname_pattern": "cpk-1912.example.invalid",
                "generated_secret_provider_registration_id": provider_ids["generated"],
                "generated_secret_reference_prefix": "secret://generated/ingress",
            },
            "admitted_at": admitted_at,
            "idempotency_key": "receiver-acceptance-ingress-zone",
        },
    )
    _registration_identity(ingress, workspace_id=driver.workspace_id)
    expected_ingress_authority = {
        "provider_kind": "cloudflare",
        "account_id": "account-1912",
        "zone_id": "zone-1912",
        "zone_name": "example.invalid",
        "api_token_ref": "secret://cloudflare/ingress/api-token",
        "allowed_hostname_pattern": "cpk-1912.example.invalid",
        "generated_secret_provider_registration_id": provider_ids["generated"],
        "generated_secret_reference_prefix": "secret://generated/ingress",
    }
    if (
        ingress.get("authority_ref") != "zone"
        or ingress.get("authority") != expected_ingress_authority
        or ingress.get("status") != "active"
    ):
        raise OperationsSequenceError("zone ingress authority was not activated")
    registrations["ingress"] = ingress
    return registrations


@dataclass(frozen=True)
class AcceptedTransition:
    label: str
    before: Mapping[str, object]
    preparation: Mapping[str, object]
    plan: Mapping[str, object]
    claim: Mapping[str, object]
    execution: Mapping[str, object]
    advancement: Mapping[str, object]
    after: Mapping[str, object]
    history: Mapping[str, object]


@dataclass(frozen=True)
class _SavedOriginalReplay:
    execution_path: Mapping[str, str]
    execution_payload: Mapping[str, object]
    execution_result: Mapping[str, object]
    advancement_path: Mapping[str, str]
    advancement_payload: Mapping[str, object]
    advancement_result: Mapping[str, object]


class PublicOperationsDriver:
    """Exact public A→B→C→teardown command driver with restart replay."""

    def __init__(
        self,
        application_factory: Callable[[], CpkServerOperationsApplication],
        *,
        workspace_id: str,
        maximum_execute_commands: int = 128,
        maximum_history_pages: int = 16,
        effect_snapshot: Callable[[], object] | None = None,
    ) -> None:
        if (
            not workspace_id
            or maximum_execute_commands < 1
            or not 1 <= maximum_history_pages <= 100
        ):
            raise ValueError("public Operations driver configuration is invalid")
        self._application_factory = application_factory
        self._application = application_factory()
        self.workspace_id = workspace_id
        self.maximum_execute_commands = maximum_execute_commands
        self.maximum_history_pages = maximum_history_pages
        self._effect_snapshot = effect_snapshot
        self._original_replays: dict[str, _SavedOriginalReplay] = {}
        all_scopes = tuple(PolicyScope)
        self.operator = witness_principal(
            workspace_id,
            subject_id="receiver-acceptance-operator",
            kind=PrincipalKind.OPERATOR,
            scopes=all_scopes,
        )
        self.worker = witness_principal(
            workspace_id,
            subject_id="receiver-acceptance-worker",
            kind=PrincipalKind.WORKER,
            scopes=all_scopes,
        )

    def reconstruct(self) -> None:
        """Recreate service objects; durable truth and external ports remain."""

        self._application = self._application_factory()

    def _replay_effect_snapshot(self) -> object | None:
        return None if self._effect_snapshot is None else self._effect_snapshot()

    @staticmethod
    def _require_replay(
        original: Mapping[str, object],
        replay: Mapping[str, object],
        *,
        label: str,
    ) -> None:
        expected = dict(original)
        if "replayed" in expected:
            if expected["replayed"] is not False:
                raise OperationsSequenceError(f"{label} original was not a first dispatch")
            expected["replayed"] = True
        if replay != expected:
            raise OperationsSequenceError(f"{label} replay changed canonical result")

    async def replay_original(self, label: str) -> dict[str, dict[str, object]]:
        """Replay one saved original execute/advance pair after later transitions."""

        saved = self._original_replays.get(label)
        if saved is None:
            raise ValueError(f"no original transition is retained for {label!r}")
        self.reconstruct()
        effects_before_execution = self._replay_effect_snapshot()
        execution = await self.invoke(
            "command.deployment.execute",
            ControlPlaneServiceRole.EXECUTION,
            path=saved.execution_path,
            payload=saved.execution_payload,
            principal=self.worker,
        )
        effects_after_execution = self._replay_effect_snapshot()
        if effects_after_execution != effects_before_execution:
            raise OperationsSequenceError(
                f"{label} original execution replay redispatched an external effect"
            )
        self._require_replay(
            saved.execution_result,
            execution,
            label=f"{label} original execution",
        )

        effects_before_advancement = self._replay_effect_snapshot()
        advancement = await self.invoke(
            "command.graph.advance-current",
            ControlPlaneServiceRole.LIFECYCLE,
            path=saved.advancement_path,
            payload=saved.advancement_payload,
            principal=self.worker,
        )
        effects_after_advancement = self._replay_effect_snapshot()
        if effects_after_advancement != effects_before_advancement:
            raise OperationsSequenceError(
                f"{label} original advancement replay redispatched an external effect"
            )
        self._require_replay(
            saved.advancement_result,
            advancement,
            label=f"{label} original advancement",
        )
        return {"execution": execution, "advancement": advancement}

    async def _history_page(
        self,
        route: str,
        *,
        path: Mapping[str, str],
    ) -> dict[str, object]:
        items: list[object] = []
        after: object | None = None
        for page_number in range(1, self.maximum_history_pages + 1):
            payload: dict[str, object] = {"limit": 100}
            if after is not None:
                payload["after"] = after
            page = await self.invoke(
                route,
                ControlPlaneServiceRole.READS,
                path=path,
                payload=payload,
            )
            page_items = page.get("items")
            if not isinstance(page_items, list):
                raise OperationsSequenceError(f"{route} returned malformed history")
            items.extend(page_items)
            after = page.get("next_cursor")
            if after is None:
                return {"items": items, "pages": page_number, "next_cursor": None}
        raise OperationsSequenceError(f"{route} exceeded its history page bound")

    async def invoke(
        self,
        route: str,
        role: ControlPlaneServiceRole,
        *,
        path: Mapping[str, str] | None = None,
        payload: Mapping[str, object] | None = None,
        principal: AuthenticatedPrincipal | None = None,
    ) -> dict[str, object]:
        result = await self._application.handle_async(
            RouteRequest(
                surface="http",
                route_id=route,
                service_role=role,
                path_parameters=dict(path or {}),
                payload=dict(payload or {}),
                principal=self.operator if principal is None else principal,
            )
        )
        return dict(result)

    async def create_workspace(self, *, name: str = "Receiver acceptance") -> dict[str, object]:
        return await self.invoke(
            "command.workspace.create",
            ControlPlaneServiceRole.PLANNING,
            payload={
                "workspace_id": self.workspace_id,
                "name": name,
                "idempotency_key": "receiver-acceptance-workspace",
            },
        )

    async def register(
        self,
        route: str,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        """Invoke one public registration route; no store-writing callback."""

        if route not in _REGISTRATION_ROUTES:
            raise ValueError("registration route is outside the witness boundary")
        return await self.invoke(
            route,
            ControlPlaneServiceRole.PLANNING,
            path={"workspace_id": self.workspace_id},
            payload=payload,
        )

    async def workspace(self) -> dict[str, object]:
        result = await self.invoke(
            "read.workspace",
            ControlPlaneServiceRole.READS,
            path={"workspace_id": self.workspace_id},
        )
        workspace = result.get("workspace")
        if not isinstance(workspace, Mapping):
            raise OperationsSequenceError("workspace read did not return durable truth")
        return dict(workspace)

    async def _emit_execution_failure(self, run_id, plan):
        try:
            page = await self._history_page("read.run-events",
                path={"workspace_id": self.workspace_id, "run_id": run_id})
            print(json.dumps(execution_failure_codes(page["items"], plan)), flush=True)
        except Exception:
            print('{"receiver_execution_failure":"evidence-unavailable"}', flush=True)

    async def accept(
        self,
        *,
        label: str,
        desired_graph: Mapping[str, object] | DeploymentGraph,
        destructive: bool,
    ) -> AcceptedTransition:
        """Prepare, approve, execute, and advance one nonempty transition."""

        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", label):
            raise ValueError("transition label is invalid")
        before = await self.workspace()
        expected_desired = None
        if before.get("desired_graph_id") is not None:
            expected_desired = {
                "authored_graph_id": before["desired_graph_id"],
                "realized_projection_id": before[
                    "desired_realized_projection_id"
                ],
            }
        preparation = await self.invoke(
            "command.deployment.prepare",
            ControlPlaneServiceRole.PLANNING,
            path={"workspace_id": self.workspace_id},
            payload={
                "desired_graph": graph_descriptor(desired_graph),
                "expected_current": {
                    "authored_graph_id": before["current_graph_id"],
                    "realized_projection_id": before[
                        "current_realized_projection_id"
                    ],
                },
                "expected_desired": expected_desired,
                "expected_desired_graph_revision": before[
                    "desired_graph_revision"
                ],
                "title": f"Receiver acceptance {label}",
                "idempotency_key": f"{label}-prepare",
            },
        )
        if preparation.get("status") != "approval-required":
            raise OperationsSequenceError(
                f"{label} did not produce an approval-required nonempty plan"
            )
        plan = await self.invoke(
            "read.plan-detail",
            ControlPlaneServiceRole.READS,
            path={
                "workspace_id": self.workspace_id,
                "plan_id": str(preparation["plan_id"]),
            },
        )
        plan_descriptor = plan.get("plan")
        if not isinstance(plan_descriptor, Mapping):
            raise OperationsSequenceError(f"{label} plan detail is unavailable")
        approval_scope = (
            PolicyScope.PLAN_APPROVE_DESTRUCTIVE
            if destructive
            else PolicyScope.PLAN_APPROVE
        )
        approver = witness_principal(
            self.workspace_id,
            subject_id=f"receiver-acceptance-{label}-approver",
            kind=PrincipalKind.OPERATOR,
            scopes=(approval_scope,),
        )
        await self.invoke(
            "command.approval.decide",
            ControlPlaneServiceRole.APPROVAL,
            path={
                "workspace_id": self.workspace_id,
                "approval_id": str(preparation["approval_request_id"]),
            },
            payload={
                "session_id": plan_descriptor["session_id"],
                "decision": "approved",
                "idempotency_key": f"{label}-approve",
            },
            principal=approver,
        )
        admitted = await self.invoke(
            "command.deployment.admit",
            ControlPlaneServiceRole.ADMISSION,
            path={
                "workspace_id": self.workspace_id,
                "plan_id": str(preparation["plan_id"]),
            },
            payload={
                "session_id": plan_descriptor["session_id"],
                "approval_request_id": preparation["approval_request_id"],
                "readiness": [],
                "idempotency_key": f"{label}-admit",
            },
        )
        claim = await self.invoke(
            "command.run.claim",
            ControlPlaneServiceRole.LIFECYCLE,
            path={
                "workspace_id": self.workspace_id,
                "run_id": str(admitted["execution_request_id"]),
            },
            payload={
                "lease_duration_seconds": 1800,
                "idempotency_key": f"{label}-claim",
            },
            principal=self.worker,
        )
        run_id = str(claim["run_id"])
        generation = claim["claim_generation"]
        await self.invoke(
            "command.run.start",
            ControlPlaneServiceRole.EXECUTION,
            path={"workspace_id": self.workspace_id, "run_id": run_id},
            payload={
                "claim_generation": generation,
                "idempotency_key": f"{label}-start",
            },
            principal=self.worker,
        )

        execution: dict[str, object] | None = None
        for number in range(1, self.maximum_execute_commands + 1):
            payload = {
                "claim_generation": generation,
                "idempotency_key": f"{label}-execute-{number}",
                "max_effects": 1,
            }
            execution = await self.invoke(
                "command.deployment.execute",
                ControlPlaneServiceRole.EXECUTION,
                path={"workspace_id": self.workspace_id, "run_id": run_id},
                payload=payload,
                principal=self.worker,
            )
            # Reconstruct all service owners, then prove exact command replay.
            self.reconstruct()
            effects_before_replay = self._replay_effect_snapshot()
            replay = await self.invoke(
                "command.deployment.execute",
                ControlPlaneServiceRole.EXECUTION,
                path={"workspace_id": self.workspace_id, "run_id": run_id},
                payload=payload,
                principal=self.worker,
            )
            effects_after_replay = self._replay_effect_snapshot()
            if effects_after_replay != effects_before_replay:
                raise OperationsSequenceError(
                    f"{label} execution replay redispatched an external effect"
                )
            self._require_replay(execution, replay, label=f"{label} execution")
            status = execution.get("coordinator_status")
            if status == "completed":
                break
            if status != "progressed":
                await self._emit_execution_failure(run_id, plan_descriptor)
                raise CoordinatorStopped(label, run_id, execution)
        else:
            raise OperationsSequenceError(f"{label} exceeded its execution bound")
        if execution is None or execution.get("run_status") != "succeeded":
            raise OperationsSequenceError(f"{label} did not complete successfully")

        advance_payload = {
            "plan_id": preparation["plan_id"],
            "expected_current_graph_id": before["current_graph_id"],
            "expected_current_realized_projection_id": before[
                "current_realized_projection_id"
            ],
            "desired_graph_id": plan_descriptor["desired_graph_id"],
            "desired_realized_projection_id": plan_descriptor[
                "desired_realized_projection_id"
            ],
            "expected_desired_graph_revision": plan_descriptor[
                "desired_graph_revision"
            ],
            "claim_generation": generation,
            "idempotency_key": f"{label}-advance",
        }
        advancement = await self.invoke(
            "command.graph.advance-current",
            ControlPlaneServiceRole.LIFECYCLE,
            path={"workspace_id": self.workspace_id, "run_id": run_id},
            payload=advance_payload,
            principal=self.worker,
        )
        self.reconstruct()
        effects_before_replay = self._replay_effect_snapshot()
        advancement_replay = await self.invoke(
            "command.graph.advance-current",
            ControlPlaneServiceRole.LIFECYCLE,
            path={"workspace_id": self.workspace_id, "run_id": run_id},
            payload=advance_payload,
            principal=self.worker,
        )
        effects_after_replay = self._replay_effect_snapshot()
        if effects_after_replay != effects_before_replay:
            raise OperationsSequenceError(
                f"{label} advancement replay redispatched an external effect"
            )
        self._require_replay(
            advancement,
            advancement_replay,
            label=f"{label} advancement",
        )
        if label in self._original_replays or len(self._original_replays) >= 4:
            raise OperationsSequenceError("original replay retention exceeded its bound")
        self._original_replays[label] = _SavedOriginalReplay(
            execution_path={"workspace_id": self.workspace_id, "run_id": run_id},
            execution_payload=dict(payload),
            execution_result=dict(execution),
            advancement_path={"workspace_id": self.workspace_id, "run_id": run_id},
            advancement_payload=dict(advance_payload),
            advancement_result=dict(advancement),
        )
        after = await self.workspace()
        history = {
            "plan": await self.invoke(
                "read.plan-detail",
                ControlPlaneServiceRole.READS,
                path={
                    "workspace_id": self.workspace_id,
                    "plan_id": str(preparation["plan_id"]),
                },
            ),
            "session": await self.invoke(
                "read.session-detail",
                ControlPlaneServiceRole.READS,
                path={
                    "workspace_id": self.workspace_id,
                    "session_id": str(plan_descriptor["session_id"]),
                },
            ),
            "runs": await self._history_page(
                "read.plan-runs",
                path={
                    "workspace_id": self.workspace_id,
                    "plan_id": str(preparation["plan_id"]),
                },
            ),
            "events": await self._history_page(
                "read.run-events",
                path={"workspace_id": self.workspace_id, "run_id": run_id},
            ),
        }
        return AcceptedTransition(
            label=label,
            before=before,
            preparation=preparation,
            plan=dict(plan_descriptor),
            claim=claim,
            execution=execution,
            advancement=advancement,
            after=after,
            history=history,
        )

    async def accept_a_b_c_and_teardown(
        self,
        *,
        graph_a: Mapping[str, object] | DeploymentGraph,
        graph_b: Mapping[str, object] | DeploymentGraph,
        graph_c: Mapping[str, object] | DeploymentGraph,
        teardown_graph: Mapping[str, object] | DeploymentGraph,
    ) -> tuple[AcceptedTransition, ...]:
        """Run one joined history; C and teardown require destructive approval."""

        result = []
        for label, graph, destructive in (
            ("a", graph_a, False),
            ("b", graph_b, False),
            ("c", graph_c, True),
            ("teardown", teardown_graph, True),
        ):
            result.append(
                await self.accept(
                    label=label,
                    desired_graph=graph,
                    destructive=destructive,
                )
            )
        return tuple(result)
