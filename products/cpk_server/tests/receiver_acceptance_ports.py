"""Named external substitutes and real signed SDK transport for issue 1912.

No port writes Operations state. Installed bytes change only on an admitted
compute request. ASGI replaces sockets; SDK/authentication and callbacks run.
"""
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets
import time

import httpx
from fastapi import FastAPI
import control_plane_kit_core as core
from control_plane_kit_core.configuration_installation import (
    ConfigurationInstallationDisposition, ConfigurationInstallationReceipt,
)
from control_plane_kit_core.configuration_invocation import (
    configuration_invocation_correlation_for_request, configuration_invocation_selection_fingerprint,
)
from control_plane_kit_core.planning import (
    ManagementBootstrapStage, ObserveManagementBootstrap, ObserveNodeHealth,
    ReconcileNode, ReconcileRuntime, RemoveNodeResource, RemoveRuntimeResource,
    StartNode, StartRuntime, StopNode, StopRuntime,
)
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact
from control_plane_kit_core.runtime_effects import RuntimeEffectRequest, RuntimeEffectResult, RuntimeEffectFailure
from control_plane_kit_core.secrets import (
    SecretCustodyReceipt, SecretResolved, SecretValue, SecretDenied,
)
from control_plane_kit_core.secret_version_grants import SecretVersionResolutionGrant
from control_plane_kit_core.secret_installation import (
    SecretResolutionReceipt, SecretInstallationReceipt, secret_installation_correlation_for_request,
    secret_material_selection_fingerprint,
)
from control_plane_kit_interpreters.secrets import validate_selected_secret_grants, resolve_selected_secret_deliveries
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, validate_graph
from control_plane_kit_interpreters.docker.management_health import DockerManagedHealthObserver
from control_plane_kit_interpreters.probes.health_signing import (
    Ed25519HealthCredentialPairSigner, HealthSigningContext, HealthSigningKey,
)
from control_plane_kit_interpreters.probes.health_transport import (
    GatewayHealthTransportCode, SelectedManagementGateway, SignedGatewayHealthClient,
)
from control_plane_kit_operations.effect_outcome_evidence import NativeConnectionObservation, NativeConnectionOutcome
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from control_plane_kit_operations.ingress_authorities import require_cloudflared_tunnel_token_delivery
from control_plane_kit_operations.runtime_management_targets import project_management_health_target
from control_plane_kit_server_sdk.fastapi import install_cpk_wrapper
from control_plane_kit_servers_cpk_local_gateway.health_relay import GatewayHealthRelay
from control_plane_kit_servers_cpk_local_gateway.health_transit_verification import gateway_health_transit_verifier_from_artifact
from control_plane_kit_servers_cpk_local_gateway.server import create_app


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def synthetic_runtime_registration(compute):
    return RuntimeAdapterRegistration(compute, exact_version_execute_with_authority=True)


