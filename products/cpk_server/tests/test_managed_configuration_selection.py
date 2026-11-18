"""Explicit managed startup intent must never disappear into the default mode."""
import unittest

from test_secret_provider_bootstrap import _base_environment, _server_module, _unload_server


class ManagedConfigurationSelectionTests(unittest.TestCase):
    def test_explicit_invalid_managed_configuration_refuses_instead_of_being_ignored(self):
        server = _server_module()
        self.addCleanup(_unload_server)
        values = {**_base_environment(), "CPK_MCP_PROFILE": "grandparent-read-only-v1",
            "CPK_MANAGED_VERIFICATION_CONFIGURATION_FILE": "relative-public-config.json"}
        with self.assertRaises(server.BootstrapConfigurationError):
            server.CpkServerBootstrapConfiguration.from_environment(values)
