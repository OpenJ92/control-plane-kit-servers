"""#180 receiving configuration, explicit management port and real process loading."""
import builtins
from dataclasses import replace
import importlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from fastapi.testclient import TestClient
from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.products import ProductRuntimeContractCodec, ProductDescriptorCodec
from health_relay_fixtures import World

PACKAGE = "control_plane_kit_servers_cpk_local_gateway"
TRUST_PATH = "/etc/cpk/gateway/health-transit.json"
TARGET_PATH = "/etc/cpk/gateway/health-targets.json"


class HealthRelayConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.world = World()

    def api(self):
        name = PACKAGE + ".health_relay_configuration"
        self.assertIsNotNone(importlib.util.find_spec(name), "#180 receiving configuration is missing")
        return importlib.import_module(name)

    def configuration(self, api):
        w = self.world
        binding = api.gateway_health_target_binding(target_id="database-management", target=w.target,
            runtime_id=w.runtime, runtime_contract=w.contract, hostname="wrapped-db")
        return api.GatewayHealthRelayConfiguration(workspace_id=w.target.workspace_id,
            gateway_node_id=w.transit.gateway, runtime_id=w.runtime, targets=(binding,))

    def artifacts(self, api):
        trust_api, _ = self.world.transit.api()
        return (self.world.transit.artifact(trust_api),
                api.gateway_health_relay_configuration_artifact(self.configuration(api)))

    def refused(self, api, action):
        with self.assertRaises(api.GatewayHealthRelayConfigurationError) as caught:
            action()
        self.assertLess(len(str(caught.exception)), 100)
        self.assertEqual(vars(caught.exception), {})
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("private-marker", str(caught.exception))

    def test_projection_selects_edge_free_control_port_not_application_or_postgres(self):
        w = self.world
        projected = w.projection()  # Exercise existing owner before missing-interface guard.
        api = self.api()
        self.assertFalse(projected.graph.edges)
        target = replace(w.target, provider_socket_name=projected.projected.workload_surface.provider_socket_name)
        binding = api.gateway_health_target_binding(target_id="database-management", target=target,
            runtime_id=w.runtime, runtime_contract=w.contract, hostname="wrapped-db")
        self.assertEqual(binding.target, target)
        self.assertEqual(binding.runtime_id, w.runtime)
        self.assertEqual(binding.declaration, w.declaration)
        self.assertEqual(binding.origin, "http://wrapped-db:8087")
        for socket in ("application", "sql", "absent"):
            candidate = replace(target, provider_socket_name=replace(target.provider_socket_name, value=socket))
            self.refused(api, lambda:api.gateway_health_target_binding(target_id="database-management", target=candidate,
                runtime_id=w.runtime, runtime_contract=w.contract, hostname="wrapped-db"))
        # A forged nominal object must be revalidated at this public boundary.
        ambiguous = replace(w.contract)
        object.__setattr__(ambiguous, "provider_ports", (*ambiguous.provider_ports, ambiguous.provider_ports[-1]))
        self.refused(api, lambda:api.gateway_health_target_binding(target_id="database-management", target=target,
            runtime_id=w.runtime, runtime_contract=ambiguous, hostname="wrapped-db"))
        for hostname in ("http://private-marker", "user@host", "host/path", "host?query", "host#fragment", "host\r\nX: x"):
            self.refused(api, lambda:api.gateway_health_target_binding(target_id="database-management", target=target,
                runtime_id=w.runtime, runtime_contract=w.contract, hostname=hostname))

    def test_configuration_roundtrip_closed_bounded_and_duplicate_target_refusal(self):
        api = self.api()
        value = self.configuration(api)
        artifact = api.gateway_health_relay_configuration_artifact(value)
        self.assertEqual((artifact.artifact_id, artifact.target_path), ("gateway-health-targets", TARGET_PATH))
        self.assertIs(artifact.file_mode, ConfigurationFileMode.READ_ONLY)
        self.assertIs(artifact.media_type, ConfigurationMediaType.JSON)
        self.assertEqual(api.decode_gateway_health_relay_configuration(artifact.content.encode()), value)
        self.assertNotIn("wrapped-db", repr(value))
        self.refused(api, lambda:replace(value, targets=(*value.targets, value.targets[0])))
        duplicate_identity = replace(value.targets[0], target_id="other-alias")
        self.refused(api, lambda:replace(value, targets=(*value.targets, duplicate_identity)))
        for raw in (b"x"*131073, b'{"profile":"x","profile":"y"}', b'{"profile":NaN}',
                    b"["*40+b"]"*40, b"{}", b"private-marker"):
            self.refused(api, lambda:api.decode_gateway_health_relay_configuration(raw))

    def test_source_contract_exact_slots_port_and_transit_without_rewriting_historical_descriptor(self):
        api = self.api()
        trust, targets = self.artifacts(api)
        contract = api.gateway_health_source_runtime_contract(trust, targets)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual({item.artifact_id:item for item in contract.configuration_artifacts},
                         {trust.artifact_id:trust, targets.artifact_id:targets})
        self.assertEqual(contract.gateway_transit.provider_socket_name, "control")
        self.assertEqual(contract.gateway_transit.protocol.value, "gateway-node-health-read-transit.v1")
        self.assertEqual({port.provider_socket:port.container_port for port in contract.provider_ports}, {"control":8000})
        historical = Path(__file__).resolve().parents[1] / "product.cpk.json"
        document = ProductDescriptorCodec().decode_document(historical.read_bytes())
        self.assertIsNone(document.product.runtime_contract.gateway_transit)
        self.assertEqual(document.product.runtime_contract.configuration_artifacts, ())
        self.assertEqual(document.product.image.digest,
            "sha256:b7cca6d0556eb5b68ef92386bc9b8e198ee62ccf10a7304b076a07283f821792")
        bad_config = replace(self.configuration(api), gateway_node_id=replace(self.world.transit.gateway, value="other-gateway"))
        other = api.gateway_health_relay_configuration_artifact(bad_config)
        self.refused(api, lambda:api.gateway_health_source_runtime_contract(trust, other))
        for bad in (replace(targets, target_path="/tmp/private-marker.json"),
                    replace(targets, file_mode=ConfigurationFileMode.OWNER_READ_ONLY)):
            self.refused(api, lambda:api.gateway_health_source_runtime_contract(trust, bad))

    def run_main(self, files, environment):
        server = importlib.import_module(PACKAGE + ".server")
        actual_open = builtins.open
        opened = []
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for name, raw in files.items():
                path = Path(directory) / Path(name).name
                path.write_bytes(raw)
                paths[name] = path
            def selected_open(path, *args, **kwargs):
                name = str(path)
                if name in (TRUST_PATH, TARGET_PATH):
                    opened.append(name)
                    if name not in paths:
                        raise FileNotFoundError("private-marker")
                    return actual_open(paths[name], *args, **kwargs)
                return actual_open(path, *args, **kwargs)
            # Patch only filesystem path placement and process serving. The actual
            # main/loader/config decoder/app construction still execute in CI.
            with patch.dict("os.environ", environment, clear=True), patch("builtins.open", selected_open), \
                    patch("io.open", selected_open), patch.object(server.uvicorn, "run") as serve, \
                    redirect_stdout(output), redirect_stderr(output):
                exit_code = None
                try:
                    exit_code = server.main()
                except SystemExit as error:
                    exit_code = error.code
            return serve, opened, output.getvalue(), exit_code

    def test_actual_main_loads_selected_files_health_only_and_fixed_port(self):
        api = self.api()
        trust_api, _ = self.world.transit.api()
        # Selected B is deliberately different from existing fixture default A.
        trust = self.world.transit.artifact(trust_api, public_keys=(self.world.transit.key_b,))
        _, targets = self.artifacts(api)
        files = {TRUST_PATH:trust.content.encode(), TARGET_PATH:targets.content.encode()}
        serve, opened, output, _ = self.run_main(files, {})
        serve.assert_called_once()
        self.assertEqual(set(opened), {TRUST_PATH, TARGET_PATH})
        self.assertEqual(serve.call_args.kwargs["port"], 8000)
        app = serve.call_args.args[0]
        with TestClient(app) as client:
            self.assertEqual(client.post("/cpk/probes", content=b"private-marker").status_code, 404)
            self.assertEqual(client.get("/health/live").json(), {"status":"live"})
            request = self.world.request
            wrong, _ = self.world.pair(request)
            now = int(time.time())
            correct = self.world.transit.token(self.world.transit.grant(request, key_id=self.world.transit.key_b.key_id,
                issued_at=now, not_before=now, expires_at=now+100),
                private=self.world.transit.private_b).decode()
            # A structurally wrong workload token distinguishes transit acceptance
            # without making any outbound request from this loader witness.
            envelope = self.world.envelope(workload="not-a-workload-token")
            self.assertEqual(client.post("/cpk/health/readiness", json=envelope,
                headers={"Authorization":"Bearer " + wrong}).status_code, 401)
            self.assertEqual(client.post("/cpk/health/readiness", json=envelope,
                headers={"Authorization":"Bearer " + correct}).status_code, 403)
        self.assertNotIn("private-marker", output)
        environment = {"PORT":"8000", "CPK_GATEWAY_PROBE_VERIFIER":"ed25519",
            "CPK_GATEWAY_PROBE_VERIFICATION_KEYS_JSON":json.dumps({"probe-key":self.world.transit.key_a.public_key_pem}),
            "CPK_GATEWAY_PROBE_ISSUER":"probe-issuer", "CPK_GATEWAY_PROBE_AUDIENCE":"probe-audience",
            "CPK_GATEWAY_PROBE_NODE_ID":"gateway-a"}
        serve, _, _, _ = self.run_main(files, environment)
        serve.assert_called_once()
        with TestClient(serve.call_args.args[0]) as client:
            self.assertEqual(client.post("/cpk/probes", content=b"{}").status_code, 401)
            self.assertEqual(client.post("/cpk/health/readiness", json=self.world.envelope()).status_code, 401)
        for environment in ({"PORT":"8088"}, {"PORT":"invalid"}, {"CPK_GATEWAY_PROBE_ISSUER":"partial"}):
            serve, _, output, _ = self.run_main(files, environment)
            serve.assert_not_called()
            self.assertNotIn("private-marker", output)
        for bad_files in ({TRUST_PATH:files[TRUST_PATH]}, {TARGET_PATH:files[TARGET_PATH]},
                          files | {TRUST_PATH:b"private-marker"}, files | {TARGET_PATH:b"x"*131073}):
            serve, _, output, _ = self.run_main(bad_files, {})
            serve.assert_not_called()
            self.assertNotIn("private-marker", output)
