"""Root launcher configuration delivery laws; no production image qualification."""
import copy
from dataclasses import replace
from hashlib import sha256
import importlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.topology import GraphDescriptorCodec
from control_plane_kit_interpreters.docker.sdk import DockerSdkImageInspection
from test_root_bootstrap import installation_input, DRIVER


def configured_input(mode=ConfigurationFileMode.READ_ONLY):
    document = installation_input()
    codec = ProductDescriptorCodec()
    for role in ("postgres", "cpk", "secrets"):
        original = codec.decode_document(document["installation"]["products"][role])
        # Inert declared product data tests delivery, not control trust or startup.
        artifact = ConfigurationArtifact("bootstrap-witness", "/etc/cpk/bootstrap-witness.json",
            ConfigurationMediaType.JSON, json.dumps({"recipient": role}), mode)
        product = replace(original.product, runtime_contract=replace(original.product.runtime_contract,
            configuration_artifacts=(artifact,)))
        document["installation"]["products"][role] = json.loads(codec.encode_document(product).content)
    return document


class RootBootstrapConfigurationTests(unittest.TestCase):
    def setUp(self):
        # Composition tests evict product modules. Resolve the current API so
        # lazy runtime imports and exception assertions share the same classes.
        self.bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")

    def planned(self, mode=ConfigurationFileMode.READ_ONLY):
        plan = self.bootstrap.plan_root_bootstrap(configured_input(mode), driver_image_id=DRIVER)
        for node in plan["resources"]["nodes"]:
            self.assertIn("configuration_files", node, "compiled configuration is missing from root delivery projection")
        return plan

    def test_complete_compiled_artifacts_project_purely_with_distinct_stable_volume_names(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("plan performed network IO")):
            plan = self.planned()
            self.assertEqual(plan, self.planned())
        graph = GraphDescriptorCodec().decode(plan["graph"])
        names = []
        for node in plan["resources"]["nodes"]:
            entries = node["configuration_files"]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            artifact, = graph.node(node["node_id"]).configuration_artifacts
            self.assertEqual(entry["artifact"], artifact.descriptor())
            self.assertEqual(entry["target"], artifact.target_path)
            self.assertEqual(entry["sha256"], sha256(artifact.content.encode()).hexdigest())
            names.append(entry["name"])
            self.assertNotIn(entry["name"], [item["name"] for item in node["secret_files"] + node["data_volumes"]])
        self.assertEqual(len(set(names)), 3)
        baseline = self.bootstrap.plan_root_bootstrap(installation_input(), driver_image_id=DRIVER)
        self.assertEqual(plan["required_material"], baseline["required_material"])

    def test_saved_projection_content_path_mode_or_digest_drift_refuses_before_acquisition(self):
        plan = self.planned()
        for field in ("content", "target_path", "file_mode", "sha256", "name"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                candidate = copy.deepcopy(plan)
                entry = candidate["resources"]["nodes"][0]["configuration_files"][0]
                if field in ("sha256", "name"): entry[field] = "substituted"
                else: entry["artifact"][field] = "substituted"
                state = Path(directory) / "state"
                with self.assertRaises(self.bootstrap.RootBootstrapError):
                    self.bootstrap.apply_root_bootstrap(candidate, expected_digest=plan["digest"], driver_image_id=DRIVER,
                        index_path=Path(directory) / "absent", state_directory=state)
                self.assertFalse((state / "receipt.json").exists())

    def exercise_refusal(self, fault, mode=ConfigurationFileMode.READ_ONLY):
        plan = self.planned(mode)
        first = plan["resources"]["nodes"][0]
        entry = first["configuration_files"][0]
        with tempfile.TemporaryDirectory() as directory:
            root, state = Path(directory), Path(directory) / "state"
            files = {}
            for index, reference in enumerate(plan["required_material"]):
                path = root / ("material-" + str(index))
                path.write_text("synthetic-private-material")
                path.chmod(0o400)
                files[reference] = path.name
            index_path = root / "index.json"
            index_path.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
            index_path.chmod(0o400)
            # Provider seams report only image/resource observations. They are not
            # alternate Docker acquisition or lifecycle implementations.
            with patch("docker.DockerClient") as client_factory, \
                 patch("control_plane_kit_interpreters.docker.DockerSdkClient") as sdk_factory:
                client, sdk = client_factory.return_value, sdk_factory.return_value
                client.info.return_value = {"ID": "fixture-daemon"}
                client.networks.list.return_value = []
                client.containers.list.return_value = []
                client.images.get.return_value.attrs = {"Config": {"Env": ["CPK_SECRETS_PROVIDER_ID=control-plane-kit"]}}
                sdk.inspect_volume.side_effect = lambda name: object() if fault == "occupied" and name == entry["name"] else None
                sdk.inspect_image.side_effect = lambda name: DockerSdkImageInspection(
                    DRIVER if name == DRIVER else "sha256:" + "b" * 64,
                    (name,), "0" if name == DRIVER else "10001")
                client.networks.create.return_value.id = "fixture-network"
                client.volumes.create.side_effect = lambda **kwargs: SimpleNamespace(
                    id=kwargs["name"], attrs={"Labels": kwargs["labels"]})
                observed = []
                def materialize(name, artifact):
                    receipt = json.loads((state / "receipt.json").read_text())
                    self.assertIsNotNone(receipt["pending"])
                    self.assertIn(name, receipt["resources"]["volumes"])
                    self.assertEqual(artifact.descriptor(), entry["artifact"])
                    observed.append((name, artifact))
                    if fault == "uncertain": raise TimeoutError("private-error-canary")
                sdk.materialize_configuration_artifact.side_effect = materialize
                sdk.configuration_artifact_digest.return_value = entry["sha256"] if fault == "mount" else "0" * 64
                client.containers.create.return_value.id = "fixture-recipient"
                sdk.inspect_container.return_value = SimpleNamespace(
                    image_id="sha256:" + "b" * 64,
                    readonly_secret_mounts=tuple(SimpleNamespace(target_path=item["target"], volume_name=item["name"])
                                                for item in first["secret_files"]))
                with self.assertRaises(self.bootstrap.RootBootstrapHold) as raised:
                    self.bootstrap.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                        index_path=index_path, state_directory=state)
                self.assertNotIn("private-error-canary", str(raised.exception))
                client.containers.create.return_value.start.assert_not_called()
                if fault == "mount":
                    client.containers.create.assert_called_once()
                    sdk.inspect_container.assert_called_once_with("fixture-recipient")
                    sdk.configuration_artifact_digest.assert_called_once_with(entry["name"])
                else:
                    client.containers.create.assert_not_called()
                if fault in ("occupied", "mode"):
                    client.networks.create.assert_not_called()
                    sdk.materialize_configuration_artifact.assert_not_called()
                else:
                    self.assertEqual(len(observed), 1)
                    receipt_path = state / "receipt.json"
                    before = receipt_path.read_bytes()
                    self.assertIsNotNone(json.loads(before)["pending"])
                    with self.assertRaises(self.bootstrap.RootBootstrapHold):
                        self.bootstrap.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                            index_path=index_path, state_directory=state)
                    self.assertEqual(before, receipt_path.read_bytes())
                    self.assertEqual(sdk.materialize_configuration_artifact.call_count, 1)
                    self.assertEqual(client.containers.create.call_count, 1 if fault == "mount" else 0)
                    client.containers.create.return_value.start.assert_not_called()

    def test_configuration_only_volume_occupancy_refuses_before_acquisition(self):
        self.exercise_refusal("occupied")

    def test_root_owned_owner_only_configuration_refuses_nonroot_before_acquisition(self):
        self.exercise_refusal("mode", ConfigurationFileMode.OWNER_READ_ONLY)

    def test_digest_mismatch_or_lost_materialization_retains_pending_without_recipient_or_retry(self):
        for fault in ("digest", "uncertain"):
            with self.subTest(fault=fault): self.exercise_refusal(fault)

    def test_missing_configuration_mount_retains_pending_without_recipient_start_or_retry(self):
        self.exercise_refusal("mount")
