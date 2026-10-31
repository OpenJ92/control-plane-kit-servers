"""Pure two-instance composition from caller-selected catalogue/public inputs.

The catalogue must contain the managed Cloudflared required-slot declaration.
The caller supplies its actual reviewed image coordinate, fresh context and
public verifiers; this example invents no image, token or verifier material.
It neither activates an ingress nor establishes deployed/runtime acceptance.
"""
from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
from control_plane_kit_core.products import ProductInstanceConfiguration, instantiate_catalog_product
from control_plane_kit_core.topology import compile_topology
from control_plane_kit_servers_cloudflared_connector import managed
from control_plane_kit_servers_cpk_server.client import ReceiverScope, prepare_receiver_configuration


def two_instances(
    *, catalog, identity, workspace_id, runtime_id, context,
    verifier_configuration, first_receiver_id, second_receiver_id,
):
    """Return a graph whose actual material precedes each ordinary instance."""
    document = catalog.lookup(identity)
    contract = document.product.runtime_contract
    if contract != managed.declared_runtime_contract():
        raise ValueError("selected product contract does not match")
    if first_receiver_id == second_receiver_id:
        raise ValueError("choose two receiver identities")
    blocks = []
    for node_id, receiver_id in (
        ("connector-a", first_receiver_id), ("connector-b", second_receiver_id),
    ):
        configured = prepare_receiver_configuration(
            workspace_id=workspace_id, runtime_id=runtime_id,
            scope=ReceiverScope(node_id, "control"), receiver_id=receiver_id,
            declaration=managed.control_declaration(), context=context,
            verifier_configuration=verifier_configuration,
        )
        artifact = managed.control_configuration_artifact(configured)
        blocks.append(instantiate_catalog_product(
            catalog, identity, role_id=node_id,
            configuration=ProductInstanceConfiguration(
                public_environment=contract.public_environment,
                configuration_artifacts=(artifact,), secret_deliveries=()),
        ))
    return compile_topology(DeploymentTopology(
        "prepared-connectors", DockerRuntime(runtime_id=runtime_id, children=tuple(blocks)),
    ))
