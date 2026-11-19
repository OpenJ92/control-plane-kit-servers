"""Complete-profile acquisition observations through the existing public API."""
import copy
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.types import Transport
from control_plane_kit_interpreters.docker.sdk import DockerSdkImageInspection, DockerSdkPublishedPort
from root_complete_fixtures import complete_input
from test_root_bootstrap import DRIVER


class CompleteRootRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.document = complete_input()

    def plan(self):
        try:
            return self.api.plan_root_bootstrap(self.document, driver_image_id=DRIVER)
        except self.api.RootBootstrapError:
            self.fail("reviewed complete-root public input is not admitted")

    def exercise(self, fault_node=None, fault=None):
        plan = self.plan()
        expected = {node: (() if port is None else (DockerSdkPublishedPort(8080, Transport.TCP, "127.0.0.1", port),))
            for node, port in (("root-a-postgres", None), ("root-a-secrets", None),
                              ("root-a-cpk", 18080), ("root-a-website", 18081))}
        with TemporaryDirectory() as directory:
            root, state = Path(directory), Path(directory) / "state"
            files = {}
            for position, reference in enumerate(plan["required_material"]):
                path = root / ("material-" + str(position))
                path.write_text("synthetic-private-material")
                path.chmod(0o400)
                files[reference] = path.name
            index = root / "index.json"
            index.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
            index.chmod(0o400)
            with patch("docker.DockerClient") as client_factory, \
                    patch("control_plane_kit_interpreters.docker.DockerSdkClient") as sdk_factory:
                client, sdk = client_factory.return_value, sdk_factory.return_value
                client.info.return_value = {"ID": "fixture-daemon"}
                client.networks.list.return_value = client.containers.list.return_value = []
                client.images.get.return_value.attrs = {"Config": {"Env": ["CPK_SECRETS_PROVIDER_ID=control-plane-kit"]}}
                client.networks.create.return_value.id = "fixture-network"
                client.volumes.create.side_effect = lambda **kw: SimpleNamespace(id=kw["name"], attrs={"Labels": kw["labels"]})
                sdk.inspect_volume.return_value = None
                sdk.inspect_image.side_effect = lambda name: DockerSdkImageInspection(
                    DRIVER if name == DRIVER else "sha256:" + "b" * 64, (name,), "0" if name == DRIVER else "10001")
                secrets, configurations, containers, started, inspected = {}, {}, {}, [], []
                def materialize(name, value, mode, *, owner_uid):
                    # End the positive observation witness at the next existing
                    # provider boundary. No fake public-setup lifecycle is built.
                    if name.endswith("-setup-plan"):
                        raise TimeoutError("fixture stop after all node observations")
                    secrets[name] = SimpleNamespace(regular_file=True, uid=owner_uid, mode=0o400,
                        content_digest=sha256(value.reveal().encode()).hexdigest())
                sdk.materialize_secret_file.side_effect = materialize
                sdk.inspect_secret_file.side_effect = secrets.get
                sdk.materialize_configuration_artifact.side_effect = lambda name, artifact: configurations.update(
                    {name: sha256(artifact.content.encode()).hexdigest()})
                sdk.configuration_artifact_digest.side_effect = configurations.get
                sdk.run_http_probe.return_value = SimpleNamespace(exit_code=0, classification="completed",
                    status_code=200, body_sha256_matches=True)
                def create(image, **options):
                    node = next(n for n in plan["resources"]["nodes"] if n["name"] == options["name"])
                    node_id = node["node_id"]
                    binding = expected[node_id]
                    self.assertEqual(options.get("ports", {}),
                        {"8080/tcp": ("127.0.0.1", binding[0].host_port)} if binding else {})
                    container = Mock()
                    container.id = node_id
                    container.attrs = {"State": {"Running": True}}
                    container.start.side_effect = lambda: started.append(node_id)
                    container.exec_run.return_value.exit_code = 0
                    containers[node_id] = container
                    return container
                client.containers.create.side_effect = create
                def inspect(node_id):
                    node = next(n for n in plan["resources"]["nodes"] if n["node_id"] == node_id)
                    ports = expected[node_id]
                    if node_id in started:
                        receipt = json.loads((state / "receipt.json").read_text())
                        self.assertEqual(receipt["pending"], "start-container:" + node_id)
                        self.assertNotIn(node_id, receipt["observations"].get("host_bindings", {}))
                        inspected.append(node_id)
                        if node_id == fault_node:
                            if fault == "missing": return None
                            if fault == "exception": raise TimeoutError("private-provider-canary")
                            if fault == "empty": ports = ()
                            if fault == "extra": ports = (*ports, DockerSdkPublishedPort(9000, Transport.TCP, "127.0.0.1", 19000))
                            if fault == "duplicate": ports = (*ports, *ports)
                            if fault == "wildcard": ports = (DockerSdkPublishedPort(8080, Transport.TCP, "0.0.0.0", ports[0].host_port),)
                            if fault == "host": ports = (DockerSdkPublishedPort(8080, Transport.TCP, "127.0.0.1", 19000),)
                            if fault == "container": ports = (DockerSdkPublishedPort(9000, Transport.TCP, "127.0.0.1", ports[0].host_port),)
                            if fault == "transport": ports = (DockerSdkPublishedPort(8080, Transport.UDP, "127.0.0.1", ports[0].host_port),)
                    return SimpleNamespace(image_id="sha256:" + "b" * 64, published_ports=ports,
                        readonly_secret_mounts=tuple(SimpleNamespace(target_path=item["target"], volume_name=item["name"])
                            for item in (*node["secret_files"], *node["configuration_files"])))
                sdk.inspect_container.side_effect = inspect
                original_stat = os.stat
                def stat(path, *args, **kwargs):
                    return SimpleNamespace(st_gid=43210) if str(path) == "/var/run/docker.sock" else original_stat(path, *args, **kwargs)
                with patch("os.stat", side_effect=stat):
                    with self.assertRaises(self.api.RootBootstrapHold) as caught:
                        self.api.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                            index_path=index, state_directory=state)
                self.assertNotIn("private-provider-canary", str(caught.exception))
                receipt_path = state / "receipt.json"
                before = receipt_path.read_bytes()
                receipt = json.loads(before)
                self.assertEqual(receipt["schema"], "cpk.root-bootstrap.receipt.v1")
                if fault_node is None:
                    self.assertEqual(set(inspected), set(expected))
                    self.assertEqual(len(started), 4)
                    self.assertTrue(receipt["pending"].startswith("materialize-file:"))
                    self.assertTrue(receipt["pending"].endswith("-setup-plan"))
                    observations = receipt["observations"]["host_bindings"]
                    self.assertEqual(observations, {node: [
                        {"container_port": p.container_port, "transport": p.transport.value,
                         "host_address": p.host_address, "host_port": p.host_port} for p in ports]
                        for node, ports in expected.items()})
                else:
                    self.assertEqual(started[-1], fault_node)
                    self.assertEqual(inspected[-1], fault_node)
                    self.assertEqual(receipt["pending"], "start-container:" + fault_node)
                    self.assertNotIn(fault_node, receipt["observations"].get("host_bindings", {}))
                calls = client.containers.create.call_count
                with self.assertRaises(self.api.RootBootstrapHold):
                    self.api.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                        index_path=root / "absent", state_directory=state)
                self.assertEqual(receipt_path.read_bytes(), before)
                self.assertEqual(client.containers.create.call_count, calls)
                self.assertEqual(sum(c.start.call_count for c in containers.values()), len(started))

    def test_complete_observations_are_recorded_only_after_all_exact_post_start_mappings(self):
        self.exercise()

    def test_api_and_website_wrong_missing_extra_duplicate_or_udp_mapping_hold_without_replay(self):
        for node in ("root-a-cpk", "root-a-website"):
            for fault in ("missing", "exception", "empty", "extra", "duplicate", "wildcard", "host", "container", "transport"):
                with self.subTest(node=node, fault=fault): self.exercise(node, fault)

    def test_postgres_and_secrets_must_have_no_published_mapping(self):
        for node in ("root-a-postgres", "root-a-secrets"):
            with self.subTest(node=node): self.exercise(node, "extra")