class ComputeSubstitute:
    """In-memory allocation/install boundary; never a Docker replacement claim."""
    def __init__(self):
        self.installed, self.identities, self.calls = {}, {}, []
        self.runtimes = set()
        self.configuration_refs = {}
        self.order = []
        self.receipt_mode = "valid"
        self.selected_resolver = None
        self._recipient_material = {}

    def execute(self, request):
        raise AssertionError("compute dispatch requires registered runtime authority")

    def execute_with_authority(self, request, authority):
        assert authority.authority_ref == request.authority_ref
        assert type(request.operation) in (StartRuntime, ReconcileRuntime, StopRuntime,
            RemoveRuntimeResource, StartNode, ReconcileNode, StopNode, RemoveNodeResource)
        self.calls.append(request)
        selected = None
        if type(request.operation) in (StartNode, ReconcileNode) and request.products[0].secret_selections:
            RuntimeEffectRequest.__post_init__(request)
            material, = request.products
            deliveries = material.product.runtime_contract.secret_deliveries
            try:
                if material.node_id != "connector" or len(deliveries) != 1:
                    raise ValueError("unsupported synthetic recipient")
                require_cloudflared_tunnel_token_delivery(deliveries)
            except ValueError:
                return RuntimeEffectResult.unsupported(request.effect_id,
                    RuntimeEffectFailure("fixture.selected-shape-unsupported", "synthetic selected shape is unsupported"))
            try:
                validate_selected_secret_grants(request, self.selected_resolver)
                selected = resolve_selected_secret_deliveries(deliveries, selections=material.secret_selections,
                    grants=request.secret_resolution_grants, resolver=self.selected_resolver)
            except Exception:
                return RuntimeEffectResult.failed(request.effect_id,
                    RuntimeEffectFailure("fixture.selected-resolution-refused", "synthetic exact resolution refused"))
        if request.configuration_instances is not None:
            for ref in request.configuration_instances.instances:
                previous = self.configuration_refs.setdefault(ref.allocation_id, ref)
                assert previous == ref, "allocation identity changed selected material"
        self.order.append((type(request.operation).__name__, request.activity_id.value))
        evidence = {"provider_boundary": "1912-memory-compute"}
        if type(request.operation) in (StartNode, ReconcileNode):
            node = request.operation.target.node_id
            material, = (value for value in request.products if value.node_id == node)
            prior = self.identities.get(node)
            identity = hashlib.sha256(request.effect_id.encode()).hexdigest()
            if type(request.operation) is StartNode:
                assert prior is None, "duplicate allocation"
            else:
                assert prior is not None and prior != identity
            # Capture the exact request material, not an independently selected desired graph.
            self.installed[node] = material
            self.identities[node] = identity
            disposition = (ConfigurationInstallationDisposition.CREATED if prior is None
                else ConfigurationInstallationDisposition.REPLACED)
            if (type(request.operation) is ReconcileNode or selected is not None) and (
                    request.configuration_instances is not None and self.receipt_mode != "missing"):
                correlation = configuration_invocation_correlation_for_request(request)
                selection = configuration_invocation_selection_fingerprint(correlation.selection)
                evidence["configuration_installation_receipt"] = ConfigurationInstallationReceipt(
                    correlation.request_fingerprint,
                    selection if self.receipt_mode == "valid" else "0" * 64,
                    disposition, prior, identity).descriptor()
            if selected is not None:
                # Private simulated file bytes, mode and path binding; no filesystem claim.
                files = {value.target_path: (value.value.reveal(), value.file_mode, value.path_environment_name)
                    for value in selected.files}
                self._recipient_material[node] = (identity, dict(selected.environment), files)
                expected_files = {value.target_path: (value.value.reveal(), value.file_mode, value.path_environment_name)
                    for value in selected.files}
                if self._recipient_material[node] != (self.identities[node], dict(selected.environment), expected_files):
                    return RuntimeEffectResult.uncertain(request.effect_id,
                        RuntimeEffectFailure("fixture.selected-recipient-unknown", "synthetic recipient check failed"))
                context = secret_installation_correlation_for_request(request)
                commitment = secret_material_selection_fingerprint(request)
                evidence.update(secret_recipient_boundary="synthetic-in-memory",
                    secret_resolution_receipt=SecretResolutionReceipt(context.request_fingerprint, commitment).descriptor(),
                    secret_installation_receipt=SecretInstallationReceipt(context.request_fingerprint,
                        commitment, disposition, prior, identity).descriptor())
        elif type(request.operation) is RemoveNodeResource:
            node = request.operation.target.node_id
            self.installed.pop(node)
            self.identities.pop(node)
            self._recipient_material.pop(node, None)
        elif type(request.operation) is StartRuntime:
            assert request.operation.target.runtime_id not in self.runtimes
            self.runtimes.add(request.operation.target.runtime_id)
        elif type(request.operation) is RemoveRuntimeResource:
            assert not self.installed
            self.runtimes.remove(request.operation.target.runtime_id)
        return RuntimeEffectResult.succeeded(request.effect_id, evidence=evidence)


@dataclass(frozen=True)
class IngressAllocation:
    secret_custody_receipt: SecretCustodyReceipt
    tunnel_id: str
    tunnel_name: str
    dns_record_id: str
    hostname: str
    endpoint_url: str


