"""Never-executed receiver models; no production catalogue or lifecycle emulator."""
from dataclasses import replace
import json
from types import SimpleNamespace

import jwt
import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSpec, BlockSockets, ProviderSocket
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity,
    ProductReference, ProductRuntimeContract, ProviderRuntimePort,
)
from control_plane_kit_core.topology import DeploymentGraph, Node, RuntimeRecord, validate_graph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
from control_plane_kit_core.secrets import SecretReference
from control_plane_kit_core.planning import compile_graph_activity_plan, ObserveNodeHealth, PlanGraphSide
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from control_plane_kit_operations.products import RegisteredProduct, InlineDescriptorSource
from control_plane_kit_operations.delegation_signing_keys import RegisteredDelegationSigningKey, RegisteredDelegationSigningKeyStatus
from control_plane_kit_operations.runtime_management_targets import project_management_health_target
from cpk_http_host_fixtures import fixture, verifier_family, with_health


def document(name, contract):
    codec = ProductDescriptorCodec()
    encoded = codec.encode_document(ContainerServerProduct(
        ProductIdentity("receiver-test", name, 1),
        OciImageReference("example.invalid", "never-executed/" + name, "sha256:" + "b" * 64),
        contract,
    ))
    # Use the actual canonical receiving value, including normalized numeric
    # fields, rather than the pre-encoding constructor's Python representation.
    return codec.decode_document(encoded.content)


class Products:
    """Only exact immutable reads; no fallback or mutation methods."""
    def __init__(self, documents):
        self.values = tuple(RegisteredProduct.from_document(workspace_id="workspace-a",
            descriptor_document=value, source=InlineDescriptorSource(), imported_by="fixture",
            imported_at="2026-09-16T00:00:00Z") for value in documents.values())
        self.calls = []

    def get(self, workspace, reference):
        self.calls.append((workspace, reference))
        for value in self.values:
            if value.workspace_id == workspace and value.reference == reference:
                return value
        raise LookupError("fixture product absent")


