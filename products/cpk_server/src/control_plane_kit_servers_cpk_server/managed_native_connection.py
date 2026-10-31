"""Process-owned capability selection, not admission or installation history."""
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from control_plane_kit_core.planning import WaitForHealthy, resolve_management_observation
from control_plane_kit_core.products import ProductDescriptorCodec, ProductDescriptorDocument, ProductReference
from control_plane_kit_core.runtime_effects import RuntimeEffectRequest
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_interpreters.docker.connector_connection import (
    ConnectorConnectionObservation, ConnectorConnectionOutcome, ConnectorConnectionQualification,
    DockerConnectorConnectionObserver, DockerConnectorConnectionQualifier,
)
from control_plane_kit_interpreters.docker.sdk import ConnectorConnectionProfile, DockerSdkClient
from control_plane_kit_operations.effect_outcome_evidence import (
    NativeConnectionObservation, NativeConnectionOutcome, NativeConnectionRefused,
)
from control_plane_kit_operations.runtime_management_targets import is_native_connection_operation

from .managed_health import ManagedHealthUnavailable, _authority, _graph_pair, _product
from .managed_health_placement import DockerRuntimeClientSelector, DockerRuntimePolicyBinding


@dataclass(frozen=True, slots=True, repr=False)
class DockerManagedNativeConnection:
    """One reviewed managed product and explicit borrowed or owned capabilities.

    Registered product values must match this process capability. Neither that
    match nor a binding grants execution authority or qualifies a live image.
    """
    provider_clients: DockerRuntimeClientSelector
    product_document: ProductDescriptorDocument
    clock: Callable[[], datetime]

    def _qualified(self, *, plan, current, desired, registered_products, runtime_authorities):
        try:
            if (type(self.provider_clients) is not DockerRuntimeClientSelector
                    or type(self.product_document) is not ProductDescriptorDocument
                    or not callable(self.clock)):
                return None
            document = ProductDescriptorCodec().decode_document(self.product_document.content)
            if document != self.product_document:
                return None
            reference = ProductReference.from_document(document)
            pair = _graph_pair(current, desired)
            selected = []
            for activity in plan.activities:
                operation = activity.operation
                if type(operation) is WaitForHealthy:
                    return None
                if not is_native_connection_operation(operation):
                    continue
                resolved = resolve_management_observation(operation, *pair, expected_operation=operation)
                runtime = resolved.selected_graph.graph.runtimes[operation.target.runtime_id]
                authority = _authority(runtime_authorities, runtime)
                product = _product(registered_products, authority.workspace_id, resolved.connector_node)
                if product.reference != reference or product.descriptor_document != document:
                    return None
                qualifier = DockerConnectorConnectionQualifier(reference,
                    document.product.image.execution_reference,
                    profile=ConnectorConnectionProfile.MANAGED_WRAPPER_V1)
                mode = qualifier.qualify_shape(activity_id=activity.activity_id, plan=plan,
                    current=pair[0], desired=pair[1], product_document=document,
                    authority_ref=authority.authority_ref)
                if mode is None:
                    return None
                selected.append((activity.activity_id, authority, mode))
            return pair, tuple(selected)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            return None

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        selected = self._qualified(plan=plan, current=current, desired=desired,
            registered_products=registered_products, runtime_authorities=runtime_authorities)
        if selected is not None:
            for activity, authority, _ in selected[1]:
                if self.provider_clients.select(workspace_id=authority.workspace_id,
                        runtime_id=plan.activity(activity).operation.target.runtime_id, authority=authority) is None:
                    return None
        return None if selected is None else tuple(item[0] for item in selected[1])

    def qualify(self, *, plan, current, desired, registered_products, runtime_authorities):
        """Original complete-plan/product qualification, without current binding reads."""
        selected = self._qualified(plan=plan, current=current, desired=desired,
            registered_products=registered_products, runtime_authorities=runtime_authorities)
        return None if selected is None else tuple(item[0] for item in selected[1])

    async def observe_connection(self, realization, request, authority, *, managed_target=None):
        try:
            if type(request) is not RuntimeEffectRequest:
                raise ValueError
            request.__post_init__()
            dynamic = self.provider_clients.capability_policy is not None
            if (dynamic and managed_target is None) or (not dynamic and managed_target is not None):
                raise ValueError
            inputs = dict(plan=realization.plan,
                current=DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor),
                desired=DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor),
                registered_products=realization.registered_products,
                runtime_authorities=realization.runtime_authorities)
            if not dynamic and self.select(**inputs) is None:
                raise ValueError
            selected = self._qualified(**inputs)
            if selected is None:
                raise ValueError
            pair, activities = selected
            activity, current_authority, mode = next(
                item for item in activities if item[0] == request.activity_id)
            if (authority != current_authority or type(authority) is not type(current_authority)
                    or request.source.workspace_id != current_authority.workspace_id
                    or request.authority_ref != current_authority.authority_ref
                    or request.operation != realization.plan.activity(activity).operation):
                raise ValueError
            arguments = dict(workspace_id=authority.workspace_id,
                runtime_id=request.operation.target.runtime_id, authority=authority)
            binding = (self.provider_clients.bind_admitted(managed_target, **arguments) if dynamic
                else self.provider_clients.select(**arguments))
            if binding is None:
                raise ValueError
            original, receipt = None, None
            if mode in (ConnectorConnectionQualification.RETAINED_CONTENT_UPDATE,
                        ConnectorConnectionQualification.RETAINED_IMAGE_INGRESS_UPDATE):
                installation = realization.connector_installation
                if installation is not None:
                    original, receipt = installation.original_request, installation.receipt
            observed = await asyncio.to_thread(self._observe, binding, request,
                plan=realization.plan, current=pair[0], desired=pair[1],
                installation_request=original, installation_receipt=receipt)
            if (type(observed) is not ConnectorConnectionObservation
                    or type(observed.outcome) is not ConnectorConnectionOutcome):
                raise ValueError
            if observed.outcome is ConnectorConnectionOutcome.REFUSED:
                if any(value is not None for value in (observed.effect_id, observed.activity_id,
                        observed.container_id, observed.sample_start, observed.sample_end,
                        observed.ready_connections, observed.connector_id)):
                    raise ValueError
                return NativeConnectionRefused()
            if (observed.effect_id != request.effect_id
                    or observed.activity_id != request.activity_id.value):
                raise ValueError
            # The existing Operations constructor validates the closed result;
            # preserve timestamp text rather than rounding through datetime.
            return NativeConnectionObservation(NativeConnectionOutcome(observed.outcome.value),
                observed.effect_id, observed.activity_id, observed.container_id,
                observed.sample_start, observed.sample_end, observed.ready_connections, observed.connector_id)
        except Exception:
            failure = ManagedHealthUnavailable("managed health is unavailable")
        # Raise outside the exception context: provider/material detail is private.
        raise failure

    def _observe(self, binding, request, **inputs):
        # Cancellation of the awaiting task cannot close a client while this
        # worker is using it. The worker retains custody until its own finally.
        owned = type(binding) is DockerRuntimePolicyBinding
        client = None
        try:
            client = (DockerSdkClient.from_authority(binding.local_client_config,
                connect_on_init=False) if owned else binding.client)
            observer = DockerConnectorConnectionObserver(client,
                ProductReference.from_document(self.product_document),
                self.product_document.product.image.execution_reference, self.clock,
                profile=ConnectorConnectionProfile.MANAGED_WRAPPER_V1)
            # Original-proof/material preflight stays in the observer and runs
            # before its first SDK read acquires the explicit Unix transport.
            return observer.observe(request, **inputs)
        finally:
            if owned and client is not None:
                client.close()
