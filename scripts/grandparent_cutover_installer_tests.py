"""Actual frozen installer client/reader, synthetic file, intercepted wire only."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import grandparent_cpk_cutover as action
from grandparent_cpk_cutover_tests import DockerFrames, PUBLIC

HUMAN = "h" * 64
SETUP = "s" * 64


class Response(io.BytesIO):
    status = 200

    def getcode(self):
        return self.status


class Wire:
    def __init__(self, calls, *, change=None):
        self.calls, self.change = calls, change

    def open(self, request, *, timeout):
        path = urlsplit(request.full_url).path
        if request.full_url.startswith("http://127.0.0.1:18163/") is False:
            raise AssertionError("unexpected destination")
        self.calls.append(("wire", path))
        if path == "/health/ready":
            if request.has_header("Authorization"):
                raise AssertionError("readiness was authenticated")
            value = dict(status="ready", application="configured", stores="configured")
        else:
            if request.get_header("Authorization") != "Bearer " + HUMAN:
                raise AssertionError("unverified credential used")
            if self.change:
                self.change()
                self.change = None
            root = "/workspaces/" + action.WORKSPACE
            if path == root:
                value = dict(workspace=dict(workspace_id=action.WORKSPACE, current_graph_id=action.CURRENT,
                    desired_graph_id=action.DESIRED, desired_graph_revision=1))
            elif path == root + "/graphs/desired":
                value = dict(assigned=True, graph_id=action.DESIRED, graph_descriptor="{}")
            elif path.endswith("/attempts"):
                value = dict(items=[], next_cursor=None)
            elif path == root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1":
                value = dict(workspace_id=action.WORKSPACE, draft_id=action.DRAFT, revision=1,
                             graph_id=action.DESIRED, graph_descriptor="{}")
            else:
                raise AssertionError("unexpected route")
        return Response(json.dumps(value).encode())


class OwnerClientTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual((os.getuid(), os.getgid()), (501, 20))
        from control_plane_kit_servers_cpk_server.client import profile, transport
        self.profile, self.transport = profile, transport
        self.assertFalse(profile.__file__.startswith("/source/"))
        self.assertFalse(transport.__file__.startswith("/source/"))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "human.bearer"
        self.path.write_text(HUMAN)
        self.path.chmod(0o400)
        self.document = json.dumps([
            dict(credential=HUMAN, subject_id="cpk163-gparent-20261109-human", kind="operator", workspace_grants={}),
            dict(credential=SETUP, subject_id="cpk163-gparent-20261109-setup", kind="operator", workspace_grants={})])

    def replace_file(self):
        self.path.chmod(0o600)
        self.path.write_text(SETUP)
        self.path.chmod(0o400)

    def test_normal_consumer_uses_actual_frozen_client_before_and_after_cutover(self):
        calls = []
        api = DockerFrames(calls)
        api.objects[action.OLD]["Config"]["Env"] = [
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=" + self.document if value.startswith(
                "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=") else value
            for value in api.objects[action.OLD]["Config"]["Env"]]
        api.initial = deepcopy(api.objects[action.OLD])
        reader = action.SavedReads(self.path)
        journal = action.Journal(Path(self.tmp.name) / "receipt", "synthetic-owner-contract")
        wire = Wire(calls)
        try:
            with patch.object(self.transport, "build_opener", return_value=wire), \
                    patch("urllib.request.build_opener", return_value=wire):
                action.cutover(api, reader, journal, {"resources": {"nodes": [{
                    "node_id": action.NODE, "environment": PUBLIC}]}}, 0)
        finally:
            journal.stream.close()
        routes = {call[1] for call in calls if call[0] == "wire" and call[1] != "/health/ready"}
        root = "/workspaces/" + action.WORKSPACE
        revision = root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1"
        self.assertEqual(routes, {root, root + "/graphs/desired", revision, revision + "/attempts"})
        self.assertLess(next(i for i, c in enumerate(calls) if c[0] == "wire"),
                        calls.index(("stop", action.OLD, "SIGTERM")))

    def test_valid_setup_bearer_refuses_before_request_or_stop(self):
        self.replace_file()
        calls, reader = [], action.SavedReads(self.path)
        api = DockerFrames(calls)
        api.objects[action.OLD]["Config"]["Env"] = [
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=" + self.document if value.startswith(
                "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=") else value
            for value in api.objects[action.OLD]["Config"]["Env"]]
        api.initial = deepcopy(api.objects[action.OLD])
        journal = action.Journal(Path(self.tmp.name) / "receipt", "synthetic-owner-contract")
        try:
            with patch.object(self.transport, "build_opener", return_value=Wire(calls)):
                with self.assertRaises(action.Hold) as caught:
                    action.cutover(api, reader, journal, {"resources": {"nodes": [{
                        "node_id": action.NODE, "environment": PUBLIC}]}}, 0)
                self.assertEqual(str(caught.exception), "verification-identity")
        finally:
            journal.stream.close()
        self.assertFalse(any(c[0] in {"wire", "stop", "create", "start"} for c in calls))

    def test_each_request_uses_the_verified_bytes_even_if_source_changes(self):
        calls = []
        reader = action.SavedReads(self.path)
        reader.bind_identity(self.document)
        with patch.object(self.transport, "build_opener", return_value=Wire(calls, change=self.replace_file)):
            reader.saved()
        self.assertEqual(self.path.read_text(), SETUP)

    def test_client_plaintext_endpoint_protection_is_unchanged(self):
        with self.assertRaises(self.profile.ClientConfigurationError):
            self.profile.ClientProfile("http://private-peer:8080", action.WORKSPACE,
                {role: self.path for role in ("operator", "worker", "approver")}, Path("/not-used"))


class InstallerProcessContract(unittest.TestCase):
    def test_actual_owner_child_and_frozen_client_without_socket_or_network(self):
        self.assertEqual(os.getuid(), 0)
        result = action.run_as_owner([sys.executable, "-m", "unittest",
            "grandparent_cutover_installer_tests.OwnerClientTests", "-v"], b"")
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-8192:])