def world(test, *, selected="b", side=PlanGraphSide.DESIRED_GRAPH, configuration_changes=None):
    from control_plane_kit_servers_cpk_server import control_configuration as cpk
    from control_plane_kit_servers_cpk_local_gateway import health_transit_configuration as gateway
    a = fixture()
    authorities = {"a": a}
    for letter in ("b", "c"):
        other = fixture(letter)
        authority = SimpleNamespace(**vars(a))
        authority.health_private = other.health_private
        authority.config = with_health(a.config, public_keys=verifier_family(other.config).public_keys)
        authorities[letter] = authority
    keys = tuple(verifier_family(authorities[letter].config).public_keys[0] for letter in selected)
    workload = with_health(a.config, public_keys=keys)
    roles = core.NodeControlGraphReferenceRole
    gateway_target = replace(a.config.target,
        node_id=core.NodeControlGraphReference(roles.NODE, "gateway-a"),
        provider_socket_name=core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "http"), receiver_id="d"*32)
    gateway_config = gateway.GatewayHealthTransitConfiguration(
        gateway_target, "transit-issuer", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, keys)
    artifacts = {"workload": cpk.cpk_control_configuration_artifact(workload),
                 "gateway": gateway.gateway_health_transit_configuration_artifact(gateway_config)}
    for family, changes in (configuration_changes or {}).items():
        artifact = artifacts[family]
        raw = json.loads(artifact.content)
        # Runtime is now part of installed receiver scope, not a duplicate field.
        if "runtime_id" in changes:
            raw["target" if family == "workload" else "gateway_target"]["runtime_id"] = changes["runtime_id"]
        else:
            raw.update(changes)
        artifacts[family] = replace(artifact, content=json.dumps(raw))
    defaults = {"workload": cpk.cpk_control_configuration_artifact(a.config),
                "gateway": gateway.gateway_health_transit_configuration_artifact(
                    replace(gateway_config, public_keys=verifier_family(a.config).public_keys))}
    full = cpk.cpk_source_runtime_contract(cpk.CpkSourceVariant.CPK, defaults["workload"])
    # Explicit receiver-only projection: do not include the four DB requirements
    # or claim the legacy HttpChecks are a ready managed production topology.
    workload_contract = ProductRuntimeContract(
        sockets=BlockSockets(providers=full.sockets.providers), provider_ports=full.provider_ports,
        capabilities=full.capabilities, control_surfaces=full.control_surfaces,
        configuration_artifacts=(defaults["workload"],), public_environment=full.public_environment)
    readiness = core.WorkloadNodeControlSurfaceDescriptor(
        core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "http"), (),
        health_reads=(core.NodeHealthReadKind.READINESS,))
    gateway_own = core.ReceiverNodeControlConfiguration(gateway_target,
        core.WorkloadNodeControlSurfaceDeclaration(readiness, core.WorkloadNodeControlSurfaceDeclarationProfile.V2),
        a.config.verifiers)
    own_artifact = ConfigurationArtifact("gateway-own", "/etc/cpk/test/gateway-own.json",
        ConfigurationMediaType.JSON, core.ReceiverNodeControlConfigurationCodec().encode_bytes(gateway_own).decode(),
        ConfigurationFileMode.READ_ONLY)
    artifacts["gateway-own"] = defaults["gateway-own"] = own_artifact
    gateway_contract = ProductRuntimeContract(
        sockets=BlockSockets(providers=(ProviderSocket("http", Protocol.HTTP),)),
        provider_ports=(ProviderRuntimePort("http", 8000),), capabilities=full.capabilities,
        control_surfaces=(readiness,),
        gateway_transit=core.GatewayTransitDeclaration("http", core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2),
        configuration_artifacts=(defaults["gateway"], own_artifact),
        public_environment=(PublicStaticEnvironmentBinding("CPK_WRAPPER_CONFIGURATION_FILE", own_artifact.target_path),))
    documents = {"workload": document("cpk-receiver-model", workload_contract),
                 "gateway": document("gateway-receiver-model", gateway_contract)}
    nodes = {}
    for family, node_id in (("workload", "cpk-a"), ("gateway", "gateway-a")):
        contract = documents[family].product.runtime_contract
        reference = ProductReference.from_document(documents[family])
        nodes[node_id] = Node(node_id, BlockFamily.APPLICATION,
            BlockSpec(node_id, capabilities=contract.capabilities, control_surfaces=contract.control_surfaces,
                      gateway_transit=contract.gateway_transit), "container-server", "runtime-a", contract.sockets,
            endpoints={socket.name: Endpoint(LiteralAddress("http://" + node_id + ":8000"), socket.protocol)
                       for socket in contract.sockets.providers},
            configuration_artifacts=(artifacts[family], own_artifact) if family == "gateway" else (artifacts[family],),
            public_environment=contract.public_environment,
            metadata={"product_identity": reference.identity.key,
                      "product_descriptor_digest": reference.descriptor_sha256.value})
    nodes["connector"] = Node("connector", BlockFamily.APPLICATION, BlockSpec("connector"),
        "container-server", "runtime-a", BlockSockets())
    graph = DeploymentGraph("receiver-test", nodes=nodes,
        runtimes={"runtime-a": RuntimeRecord("runtime-a", RuntimeKind.DOCKER, tuple(nodes),
            management=core.RuntimeManagement("gateway-a", "management"))},
        public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("fixture-authority"),
            PublicIngressTarget("gateway-a", "http"), "connector", "management.example.invalid"),))
    desired = validate_graph(graph)
    current = validate_graph(DeploymentGraph("receiver-test"))
    desired.require_valid()
    current.require_valid()
    plan = compile_graph_activity_plan(current, desired)
    test.assertTrue(plan.ready_for_execution)
    activity = next(item for item in plan.activities
                    if type(item.operation) is ObserveNodeHealth and item.operation.node_id == "cpk-a")
    if side is PlanGraphSide.BASE_GRAPH:
        # Preserve the compiled graph pin, obligations and dependencies. Move the
        # same immutable snapshot to BASE and validate the explicit operation
        # with the real resolver; this is not executed historical replay.
        operation = replace(activity.operation, target=replace(activity.operation.target, graph_side=side))
        plan = replace(plan, activities=tuple(replace(item, operation=operation) if item == activity else item
                                               for item in plan.activities))
        activity = plan.activity(activity.activity_id)
        current = desired
        # The other snapshot trusts only default A. Selecting DESIRED by mistake
        # now fails the graph pin and B coverage instead of accidentally passing.
        alternate = dict(graph.nodes)
        for family, node_id in (("workload", "cpk-a"), ("gateway", "gateway-a")):
            alternate[node_id] = replace(alternate[node_id], configuration_artifacts=(defaults[family], own_artifact)
                if family == "gateway" else (defaults[family],))
        desired = validate_graph(replace(graph, nodes=alternate))
        desired.require_valid()
    projected = project_management_health_target(plan, activity.activity_id, activity.operation, current, desired)
    products = Products(documents)
    return SimpleNamespace(authorities=authorities, config=workload, gateway_config=gateway_config,
        artifacts=artifacts, defaults=defaults, documents=documents, graphs=(current, desired),
        plan=plan, projected=projected, stores=SimpleNamespace(registered_products=products),
        pins=SimpleNamespace(base_graph_id="revision-a", desired_graph_id="revision-a",
            base_realized_projection_id="projection-base", desired_realized_projection_id="projection-desired"))


