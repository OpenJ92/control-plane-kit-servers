"""Frozen installer, exact helper capabilities, synthetic inputs/intercepted wire."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import grandparent_cpk_cutover as action
from grandparent_cpk_cutover_tests import DockerFrames, NEW, PUBLIC

HUMAN = "h" * 64
SETUP = "s" * 64


class Response(io.BytesIO):
    status = 200

    def getcode(self):
        return self.status


class Wire:
    def __init__(self, path, *, mutate=False):
        self.path, self.mutate = path, mutate

    def open(self, request, *, timeout):
        route = urlsplit(request.full_url).path
        if not request.full_url.startswith("http://127.0.0.1:18163/"):
            raise AssertionError("unexpected destination")
        if request.get_header("Authorization") != "Bearer " + HUMAN:
            raise AssertionError("unverified credential used")
        if self.mutate:
            self.path.chmod(0o600)
            self.path.write_text(SETUP)
            self.path.chmod(0o400)
            self.mutate = False
        with (self.path.parent / "wire.jsonl").open("a") as stream:
            stream.write(json.dumps(route) + "\n")
        root = "/workspaces/" + action.WORKSPACE
        if route == root:
            value = dict(workspace=dict(workspace_id=action.WORKSPACE, current_graph_id=action.CURRENT,
                desired_graph_id=action.DESIRED, desired_graph_revision=1))
        elif route == root + "/graphs/desired":
            value = dict(assigned=True, graph_id=action.DESIRED, graph_descriptor="{}")
        elif route.endswith("/attempts"):
            value = dict(items=[], next_cursor=None)
        elif route == root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1":
            value = dict(workspace_id=action.WORKSPACE, draft_id=action.DRAFT, revision=1,
                         graph_id=action.DESIRED, graph_descriptor="{}")
        else:
            raise AssertionError("unexpected route")
        return Response(json.dumps(value).encode())


class InstallerProcessContract(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.getuid(), 0)
        from control_plane_kit_servers_cpk_server.client import profile, transport
        self.assertFalse(profile.__file__.startswith("/source/"))
        self.assertFalse(transport.__file__.startswith("/source/"))
        created = action.run_as_owner([sys.executable, __file__, "--make-fixture"], b"")
        self.assertEqual(created.returncode, 0, created.stderr.decode()[-1000:])
        self.root = Path(created.stdout.decode().strip())
        self.path = self.root / "human.bearer"
        self.document = json.dumps([
            dict(credential=HUMAN, subject_id="cpk163-gparent-20261109-human", kind="operator", workspace_grants={}),
            dict(credential=SETUP, subject_id="cpk163-gparent-20261109-setup", kind="operator", workspace_grants={})])
        self.addCleanup(self.remove_fixture)

    def remove_fixture(self):
        result = action.run_as_owner([sys.executable, __file__, "--remove-fixture", str(self.root)], b"")
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-1000:])

    def reader(self, *, mutate=False):
        # Only the external wire is intercepted in the child. Production owner
        # process/pipe/client/credential and administrator verifier paths run.
        def spawn(_production_argv, pass_fds=()):
            return action.spawn_as_owner([sys.executable, __file__, "--wire-child", str(self.path),
                                          "mutate" if mutate else "stable", str(pass_fds[0])], pass_fds=pass_fds)
        reader = action.OwnerUidReads("a" * 64, spawn=spawn)
        reader.bind_identity(self.document)
        return reader

    def api(self, calls):
        api = DockerFrames(calls)
        api.objects[action.OLD]["Config"]["Env"] = [
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=" + self.document if v.startswith(
                "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=") else v
            for v in api.objects[action.OLD]["Config"]["Env"]]
        api.initial = deepcopy(api.objects[action.OLD])
        return api

    def test_normal_consumer_admin_verifier_and_real_owner_client_without_document_delivery(self):
        calls, reader = [], self.reader()
        # Readiness is a separate unauthenticated boundary, not this HTTP fixture.
        reader.ready = lambda: calls.append(("unauthenticated-readiness-frame",))
        journal = action.Journal(self.root / "maintenance", "synthetic-contract", owner=(501, 20))
        action.cutover(self.api(calls), reader, journal, {"resources": {"nodes": [{
            "node_id": action.NODE, "environment": PUBLIC}]}}, 0)
        receipt = journal.finish(True, "complete")
        self.assertTrue(receipt["saved_revision_compared"])
        root = "/workspaces/" + action.WORKSPACE
        revision = root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1"
        routes = {json.loads(line) for line in (self.root / "wire.jsonl").read_text().splitlines()}
        self.assertEqual(routes, {root, root + "/graphs/desired", revision, revision + "/attempts"})

    def test_valid_setup_bearer_refuses_before_first_request_or_stop(self):
        changed = action.run_as_owner([sys.executable, __file__, "--replace-source", str(self.path)], b"")
        self.assertEqual(changed.returncode, 0)
        calls = []
        journal = action.Journal(self.root / "maintenance", "synthetic-contract", owner=(501, 20))
        with self.assertRaises(action.Hold) as caught:
            action.cutover(self.api(calls), self.reader(), journal, {"resources": {"nodes": [{
                "node_id": action.NODE, "environment": PUBLIC}]}}, 0)
        self.assertEqual(str(caught.exception), "verification-identity")
        journal.finish(False, "verification-identity")
        self.assertFalse((self.root / "wire.jsonl").exists())
        self.assertFalse(any(c[0] in {"stop", "create", "start"} for c in calls))

    def test_each_request_uses_the_verified_bytes_if_the_source_changes(self):
        self.reader(mutate=True).saved()
        self.assertEqual(self.path.read_text(), SETUP)

    def test_production_receipt_writer_works_without_root_directory_write_permission(self):
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(self.root.stat().st_uid, 501)
        with self.assertRaises(PermissionError):
            (self.root / "root-must-not-write").touch(exist_ok=False)
        journal = action.Journal(self.root / "maintenance", "synthetic-contract", owner=(501, 20))
        journal.event("preflight-verified")
        journal.create(lambda: {"Id": NEW})
        result = journal.finish(False, "source-only")
        for path, mode in ((journal.root, 0o700), (journal.root / "events.jsonl", 0o600),
                           (journal.root / "receipt.json", 0o600)):
            metadata = path.stat()
            self.assertEqual((metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)), (501, 20, mode))
        self.assertEqual(json.loads((journal.root / "receipt.json").read_text()), result)
        created = json.loads((journal.root / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((created["successor_id"], created["pending"]), (NEW, None))

    def test_client_plaintext_endpoint_protection_is_unchanged(self):
        result = action.run_as_owner([sys.executable, __file__, "--assert-client-protection", str(self.path)], b"")
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-1000:])

    def test_direct_production_entry_missing_or_stdout_channel_never_loads_or_reports_bearer(self):
        created = action.run_as_owner([sys.executable, __file__, "--make-entry-target"], b"")
        self.assertEqual(created.returncode, 0)
        self.addCleanup(action.run_as_owner, [sys.executable, __file__, "--remove-entry-target"], b"")
        for mode, extra in (("missing", []), ("stdout", ["--admin-fd", "1"])):
            with self.subTest(mode=mode):
                direct = action.run_as_owner([sys.executable, action.__file__, "--read-saved", "a" * 64, *extra], b"")
                self.assertEqual(direct.returncode, 1)
                self.assertEqual(json.loads(direct.stdout)["reason"], "reader-channel-refused")
                self.assertNotIn(HUMAN.encode(), direct.stdout + direct.stderr)
                self.assertNotIn(SETUP.encode(), direct.stdout + direct.stderr)
                observed = action.run_as_owner([sys.executable, __file__, "--probe-entry", mode], b"")
                self.assertEqual(observed.returncode, 0, observed.stderr.decode()[-1000:])
                self.assertNotIn(HUMAN.encode(), observed.stdout + observed.stderr)

    def test_timed_out_owner_writer_is_terminated_and_reaped_without_late_write(self):
        late = self.root / "late-write"
        with self.assertRaises(action.ChildOutcomeError) as caught:
            action.run_as_owner([sys.executable, __file__, "--late-writer", str(late)], b"", timeout=0.1)
        outcome = next(x for x in caught.exception.outcomes if x["role"] == "evidence-or-owner-worker")
        self.assertTrue(outcome["reaped"])
        self.assertEqual(outcome["signal"], "sent")
        self.assertFalse(late.exists())
        with self.assertRaises(ChildProcessError):
            os.waitpid(outcome["pid"], os.WNOHANG)

    def test_inherited_duplicate_of_stdout_socket_is_not_an_admin_channel(self):
        created = action.run_as_owner([sys.executable, __file__, "--make-entry-target"], b"")
        self.assertEqual(created.returncode, 0)
        self.addCleanup(action.run_as_owner, [sys.executable, __file__, "--remove-entry-target"], b"")
        parent, routed_stdout = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        parent.settimeout(5)
        descriptor = routed_stdout.fileno()
        process = subprocess.Popen([sys.executable, action.__file__, "--read-saved", "a" * 64,
            "--admin-fd", str(descriptor)], stdin=subprocess.DEVNULL, stdout=routed_stdout,
            stderr=subprocess.PIPE, user=501, group=20, extra_groups=[], pass_fds=(descriptor,))
        process.cpk_pidfd = os.pidfd_open(process.pid)
        routed_stdout.close()
        try:
            _out, error = process.communicate(timeout=5)
            data = bytearray()
            while True:
                part = parent.recv(8192 - len(data))
                if not part:
                    break
                data.extend(part)
                self.assertLess(len(data), 8192)
            self.assertEqual(process.returncode, 1)
            self.assertEqual(json.loads(data)["reason"], "reader-channel-refused")
            self.assertNotIn(HUMAN.encode(), bytes(data) + error)
        finally:
            parent.close()
            action.close_child_handles(process)


def fixture_command():
    action.require((os.getuid(), os.getgid()) == (501, 20), "synthetic-owner")
    mode = sys.argv[1]
    if mode == "--make-fixture":
        root = Path(tempfile.mkdtemp())
        path = root / "human.bearer"
        path.write_text(HUMAN)
        path.chmod(0o400)
        print(root)
    elif mode == "--remove-fixture":
        shutil.rmtree(sys.argv[2])
    elif mode == "--replace-source":
        path = Path(sys.argv[2])
        path.chmod(0o600)
        path.write_text(SETUP)
        path.chmod(0o400)
    elif mode == "--wire-child":
        from control_plane_kit_servers_cpk_server.client import transport
        path = Path(sys.argv[2])
        with patch.object(transport, "build_opener", return_value=Wire(path, mutate=sys.argv[3] == "mutate")):
            with action.administrator_channel(int(sys.argv[4])) as channel:
                action.owner_read_batch(path, channel)
    elif mode == "--make-entry-target":
        path = Path("/credentials/human.bearer")
        with path.open("x") as stream:
            stream.write(HUMAN)
        path.chmod(0o400)
    elif mode == "--remove-entry-target":
        Path("/credentials/human.bearer").unlink()
    elif mode == "--probe-entry":
        from control_plane_kit_servers_cpk_server.client import profile, transport
        extra = [] if sys.argv[2] == "missing" else ["--admin-fd", "1"]
        sys.argv = [action.__file__, "--read-saved", "a" * 64, *extra]
        with patch.object(profile.ClientProfile, "credential") as load, \
                patch.object(transport.PublicHttpTransport, "call") as request:
            status = action.entry_point()
            if status != 1 or load.called or request.called:
                raise AssertionError("invalid channel crossed the private/request boundary")
    elif mode == "--late-writer":
        time.sleep(5)
        Path(sys.argv[2]).write_text("late")
    elif mode == "--assert-client-protection":
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile, ClientConfigurationError
        try:
            ClientProfile("http://private-peer:8080", action.WORKSPACE,
                {role: Path(sys.argv[2]) for role in ("operator", "worker", "approver")}, Path("/not-used"))
        except ClientConfigurationError:
            return
        raise AssertionError("plaintext protection lost")
    else:
        raise AssertionError("unknown synthetic fixture command")


if __name__ == "__main__":
    fixture_command()
