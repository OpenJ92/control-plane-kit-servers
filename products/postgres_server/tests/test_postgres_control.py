from pathlib import Path
import unittest

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.lifecycle import ResourcePersistence
from control_plane_kit_core.products import ProductDescriptorCodec, ProductRuntimeContractCodec
from control_plane_kit_core.secrets import SecretFileDelivery
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from postgres_control_fixtures import fixture, readiness_only

from control_plane_kit_servers_postgres_server import configuration as config


PRODUCT = Path(__file__).resolve().parents[1]


class PostgresControlContractTests(unittest.TestCase):
    def setUp(self):
        self.receiver = readiness_only(fixture().config)
        self.artifact = config.postgres_control_configuration_artifact(self.receiver)

    def test_source_contract_is_one_product_with_native_and_management_providers(self):
        self.assertEqual(
            config.decode_postgres_control_configuration(self.artifact.content.encode()),
            self.receiver,
        )
        self.assertEqual(ConfigurationArtifact.from_descriptor(self.artifact.descriptor()), self.artifact)
        contract = config.postgres_source_runtime_contract(self.artifact)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(
            {socket.name: socket.protocol for socket in contract.sockets.providers},
            {"postgres": Protocol.POSTGRES, "management": Protocol.HTTP},
        )
        self.assertEqual(
            {port.provider_socket: port.container_port for port in contract.provider_ports},
            {"postgres": 5432, "management": 8000},
        )
        self.assertEqual(contract.sockets.requirement_names(), ())
        self.assertEqual(contract.control_surfaces, (self.receiver.declaration.surface,))
        self.assertEqual(contract.configuration_artifacts, (self.artifact,))
        self.assertIn(
            PublicStaticEnvironmentBinding(
                WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT,
                config.CONTROL_PATH,
            ),
            contract.public_environment,
        )
        self.assertEqual(
            {item.name: item.value for item in contract.public_environment if item.name.startswith("POSTGRES_")},
            {
                "POSTGRES_DB": "cpk",
                "POSTGRES_USER": "cpk",
            },
        )
        (delivery,) = contract.secret_deliveries
        self.assertIs(type(delivery), SecretFileDelivery)
        self.assertEqual(delivery.target_path, config.PASSWORD_PATH)
        self.assertEqual(delivery.reference.reference_id, "secret://control-plane-kit/postgres/password")
        self.assertEqual(delivery.path_binding.environment_name, "POSTGRES_PASSWORD_FILE")
        self.assertEqual(contract.retained_data_mounts[0].target_path, config.PGDATA)
        self.assertIs(
            contract.lifecycle.data_resource("postgres-data").persistence,
            ResourcePersistence.RETAINED,
        )

    def test_historical_descriptor_remains_byte_stable_and_unpublished(self):
        descriptor = PRODUCT / "product.cpk.json"
        raw = descriptor.read_bytes()
        self.assertEqual(
            __import__("hashlib").sha256(raw).hexdigest(),
            "e2df3914cbb6eb60027e836e7f8bcd2275521d2958ef5a0e90d28117f34096c7",
        )
        historical = ProductDescriptorCodec().decode_document(raw).product.runtime_contract
        self.assertEqual(historical.sockets.provider_names(), ("postgres",))
        self.assertNotEqual(historical, config.postgres_source_runtime_contract(self.artifact))

    def test_foreign_surface_is_rejected_before_contract_composition(self):
        foreign = core.NodeControlGraphReference(
            core.NodeControlGraphReferenceRole.PROVIDER_SOCKET,
            "postgres",
        )
        receiver = self.receiver
        from dataclasses import replace
        selected = replace(
            receiver,
            target=replace(receiver.target, provider_socket_name=foreign),
            declaration=replace(
                receiver.declaration,
                surface=replace(receiver.declaration.surface, provider_socket_name=foreign),
            ),
        )
        with self.assertRaises(config.PostgresConfigurationError):
            config.postgres_control_configuration_artifact(selected)


if __name__ == "__main__":
    unittest.main()