def signers(value, letter):
    key = verifier_family(value.authorities[letter].config).public_keys[0]
    return tuple(RegisteredDelegationSigningKey("fixture-" + family, "workspace-a", purpose, issuer,
        key, SecretReference("secret://synthetic/never-resolved/" + family),
        "fixture", "2026-09-16T00:00:00Z", status=RegisteredDelegationSigningKeyStatus.ACTIVE,
        activated_by="fixture", activated_at="2026-09-16T00:00:00Z")
        for family, purpose, issuer in (
            ("gateway", value.gateway_config.purpose, value.gateway_config.issuer),
            ("workload", verifier_family(value.config).purpose, verifier_family(value.config).issuer)))


def gateway_token(value, letter):
    config = value.config
    authority = value.authorities[letter]
    key = verifier_family(authority.config).public_keys[0]
    request = core.ReceiverHealthReadRequest(config.target, authority.authority,
        core.NodeHealthReadKind.LIVENESS, config.declaration.identity(), "request-a")
    grant = core.DelegatedGatewayReceiverHealthReadTransitGrant(
        profile=core.DelegatedGatewayReceiverHealthReadTransitGrantProfile.V2,
        canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        purpose=value.gateway_config.purpose, issuer=value.gateway_config.issuer,
        key_id=key.key_id, attempt_id="attempt-a", gateway_target=value.gateway_config.gateway_target,
        target=request.target, authority_context=request.authority_context, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=100, not_before=100, expires_at=200, jti="transit-test")
    encoded = jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=100, nbf=100, exp=200,
        jti=grant.jti, gateway_node_health_read_transit=grant.descriptor()), authority.health_private,
        algorithm="EdDSA", headers={"kid":key.key_id, "typ":"CPK-GATEWAY-NODE-HEALTH-READ-TRANSIT+JWT"})
    return encoded.encode("ascii"), request


def gateway_self_world():
    """Actual #182 three-artifact source contract; no admission or running claim."""
    from control_plane_kit_servers_cpk_local_gateway import control_configuration as control
    from control_plane_kit_servers_cpk_local_gateway import health_relay_configuration as relay
    from control_plane_kit_servers_cpk_local_gateway import health_transit_configuration as transit
    a, b = fixture(), fixture("b")
    target = replace(a.config.target, node_id=replace(a.config.target.node_id, value="gateway-a"),
                     provider_socket_name=replace(a.config.target.provider_socket_name, value="control"))
    configured = core.ReceiverNodeControlConfiguration(target=target,
        declaration=control.gateway_control_declaration(), verifiers=a.config.verifiers)
    trusted = transit.GatewayHealthTransitConfiguration(target,
        "transit-issuer", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
        verifier_family(configured).public_keys)
    targets = relay.GatewayHealthRelayConfiguration(target, ())
    trust_artifact = transit.gateway_health_transit_configuration_artifact(trusted)
    control_artifact = control.gateway_control_configuration_artifact(configured)
    contract = relay.gateway_health_source_runtime_contract(trust_artifact,
        relay.gateway_health_relay_configuration_artifact(targets), control_artifact)
    binding = relay.gateway_health_target_binding(target_id="unrelated-alias-73", target=target,
        runtime_contract=contract, hostname="private-origin-canary")
    targets = replace(targets, targets=(binding,))
    defaults = dict(transit=trust_artifact, targets=relay.gateway_health_relay_configuration_artifact(targets),
                    control=control_artifact)
    contract = relay.gateway_health_source_runtime_contract(defaults["transit"], defaults["targets"], defaults["control"])
    doc = document("gateway-self-source", contract)
    # Selected B differs from registered default A in BOTH independently selected purposes.
    configured = with_health(configured, public_keys=verifier_family(b.config).public_keys)
    trusted = replace(trusted, public_keys=verifier_family(b.config).public_keys)
    artifacts = dict(defaults, transit=transit.gateway_health_transit_configuration_artifact(trusted),
                     control=control.gateway_control_configuration_artifact(configured))
    return SimpleNamespace(config=configured, trust=trusted, targets=targets, binding=binding,
        artifacts=artifacts, defaults=defaults, document=doc, contract=contract,
        registered=Products({"gateway":doc}), control=control, relay=relay, transit=transit)
