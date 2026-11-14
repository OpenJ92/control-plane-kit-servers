"""Finite Docker and public-read frames prove maintenance ordering, not runtime.

No actual Docker client, listener, credential, Operations store or schema runs.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

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
    def __init__(self, calls, *, tamper=None, ambiguous_create=False, ambiguous_stop=False,
                 restart_before_start=False, stuck_stop=False):
        self.calls, self.tamper, self.ambiguous_create = calls, tamper, ambiguous_create
        self.objects = {action.OLD: external_container()}
        self.initial = deepcopy(self.objects[action.OLD])
        self.ambiguous_stop, self.restart_before_start = ambiguous_stop, restart_before_start
        self.stuck_stop = stuck_stop

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
        config["Labels"] = None  # Actual Docker image-inspect no-labels shape.
        return dict(Id=identity, Config=config, Os="linux", Architecture="amd64")

    def inspect_volume(self, name):
        return dict(Name=name, Labels=dict(action.LABELS))

    def kill(self, identity, *, signal):
        self.calls.append(("stop", identity, signal))
        if not self.stuck_stop:
            self.objects[identity]["State"]["Running"] = False
        if self.ambiguous_stop:
            raise TimeoutError(PRIVATE)

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
        obj["NetworkSettings"]["Networks"]["installation"]["NetworkID"] = ""
        self.objects[NEW] = obj
        if self.tamper:
            self.tamper(obj)
        if self.restart_before_start:
            self.objects[action.OLD]["State"]["Running"] = True
        return {"Id": NEW}

    def start(self, identity):
        self.calls.append(("start", identity))
        self.objects[identity]["State"]["Running"] = True
        self.objects[identity]["NetworkSettings"]["Ports"] = deepcopy(action.PORTS)
        self.objects[identity]["NetworkSettings"]["Networks"]["installation"]["NetworkID"] = action.NETWORK

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

    def bind_identity(self, _configured_document):
        self.calls.append(("verification-identity",))

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
    def invoke(self, *, tamper=None, ambiguous_create=False, ambiguous_stop=False,
               restart_before_start=False, stuck_stop=False, journal_type=action.Journal, **read_options):
        calls = []
        api = DockerFrames(calls, tamper=tamper, ambiguous_create=ambiguous_create,
                           ambiguous_stop=ambiguous_stop, restart_before_start=restart_before_start, stuck_stop=stuck_stop)
        reader = ReadFrames(calls, **read_options)
        plan = {"resources": {"nodes": [{"node_id": action.NODE, "environment": PUBLIC}]}}
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "new-attempt"
            journal = journal_type(root, "synthetic-source-only-release")
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
            "desired": dict(assigned=True, graph_id=action.DESIRED),
            "attempts": dict(items=[], next_cursor=None),
            "revision": dict(workspace_id=action.WORKSPACE, draft_id=action.DRAFT, revision=1,
                             graph_id=action.DESIRED, graph_descriptor="redacted-public-graph")}
        reader.read = lambda kind: deepcopy(frames[kind])
        self.assertEqual(json.loads(reader.saved()), [frames[k] for k in ("workspace", "desired", "revision", "attempts")])
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

    def test_unknown_stop_never_reports_the_original_as_confirmed_running_or_retained(self):
        result, _api, calls = self.invoke(ambiguous_stop=True)
        self.assertEqual(result["original_state"], "stop-outcome-unknown")
        self.assertIsNone(result["original_stopped_retained"])
        self.assertEqual(result["pending"], "stop-original")
        self.assertEqual(result["historical_inspector"], "original-stop-unverified")
        self.assertFalse(any(c[0] in {"retain", "create", "start"} for c in calls))

    def test_created_id_persistence_failure_preserves_pending_and_never_starts(self):
        class BrokenEvidence(action.Journal):
            def event(self, kind, **updates):
                if kind == "created-id-confirmed":
                    raise OSError(PRIVATE)
                super().event(kind, **updates)
        result, _api, calls = self.invoke(journal_type=BrokenEvidence)
        self.assertEqual(result["successor_id"], NEW)
        self.assertEqual(result["pending"], "create-successor")
        self.assertNotIn(("start", NEW), calls)

    def test_stop_timeout_retains_unknown_outcome_without_escalation(self):
        with patch.object(action.time, "monotonic", side_effect=[0, 31]):
            result, _api, calls = self.invoke(stuck_stop=True)
        self.assertEqual(result["reason"], "stop-timeout")
        self.assertEqual(result["original_state"], "stop-outcome-unknown")
        self.assertIsNone(result["original_stopped_retained"])
        self.assertEqual([c for c in calls if c[0] == "stop"], [("stop", action.OLD, "SIGTERM")])

    def test_original_restart_during_comparison_keeps_successor_stopped(self):
        result, api, calls = self.invoke(restart_before_start=True)
        self.assertEqual(result["reason"], "single-writer-before-start")
        self.assertEqual(result["original_state"], "running-observed")
        self.assertFalse(api.objects[NEW]["State"]["Running"])
        self.assertNotIn(("start", NEW), calls)
        self.assertFalse(result["schema_change_possible"])

    def test_launcher_rejects_unbound_custody_or_owner_revision_before_docker(self):
        root = Path(__file__).resolve().parents[1]
        sha = lambda name: hashlib.sha256((root / "scripts" / name).read_bytes()).hexdigest()
        for defect in ("custody", "owner"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                credential = directory / "synthetic.bearer"
                credential.write_text("s" * 64)
                bootstrap = directory / "public-bootstrap.json"
                bootstrap.write_text("{}")
                for binary, content in {
                    "git": '#!/bin/sh\ncase "$*" in *status*) exit 0 ;; *) printf "%s\\n" aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ;; esac\n',
                    "docker": '#!/bin/sh\ntouch "$DOCKER_CALLED"\nexit 99\n'}.items():
                    path = directory / binary
                    path.write_text(content)
                    path.chmod(0o700)
                plan = dict(schema="cpk399.cutover-approval.v1", source_commit="a" * 40,
                    script_sha256=sha("grandparent_cpk_cutover.py"), launcher_sha256=sha("grandparent_cpk_cutover.sh"),
                    owner_sha256=sha("gateway_packaged_owner.sh"), daemon_admission_sha256=sha("docker_witness_daemon.sh"),
                    credential_source=str(credential), credential_target="/credentials/human.bearer",
                    credential_subject="cpk163-gparent-20261109-human", reader_uid=501, reader_gid=20,
                    reader_endpoint="http://127.0.0.1:18163", quiescence_confirmed=True, exposure_reviewed=True,
                    private_wiring_reuse_approved=True, verification_bearer_use_approved=True,
                    driver_image="sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80",
                    approval_reference="synthetic-no-execution")
                plan["credential_source" if defect == "custody" else "owner_sha256"] = "different-approved-input"
                action_file = directory / "action.json"
                raw = action.canonical(plan)
                action_file.write_bytes(raw)
                marker = directory / "docker-called"
                environment = {**os.environ, "PATH": str(directory) + os.pathsep + os.environ["PATH"],
                               "DOCKER_CALLED": str(marker)}
                for key in ("DOCKER_HOST", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
                    environment.pop(key, None)
                result = subprocess.run(["sh", str(root / "scripts/grandparent_cpk_cutover.sh"),
                    str(action_file), hashlib.sha256(raw).hexdigest(), str(credential), str(bootstrap)],
                    env=environment, capture_output=True, timeout=10, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertNotIn(PRIVATE, result.stdout.decode() + result.stderr.decode())

    def test_child_that_cannot_be_reaped_is_explicitly_unknown(self):
        class Unsettled:
            def __init__(self, pid):
                self.pid = pid
                self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                self.cpk_pidfd = os.open("/dev/null", os.O_RDONLY)
            def poll(self):
                return None
            def communicate(self, **_options):
                raise subprocess.TimeoutExpired("synthetic-owner", 3)
        child, terminator = Unsettled(12345), Unsettled(12346)
        try:
            with patch.object(action, "spawn_as_owner", return_value=terminator):
                outcomes = action.settle_owned_child(child, "synthetic-writer")
            self.assertTrue(all(not x["reaped"] for x in outcomes))
            self.assertEqual({x["role"] for x in outcomes}, {"synthetic-writer", "termination-helper"})
            self.assertTrue(all(x["outcome"] == "unknown-after-timeout" for x in outcomes))
        finally:
            action.close_child_handles(child)
