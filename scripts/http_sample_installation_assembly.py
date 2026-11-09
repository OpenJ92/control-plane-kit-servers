"""Pure full-child source assembly diagnostic, never approved-run evidence.

Reuses the owning complete-installation fixture and production composition. No
Operations rows, provider responses, invocations, credentials or runs are made.
Both CPK and Secrets retain their full original HTTP checks in this slice.
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
from control_plane_kit_core.products import ProductReference, OciImageReference
from control_plane_kit_core.secret_selections import SecretVersionSelection, secret_selections_from_descriptor
from control_plane_kit_core.topology.secret_selection import carry_forward_secret_selections
from control_plane_kit_core.planning import WaitForHealthy, ReviewChange
from control_plane_kit_core.topology import compile_topology, validate_graph, DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_servers_cpk_server import control_configuration as cpk
from control_plane_kit_servers_secrets_server import configuration as secrets
from control_plane_kit_servers_cpk_server.installation import (
    compose_docker_cpk_installation, installation_secret_version_choices,
)
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    gateway_http_sample_trust_artifact, gateway_http_sample_declared_runtime_contract,
    CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH,
)
from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleTrust
from test_installation_management import InstallationManagementTests
from receiver_acceptance_material import AuthoredMaterial
from http_sample_image_inputs import require_images, image_options


def assemble(*, commissioning_directory=None, postgres_image=None, secret_versions=None, images=None):
    """Return original installation inputs, full graph and exact sample plan."""
    if images is not None:
        images = require_images(images)
        if postgres_image is not None:
            raise ValueError("source assembly image inputs conflict")
    fixture = InstallationManagementTests()
    fixture.commissioning_directory = commissioning_directory
    fixture.setUp()
    # Synthetic source inputs only. An actual isolated run must still admit
    # matching public keys/references through normal registration/activation.
    fixture.signing_material = AuthoredMaterial()
    fixture.keys = fixture.signing_material.public
    fixture.sample_signing_material = AuthoredMaterial()
    fixture.sample_signing_material.public = {name: replace(key, key_id="sample-" + name)
        for name, key in fixture.sample_signing_material.public.items()}
    fixture.trust = replace(fixture.trust, public_keys=(fixture.keys["transit"],))
    original = fixture.installation(website=fixture.managed_website())
    if images is not None:
        def select(document, role):
            return fixture.codec.encode_document(replace(document.product, image=images[role]))
        connector = select(original.connector_product, "connector")
        management = replace(original.management,
            gateway_product=select(original.management.gateway_product, "gateway"), connector_product=connector)
        original = replace(original,
            cpk_product=select(original.cpk_product, "cpk"),
            postgres_product=select(original.postgres_product, "postgres"),
            secrets_product=select(original.secrets_product, "secrets"),
            website=replace(original.website, image=images["website"], connector_product=connector),
            connector_product=connector, management=management)
    elif postgres_image is not None:
        if type(postgres_image) is not OciImageReference:
            raise ValueError("source assembly requires an explicit immutable PostgreSQL image")
        original = replace(original, postgres_product=fixture.codec.encode_document(replace(
            original.postgres_product.product, image=postgres_image)))
    elif secret_versions is not None:
        raise ValueError("selected source assembly requires an explicit PostgreSQL image")
    baseline = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(fixture.graph(original)))
    control = fixture.receiver(baseline.node(original.cpk_node_id))
    checks = original.cpk_product.product.runtime_contract.verification.checks
    configuration = HttpVerificationSampleReceiverConfiguration(control.target,
        control.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
            "parent-cpk", (fixture.sample_signing_material.public["workload"],)), tuple(
                HttpVerificationSampleCheckBinding(check.check_id, http_verification_check_digest(check))
                for check in checks))
    artifact = cpk.cpk_http_sample_configuration_artifact(control, configuration)
    control_artifact, = original.cpk_product.product.runtime_contract.configuration_artifacts
    selected = replace(original, cpk_product=fixture.codec.encode_document(replace(
        original.cpk_product.product, runtime_contract=cpk.cpk_source_runtime_contract(
            cpk.CpkSourceVariant.DOCKER_CLOUDFLARE, control_artifact, sample_artifact=artifact))))
    secrets_control = fixture.receiver(baseline.node(original.secrets_node_id))
    companion = secrets.secrets_full_http_sample_configuration_artifact(secrets_control,
        HttpVerificationSampleVerifierConfiguration(core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
            "parent-cpk", (fixture.sample_signing_material.public["workload"],)))
    secrets_control_artifact, = original.secrets_product.product.runtime_contract.configuration_artifacts
    selected = replace(selected, secrets_product=fixture.codec.encode_document(replace(
        original.secrets_product.product, runtime_contract=secrets.secrets_source_runtime_contract(
            secrets_control_artifact, sample_artifact=companion))))
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
        selected.management.gateway_control.target, "parent-cpk", (fixture.sample_signing_material.public["transit"],)))
    gateway = replace(gateway, configuration_artifacts=gateway.configuration_artifacts + (trust,),
        public_environment=gateway.public_environment + (PublicStaticEnvironmentBinding(
            CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH),),
        metadata={**gateway.metadata, "product_identity": reference.identity.key,
            "product_descriptor_digest": reference.descriptor_sha256.value})
    graph = graph.update_node(gateway)
    # Exact documents for normal product import in the SAME commissioning
    # lifetime. The graph's explicit gateway extension supersedes its original.
    fixture.product_documents = tuple(
        document if child.block_id == gateway_id else child.implementation.document
        for child in topology.root.children if hasattr(child, "implementation"))
    assert {ProductReference.from_document(entry).descriptor_sha256.value
        for entry in fixture.product_documents} == {
            node.metadata["product_descriptor_digest"] for node in graph.nodes.values()}
    # Match the actual descriptor boundary before the owning pure compiler.
    graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(graph))
    fixture.secret_version_choices = None
    if secret_versions is not None:
        fixture.secret_version_choices = installation_secret_version_choices(selected, secret_versions)
        graph = carry_forward_secret_selections(DeploymentGraph(graph.name), graph,
            {node: secret_selections_from_descriptor(choices)
                for node, choices in fixture.secret_version_choices.items()})
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
    options = image_options(os.environ)
    postgres_image = options["images"]["postgres"] if "images" in options else options["postgres_image"]
    has_images = options.get("images") is not None or options.get("postgres_image") is not None
    try:
        with TemporaryDirectory(prefix="cpk181-full-child-") as directory:
            os.chdir(directory)
            custody = Path(directory) / "commissioning"
            custody.mkdir(mode=0o700)
            fixture, original, baseline, graph, gateway_document, plan = assemble(
                commissioning_directory=custody, **options)
            if has_images:
                # Explicit fixture metadata only, never provider-admitted IDs.
                uses = sorted({(entry.reference, entry.intent) for node in graph.nodes.values()
                    for entry in node.secret_selections}, key=lambda pair: (pair[0].reference_id, pair[1].value))
                versions = tuple(SecretVersionSelection(reference, intent, "synthetic-source-version-" + str(index))
                    for index, (reference, intent) in enumerate(uses))
                fixture, original, baseline, graph, gateway_document, plan = assemble(
                    commissioning_directory=custody, secret_versions=versions, **options)
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
    postgres = graph.node(original.postgres_node_id)
    check, = postgres.block_spec.verification.checks
    assert postgres.block_spec.verification == baseline.node(postgres.node_id).block_spec.verification
    assert check.check_id == "installation-postgres-ready"
    assert check.authentication.password_reference == original.postgres_password
    postgres_selection, = (value for value in postgres.secret_selections
        if value.reference == original.postgres_password)
    cpk_selection, = (value for value in child.secret_selections
        if value.reference == original.postgres_password)
    assert postgres_selection == cpk_selection
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
        secrets_original_checks=[check.check_id for check in graph.node(original.secrets_node_id).block_spec.verification.checks],
        signing_material="synthetic-held-through-fixture-lifetime-unregistered",
        postgres_password=("unresolved-original-reference" if postgres_image is None
            else "explicit-synthetic-version-not-provider-admitted"),
        postgres_image=(None if postgres_image is None else postgres_image.execution_reference),
        selected_images=(None if "images" not in options else
            {role:value.execution_reference for role, value in options["images"].items()}),
        postgres_product_reference={"identity": postgres.metadata["product_identity"],
            "descriptor_sha256": postgres.metadata["product_descriptor_digest"]},
        postgres_password_selection=postgres_selection.descriptor(),
        secret_selection_nodes=(0 if fixture.secret_version_choices is None else len(fixture.secret_version_choices)),
        node_count=len(graph.nodes),
        ingress_count=len(graph.public_ingresses), plan_ready=plan.ready_for_execution,
        ordinary_waits=waits, reviews=reviews, operations_commands=0, provider_calls=0,
        gateway_extension="explicit-source-fixture-after-normal-installation-composition",
        completed_run=False), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
