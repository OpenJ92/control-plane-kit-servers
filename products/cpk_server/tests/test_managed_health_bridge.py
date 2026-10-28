"""The production bridge qualifies the original complete plan before effects."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.topology import validate_graph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.products import InlineDescriptorSource, RegisteredProduct
from control_plane_kit_operations.runtime_authorities import LocalDockerSocketAuthority, RegisteredRuntimeAuthority
from control_plane_kit_operations.runtime_management_targets import is_native_connection_operation
from receiver_acceptance_material import AuthoredMaterial


class ManagedHealthBridgeSelectionTests(unittest.TestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBridge
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerControllerPlacement, DockerGatewayEndpointReader, DockerRuntimeClientBinding, DockerRuntimeClientSelector,
        )
        from control_plane_kit_interpreters.docker import DockerSdkClient
        self.material = AuthoredMaterial()
        graph = self.material.a
        retained = {"gateway", "connector"}
        self.current = replace(graph, nodes={key: value for key, value in graph.nodes.items() if key in retained},
            runtimes={key: replace(value, children=tuple(node for node in value.children if node in retained))
                for key, value in graph.runtimes.items()})
        self.desired = graph
        self.plan = core.compile_graph_activity_plan(validate_graph(self.current), validate_graph(self.desired))
        self.assertTrue(self.plan.ready_for_execution)
        self.assertTrue(any(type(item.operation) is core.ObserveManagementBootstrap
            and item.operation.stage is core.ManagementBootstrapStage.GATEWAY_LOCAL_READY
            for item in self.plan.activities), "witness must exercise an actual compiled local stage")
        self.authority = RegisteredRuntimeAuthority("registration", "workspace-a",
            graph.runtimes["docker"].authority_ref, RuntimeKind.DOCKER,
            LocalDockerSocketAuthority(), "operator", "2026-10-13T00:00:00Z")
        self.products = tuple(RegisteredProduct("product-" + name, "workspace-a",
            ProductReference.from_document(document), document, InlineDescriptorSource(),
            "operator", "2026-10-13T00:00:00Z") for name, document in self.material.documents.items())
        self.client, self.bindings, self.reader = Mock(), Mock(), Mock()
        self.sdk = DockerSdkClient(client=self.client, connect_on_init=False)
        self.provider = DockerRuntimeClientBinding("workspace-a", "docker", self.authority.authority_ref, self.sdk)
        self.provider_clients = DockerRuntimeClientSelector((self.provider,))
        self.endpoints = DockerGatewayEndpointReader((DockerControllerPlacement(self.provider, "c" * 64),), self.bindings)
        self.native = Mock()
        self.native.provider_clients = self.provider_clients
        self.native.select.return_value = tuple(item.activity_id for item in self.plan.activities
            if is_native_connection_operation(item.operation))
        self.bridge = ManagedHealthBridge(self.reader, self.provider_clients, self.endpoints, self.material.decoders, self.native)

    def select(self, bridge=None, authorities=None):
        return (bridge or self.bridge).select(plan=self.plan, current=self.current, desired=self.desired,
            registered_products=self.products,
            runtime_authorities=(self.authority,) if authorities is None else authorities)

    def test_complete_original_plan_selection_is_pure(self):
        expected = tuple(item.activity_id for item in self.plan.activities
            if type(item.operation) in (core.ObserveManagementBootstrap, core.ObserveNodeHealth))
        self.assertEqual(self.select(), expected)
        self.assertEqual(self.client.mock_calls, [])
        self.bindings.assert_not_called()
        self.assertEqual(self.reader.mock_calls, [])
        self.assertIs(self.native.select.call_args.kwargs["plan"], self.plan)

    def test_missing_placement_or_native_qualification_is_unsupported(self):
        self.assertIsNone(self.select(replace(self.bridge, endpoints=None)))
        # The retained transition has a genuine connector stage; no filtered subplan.
        self.assertTrue(self.native.select.return_value)
        self.assertIsNone(self.select(replace(self.bridge, native=None)))
        self.native.select.return_value = ()
        self.assertIsNone(self.select())
        self.assertEqual(self.client.mock_calls, [])
        self.assertEqual(self.reader.mock_calls, [])

    def test_wrong_workspace_or_ambiguous_authority_refuses_before_reads(self):
        for authorities in ((), (self.authority, self.authority),
                (replace(self.authority, workspace_id="workspace-b"),)):
            with self.subTest(count=len(authorities)):
                self.assertIsNone(self.select(authorities=authorities))
        self.assertEqual(self.client.mock_calls, [])
        self.bindings.assert_not_called()
        self.assertEqual(self.reader.mock_calls, [])

    def test_missing_exact_gateway_decoder_refuses_without_catalogue_fallback(self):
        from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
        self.assertIsNone(self.select(replace(self.bridge, decoders=HealthReceiverDecoders(()))))
        self.assertEqual(self.reader.mock_calls, [])
        self.assertEqual(self.client.mock_calls, [])

    def use_fresh_plan(self):
        from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
        self.current = DeploymentGraph(self.desired.name)
        self.desired = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(self.desired))
        self.plan = core.compile_graph_activity_plan(validate_graph(self.current), validate_graph(self.desired))
        self.assertTrue(self.plan.ready_for_execution)
        self.assertFalse(any(type(item.operation) is core.ObserveManagementBootstrap
            and item.operation.stage is core.ManagementBootstrapStage.GATEWAY_LOCAL_READY
            for item in self.plan.activities))
        self.native.select.return_value = tuple(item.activity_id for item in self.plan.activities
            if is_native_connection_operation(item.operation))

    def dispatch_inputs(self, *, local, stage=None):
        from types import SimpleNamespace
        from control_plane_kit_core.operations import RunId
        from control_plane_kit_core.runtime_effects import RuntimeEffectKind, RuntimeEffectRequest, RuntimeEffectSource
        from control_plane_kit_core.secrets import SecretProviderEndpointReference, SecretReference, SecretResolutionGrant, SecretUseIntent
        from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
        if local:
            stage = core.ManagementBootstrapStage.GATEWAY_LOCAL_READY
        operation_type = core.ObserveManagementBootstrap if stage is not None else core.ObserveNodeHealth
        activity = next(item for item in self.plan.activities if type(item.operation) is operation_type
            and (stage is None or item.operation.stage is stage))
        configured = self.material.configurations["gateway" if stage is not None else activity.operation.node_id]
        gateway = self.material.configurations["gateway"]
        request = core.ReceiverHealthReadRequest(configured.target,
            core.NodeControlAuthorityContext("graph-desired", "projection-desired"),
            core.NodeHealthReadKind.READINESS, configured.declaration.identity(), "health-request")
        common = dict(canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            target=request.target, authority_context=request.authority_context, kind=request.kind,
            declaration_identity=request.declaration_identity, request_id=request.request_id,
            request_digest=request.canonical_digest(), issued_at=100, not_before=101, expires_at=200)
        transit = core.DelegatedGatewayReceiverHealthReadTransitGrant(
            profile=core.DelegatedGatewayReceiverHealthReadTransitGrantProfile.V2,
            purpose=core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, issuer="cpk-server",
            key_id=self.material.public["transit"].key_id, gateway_target=gateway.target,
            attempt_id="attempt-a", jti="transit-jti", **common)
        workload = core.DelegatedWorkloadReceiverHealthReadGrant(
            profile=core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2,
            purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, issuer="cpk-server",
            key_id=self.material.public["workload"].key_id,
            audience=core.receiver_node_control_audience(request.target), jti="workload-jti", **common)
        resolutions = tuple(SecretResolutionGrant(
            authorization_id="suse_" + marker * 64, workspace_id="workspace-a",
            reference_registration_id="sref_" + marker * 64, provider_registration_id="sprov_" + "c" * 64,
            endpoint_reference=SecretProviderEndpointReference("provider-a"),
            credential_reference=SecretReference("secret://bootstrap/provider-token"),
            reference=SecretReference("secret://provider-a/keys/" + family), intent=intent,
            actor_subject="actor-a", correlation_id="correlation-" + marker, intent_fingerprint=marker * 64,
            operation_id="attempt-a", session_id="session-a", run_id="run-a", activity_id=activity.activity_id.value)
            for marker, family, intent in (("a", "transit", SecretUseIntent.GATEWAY_NODE_HEALTH_READ_TRANSIT_SIGNING_KEY),
                ("b", "workload", SecretUseIntent.WORKLOAD_NODE_HEALTH_READ_SIGNING_KEY)))
        # Pure values at the owner effect seam; no claim to have admitted a run.
        authority = SimpleNamespace(preparation=SimpleNamespace(workspace_id="workspace-a", request=request,
            transit_grant=transit, workload_grant=workload),
            transit=SimpleNamespace(public_key=self.material.public["transit"], resolution_grant=resolutions[0]),
            workload=SimpleNamespace(public_key=self.material.public["workload"], resolution_grant=resolutions[1]))
        source = RuntimeEffectSource("workspace-a", "request-a", RunId("run-a"), "plan-a",
            "graph-base", "graph-desired", "event-a")
        effect = RuntimeEffectRequest("event-a", RuntimeEffectKind.REALIZE_ACTIVITY, RuntimeKind.DOCKER,
            source, activity.activity_id, activity.operation, authority_ref=self.authority.authority_ref)
        realization = SimpleNamespace(plan=self.plan, registered_products=self.products,
            runtime_authorities=(self.authority,),
            base_graph=SimpleNamespace(graph_descriptor=DEFAULT_GRAPH_CODEC.encode(self.current)),
            desired_graph=SimpleNamespace(graph_descriptor=DEFAULT_GRAPH_CODEC.encode(self.desired)))
        result = core.ReceiverHealthReadResult(request, configured.declaration, core.NodeHealthReadOutcome.HEALTHY)
        return realization, effect, authority, result

    def test_signed_dispatch_preserves_original_values_and_selects_local_or_public(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode
        for local in (True, False):
            with self.subTest(local=local):
                realization, request, authority, result = self.dispatch_inputs(local=local)
                endpoint = object()
                read = Mock(return_value=endpoint)
                endpoints = SimpleNamespace(select=self.endpoints.select, read=read)
                reader = SimpleNamespace(observe=AsyncMock(return_value=SimpleNamespace(
                    code=GatewayHealthTransportCode.RECEIVED, result=result)))
                bridge = replace(self.bridge, reader=reader, endpoints=endpoints)
                observed = asyncio.run(bridge.observe_signed(realization, request, authority))
                self.assertIs(observed, result)
                reader.observe.assert_awaited_once()
                args = reader.observe.call_args
                self.assertIs(args.args[0], request)
                self.assertIs(args.kwargs["plan"], realization.plan)
                self.assertIs(args.kwargs["context"].request, authority.preparation.request)
                for family in ("transit", "workload"):
                    self.assertIs(args.kwargs[family + "_grant"], getattr(authority.preparation, family + "_grant"))
                    self.assertIs(args.kwargs[family + "_key"].resolution_grant, getattr(authority, family).resolution_grant)
                self.assertIs(args.kwargs["local_destination"], endpoint if local else None)
                if local:
                    self.assertIsNone(args.kwargs["destination"])
                    read.assert_called_once_with(provider_binding=self.provider, workspace_id="workspace-a", runtime_id="docker",
                        authority=self.authority, gateway_node_id="gateway", socket_name="control", port=8000,
                        graph_id="graph-desired")
                else:
                    destination = args.kwargs["destination"]
                    self.assertEqual(destination.gateway_node_id.value, "gateway")
                    self.assertEqual(destination.target_id, "api")
                    read.assert_not_called()
                reader.observe.return_value = SimpleNamespace(code=GatewayHealthTransportCode.TIMED_OUT)
                self.assertIsNone(asyncio.run(bridge.observe_signed(realization, request, authority)))

    def test_fresh_public_stages_preserve_named_ingress_without_private_reads(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode
        self.use_fresh_plan()
        for stage in (core.ManagementBootstrapStage.AUTHENTICATED_MANAGEMENT_PATH,
                core.ManagementBootstrapStage.GATEWAY_INGRESS_READY, None):
            with self.subTest(stage=stage):
                realization, request, authority, result = self.dispatch_inputs(local=False, stage=stage)
                read = Mock(side_effect=AssertionError("public health must not inspect private placement"))
                reader = SimpleNamespace(observe=AsyncMock(return_value=SimpleNamespace(
                    code=GatewayHealthTransportCode.RECEIVED, result=result)))
                bridge = replace(self.bridge, reader=reader,
                    endpoints=SimpleNamespace(select=self.endpoints.select, read=read))
                self.assertIs(asyncio.run(bridge.observe_signed(realization, request, authority)), result)
                read.assert_not_called()
                reader.observe.assert_awaited_once()
                args = reader.observe.call_args
                self.assertIs(args.args[0], request)
                self.assertIs(args.kwargs["plan"], self.plan)
                self.assertEqual(args.kwargs["current"], validate_graph(self.current))
                self.assertEqual(args.kwargs["desired"], validate_graph(self.desired))
                self.assertIs(args.kwargs["context"].request, authority.preparation.request)
                self.assertIs(args.kwargs["authority_context"], authority.preparation.request.authority_context)
                for family in ("transit", "workload"):
                    self.assertIs(args.kwargs[family + "_grant"], getattr(authority.preparation, family + "_grant"))
                    self.assertIs(args.kwargs[family + "_key"].resolution_grant, getattr(authority, family).resolution_grant)
                self.assertIsNone(args.kwargs["local_destination"])
                destination = args.kwargs["destination"]
                self.assertEqual(destination.ingress, self.desired.public_ingresses[0])
                self.assertEqual(destination.gateway_node_id.value, "gateway")
                self.assertEqual(destination.runtime_id.value, "docker")
                self.assertEqual(destination.gateway_transit_provider_socket_name, "control")
                self.assertEqual(destination.target_id, "self" if stage is not None else "api")

    def test_public_stage_wrong_current_authority_refuses_before_any_reader(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        self.use_fresh_plan()
        for stage in (core.ManagementBootstrapStage.AUTHENTICATED_MANAGEMENT_PATH,
                core.ManagementBootstrapStage.GATEWAY_INGRESS_READY, None):
            with self.subTest(stage=stage):
                realization, request, authority, _ = self.dispatch_inputs(local=False, stage=stage)
                request = replace(request, authority_ref=RuntimeAuthorityReference("wrong-authority"))
                reader, read = SimpleNamespace(observe=AsyncMock()), Mock()
                bridge = replace(self.bridge, reader=reader,
                    endpoints=SimpleNamespace(select=self.endpoints.select, read=read))
                with self.assertRaises(ManagedHealthUnavailable):
                    asyncio.run(bridge.observe_signed(realization, request, authority))
                read.assert_not_called()
                reader.observe.assert_not_awaited()

    def test_actual_public_transport_failure_is_redacted_without_private_fallback(self):
        import asyncio
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import httpx
        from control_plane_kit_core.secrets import SecretResolved, SecretValue
        from control_plane_kit_interpreters.docker.managed_health import DockerManagedHealthReader
        from control_plane_kit_interpreters.probes.health_signing import Ed25519HealthCredentialPairSigner
        from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode, SignedGatewayHealthClient
        from control_plane_kit_interpreters.probes.local_health import LocalGatewayHealthClient
        self.use_fresh_plan()
        for error_type, code in ((httpx.ReadTimeout, GatewayHealthTransportCode.TIMED_OUT),
                (httpx.ConnectError, GatewayHealthTransportCode.TRANSPORT_FAILED)):
            with self.subTest(code=code):
                realization, request, authority, _ = self.dispatch_inputs(local=False)
                resolved = {getattr(authority, family).resolution_grant.reference:
                    SecretResolved(getattr(authority, family).resolution_grant.reference,
                        SecretValue(self.material.private[family].decode("ascii")))
                    for family in ("transit", "workload")}
                resolver = SimpleNamespace(resolve=Mock(side_effect=lambda grant: resolved[grant.reference]))
                dns = SimpleNamespace(resolve=AsyncMock(return_value=("93.184.216.34",)))
                sent, observations = [], []
                def fail(outbound):
                    sent.append(outbound)
                    raise error_type("sensitive-provider-sentinel", request=outbound)
                actual = DockerManagedHealthReader(Ed25519HealthCredentialPairSigner(resolver, lambda: 150),
                    SignedGatewayHealthClient(lambda: 150, public_resolver=dns, transport=httpx.MockTransport(fail)),
                    LocalGatewayHealthClient(lambda: 150))
                async def observe(*args, **kwargs):
                    outcome = await actual.observe(*args, **kwargs)
                    observations.append(outcome)
                    return outcome
                read = Mock(side_effect=AssertionError("public transport must not fall back to private placement"))
                bridge = replace(self.bridge, reader=SimpleNamespace(observe=observe),
                    endpoints=SimpleNamespace(select=self.endpoints.select, read=read))
                self.assertIsNone(asyncio.run(bridge.observe_signed(realization, request, authority)))
                self.assertEqual(len(sent), 1)
                self.assertEqual(str(sent[0].url), "https://93.184.216.34/cpk/health/readiness")
                self.assertEqual(sent[0].headers["Host"], "cpk-1912.example.invalid:443")
                self.assertEqual(sent[0].extensions["sni_hostname"], "cpk-1912.example.invalid")
                self.assertEqual(json.loads(sent[0].content)["target_id"], "api")
                self.assertEqual(len(observations), 1)
                self.assertIs(observations[0].code, code)
                self.assertIsNone(observations[0].result)
                self.assertNotIn("sensitive-provider-sentinel", repr(observations[0]))
                read.assert_not_called()
                dns.resolve.assert_awaited_once_with("cpk-1912.example.invalid")
                self.assertEqual(resolver.resolve.call_count, 2)

    def test_unavailable_placement_cannot_reach_signing_reader(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from control_plane_kit_servers_cpk_server.managed_health_placement import GatewayPlacementUnavailable
        realization, request, authority, result = self.dispatch_inputs(local=True)
        reader = SimpleNamespace(observe=AsyncMock())
        endpoints = SimpleNamespace(select=self.endpoints.select,
            read=Mock(side_effect=GatewayPlacementUnavailable("gateway placement is unavailable")))
        bridge = replace(self.bridge, reader=reader, endpoints=endpoints)
        with self.assertRaises(GatewayPlacementUnavailable):
            asyncio.run(bridge.observe_signed(realization, request, authority))
        reader.observe.assert_not_awaited()

    def test_dynamic_public_signed_dispatch_preserves_invocation_controls(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import httpx
        from control_plane_kit_core.secrets import SecretResolved, SecretValue
        from control_plane_kit_interpreters.docker.managed_health import DockerManagedHealthReader
        from control_plane_kit_interpreters.docker.sdk import DockerUnixSocketClientConfig
        from control_plane_kit_interpreters.probes.health_signing import Ed25519HealthCredentialPairSigner
        from control_plane_kit_interpreters.probes.health_transport import SignedGatewayHealthClient
        from control_plane_kit_interpreters.probes.local_health import LocalGatewayHealthClient
        from control_plane_kit_operations.managed_runtime_assignments import (
            ManagedRuntimeCapability, ManagedRuntimeCapabilityPolicy, ManagedRuntimeSelection,
            managed_runtime_assignment_id,
        )
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBridge, ManagedHealthUnavailable
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerRuntimeCapabilityBinding, DockerRuntimeClientSelector,
        )
        from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
        from managed_native_material import NativeMaterial
        world = NativeMaterial()
        self.material, self.authority, self.products = world.authored, world.authority, world.products
        self.current, self.desired, self.plan = world.current, world.desired, world.plan
        capability = ManagedRuntimeCapability("installed-a")
        policy = ManagedRuntimeCapabilityPolicy("installation-a", (capability,))
        uow = Mock(side_effect=AssertionError("signed dispatch must not reselect assignments"))
        selector = DockerRuntimeClientSelector((), capability_policy=policy,
            capability_bindings=(DockerRuntimeCapabilityBinding(capability,
                DockerUnixSocketClientConfig("/var/run/synthetic-never-opened.sock", 5.0)),),
            unit_of_work_factory=uow)
        native = DockerManagedNativeConnection(selector, world.document, Mock())
        target = ManagedRuntimeSelection(managed_runtime_assignment_id(policy.installation_id,
            "workspace-a", "docker", world.authority.authority_ref), policy.installation_id,
            "workspace-a", "docker", world.authority.authority_ref,
            world.authority.registration_id, capability.capability_id, 3)
        realization, request, authority, _ = self.dispatch_inputs(local=False)
        resolved = {getattr(authority, family).resolution_grant.reference:
            SecretResolved(getattr(authority, family).resolution_grant.reference,
                SecretValue(self.material.private[family].decode("ascii"))) for family in ("transit", "workload")}

        class ControlStop(RuntimeError):
            pass

        for stop in ("denied", "acknowledgement", None):
            with self.subTest(stop=stop):
                events, sent = [], []
                resolver = SimpleNamespace(resolve=Mock(side_effect=lambda grant: resolved[grant.reference]))
                def admit(kind, *, authorization_id=None):
                    events.append(("admit", kind, authorization_id))
                    if stop == "denied" and authorization_id == authority.workload.resolution_grant.authorization_id:
                        raise ControlStop("denied")
                    return object()
                def acknowledge(permit, outcome):
                    events.append(("outcome", outcome))
                    if stop == "acknowledgement":
                        raise ControlStop("acknowledgement unavailable")
                port = SimpleNamespace(control_error=ControlStop, admit=admit, record_outcome=acknowledge)
                def fail(outbound):
                    sent.append(outbound)
                    raise httpx.ReadTimeout("synthetic unavailable transport", request=outbound)
                dns = SimpleNamespace(resolve=AsyncMock(return_value=("93.184.216.34",)))
                reader = DockerManagedHealthReader(Ed25519HealthCredentialPairSigner(resolver, lambda: 150),
                    SignedGatewayHealthClient(lambda: 150, public_resolver=dns, transport=httpx.MockTransport(fail)),
                    LocalGatewayHealthClient(lambda: 150), require_invocations=True)
                bridge = ManagedHealthBridge(reader, selector, None, self.material.decoders, native)
                call = bridge.observe_signed(realization, request, authority,
                    invocations=port, managed_target=target)
                if stop is None:
                    self.assertIsNone(asyncio.run(call))
                    self.assertEqual(resolver.resolve.call_count, 2)
                    self.assertEqual(len(sent), 1)
                    self.assertEqual([event[1] for event in events if event[0] == "admit"],
                        ["secret-resolution", "secret-resolution", "signed-health-transport"])
                else:
                    with self.assertRaises(ControlStop):
                        asyncio.run(call)
                    resolver.resolve.assert_called_once_with(authority.transit.resolution_grant)
                    self.assertEqual(sent, [])
                    dns.resolve.assert_not_awaited()
                self.assertEqual(events[0], ("admit", "secret-resolution",
                    authority.transit.resolution_grant.authorization_id))
                with self.assertRaises(ManagedHealthUnavailable):
                    asyncio.run(bridge.observe_signed(realization, request, authority, invocations=port))
        uow.assert_not_called()

    def test_configured_local_endpoint_admission_and_ack_precede_signed_reader(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode
        realization, request, authority, result = self.dispatch_inputs(local=True)

        class ControlStop(RuntimeError):
            pass

        for stop in ("denied", "acknowledgement", None):
            with self.subTest(stop=stop):
                events, permit, endpoint = [], object(), object()
                def admit(kind, *, authorization_id=None):
                    events.append("admit")
                    self.assertEqual((kind, authorization_id), ("endpoint-observation", None))
                    if stop == "denied":
                        raise ControlStop("denied")
                    return permit
                def read(**kwargs):
                    events.append("read")
                    return endpoint
                def acknowledge(actual_permit, outcome):
                    events.append("acknowledge")
                    self.assertIs(actual_permit, permit)
                    self.assertEqual(outcome, "returned")
                    if stop == "acknowledgement":
                        raise ControlStop("acknowledgement unavailable")
                port = SimpleNamespace(control_error=ControlStop, admit=admit, record_outcome=acknowledge)
                reader = SimpleNamespace(observe=AsyncMock(return_value=SimpleNamespace(
                    code=GatewayHealthTransportCode.RECEIVED, result=result)))
                bridge = replace(self.bridge, reader=reader,
                    endpoints=SimpleNamespace(select=self.endpoints.select, read=read))
                call = bridge.observe_signed(realization, request, authority, invocations=port)
                if stop is None:
                    self.assertIs(asyncio.run(call), result)
                    self.assertEqual(events, ["admit", "read", "acknowledge"])
                    self.assertIs(reader.observe.call_args.kwargs["invocations"], port)
                    self.assertIs(reader.observe.call_args.kwargs["local_destination"], endpoint)
                else:
                    with self.assertRaises(ControlStop):
                        asyncio.run(call)
                    self.assertEqual(events, ["admit"] if stop == "denied" else ["admit", "read", "acknowledge"])
                    reader.observe.assert_not_awaited()