class IngressSubstitute:
    """Deterministic external ingress/custody boundary, no provider API calls."""
    def __init__(self, compute):
        self.compute = compute
        self.allocations, self.calls = {}, []
        self._private_material = {}
        compute.selected_resolver = self

    def create(self, ingress, *, authority, allocation_name, origin_service_url,
               secret_resolution_grant, secret_custody_grant):
        assert allocation_name not in self.allocations
        self.calls.append(("create", allocation_name))
        self.compute.order.append(("ingress-create", allocation_name))
        receipt = SecretCustodyReceipt(secret_custody_grant.custody_id,
            secret_custody_grant.provider_registration_id, secret_custody_grant.reference,
            "synthetic-version", 1)
        identity = hashlib.sha256(allocation_name.encode()).hexdigest()[:24]
        allocation = IngressAllocation(receipt, "tunnel-" + identity, allocation_name,
            "dns-" + identity, ingress.hostname, "https://" + ingress.hostname)
        self.allocations[allocation_name] = allocation
        self._private_material[allocation_name] = (secret_custody_grant, SecretValue(secrets.token_urlsafe(32)))
        return allocation

    def resolve(self, grant):
        if type(grant) is not SecretVersionResolutionGrant:
            raise ValueError("synthetic resolution requires an exact version grant")
        for name, allocation in self.allocations.items():
            custody, value = self._private_material[name]
            receipt = allocation.secret_custody_receipt
            if (grant.selection.reference == receipt.reference and grant.selection.version_id == receipt.version_id
                    and grant.selection.intent is custody.intent and all(getattr(grant, field) == getattr(custody, field)
                        for field in ("workspace_id", "provider_registration_id", "endpoint_reference", "credential_reference"))):
                return SecretResolved(receipt.reference, value)
        return SecretDenied(grant.selection.reference)

    def teardown(self, *, authority, resources, secret_resolution_grant, secret_custody_grant):
        key, = (key for key, value in self.allocations.items()
            if value.tunnel_id == resources.tunnel_id and value.dns_record_id == resources.dns_record_id)
        self.calls.append(("remove", key))
        self.allocations.pop(key)
        self._private_material.pop(key)


class KeyMaterialSubstitute:
    def __init__(self, material):
        self.material, self.calls = material, []
        self.unavailable = False
        self.failures = 0

    def resolve(self, grant):
        self.calls.append(grant)
        if self.unavailable:
            self.failures += 1
            raise RuntimeError("synthetic external key material unavailable")
        family = grant.reference.reference_id.rsplit("/", 1)[-1]
        assert grant.reference.reference_id == "secret://health-secrets/keys/" + family
        return SecretResolved(grant.reference, SecretValue(self.material.private[family].decode("ascii")))


class InstalledTransport(httpx.AsyncBaseTransport):
    """Explicit socket substitute; only dispatch to apps from installed bytes."""
    def __init__(self, apps):
        self.apps, self.calls = apps, []

    async def handle_async_request(self, request):
        self.calls.append((request.url.host, request.url.path))
        return await httpx.ASGITransport(app=self.apps[request.url.host]).handle_async_request(request)


class PublicAddressSubstitute:
    async def resolve(self, hostname):
        assert hostname == "cpk-1912.example.invalid"
        return ("8.8.8.8",)


