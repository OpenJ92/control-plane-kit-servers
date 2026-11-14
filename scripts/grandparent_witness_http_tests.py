"""Witness consumes frozen public HTTP examples; ASGI is an external wire double.

No Operations state machine, listening process, database or credential is run.
The real installed httpx2 stream implementation consumes finite public frames.
"""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx2
import grandparent_artifact_fixture as fixture

READY = dict(status="ready", application="configured", stores="configured")
MARKER = "private-sentinel-never-report"


class PublicFrames:
    def __init__(self, frames):
        self.frames, self.requests = list(frames), []

    async def __call__(self, scope, receive, send):
        method, path, status, value = self.frames.pop(0)
        assert (scope["method"], scope["path"]) == (method, path)
        body = bytearray()
        while True:
            message = await receive()
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        self.requests.append((method, path, json.loads(body) if body else None))
        await send(dict(type="http.response.start", status=status,
            headers=[(b"content-type", b"application/json")]))
        await send(dict(type="http.response.body", body=json.dumps(value).encode()))


class WitnessHttpTests(unittest.TestCase):
    def actor_directory(self, root):
        (root / "actors.json").write_text(json.dumps(dict(setup=MARKER, reader="synthetic-reader")))

    def client(self, app):
        actual = httpx2.AsyncClient
        return patch.object(httpx2, "AsyncClient", side_effect=lambda **options:
            actual(transport=httpx2.ASGITransport(app=app), **options))

    def test_seed_consumes_http_preparation_shape_instead_of_internal_projection(self):
        root = "/workspaces/workspace-a"
        draft = root + "/desired-topology-drafts/draft-a"
        revision = draft + "/revisions/1"
        before = dict(current_graph_id="current", current_realized_projection_id="current-projection",
            desired_graph_id=None, desired_realized_projection_id=None, desired_graph_revision=0)
        selected = before | dict(desired_graph_id="desired", desired_realized_projection_id="desired-projection",
            desired_graph_revision=1)
        prepared = dict(status="review-blocked", workspace_id="workspace-a", plan_id="plan-a")
        history = dict(items=[dict(session_id="preparation-session")])
        plan = dict(derivation_profile="managed-sql-http-bootstrap-v1", base_graph_id="current",
            base_realized_projection_id="current-projection", desired_graph_id="desired",
            desired_realized_projection_id="desired-projection", desired_graph_revision=1)
        # Flat session/draft/preparation and nested plan shapes follow Ops701's
        # descriptor/mapping owners. These frames do not execute those owners.
        frames = PublicFrames([
            ("GET", "/health/ready", 200, READY),
            ("POST", "/administration/workspaces", 200, dict(receipt={})),
            ("POST", root + "/permissions/grant", 200, dict(revision=1)),
            ("POST", root + "/permissions/grant", 200, dict(revision=1)),
            ("POST", root + "/sessions", 200, dict(session_id="session-a")),
            ("POST", root + "/desired-topology-drafts", 200, dict(draft_id="draft-a", revision=1)),
            ("GET", root, 200, dict(workspace=before)),
            ("POST", draft + "/select", 200, dict(desired_graph_revision=1)),
            ("GET", root, 200, dict(workspace=selected)),
            ("POST", root + "/deployments/prepare", 200, prepared),
            ("GET", root, 200, dict(workspace=selected)),
            ("GET", revision + "/preparations", 200, history),
            ("GET", root + "/plans/plan-a", 200, dict(plan=plan)),
            ("POST", root + "/deployments/prepare", 200, prepared),
            ("GET", revision + "/preparations", 200, history),
        ])
        with tempfile.TemporaryDirectory() as name, self.client(frames):
            directory = Path(name)
            self.actor_directory(directory)
            asyncio.run(fixture.Witness(directory).seed())
            saved = json.loads((directory / "saved.json").read_text())
            self.assertEqual(saved["preparation"], prepared)
            self.assertEqual(saved["plan_path"], root + "/plans/plan-a")
        preparation = next(body for method, path, body in frames.requests if path.endswith("deployments/prepare"))
        self.assertEqual(preparation["managed_verification"], "authenticated-local-postgres-and-http")
        self.assertEqual(preparation["expected_desired"]["authored_graph_id"], "desired")

    def run_failed_seed(self, app, *, seed=None, step="readiness"):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as name, self.client(app), \
                patch.object(sys, "argv", ["witness", "seed", name]), \
                patch.object(fixture.asyncio, "sleep", new=AsyncMock()), \
                (patch.object(fixture.Witness, "seed", seed) if seed else contextlib.nullcontext()), \
                contextlib.redirect_stderr(output):
            self.actor_directory(Path(name))
            status = fixture.main()
        self.assertEqual(status, 1)
        self.assertNotIn(MARKER, output.getvalue())
        self.assertLessEqual(len(output.getvalue().encode()), 512)
        report = json.loads(output.getvalue())
        self.assertEqual(set(report), {"schema", "mode", "step", "category", "http_status"})
        self.assertEqual(report["mode"], "seed")
        self.assertEqual(report["step"], step)
        return report

    def test_http_denial_retains_only_fixed_step_category_and_safe_status(self):
        async def denied(witness):
            witness.step = "session-start"
            await witness.request("/" + MARKER)
        frames = PublicFrames([("GET", "/" + MARKER, 403, dict(private=MARKER))])
        report = self.run_failed_seed(frames, seed=denied, step="session-start")
        self.assertEqual(report["category"], "http-status")
        self.assertEqual(report["http_status"], 403)

    def test_credential_echo_is_not_returned_as_diagnostic_data(self):
        frames = PublicFrames([("GET", "/health/ready", 200, dict(status="live", private=MARKER))])
        report = self.run_failed_seed(frames)
        self.assertEqual(report["category"], "redaction")
        self.assertIsNone(report["http_status"])

    def test_ready_requires_the_selected_public_readiness_shape(self):
        frames = PublicFrames([("GET", "/health/ready", 200, dict(status="live"))])
        report = self.run_failed_seed(frames)
        self.assertEqual(report["category"], "shape")
        self.assertIsNone(report["http_status"])

    def test_arbitrary_exception_text_is_not_a_diagnostic(self):
        async def broken(scope, receive, send):
            raise ValueError(MARKER)
        report = self.run_failed_seed(broken)
        self.assertEqual(report["category"], "unexpected")
        self.assertIsNone(report["http_status"])

    def test_transport_only_readiness_polling_has_a_closed_timeout_result(self):
        async def unavailable(scope, receive, send):
            raise httpx2.ConnectError(MARKER)
        report = self.run_failed_seed(unavailable)
        self.assertEqual(report["category"], "readiness-timeout")
        self.assertIsNone(report["http_status"])
