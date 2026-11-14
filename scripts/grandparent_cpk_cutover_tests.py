"""Finite Docker and public-read frames prove maintenance ordering, not runtime.

No actual Docker client, listener, credential, Operations store or schema runs.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import grandparent_cpk_cutover as action

PRIVATE = "synthetic-private-value-never-report"
NEW = "c" * 64
PUBLIC = {"CPK_PORT": "8080", "CPK_GRAPH_TOPOLOGY_DATABASE_URL": "postgresql://private-store:5432"}


def external_container():
    mounts = [dict(Type="volume", Source=name, Target=target, ReadOnly=True,
                   VolumeOptions={"Subpath": "content"}) for name, target in action.MOUNTS.items()]
    mounts.append(dict(Type="bind", Source="/var/run/docker.sock", Target="/var/run/docker.sock", ReadOnly=False))
    config = dict(User="10001", Cmd=list(action.COMMAND), Entrypoint=None, WorkingDir="/app",
        StopSignal="SIGTERM", Labels=dict(action.LABELS),
        Env=["PATH=/usr/bin"] + [k + "=" + v for k, v in PUBLIC.items()] + [
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=" + PRIVATE, "PGPASSWORD=" + PRIVATE],
        ExposedPorts={"8080/tcp": {}})
    host = dict(NetworkMode=action.NETWORK, PortBindings=deepcopy(action.PORTS), Mounts=mounts,
        GroupAdd=["0"], LogConfig={"Type": "json-file", "Config": {"max-size": "1m", "max-file": "2"}},
        RestartPolicy={"Name": "no", "MaximumRetryCount": 0}, ReadonlyRootfs=False,
        CapAdd=None, CapDrop=None, SecurityOpt=None, Memory=0, NanoCpus=0, PidsLimit=None,
        AutoRemove=False, Privileged=False, PublishAllPorts=False)
    actual = [dict(Type="volume", Name=name, Destination=target, RW=False)
              for name, target in action.MOUNTS.items()]
    actual.append(dict(Type="bind", Source="/var/run/docker.sock", Destination="/var/run/docker.sock", RW=True))
    return dict(Id=action.OLD, Name="/" + action.NAME, Image=action.OLD_IMAGE,
        Config=config, HostConfig=host, Mounts=actual,
        State=dict(Running=True, Paused=False, Restarting=False, ExitCode=0),
        NetworkSettings=dict(Ports=deepcopy(action.PORTS), Networks={"installation": {
            "NetworkID": action.NETWORK, "Aliases": [action.NODE]}}), Path="python", Args=action.COMMAND[1:])


class DockerFrames:
    def __init__(self, calls, *, tamper=None, ambiguous_create=False):
        self.calls, self.tamper, self.ambiguous_create = calls, tamper, ambiguous_create
        self.objects = {action.OLD: external_container()}
        self.initial = deepcopy(self.objects[action.OLD])

    def info(self):
        return {"ID": action.ENGINE}

    def inspect_container(self, identity):
        self.calls.append(("inspect", identity))
        return deepcopy(self.objects[identity])

    def inspect_network(self, identity):
        return dict(Id=identity, Labels=dict(action.LABELS), Containers={k: {} for k, v in self.objects.items()
            if v["State"]["Running"] and v["NetworkSettings"]["Networks"]})

    def containers(self, **_options):
        return []

    def inspect_image(self, identity):
        config = deepcopy(self.initial["Config"])
        config["Env"] = ["PATH=/usr/bin"]
        return dict(Id=identity, Config=config, Os="linux", Architecture="amd64")

    def inspect_volume(self, name):
        return dict(Name=name, Labels=dict(action.LABELS))

    def kill(self, identity, *, signal):
        self.calls.append(("stop", identity, signal))
        self.objects[identity]["State"]["Running"] = False

    def rename(self, identity, name):
        self.calls.append(("retain", identity))
        self.objects[identity]["Name"] = "/" + name

    def create_container_from_config(self, config, *, name):
        self.calls.append(("create", name))
        self.create_config = deepcopy(config)
        if self.ambiguous_create:
            raise TimeoutError(PRIVATE)
        obj = deepcopy(self.initial)
        obj.update(Id=NEW, Name="/" + name, Image=config["Image"],
            Config={k: deepcopy(v) for k, v in config.items() if k not in ("HostConfig", "NetworkingConfig")},
            HostConfig=deepcopy(config["HostConfig"]))
        obj["State"]["Running"] = False
        obj["NetworkSettings"]["Ports"] = None
        self.objects[NEW] = obj
        if self.tamper:
            self.tamper(obj)
        return {"Id": NEW}

    def start(self, identity):
        self.calls.append(("start", identity))
        self.objects[identity]["State"]["Running"] = True
        self.objects[identity]["NetworkSettings"]["Ports"] = deepcopy(action.PORTS)

    def exec_create(self, identity, command, **_options):
        self.calls.append(("pid1-verification", identity))
        return {"Id": "verification"}

    def exec_start(self, identity):
        return b"verified\n"

    def exec_inspect(self, identity):
        return {"ExitCode": 0}


class ReadFrames:
    def __init__(self, calls, *, before_error=False, after_changed=False, readiness_error=False):
        self.calls, self.before_error = calls, before_error
        self.after_changed, self.readiness_error = after_changed, readiness_error
        self.first = True

    def saved(self):
        self.calls.append(("saved-read",))
        if self.first:
            self.first = False
            if self.before_error:
                raise action.Hold("saved-revision-mismatch")
            return b"bounded-public-revision"
        return b"changed" if self.after_changed else b"bounded-public-revision"

    def ready(self):
        self.calls.append(("readiness",))
        if self.readiness_error:
            raise RuntimeError(PRIVATE)


class CutoverTests(unittest.TestCase):
    def invoke(self, *, tamper=None, ambiguous_create=False, **read_options):
        calls = []
        api = DockerFrames(calls, tamper=tamper, ambiguous_create=ambiguous_create)
        reader = ReadFrames(calls, **read_options)
        plan = {"resources": {"nodes": [{"node_id": action.NODE, "environment": PUBLIC}]}}
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "new-attempt"
            journal = action.Journal(root, "synthetic-source-only-release")
            success, reason = False, "provider-or-transport-failure"
            try:
                action.cutover(api, reader, journal, plan, 0, sleep=lambda _seconds: None)
                success, reason = True, "complete"
            except action.Hold as error:
                reason = str(error)
            except Exception:
                reason = "provider-or-transport-failure"
            result = journal.finish(success, reason)
            artifacts = b"".join(path.read_bytes() for path in root.iterdir())
        self.assertNotIn(PRIVATE.encode(), artifacts)
        return result, api, calls

    def test_success_reads_before_outage_reuses_name_and_verifies_stopped_created_id(self):
        result, api, calls = self.invoke()
        self.assertEqual(result["status"], "verified")
        before = calls.index(("saved-read",))
        stop = calls.index(("stop", action.OLD, "SIGTERM"))
        retain = calls.index(("retain", action.OLD))
        create = calls.index(("create", action.NAME))
        inspect_new = calls.index(("inspect", NEW))
        start = calls.index(("start", NEW))
        self.assertTrue(before < stop < retain < create < inspect_new < start)
        self.assertEqual(api.objects[action.OLD]["Name"], "/" + action.BACKUP)
        self.assertFalse(api.objects[action.OLD]["State"]["Running"])
        self.assertIn("PGPASSWORD=" + PRIVATE, api.create_config["Env"])
        self.assertEqual(result["historical_inspector"], "original-id-stopped-by-maintenance")
        self.assertTrue(result["saved_revision_compared"])

    def test_pre_stop_failed_saved_revision_read_has_no_outage(self):
        result, _api, calls = self.invoke(before_error=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(any(call[0] in {"stop", "retain", "detach-alias", "create", "start"} for call in calls))
        self.assertFalse(result["schema_change_possible"])

    def test_stopped_successor_private_wiring_mismatch_never_starts(self):
        def change(value):
            value["Config"]["Env"] = [v for v in value["Config"]["Env"] if not v.startswith("PGPASSWORD=")]
        result, api, calls = self.invoke(tamper=change)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(api.objects[NEW]["State"]["Running"])
        self.assertNotIn(("start", NEW), calls)
        self.assertFalse(result["schema_change_possible"])

    def test_stopped_successor_mount_mismatch_never_starts(self):
        result, _api, calls = self.invoke(tamper=lambda value: value["Mounts"][0].update(RW=True))
        self.assertEqual(result["reason"], "actual-mounts")
        self.assertNotIn(("start", NEW), calls)

    def test_ambiguous_create_retains_pending_without_retry_or_rollback(self):
        result, _api, calls = self.invoke(ambiguous_create=True)
        self.assertEqual(result["pending"], "create-successor")
        self.assertEqual([c for c in calls if c[0] == "create"], [("create", action.NAME)])
        self.assertFalse(result["rollback"])
        self.assertIsNone(result["successor_id"])

    def test_post_start_failure_reports_possible_schema_work_and_keeps_resources(self):
        for options in ({"readiness_error": True}, {"after_changed": True}):
            with self.subTest(options=options):
                result, api, calls = self.invoke(**options)
                self.assertEqual(result["status"], "HOLD")
                self.assertTrue(result["schema_change_possible"])
                self.assertTrue(api.objects[NEW]["State"]["Running"])
                self.assertFalse(api.objects[action.OLD]["State"]["Running"])
                self.assertFalse(result["saved_revision_compared"])
                self.assertFalse(result["rollback"])

    def test_selected_public_flat_revision_shape_is_checked_before_comparison(self):
        reader = object.__new__(action.SavedReads)
        frames = {"workspace": {"workspace": dict(workspace_id=action.WORKSPACE,
            current_graph_id=action.CURRENT, desired_graph_id=action.DESIRED, desired_graph_revision=1)},
            "revision": dict(workspace_id=action.WORKSPACE, draft_id=action.DRAFT, revision=1,
                             graph_id=action.DESIRED, graph_descriptor="redacted-public-graph")}
        reader.read = lambda kind: deepcopy(frames[kind])
        self.assertEqual(json.loads(reader.saved()), [frames["workspace"], frames["revision"]])
        frames["revision"]["graph_id"] = "different-revision-graph"
        with self.assertRaises(action.Hold):
            reader.saved()

    def test_existing_attempt_is_not_resumed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "attempt"
            journal = action.Journal(root, "source-test")
            journal.finish(False, "not-executed")
            with self.assertRaises(FileExistsError):
                action.Journal(root, "source-test")
