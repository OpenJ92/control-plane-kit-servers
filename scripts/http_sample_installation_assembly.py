"""Pure full-child source assembly diagnostic, never approved-run evidence.

Reuses the owning complete-installation fixture and production composition. No
Operations rows, provider responses, invocations, credentials or runs are made.
Only the CPK child's original HTTP checks receive sample trust in this slice.
"""
from dataclasses import replace
import json
from pathlib import Path
import importlib
import os
from tempfile import TemporaryDirectory

import control_plane_kit_core as core
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleReceiverConfiguration, HttpVerificationSampleVerifierConfiguration,
    HttpVerificationSampleCheckBinding,
)
from control_plane_kit_core.http_verification_samples import http_verification_check_digest
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.planning import WaitForHealthy, ReviewChange
from control_plane_kit_core.topology import compile_topology, validate_graph, DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_servers_cpk_server import control_configuration as cpk
from control_plane_kit_servers_cpk_server.installation import compose_docker_cpk_installation
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    gateway_http_sample_trust_artifact, gateway_http_sample_declared_runtime_contract,
    CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH,
)
from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleTrust
from test_installation_management import InstallationManagementTests


def assemble():
    """Return original installation inputs, full graph and exact sample plan."""
    fixture = InstallationManagementTests()
    fixture.setUp()
    original = fixture.installation(website=fixture.managed_website())
    baseline = fixture.graph(original)
    control = fixture.receiver(baseline.node(original.cpk_node_id))
    checks = original.cpk_product.product.runtime_contract.verification.checks
    configuration = HttpVerificationSampleReceiverConfiguration(control.target,
        control.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
            "parent-cpk", (fixture.keys["workload"],)), tuple(
                HttpVerificationSampleCheckBinding(check.check_id, http_verification_check_digest(check))
                for check in checks))
    artifact = cpk.cpk_http_sample_configuration_artifact(control, configuration)
    control_artifact, = original.cpk_product.product.runtime_contract.configuration_artifacts
    selected = replace(original, cpk_product=fixture.codec.encode_document(replace(
        original.cpk_product.product, runtime_contract=cpk.cpk_source_runtime_contract(
            cpk.CpkSourceVariant.DOCKER_CLOUDFLARE, control_artifact, sample_artifact=artifact))))
    topology = compose_docker_cpk_installation(selected)
    graph = compile_topology(topology)
    # The installation owner currently selects the health-only gateway
    # declaration. This source fixture explicitly extends its graph/document
    # after composition; it does not loosen that public owner's admission.
    gateway_id = selected.management.runtime_management.gateway_node_id
    gateway = graph.node(gateway_id)
    document = fixture.codec.encode_document(replace(selected.management.gateway_product.product,
        runtime_contract=gateway_http_sample_declared_runtime_contract()))
    reference = ProductReference.from_document(document)
    trust = gateway_http_sample_trust_artifact(GatewayHttpSampleTrust(
        selected.management.gateway_control.target, "parent-cpk", (fixture.keys["transit"],)))
    gateway = replace(gateway, configuration_artifacts=gateway.configuration_artifacts + (trust,),
        public_environment=gateway.public_environment + (PublicStaticEnvironmentBinding(
            CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH),),
        metadata={**gateway.metadata, "product_identity": reference.identity.key,
            "product_descriptor_digest": reference.descriptor_sha256.value})
    graph = graph.update_node(gateway)
    # Match the actual descriptor boundary before the owning pure compiler.
    graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(graph))
    pair = validate_graph(DeploymentGraph(graph.name)), validate_graph(graph)
    for validated in pair:
        validated.require_valid()
    plan = core.compile_http_sample_bootstrap_activity_plan(*pair)
    return fixture, original, baseline, graph, document, plan


def main():
    for name, root in (("control_plane_kit_core", "/reviewed-http-sample/core/src"),
                       ("control_plane_kit_operations", "/reviewed-http-sample/operations/src"),
                       ("control_plane_kit_interpreters", "/reviewed-http-sample/interpreters/src")):
        assert Path(importlib.import_module(name).__file__).resolve().is_relative_to(root)
    # Existing commissioning fixture writes only its owned temporary directory.
    previous = Path.cwd()
    try:
        with TemporaryDirectory(prefix="cpk181-full-child-") as directory:
            os.chdir(directory)
            fixture, original, baseline, graph, gateway_document, plan = assemble()
    finally:
        os.chdir(previous)
    before, child = baseline.node(original.cpk_node_id), graph.node(original.cpk_node_id)
    assert child.sockets == before.sockets
    assert child.socket_environment == before.socket_environment
    assert child.secret_deliveries == before.secret_deliveries
    assert child.runtime_authority_deliveries == before.runtime_authority_deliveries
    assert child.block_spec.verification == before.block_spec.verification
    checks = child.block_spec.verification.checks
    assert tuple(check.check_id for check in checks) == ("live", "ready")
    requirements = {socket.name for socket in child.sockets.requirements}
    assert requirements == {"activity-history-store", "graph-topology-store", "observer-state-store", "workplace-store"}
    assert {(edge.provider_role, edge.provider_socket, edge.requirement_socket)
        for edge in graph.edges.values() if edge.consumer_role == child.node_id} == {
            (original.postgres_node_id, "postgres", requirement) for requirement in requirements}
    password, = (delivery for delivery in child.secret_deliveries
        if getattr(delivery, "environment_name", None) == "PGPASSWORD")
    assert password.reference == original.postgres_password
    assert password.intent.value == "postgres.password"
    waits = [dict(node_id=activity.operation.target.node_id,
        checks=[dict(check_id=check.check_id, kind=type(check).__name__)
            for check in graph.node(activity.operation.target.node_id).block_spec.verification.checks])
        for activity in plan.activities if type(activity.operation) is WaitForHealthy]
    reviews = [dict(target_kind=type(activity.operation.target.subject).__name__,
        node_id=getattr(activity.operation.target.subject, "node_id", None), reason=activity.operation.reason.value)
        for activity in plan.activities
        if type(activity.operation) is ReviewChange]
    print(json.dumps(dict(evidence="pure-full-child-assembly-only", graph_valid=True,
        cpk_original_checks=[check.check_id for check in checks], postgres_requirements=sorted(requirements),
        postgres_password="unresolved-original-reference", node_count=len(graph.nodes),
        ingress_count=len(graph.public_ingresses), plan_ready=plan.ready_for_execution,
        ordinary_waits=waits, reviews=reviews, operations_commands=0, provider_calls=0,
        gateway_extension="explicit-source-fixture-after-normal-installation-composition",
        completed_run=False), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