class SignedHealthComposition:
    def __init__(self, material, compute, ingress):
        self.compute, self.ingress = compute, ingress
        self.keys = KeyMaterialSubstitute(material)
        self.signed_reads, self.native_reads, self.local_reads = [], [], []
        self.public_dispatches = []
        self.attempted_reads = []

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        return tuple(value.activity_id for value in plan.activities
            if type(value.operation) in (ObserveManagementBootstrap, ObserveNodeHealth))

    async def observe_connection(self, realization, request, authority):
        assert authority.authority_ref == request.authority_ref
        assert self.ingress.allocations and "connector" in self.compute.identities
        self.native_reads.append(request.activity_id.value)
        self.compute.order.append(("native-connected", request.activity_id.value))
        instant = stamp()
        return NativeConnectionObservation(NativeConnectionOutcome.CONNECTED, request.effect_id,
            request.activity_id.value, self.compute.identities["connector"], instant, instant, 1,
            "11111111-1111-4111-8111-111111111111")

    def installed_configuration(self, name):
        material = self.compute.installed[name]
        contract = material.product.runtime_contract
        artifact = select_receiver_node_control_configuration_artifact(
            artifacts=contract.configuration_artifacts,
            environment=(*material.public_environment, *material.socket_environment),
            control_surfaces=contract.control_surfaces)
        return core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())

    def applications(self):
        apps = {}
        transport = InstalledTransport(apps)
        for name in self.compute.installed:
            if name in ("gateway", "connector"):
                continue
            app = FastAPI()
            install_cpk_wrapper(app, configuration=self.installed_configuration(name),
                readiness=lambda:core.NodeHealthReadOutcome.HEALTHY)
            apps[name] = app
        configured = self.installed_configuration("gateway")
        artifacts = {value.artifact_id: value for value in
            self.compute.installed["gateway"].product.runtime_contract.configuration_artifacts}
        routes = core.ReceiverManagementRoutesCodec().decode_bytes(artifacts["gateway-health-targets"].content.encode())
        relay = GatewayHealthRelay(routes,
            gateway_health_transit_verifier_from_artifact(artifacts["gateway-health-transit"]),
            clock=lambda:int(time.time()), transport=transport)
        apps["gateway"] = create_app(health_relay=relay, control_configuration=configured)
        return apps, routes, transport

    async def observe_signed(self, realization, request, authority):
        self.attempted_reads.append(request)
        preparation = authority.preparation
        configured = self.installed_configuration(preparation.request.target.node_id.value)
        assert configured.target == preparation.request.target
        assert configured.declaration.identity() == preparation.request.declaration_identity
        context = HealthSigningContext(preparation.request, preparation.transit_grant.attempt_id,
            preparation.transit_grant.gateway_target, configured.declaration,
            preparation.transit_grant.issuer, preparation.workload_grant.issuer)
        pair = Ed25519HealthCredentialPairSigner(self.keys, lambda:int(time.time())).sign(context,
            transit_grant=preparation.transit_grant, workload_grant=preparation.workload_grant,
            transit_key=HealthSigningKey(authority.transit.public_key, authority.transit.resolution_grant),
            workload_key=HealthSigningKey(authority.workload.public_key, authority.workload.resolution_grant))
        apps, routes, transport = self.applications()
        local = (type(request.operation) is ObserveManagementBootstrap
            and request.operation.stage is ManagementBootstrapStage.GATEWAY_LOCAL_READY)
        gateway = apps["gateway"]
        # Construction/configuration is not serving readiness.
        assert gateway.state.gateway_local_health.readiness() is core.NodeHealthReadOutcome.UNHEALTHY
        async with AsyncExitStack() as stack:
            for app in apps.values():
                await stack.enter_async_context(app.router.lifespan_context(app))
            if local:
                # Initial LOCAL has no ingress or connector. Updates may retain them.
                if not DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor).nodes:
                    assert not self.ingress.calls and "connector" not in self.compute.installed
                    assert not self.public_dispatches
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway),
                        base_url="http://gateway:8000") as client:
                    response = await client.get("/__control/health/readiness",
                        headers={"Authorization": "Bearer " + pair.workload_credential.decode("ascii")})
                assert response.status_code == 200 and len(response.content) <= 16384
                result = core.ReceiverHealthReadResultCodec(preparation.request, configured.declaration).decode(response.json())
                self.local_reads.append(request.activity_id.value)
            else:
                current = validate_graph(DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor))
                desired = validate_graph(DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor))
                projection = project_management_health_target(realization.plan, request.activity_id,
                    request.operation, current, desired)
                binding, = (value for value in routes.targets if value.target == configured.target
                    and value.declaration == configured.declaration)
                roles = core.NodeControlGraphReferenceRole
                destination = SelectedManagementGateway(projection.ingress,
                    core.NodeControlGraphReference(roles.NODE, projection.gateway_node_id),
                    projection.gateway_transit_provider_socket_name, configured.target.runtime_id,
                    binding.target_id, core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2)
                client = SignedGatewayHealthClient(clock=lambda:int(time.time()),
                    public_resolver=PublicAddressSubstitute(), transport=httpx.ASGITransport(app=gateway))
                response = await DockerManagedHealthObserver(client).observe(request.operation,
                    plan=realization.plan, activity_id=request.activity_id, source=request.source,
                    current=current, desired=desired, authority_context=preparation.request.authority_context,
                    context=context, pair=pair, transit_grant=preparation.transit_grant,
                    workload_grant=preparation.workload_grant, destination=destination)
                assert response.code is GatewayHealthTransportCode.RECEIVED
                result = response.result
                self.public_dispatches.append(request.activity_id.value)
        assert gateway.state.gateway_local_health.readiness() is core.NodeHealthReadOutcome.UNHEALTHY
        self.signed_reads.append((request.activity_id.value, result.request.target.node_id.value,
            self.compute.identities["gateway"], tuple(value.target_id for value in routes.targets)))
        self.compute.order.append(("signed-health", request.activity_id.value))
        return result
