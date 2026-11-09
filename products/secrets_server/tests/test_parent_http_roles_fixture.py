"""Synthetic fixture/transport checks; packaged HTTP remains a separate action."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from child_bootstrap_fixture import populate
from parent_http_roles_fixture import ROLES, WORKSPACE, exercise, BoundedProviderClient, DENIED, UNSUPPORTED_GENERATION
from source_control_fixture import verify_logs


class Response:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class Transport:
    """Prescribed HTTP responses only, no provider-policy/store reimplementation."""
    def __init__(self, private, *, generation_status=400, wrong_role_status=403, denial_leak=None):
        self.private = private
        self.generation_status, self.wrong_role_status = generation_status, wrong_role_status
        self.denial_leak = denial_leak
        self.writes = 0

    def post(self, path, *, headers, json):
        correlation = json["correlation_id"]
        if "wrong-role" in correlation:
            body = deepcopy(DENIED)
            if self.denial_leak == "nested":
                body["detail"]["diagnostic"] = {"payload":(self.private / (ROLES[0][0] + ".key")).read_text()}
            elif self.denial_leak == "renamed":
                body["renamed_material"] = base64.b64encode((self.private / (ROLES[0][0] + ".key")).read_bytes()).decode()
            return Response(self.wrong_role_status, body)
        if "foreign-workspace" in correlation:
            return Response(403, DENIED)
        if "unsupported-generation" in correlation:
            return Response(self.generation_status, UNSUPPORTED_GENERATION)
        if "ungranted-generation" in correlation:
            return Response(403, DENIED)
        role = next(role for role, _, _ in ROLES if correlation.startswith(role + "-"))
        intent = next(intent for name, intent, _ in ROLES if name == role)
        if correlation.endswith("-write"):
            self.writes += 1
            return Response(200, {"metadata":{"version_id":role + "-version", "labels":{"intent":intent}}})
        return Response(200, {"metadata":{"version_id":role + "-version"},
            "value_base64":base64.b64encode((self.private / (role + ".key")).read_bytes()).decode()})


class ParentHttpRolesFixtureTests(unittest.TestCase):
    def test_transport_refuses_oversize_response(self):
        import httpx
        with httpx.Client(base_url="http://unit.invalid", transport=httpx.MockTransport(
                lambda request:httpx.Response(200, content=b"x" * 65537))) as client:
            with self.assertRaises(ValueError):
                BoundedProviderClient(client).post("/unit")

    def seed(self, directory):
        provider, client, data = (Path(directory) / name for name in ("provider", "client", "data"))
        for path in (provider, client, data):
            path.mkdir()
        populate(provider, client, data, parent=True)
        return provider, client, data

    def test_fresh_parent_seed_has_two_distinct_exact_import_roles_without_generation(self):
        with TemporaryDirectory() as directory:
            provider, client, data = self.seed(directory)
            credentials = json.loads((provider / "credentials.json").read_text())
            self.assertEqual(len(credentials), 3)
            self.assertTrue(len({row["token"] for row in credentials}) == 3)
            for role, intent, _ in ROLES:
                credential = next(row for row in credentials if row["subject"] == role)
                self.assertEqual(credential["grants"], [{"action":action, "workspace_id":WORKSPACE, "intents":[intent]}
                    for action in ("secret.write", "secret.resolve")])
                for suffix in (".key", ".token"):
                    path = client / (role + suffix)
                    self.assertEqual(path.stat().st_uid, 0)
                    self.assertEqual(path.stat().st_mode & 0o777, 0o400)
            with self.assertRaises(ValueError):
                populate(provider, client, data, parent=True)

    def test_witness_preserves_versions_on_restart_and_emits_no_private_values(self):
        with TemporaryDirectory() as directory:
            _, private, _ = self.seed(directory)
            evidence = Path(directory) / "evidence"
            evidence.mkdir()
            transport = Transport(private)
            initial = exercise(transport, private, None, "initial")
            previous = evidence / "initial-public.json"
            previous.write_text(json.dumps(initial))
            previous.chmod(0o444)
            restarted = exercise(transport, private, previous, "restart")
            self.assertEqual(transport.writes, 2)
            self.assertEqual([row["version_id"] for row in initial["roles"]],
                [row["version_id"] for row in restarted["roles"]])
            public = json.dumps(initial).encode()
            for role, _, _ in ROLES:
                for suffix in (".key", ".token"):
                    raw = (private / (role + suffix)).read_bytes()
                    self.assertTrue(raw not in public and base64.b64encode(raw) not in public)

    def test_generation_or_wrong_role_acceptance_prevents_success_evidence(self):
        for fault in ({"generation_status":200}, {"wrong_role_status":200},
                {"denial_leak":"nested"}, {"denial_leak":"renamed"}):
            with self.subTest(fault=fault), TemporaryDirectory() as directory:
                _, private, _ = self.seed(directory)
                evidence = Path(directory) / "evidence"
                evidence.mkdir()
                with self.assertRaisesRegex(ValueError, "^parent HTTP signing witness failed$"):
                    exercise(Transport(private, **fault), private, None, "initial")
                self.assertEqual(tuple(evidence.iterdir()), ())

    def test_parent_log_checker_refuses_encoded_key_or_token_leaks(self):
        with TemporaryDirectory() as directory:
            _, private, _ = self.seed(directory)
            logs = Path(directory) / "logs"
            logs.mkdir()
            (logs / "log.status").write_bytes(b"0\n")
            for suffix in (".key", ".token"):
                (logs / "provider.log").write_bytes(base64.b64encode((private / (ROLES[0][0] + suffix)).read_bytes()))
                with self.assertRaises(ValueError):
                    verify_logs(logs, private, parent=True)
