"""Frozen installer, exact helper capabilities, synthetic inputs/intercepted wire."""
from copy import deepcopy
from contextlib import redirect_stderr
import hashlib
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
from urllib.error import HTTPError

import grandparent_cpk_cutover as action
from grandparent_cpk_cutover_tests import DockerFrames, NEW, PUBLIC

HUMAN = "h" * 64
SETUP = "s" * 64
SYNTHETIC_GRAPH = dict(name=action.WORKSPACE, nodes={"node-" + str(i): {"count": i} for i in range(8)})


class Response(io.BytesIO):
    status = 200

    def getcode(self):
        return self.status


class Wire:
    def __init__(self, path, *, mutate=False, diagnosis=None):
        self.path, self.mutate, self.diagnosis = path, mutate, diagnosis

    def open(self, request, *, timeout):
        parts = urlsplit(request.full_url)
        route = parts.path
        if not request.full_url.startswith("http://127.0.0.1:18163/"):
            raise AssertionError("unexpected destination")
        if request.get_method() != "GET" or request.data is not None:
            raise AssertionError("verification crossed read-only HTTP boundary")
        if request.get_header("Authorization") != "Bearer " + HUMAN:
            raise AssertionError("unverified credential used")
        if self.mutate:
            self.path.chmod(0o600)
            self.path.write_text(SETUP)
            self.path.chmod(0o400)
            self.mutate = False
        with (self.path.parent / "wire.jsonl").open("a") as stream:
            stream.write(json.dumps(route) + "\n")
        if self.diagnosis:
            with (self.path.parent / "queries.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(path=route, query=parts.query)) + "\n")
        if self.diagnosis == "oversize":
            from control_plane_kit_servers_cpk_server.client.transport import MAXIMUM_RESPONSE_BYTES
            return Response(b"x" * (MAXIMUM_RESPONSE_BYTES + 1))
        if self.diagnosis == "authorization":
            raise HTTPError(request.full_url, 403, "synthetic", {}, io.BytesIO(b"private-response-never-report"))
        from control_plane_kit_operations.read_services.workspace_graph import _redact_graph_descriptor
        from control_plane_kit_operations.read_services.workspace_graph import GraphPointerReadModel
        from grandparent_saved_read import CURRENT_PROJECTION, DESIRED_PROJECTION
        graph = _redact_graph_descriptor(SYNTHETIC_GRAPH)
        pointer = GraphPointerReadModel("desired", True, graph_id=action.DESIRED, authored_graph_id=action.DESIRED,
            realized_projection_id=DESIRED_PROJECTION, version=1, graph_name=action.WORKSPACE, graph_descriptor=graph).descriptor()
        current = GraphPointerReadModel("current", True, graph_id=action.CURRENT, authored_graph_id=action.CURRENT,
            realized_projection_id=CURRENT_PROJECTION).descriptor()
        root = "/workspaces/" + action.WORKSPACE
        if route == root:
            value = dict(workspace=dict(workspace_id=action.WORKSPACE, current_graph_id=action.CURRENT,
                desired_graph_id=action.DESIRED, desired_graph_revision=1, desired_realized_projection_id=DESIRED_PROJECTION,
                current_realized_projection_id=CURRENT_PROJECTION), desired_graph=pointer, current_graph=current)
        elif route == root + "/graphs/desired":
            value = pointer
        elif route.endswith("/attempts"):
            # Actual installed query decoding and owner page projection in every
            # successful fixture; no query-stripping or string-graph shortcut.
            from control_plane_kit_core.operations import operator_read_http_routes
            from control_plane_kit_operations.read_pages import ReadCollection, ReadPage, ReadPageRequest, RevisionReadScope
            from control_plane_kit_servers_cpk_server.boundary import _decode_http_read_query
            contract = next(r for r in operator_read_http_routes()
                if r.route_id == "read.desired-topology-draft-revision-attempts")
            query = _decode_http_read_query(contract, parts.query.encode("ascii"))
            request = ReadPageRequest(ReadCollection.DESIRED_TOPOLOGY_DRAFT_REVISION_ATTEMPTS,
                RevisionReadScope(action.WORKSPACE, action.DRAFT, 1), query["limit"])
            value = ReadPage.from_candidates(request, ()).descriptor()
        elif route == root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1":
            value = dict(workspace_id=action.WORKSPACE, draft_id=action.DRAFT, revision=1,
                         graph_id=action.DESIRED, graph_descriptor=graph)
            from control_plane_kit_operations.read_services.models import FocusedDetailReadModel
            value = FocusedDetailReadModel(action.WORKSPACE, "desired-topology-draft-revision", value).descriptor()
            if self.diagnosis == "invalid-shape":
                value["graph_descriptor"] = "{}"
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

    def diagnostic_reader(self, mode):
        created = action.run_as_owner([sys.executable, __file__, "--make-entry-target"], b"")
        self.assertEqual(created.returncode, 0)
        self.addCleanup(action.run_as_owner, [sys.executable, __file__, "--remove-entry-target"], b"")
        def spawn(_production_argv, pass_fds=()):
            return action.spawn_as_owner([sys.executable, __file__, "--diagnostic-entry", str(self.path),
                mode, str(pass_fds[0])], pass_fds=pass_fds)
        reader = action.OwnerUidReads("a" * 64, spawn=spawn)
        reader.bind_identity(self.document)
        return reader

    def test_repaired_production_reader_uses_owner_valid_page_and_object_projection(self):
        snapshot = self.diagnostic_reader("owner-contract").saved()
        self.assertIs(type(json.loads(snapshot)[2]["graph_descriptor"]), dict)
        queries = [json.loads(line) for line in (self.root / "queries.jsonl").read_text().splitlines()]
        root = "/workspaces/" + action.WORKSPACE
        revision = root + "/desired-topology-drafts/" + action.DRAFT + "/revisions/1"
        self.assertEqual(queries, [dict(path=p, query=q) for p, q in (
            (root, ""), (root + "/graphs/desired", ""), (revision, ""), (revision + "/attempts", "limit=10"))])
        observed = json.loads((self.root / "diagnosis.json").read_text())
        self.assertEqual(observed, dict(error_class="none", reason="not-emitted", exit_status=0))

    def test_invalid_revision_shape_keeps_fixed_route_and_reason_across_reader_parent(self):
        with self.assertRaises(action.ReadFailure) as caught:
            self.diagnostic_reader("invalid-shape").saved()
        self.assertEqual((caught.exception.route, caught.exception.reason),
                         (action.READ_ROUTES["revision"], "projection-mismatch"))
        queries = [json.loads(line) for line in (self.root / "queries.jsonl").read_text().splitlines()]
        self.assertEqual(len(queries), 4)
        self.assertEqual(queries[-1]["query"], "limit=10")
        observed = json.loads((self.root / "diagnosis.json").read_text())
        self.assertEqual(observed, dict(error_class="ReadFailure", reason="projection-mismatch", exit_status=1))

    def test_response_bound_keeps_safe_reason_and_nonzero_status(self):
        with self.assertRaises(action.ReadFailure) as caught:
            self.diagnostic_reader("oversize").saved()
        self.assertEqual((caught.exception.route, caught.exception.reason),
                         (action.READ_ROUTES["workspace"], "response-too-large"))
        observed = json.loads((self.root / "diagnosis.json").read_text())
        self.assertEqual(observed, dict(error_class="ReadFailure", reason="response-too-large", exit_status=1))

    def test_first_read_preparation_failure_keeps_stage_across_production_child_parent(self):
        with self.assertRaises(action.ReadFailure) as caught:
            self.diagnostic_reader("prepare").saved()
        self.assertEqual((caught.exception.stage, caught.exception.reason),
                         ("prepare:read.workspace", "preparation-failed"))
        self.assertFalse((self.root / "wire.jsonl").exists())
        self.assertNotIn("synthetic-private-detail", json.dumps(caught.exception.record()))

    def test_authorization_error_is_closed_and_does_not_reveal_response_body(self):
        with self.assertRaises(action.ReadFailure) as caught:
            self.diagnostic_reader("authorization").saved()
        record = caught.exception.record()
        self.assertEqual((record["route"], record["reason"]), (action.READ_ROUTES["workspace"], "authorization-refused"))
        self.assertNotIn("private-response", json.dumps(record))
        self.assertNotIn(HUMAN, json.dumps(record))

    def test_public_baseline_verification_and_first_page_coverage(self):
        import grandparent_saved_read as verification
        snapshot = self.reader().saved()
        report = verification.summarize(snapshot, SYNTHETIC_GRAPH)
        self.assertEqual(report["public_graph"]["node_count"], 8)
        self.assertEqual(report["desired_realized_projection_id"], verification.DESIRED_PROJECTION)
        self.assertEqual(report["attempts"], dict(limit=10, returned=0, next_cursor_present=False,
                                                coverage="first-page-only", page_exhausted_observed=True))
        values = json.loads(snapshot)
        values[3].update(items=[{"run_id": "synthetic"}], next_cursor={"opaque": "first-page"})
        page = verification.summarize(action.canonical(values), SYNTHETIC_GRAPH)["attempts"]
        self.assertEqual((page["returned"], page["next_cursor_present"], page["page_exhausted_observed"]), (1, True, False))
        self.assertNotEqual(snapshot, action.canonical(values))
        values[2]["graph_descriptor"]["nodes"]["node-1"]["count"] = True
        with self.assertRaises(action.ReadFailure) as caught:
            verification.summarize(action.canonical(values), SYNTHETIC_GRAPH)
        self.assertEqual(caught.exception.reason, "baseline-mismatch")
        values = json.loads(snapshot)
        values[0]["desired_graph"]["realized_projection_id"] = "wrong-projection"
        with self.assertRaises(action.ReadFailure) as caught:
            verification.summarize(action.canonical(values), SYNTHETIC_GRAPH)
        self.assertEqual((caught.exception.route, caught.exception.reason), (action.READ_ROUTES["workspace"], "projection-mismatch"))

    def test_verification_only_entry_completes_exactly_four_gets_without_graph_or_bearer_output(self):
        created = action.run_as_owner([sys.executable, __file__, "--make-entry-target"], b"")
        self.assertEqual(created.returncode, 0)
        self.addCleanup(action.run_as_owner, [sys.executable, __file__, "--remove-entry-target"], b"")
        result = action.run_as_owner([sys.executable, __file__, "--verification-entry", str(self.path)], b"")
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-1000:])
        report = json.loads(result.stdout)
        self.assertEqual((report["status"], report["completed_reads"], report["switch_attempted"]), ("verified", 4, False))
        self.assertEqual(report["stage"], "verified")
        self.assertEqual(report["public_graph"]["node_count"], 8)
        self.assertNotIn(b"graph_descriptor", result.stdout)
        self.assertNotIn(HUMAN.encode(), result.stdout + result.stderr)
        self.assertEqual(len((self.root / "wire.jsonl").read_text().splitlines()), 4)

    def test_verification_only_failure_stages_are_bounded_before_any_request(self):
        created = action.run_as_owner([sys.executable, __file__, "--make-entry-target"], b"")
        self.assertEqual(created.returncode, 0)
        self.addCleanup(action.run_as_owner, [sys.executable, __file__, "--remove-entry-target"], b"")
        cases = (("plan", "plan-read", "permission-denied"),
                 ("reader-source", "reader-source-read", "permission-denied"),
                 ("shared-source", "shared-source-read", "permission-denied"),
                 ("baseline", "baseline-read", "permission-denied"),
                 ("proxy", "proxy-environment", "check-refused"),
                 ("prepare", "prepare:read.workspace", None),
                 ("credential-invalid", "credential-load", "credential-configuration"))
        for case, stage, category in cases:
            with self.subTest(case=case):
                process = action.run_as_owner([sys.executable, __file__, "--verification-entry", str(self.path), case], b"")
                self.assertEqual(process.returncode, 1)
                report = json.loads(process.stdout)
                self.assertEqual((report["stage"], report["completed_reads"], report["status"]), (stage, 0, "HOLD"))
                if category is None:
                    self.assertEqual(report["read_failure"]["reason"], "preparation-failed")
                    self.assertEqual(report["read_failure"]["stage"], stage)
                else:
                    self.assertEqual(report["failure_category"], category)
                self.assertFalse((self.root / "wire.jsonl").exists())
                for private in (HUMAN.encode(), b"synthetic-private-detail", b"graph_descriptor"):
                    self.assertNotIn(private, process.stdout + process.stderr)

    def test_installed_client_error_exit_codes_and_owner_projection_metadata(self):
        from control_plane_kit_operations import read_pages
        from control_plane_kit_operations.read_services import models, workspace_graph
        from control_plane_kit_servers_cpk_server.client import cli, profile, transport
        for error, code in ((transport.ClientAuthorizationError(), 3), (transport.ClientTransportError(), 5)):
            with self.subTest(error=type(error).__name__), patch.object(cli, "load_profile"), \
                    patch.object(cli, "TopologyClient") as client, redirect_stderr(io.StringIO()) as errors:
                client.return_value.overview.side_effect = error
                self.assertEqual(cli.main(["--profile", "synthetic", "overview"]), code)
                self.assertNotIn(HUMAN, errors.getvalue())
        spec = read_pages.read_collection_spec(read_pages.ReadCollection.DESIRED_TOPOLOGY_DRAFT_REVISION_ATTEMPTS)
        self.assertEqual((spec.max_page_size, spec.default_page_size), (10, 10))
        projection = models.FocusedDetailReadModel(action.WORKSPACE, "desired-topology-draft-revision",
            dict(graph_descriptor=workspace_graph._redact_graph_descriptor({"name": "synthetic-diagnosis"}))).descriptor()
        self.assertIs(type(json.loads(json.dumps(projection))["graph_descriptor"]), dict)
        print("installed-saved-read-contract " + json.dumps(dict(maximum_response_bytes=transport.MAXIMUM_RESPONSE_BYTES,
            attempts_maximum=spec.max_page_size, revision_graph_json_type="object",
            module_sha256={m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                for m in (read_pages, models, workspace_graph, profile, transport, cli)}), sort_keys=True))

    def test_frozen_material_owner_and_qualified_mcp_bootstrap_plan_compatibility(self):
        import importlib.util
        from control_plane_kit_servers_cpk_server import bootstrap, root_material_preparation
        self.assertFalse(root_material_preparation.__file__.startswith("/source/"))
        self.assertTrue(callable(root_material_preparation.plan_root_material_preparation))
        self.assertTrue(callable(root_material_preparation.prepare_root_material))
        # Only public fixture values are borrowed; the selected frozen owner
        # performs compilation/verification. No material, Docker or DB effects.
        path = Path("/source/products/cpk_server/tests/test_root_bootstrap.py")
        spec = importlib.util.spec_from_file_location("root_input_values", path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        document = fixture.installation_input()
        product = document["installation"]["products"]["cpk"]["product"]
        digest = "sha256:49ae1044c73f5fb94cce229f736be5fa1ee3d1a0fcbe4e423d54b2831d2986a7"
        product["image"].update(registry="localhost", repository="control-plane-kit-servers/cpk-grandparent",
            digest=digest, tag=None, provenance={}, platforms=[dict(os="linux", architecture="amd64", variant=None)])
        environment = product["runtime_contract"]["public_environment"]
        environment[:] = [x for x in environment if x["name"] != "CPK_MCP_PROFILE"]
        environment.append(dict(kind="public-static", name="CPK_MCP_PROFILE", value="grandparent-read-only-v1"))
        driver = "sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80"
        plan = bootstrap.plan_root_bootstrap(document, driver_image_id=driver)
        self.assertEqual(bootstrap.verified_plan(plan, expected_digest=plan["digest"], driver_image_id=driver), plan)
        cpk = next(n for n in plan["resources"]["nodes"] if n["node_id"] == plan["cpk_node_id"])
        self.assertEqual(cpk["image"], "localhost/control-plane-kit-servers/cpk-grandparent@" + digest)
        self.assertEqual(cpk["environment"]["CPK_MCP_PROFILE"], "grandparent-read-only-v1")
        self.assertTrue(bootstrap.matches_image_reference(cpk["image"], (cpk["image"],)))
        print("reset-bootstrap-compatibility " + json.dumps(dict(schema="cpk399.reset-compatibility.v1",
            installed_material_owner=True, material_module_sha256=hashlib.sha256(
                Path(root_material_preparation.__file__).read_bytes()).hexdigest(),
            pure_bootstrap_plan_verified=True, qualified_cpk_image=digest,
            mcp_profile="grandparent-read-only-v1", material_generated=False,
            runtime_started=False, fresh_private_policy_tested=False), sort_keys=True))


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
    elif mode == "--diagnostic-entry":
        # Real production reader entry, owner UID/channel and installed client.
        # Only public proposal bytes and the external wire are synthetic. A
        # single request-limit perturbation isolates the later shape defect.
        from control_plane_kit_servers_cpk_server.client import transport
        path, diagnosis, descriptor = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
        raw_bootstrap = b"{}"
        plan = dict(approval_reference="synthetic-offline-diagnosis", quiescence_confirmed=True,
            exposure_reviewed=True, private_wiring_reuse_approved=True, verification_bearer_use_approved=True,
            script_sha256=hashlib.sha256(Path(action.__file__).read_bytes()).hexdigest())
        raw_plan = action.canonical(plan)
        original_read = Path.read_bytes
        def public_proposal_bytes(target):
            if str(target) == "/proposal/action.json":
                return raw_plan
            if str(target) == "/proposal/bootstrap.json":
                return raw_bootstrap
            return original_read(target)
        original_saved, original_call = action.SavedReads.saved, transport.PublicHttpTransport.call
        result = dict(error_class="none", reason="not-emitted")
        def observe_saved(reader):
            try:
                return original_saved(reader)
            except BaseException as error:
                name = type(error).__name__
                result["error_class"] = name if name in {"ReadPageError", "Hold", "ClientTransportError", "ReadFailure"} else "other"
                if isinstance(error, action.ReadFailure):
                    result["reason"] = error.reason
                if isinstance(error, action.Hold) and str(error) == "saved-revision-mismatch":
                    result["reason"] = "saved-revision-mismatch"
                if isinstance(error, transport.ClientTransportError) and str(error) == "cpk-server response exceeds the client bound":
                    result["reason"] = "response-client-bound"
                raise
        def request(client, route, **kwargs):
            if diagnosis == "limit10" and route == "read.desired-topology-draft-revision-attempts":
                kwargs["payload"] = {"limit": 10}
            return original_call(client, route, **kwargs)
        with patch.object(Path, "read_bytes", public_proposal_bytes), \
                patch.object(action, "PUBLIC_PLAN_SHA", hashlib.sha256(raw_bootstrap).hexdigest()), \
                patch.object(sys, "argv", [action.__file__, "--read-saved", hashlib.sha256(raw_plan).hexdigest(), "--admin-fd", descriptor]), \
                patch.object(action.SavedReads, "saved", observe_saved), \
                patch.object(transport.PublicHttpTransport, "call", request), \
                patch.object(transport, "build_opener", return_value=Wire(path, diagnosis=diagnosis),
                    side_effect=RuntimeError("synthetic-private-detail") if diagnosis == "prepare" else None):
            result["exit_status"] = action.entry_point()
        (path.parent / "diagnosis.json").write_text(json.dumps(result))
        raise SystemExit(result["exit_status"])
    elif mode == "--verification-entry":
        import grandparent_saved_read as verification
        from control_plane_kit_servers_cpk_server.client import transport
        path = Path(sys.argv[2])
        case = sys.argv[3] if len(sys.argv) == 4 else "success"
        assert case in {"success", "plan", "reader-source", "shared-source", "baseline", "proxy", "prepare", "credential-invalid"}
        if case == "credential-invalid":
            credential = Path("/credentials/human.bearer")
            credential.chmod(0o600)
            credential.write_text("h" * 63 + "\n")
            credential.chmod(0o400)
        raw_baseline = action.canonical(SYNTHETIC_GRAPH)
        raw_shared = Path(action.__file__).read_bytes()
        plan = dict(schema="cpk399.read-only-approval.v1", run=verification.RUN, read_once_approved=True,
            reader_sha256=hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest(),
            shared_reader_sha256=hashlib.sha256(raw_shared).hexdigest(), endpoint="http://127.0.0.1:18163",
            routes=list(action.READ_ROUTES.values()))
        raw_plan = action.canonical(plan)
        original_read = Path.read_bytes
        def public_read(target):
            inputs = {"/proposal/verification.json": raw_plan, "/public/desired.json": raw_baseline,
                      "/grandparent_cpk_cutover.py": raw_shared}
            denied = {"plan": "/proposal/verification.json", "reader-source": verification.__file__,
                      "shared-source": "/grandparent_cpk_cutover.py", "baseline": "/public/desired.json"}
            if str(target) == denied.get(case):
                raise PermissionError("synthetic-private-detail")
            return inputs[str(target)] if str(target) in inputs else original_read(target)
        with patch.object(Path, "read_bytes", public_read), \
                patch.object(verification, "BASELINE_SHA", hashlib.sha256(raw_baseline).hexdigest()), \
                patch.dict(os.environ, {"HTTP_PROXY": "synthetic-private-detail"} if case == "proxy" else {}), \
                patch.object(sys, "argv", [verification.__file__, "--verify-saved-read-only", hashlib.sha256(raw_plan).hexdigest()]), \
                patch.object(transport, "build_opener", return_value=Wire(path, diagnosis="verification"),
                    side_effect=RuntimeError("synthetic-private-detail") if case == "prepare" else None):
            status = verification.main()
        raise SystemExit(status)
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
