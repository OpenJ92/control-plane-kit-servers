"""One production assembly of Operations owners and explicitly supplied effects."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from control_plane_kit_core.identity import PrincipalAuthorizer
from control_plane_kit_core.secrets import SecretCustodian
from control_plane_kit_operations import (
    ActivityExecutionDispatcher, ActivityPlanningCommandService, ApprovalCommandService,
    CpkServerOperationsApplication, CurrentGraphAdvancementCommandService,
    DelegationSigningKeyRegistrationService, DesiredGraphCommandService,
    EffectAttemptFoldService, EffectAttemptReconciliationService, EffectAttemptStartService,
    ExecutionAdmissionCommandService, ExecutionCoordinator, ImagePullAuthorityRegistrationService,
    IngressAuthorityRegistrationService, IngressRealizationAdapter, OperationCommandService,
    ProductRegistrationService, RunLifecycleCommandService, RuntimeAuthorityRegistrationService,
    RuntimeInterpreterDispatcher, SecretProviderRegistrationService, SecretUseAuthorizationService,
    WorkspaceCommandService, cpk_server_services,
)
from control_plane_kit_operations.desired_topology_drafts import DesiredTopologyDraftCommandService
from control_plane_kit_operations.health_signing_authority import HealthSigningAuthorityReloadService
from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
from control_plane_kit_operations.graph_authoring import SecretVersionMetadataReader
from control_plane_kit_operations.delegation_key_generation import DelegationKeyGenerator
from control_plane_kit_operations.delegation_key_generation_commands import DelegationKeyGenerationCommandService
from control_plane_kit_operations.secret_material_provision_commands import SecretMaterialProvisionCommandService
from control_plane_kit_operations.cpk_server import CpkServerWorkspaceAdministrationService
from control_plane_kit_operations.effect_permissions import CurrentWorkspaceEffectPolicy
from control_plane_kit_operations.execution_invocation_service import ExecutionInvocationService
from control_plane_kit_operations.ingress_invocation_service import IngressInvocationService
from control_plane_kit_operations.managed_runtime_assignments import (
    ManagedRuntimeAssignmentCommandService, ManagedRuntimeAssignmentReadService,
    ManagedRuntimeCapabilityPolicy,
)
from control_plane_kit_operations.workspace_permissions import (
    DurablePrincipalAuthorizer, WorkspaceAdministrationPolicy, WorkspaceContextResolver,
    WorkspacePermissionCommandService, WorkspacePermissionReadService,
)


@dataclass(frozen=True)
class WorkspaceAuthorityConfiguration:
    """Trusted installation policies, without credentials or private transports."""
    administration_policy: WorkspaceAdministrationPolicy
    capability_policy: ManagedRuntimeCapabilityPolicy

    def __post_init__(self):
        if (type(self.administration_policy) is not WorkspaceAdministrationPolicy
                or type(self.capability_policy) is not ManagedRuntimeCapabilityPolicy
                or self.administration_policy.installation_id != self.capability_policy.installation_id):
            raise ValueError("workspace authority configuration is invalid")
        self.administration_policy.__post_init__()
        self.capability_policy.__post_init__()


@dataclass(frozen=True)
class OperationsIdFactories:
    service: Callable[[], str]
    lifecycle: Callable[[], str]
    start: Callable[[], str]
    fold: Callable[[], str]
    coordinator: Callable[[], str]


@dataclass(frozen=True)
class OperationsEffectPorts:
    """External ports have no authority to write Operations durable truth.

    None disables an interpreter family; an empty mapping is an enabled dispatcher
    with no supported providers. The disabled runtime adapter is explicit.
    """
    runtime_interpreters: Mapping | None
    ingress_interpreters: Mapping | None
    managed_health: object | None
    health_receiver_decoders: HealthReceiverDecoders
    runtime_observer: object
    disabled_runtime_adapter: object | None = None
    secret_metadata_reader: SecretVersionMetadataReader | None = None
    delegation_key_generator: DelegationKeyGenerator | None = None
    secret_custodian: SecretCustodian | None = None


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OperationsApplicationFactory:
    unit_of_work_factory: Callable
    ports: OperationsEffectPorts
    ids: OperationsIdFactories
    clock: Callable[[], str] = _utc_now
    gateway_probe_factory: Callable | None = None
    start_service_decorator: Callable | None = None
    principal_authorizer: PrincipalAuthorizer | None = None
    workspace_authority: WorkspaceAuthorityConfiguration | None = None

    def __call__(self) -> CpkServerOperationsApplication:
        unit_of_work, ports, ids, clock = self.unit_of_work_factory, self.ports, self.ids, self.clock
        principal_authorizer = self.principal_authorizer
        policy_options, execution_options, ingress_options = {}, {}, {}
        service_options, application_options = {}, {}
        authority = self.workspace_authority
        if authority is None:
            workspaces = WorkspaceCommandService(unit_of_work, clock=clock, id_factory=ids.service)
        else:
            if type(authority) is not WorkspaceAuthorityConfiguration or principal_authorizer is not None:
                raise ValueError("dynamic workspace authority composition is invalid")
            authority.__post_init__()
            administration = authority.administration_policy
            installation_id = administration.installation_id
            principal_authorizer = DurablePrincipalAuthorizer(unit_of_work, installation_id=installation_id)
            policy = CurrentWorkspaceEffectPolicy(installation_id, authority.capability_policy)
            policy_options = {"permission_policy": policy}
            execution_options = {**policy_options, "invocation_service": ExecutionInvocationService(
                unit_of_work, permission_policy=policy, clock=clock,
                health_receiver_decoders=ports.health_receiver_decoders)}
            ingress_options = {"invocation_service": IngressInvocationService(
                unit_of_work, permission_policy=policy, clock=clock)}
            workspaces = WorkspaceCommandService(unit_of_work, clock=clock, id_factory=ids.service,
                administration_policy=administration)
            service_options = {"workspace_administration": CpkServerWorkspaceAdministrationService(
                administration_policy=administration, workspaces=workspaces,
                permission_commands=WorkspacePermissionCommandService(unit_of_work,
                    administration_policy=administration, clock=clock, id_factory=ids.service),
                permission_reads=WorkspacePermissionReadService(unit_of_work,
                    administration_policy=administration),
                management_commands=ManagedRuntimeAssignmentCommandService(unit_of_work,
                    administration_policy=administration, capability_policy=authority.capability_policy,
                    clock=clock, id_factory=ids.service),
                management_reads=ManagedRuntimeAssignmentReadService(unit_of_work,
                    administration_policy=administration))}
            application_options = {"authority_mode": "dynamic", "workspace_context_resolver":
                WorkspaceContextResolver(unit_of_work, installation_id=installation_id)}
        authorizer = SecretUseAuthorizationService(unit_of_work)
        runtime = ports.disabled_runtime_adapter
        if ports.runtime_interpreters is not None:
            runtime = RuntimeInterpreterDispatcher(ports.runtime_interpreters,
                secret_use_authorizer=authorizer)
        if runtime is None or ports.runtime_observer is None:
            raise ValueError("operations runtime ports are incomplete")
        adapter = runtime
        if ports.ingress_interpreters is not None:
            adapter = ActivityExecutionDispatcher(runtime=runtime,
                ingress=IngressRealizationAdapter(unit_of_work,
                    interpreters=ports.ingress_interpreters, clock=clock,
                    secret_use_authorizer=authorizer, **ingress_options))
        lifecycle = RunLifecycleCommandService(unit_of_work, clock=clock, id_factory=ids.lifecycle)
        fold = EffectAttemptFoldService(unit_of_work, id_factory=ids.fold)
        start = EffectAttemptStartService(unit_of_work, id_factory=ids.start,
            health_receiver_decoders=ports.health_receiver_decoders, **policy_options)
        if self.start_service_decorator is not None:
            start = self.start_service_decorator(start)
        reload = HealthSigningAuthorityReloadService(unit_of_work,
            health_receiver_decoders=ports.health_receiver_decoders)
        reconciliation = EffectAttemptReconciliationService(unit_of_work, ports.runtime_observer, fold,
            **execution_options)
        execution = ExecutionCoordinator(unit_of_work,
            lifecycle=lifecycle, adapter=adapter, start_service=start, fold_service=fold,
            reconciliation_service=reconciliation, clock=clock, id_factory=ids.coordinator,
            managed_health=ports.managed_health, health_signing_authority=reload, **execution_options)
        probes = (None if self.gateway_probe_factory is None
            else self.gateway_probe_factory(unit_of_work, authorizer))
        generation = None
        if ports.delegation_key_generator is not None and principal_authorizer is not None:
            generation = DelegationKeyGenerationCommandService(unit_of_work,
                ports.delegation_key_generator, authorizer=principal_authorizer, clock=clock)
        provision = None
        if ports.secret_custodian is not None and principal_authorizer is not None:
            provision = SecretMaterialProvisionCommandService(unit_of_work,
                ports.secret_custodian, authorizer=principal_authorizer, clock=clock)
        return CpkServerOperationsApplication(cpk_server_services(
            unit_of_work_factory=unit_of_work,
            planning=ActivityPlanningCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            workspaces=workspaces,
            products=ProductRegistrationService(unit_of_work),
            image_pull_authorities=ImagePullAuthorityRegistrationService(unit_of_work),
            runtime_authorities=RuntimeAuthorityRegistrationService(unit_of_work),
            ingress_authorities=IngressAuthorityRegistrationService(unit_of_work),
            secret_providers=SecretProviderRegistrationService(unit_of_work),
            delegation_signing_keys=DelegationSigningKeyRegistrationService(unit_of_work),
            delegation_key_generation=generation,
            secret_material_provision=provision,
            desired_topology_drafts=DesiredTopologyDraftCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            desired_graphs=DesiredGraphCommandService(unit_of_work, clock=clock, id_factory=ids.service,
                secret_metadata_reader=ports.secret_metadata_reader),
            approval=ApprovalCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            admission=ExecutionAdmissionCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            lifecycle=lifecycle,
            operations=OperationCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            execution=execution,
            advancement=CurrentGraphAdvancementCommandService(unit_of_work, clock=clock, id_factory=ids.service),
            gateway_probes=probes,
            clock=lambda: datetime.now(timezone.utc),
            **service_options,
        ), **application_options)
