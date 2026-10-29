"""Provider observations around one bounded initialization inspection helper."""
import copy
import hashlib
import importlib
import io
import json
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import docker
from control_plane_kit_interpreters.docker.sdk import DockerSdkImageInspection
from workspace_initialization_fixtures import initialization_inputs


class WorkspaceInitializationRuntimeTests(unittest.TestCase):
    def exercise(self, *, fault=None):
        fixture, module, plan, index, root, target, intent = initialization_inputs(self)
        controller = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_initialization_runtime")
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        state = fixture.root / "state"
        state.mkdir(mode=0o700)
        pg = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["postgres_node_id"])
        cpk_image = "sha256:" + "d" * 64
        receipt = {"schema": "cpk.root-bootstrap.receipt.v1", "phase": "acquiring",
            "pending": "initialize-workspace", "plan_digest": plan["digest"],
            "driver_image_id": plan["driver_image_id"], "engine_id": target["engine_id"],
            "labels": target["labels"], "resources": {"containers": {pg["node_id"]:
                {"id": target["postgres_container_id"]}}, "volumes": {}, "networks": {}},
            "observations": {"fresh_postgres_volumes": [item["name"] for item in pg["data_volumes"]],
                "images": {pg["node_id"]: target["postgres_image_id"], plan["cpk_node_id"]: cpk_image},
                "initialization": {"schema_acknowledged": True, "initialization": "unknown"}}}
        volumes, containers, protected = {}, {}, {}
        labels = target["labels"]
        def volume(name, resource_labels):
            resource = Mock()
            resource.id, resource.attrs = name, {"Labels": resource_labels}
            resource.remove.side_effect = lambda: volumes.pop(name)
            volumes[name] = resource
            return resource
        mounts = []
        for category in ("data_volumes", "secret_files", "configuration_files"):
            for item in pg[category]:
                volume(item["name"], labels)
                receipt["resources"]["volumes"][item["name"]] = {"id": item["name"]}
                mounts.append({"Type": "volume", "Name": item["name"], "Destination": item["target"],
                    "RW": category == "data_volumes"})
        postgres = Mock()
        postgres.id = target["postgres_container_id"]
        image_labels = {"org.opencontainers.image.revision": "1" * 40}
        postgres.attrs = {"Image": target["postgres_image_id"], "Config": {"Labels": {**image_labels, **labels}},
            "State": {"Running": True}, "Mounts": mounts}
        containers[postgres.id] = postgres
        if fault == "foreign-data":
            volumes[pg["data_volumes"][0]["name"]].attrs = {"Labels": {"foreign": "true"}}
        runtime._save(state, receipt)
        original = copy.deepcopy(receipt)
        def lookup(resources, identity):
            if identity not in resources:
                raise docker.errors.NotFound("synthetic absent resource")
            return resources[identity]
        helper = None
        with patch("docker.DockerClient") as factory, \
                patch("control_plane_kit_interpreters.docker.DockerSdkClient") as sdk_factory:
            client, sdk = factory.return_value, sdk_factory.return_value
            client.info.return_value = {"ID": target["engine_id"]}
            client.containers.list.return_value = []
            client.containers.get.side_effect = lambda identity: lookup(containers, identity)
            client.volumes.get.side_effect = lambda identity: lookup(volumes, identity)
            client.volumes.create.side_effect = lambda **kw: volume(kw["name"], kw["labels"])
            client.images.get.side_effect = lambda identity: SimpleNamespace(id=identity)
            sdk.inspect_volume.return_value = None
            sdk.inspect_image.return_value = DockerSdkImageInspection(cpk_image, (), "10001")
            def materialize(name, value, mode, *, owner_uid):
                protected[name] = SimpleNamespace(regular_file=True, uid=owner_uid, mode=0o400,
                    content_digest=hashlib.sha256(value.reveal().encode()).hexdigest())
            sdk.materialize_secret_file.side_effect = materialize
            sdk.inspect_secret_file.side_effect = protected.get
            def create(image, **options):
                nonlocal helper
                self.assertEqual(image, plan["driver_image_id"])
                self.assertEqual(options["command"][-1], "inspect-workspace-initialization")
                self.assertEqual(options["user"], "10001")
                self.assertEqual(options["network_mode"], "container:" + postgres.id)
                self.assertEqual(options["cap_drop"], ["ALL"])
                self.assertEqual(options["security_opt"], ["no-new-privileges:true"])
                self.assertNotIn("ports", options)
                writable = [m for m in options["mounts"] if not m["ReadOnly"]]
                self.assertEqual(len(writable), 1)
                self.assertEqual(writable[0]["Target"], module.PROGRESS_VOLUME_PATH)
                self.assertTrue(all(m["Type"] == "volume" for m in options["mounts"]))
                progress_volume = volumes[writable[0]["Source"]]
                progress_volume.files = {}
                saved = json.loads((state / "receipt.json").read_bytes())
                self.assertEqual(saved["pending"], original["pending"])
                self.assertEqual(saved["initialization_inspection"]["pending"], "create-initialization-helper")
                helper = Mock()
                helper.id = "e" * 64
                configured_mounts = copy.deepcopy(options["mounts"])
                for mount in configured_mounts:
                    if mount["ReadOnly"] is False:
                        del mount["ReadOnly"]  # Docker may omit a false boolean.
                helper.attrs = {"Image": image, "Config": {"Labels": {**image_labels, **labels}, "User": options["user"],
                    "Cmd": options["command"]}, "State": {"Running": False}, "HostConfig": {
                    "NetworkMode": options["network_mode"], "Privileged": False, "ReadonlyRootfs": True,
                    "CapDrop": options["cap_drop"], "SecurityOpt": options["security_opt"],
                    "Mounts": configured_mounts}, "Mounts": [{"Type": "volume", "Name": m["Source"],
                        "Destination": m["Target"], "RW": not m["ReadOnly"]} for m in options["mounts"]]}
                def prepare(path, raw):
                    self.assertFalse(helper.attrs["State"]["Running"])
                    self.assertEqual(path, module.PROGRESS_VOLUME_PATH)
                    saved = json.loads((state / "receipt.json").read_bytes())
                    self.assertEqual(saved["initialization_inspection"]["pending"], "prepare-initialization-progress")
                    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                        entries = archive.getmembers()
                        self.assertEqual(len(entries), 1)
                        entry = entries[0]
                        self.assertTrue(entry.isdir())
                        self.assertEqual((entry.name, entry.uid, entry.mode), ("private", 10001, 0o700))
                    progress_volume.files["private"] = True
                    if fault == "prepare-unknown":
                        raise TimeoutError("synthetic-private-cleanup-canary")
                    return True
                helper.put_archive.side_effect = prepare
                def start():
                    self.assertTrue(progress_volume.files["private"])
                    helper.attrs["State"]["Running"] = True
                    progress_volume.files[module.PROGRESS_PATH] = output.getvalue()
                helper.start.side_effect = start
                def wait(**kw):
                    helper.attrs["State"]["Running"] = False
                    if fault == "cleanup-unknown":
                        name = next(name for name in volumes if name not in original["resources"]["volumes"])
                        def uncertain_remove():
                            volumes.pop(name)
                            raise TimeoutError("synthetic-private-cleanup-canary")
                        volumes[name].remove.side_effect = uncertain_remove
                    return {"StatusCode": 1 if fault == "helper-failed" else 0}
                helper.wait.side_effect = wait
                progress = {"schema": module.PROGRESS_SCHEMA, "plan_digest": plan["digest"],
                    "installation_id": target["installation_id"], "operations_commit": target["operations_commit"],
                    "schema_sha256": target["schema_sha256"], "schema_acknowledged": False,
                    "pending": None, "initialization": "matching", "occurred_at": "2026-10-28T12:00:00Z"}
                if fault == "helper-failed":
                    progress.update(schema_acknowledged=True, pending="initialization",
                        initialization="unknown", occurred_at=None)
                raw = fixture.api.canonical(progress)
                output = io.BytesIO()
                with tarfile.open(fileobj=output, mode="w") as archive:
                    entry = tarfile.TarInfo("progress.json")
                    entry.uid, entry.mode, entry.size = 10001, 0o600, len(raw)
                    archive.addfile(entry, io.BytesIO(raw))
                def archive(path):
                    self.assertFalse(helper.attrs["State"]["Running"])
                    # Only the mounted volume survives stop; no archive is
                    # manufactured independently of the selected storage.
                    return [progress_volume.files[path]], {}
                helper.get_archive.side_effect = archive
                helper.remove.side_effect = lambda: containers.pop(helper.id)
                containers[helper.id] = helper
                if fault == "target-drift":
                    postgres.attrs["Image"] = "sha256:" + "f" * 64
                return helper
            client.containers.create.side_effect = create
            if fault is None:
                result = controller.inspect_initialization(plan, index, state)
                self.assertEqual(result["status"], "observed-initialization")
            else:
                with self.assertRaises(fixture.api.RootBootstrapError) as caught:
                    controller.inspect_initialization(plan, index, state)
                self.assertNotIn("synthetic-private-cleanup-canary", str(caught.exception))
                self.assertIsNone(caught.exception.__context__)
            saved = json.loads((state / "receipt.json").read_bytes())
            self.assertEqual({k: v for k, v in saved.items() if k != "initialization_inspection"}, original)
            self.assertIn(postgres.id, containers)
            self.assertTrue(set(original["resources"]["volumes"]) <= set(volumes))
            if fault == "foreign-data":
                client.containers.create.assert_not_called()
                client.volumes.create.assert_not_called()
            else:
                record = saved["initialization_inspection"]
                if fault is None:
                    self.assertEqual(record["cleanup"], "complete")
                    self.assertTrue(record["helper_removed"])
                    self.assertTrue(all(value["removed"] for value in record["temporary_volumes"].values()))
                    self.assertEqual(set(volumes), set(original["resources"]["volumes"]))
                elif fault == "cleanup-unknown":
                    self.assertEqual(record["observation"]["initialization"], "matching")
                    self.assertTrue(record["pending"].startswith("remove-initialization-volume:"))
                elif fault == "helper-failed":
                    self.assertTrue(record["observation"]["schema_acknowledged"])
                    self.assertEqual(record["observation"]["pending"], "initialization")
                    self.assertEqual(record["pending"], "inspect-workspace-initialization")
                    self.assertIn(helper.id, containers)
                    self.assertTrue(all(value["id"] in volumes for value in record["temporary_volumes"].values()))
                    self.assertEqual(record["cleanup"], "not-started")
                else:
                    helper.start.assert_not_called()
                    self.assertIn(helper.id, containers)
                    if fault == "prepare-unknown":
                        self.assertEqual(record["pending"], "prepare-initialization-progress")
                calls = client.containers.create.call_count
                before = (state / "receipt.json").read_bytes()
                if fault is None:
                    self.assertEqual(controller.inspect_initialization(plan, index, state)["status"], "retained-inspection")
                else:
                    with self.assertRaises(fixture.api.RootBootstrapError):
                        controller.inspect_initialization(plan, index, state)
                self.assertEqual(client.containers.create.call_count, calls)
                self.assertEqual((state / "receipt.json").read_bytes(), before)

    def test_matching_inspection_preserves_acquisition_and_removes_only_owned_temporary_resources(self):
        self.exercise()

    def test_matching_read_does_not_clear_uncertain_cleanup_or_authorize_another_helper(self):
        self.exercise(fault="cleanup-unknown")

    def test_failed_helper_retains_partial_progress_and_owned_storage_without_redispatch(self):
        self.exercise(fault="helper-failed")

    def test_uncertain_directory_preparation_retains_pending_without_start_or_redispatch(self):
        self.exercise(fault="prepare-unknown")

    def test_foreign_data_or_target_drift_stops_before_helper_dispatch(self):
        for fault in ("foreign-data", "target-drift"):
            with self.subTest(fault=fault):
                self.exercise(fault=fault)
