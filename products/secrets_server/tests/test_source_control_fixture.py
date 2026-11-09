"""Adapter-owned file/diagnostic laws; real HTTP lives in the maintained smoke."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

from control_plane_kit_secrets.control import decode_secrets_control_configuration
from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
import source_control_fixture as fixture


class SourceControlFixtureTests(unittest.TestCase):
    def test_child_target_preserves_v2_liveness_and_full_named_pair_across_restart(self):
        from scripts.http_sample_fixture import SampleAuthority
        from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract, secrets_http_sample_binding
        controls = []
        with TemporaryDirectory() as directory:
            for phase in ("initial", "restart"):
                root = Path(directory) / phase
                root.mkdir()
                fixture.generate(root, "fresh-child-fixture", child=True)
                control = decode_secrets_control_configuration((root / "control.json").read_bytes())
                self.assertEqual((control.target.workspace_id.value, control.target.runtime_id.value,
                    control.target.node_id.value, control.target.provider_socket_name.value),
                    ("root-workspace", "root-a-docker", "root-a-secrets", "control"))
                ordinary = secrets_source_runtime_contract(secrets_control_configuration_artifact(control))
                sample = SampleAuthority(control, ordinary, all_checks=True)
                self.assertEqual(tuple(entry.check for entry in secrets_http_sample_binding(
                    control, sample.configuration).checks), ordinary.verification.checks)
                requests = tuple(sample.request(check) for check in ordinary.verification.checks)
                self.assertEqual(tuple(request.check_id for request in requests), ("live", "ready"))
                self.assertNotEqual(requests[0].request_id, requests[1].request_id)
                controls.append(control)
        self.assertEqual(controls[0].target, controls[1].target)
        self.assertEqual(controls[0].declaration, controls[1].declaration)
        self.assertNotEqual(controls[0].verifiers, controls[1].verifiers)

    def test_phase_files_preserve_identity_with_fresh_public_keys(self):
        with TemporaryDirectory() as directory:
            configurations = []
            for phase in ("initial", "restart"):
                root = Path(directory) / phase
                root.mkdir(mode=0o700)
                fixture.generate(root, "fixture-run")
                self.assertEqual({path.name for path in root.iterdir()},
                                 {"control.json", "surface.headers", "health.headers"})
                raw = (root / "control.json").read_bytes()
                configuration = decode_secrets_control_configuration(raw)
                self.assertEqual(raw, secrets_control_configuration_artifact(configuration).content.encode())
                configurations.append(configuration)
                for name, mode in (("control.json", 0o444), ("surface.headers", 0o600),
                                   ("health.headers", 0o600)):
                    path = root / name
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                    self.assertNotIn(b"PRIVATE KEY", path.read_bytes())
                self.assertNotEqual((root / "surface.headers").read_bytes(),
                                    (root / "health.headers").read_bytes())
            first, second = configurations
            self.assertEqual((first.target, first.declaration), (second.target, second.declaration))
            self.assertEqual(first.target.runtime_id, second.target.runtime_id)
            self.assertEqual({family.purpose for family in first.verifiers},
                             {family.purpose for family in second.verifiers})
            for family in first.verifiers:
                changed = next(item for item in second.verifiers if item.purpose is family.purpose)
                self.assertNotEqual(family.public_keys, changed.public_keys)

    def test_log_cli_is_bounded_and_never_echoes_failure_material(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "client"
            client.mkdir()
            phase = root / "initial"
            phase.mkdir()
            fixture.generate(phase, "log-fixture")
            (client / "provider-token").write_bytes(b"private-provider-marker")
            (client / "application-value").write_bytes(b"private-value-marker")
            token = (phase / "surface.headers").read_bytes().removeprefix(b"Authorization: Bearer ").strip()
            cases = (
                (b"normal process output", b"0\n", True),
                (b"Bearer synthetic-leak", b"0\n", False),
                (b"PRIVATE KEY synthetic-leak", b"0\n", False),
                (b"provider-token synthetic-leak", b"0\n", False),
                (b"private-provider-marker", b"0\n", False),
                (b"private-value-marker", b"0\n", False),
                (token, b"0\n", False),
                (b"x" * (fixture.MAX_LOG_BYTES + 1), b"0\n", False),
                (b"normal process output", b"1\n", False),
                (b"normal process output", b"", False),
            )
            for index, (body, status, accepted) in enumerate(cases):
                with self.subTest(case=index):
                    (root / "provider.log").write_bytes(body)
                    (root / "log.status").write_bytes(status)
                    out, error = StringIO(), StringIO()
                    with redirect_stdout(out), redirect_stderr(error):
                        result = fixture.main(["logs", str(root), str(client), str(phase)])
                    self.assertEqual(result, 0 if accepted else 1)
                    self.assertEqual(out.getvalue(), "")
                    self.assertEqual(error.getvalue(), "" if accepted else "Secrets smoke fixture failed\n")
            # Historical mode checks the same private laws without any source phase.
            (root / "provider.log").write_bytes(b"normal process output")
            (root / "log.status").write_bytes(b"0\n")
            self.assertEqual(fixture.main(["logs", str(root), str(client)]), 0)
            (root / "provider.log").unlink()
            error = StringIO()
            with redirect_stderr(error):
                self.assertEqual(fixture.main(["logs", str(root), str(client)]), 1)
            self.assertEqual(error.getvalue(), "Secrets smoke fixture failed\n")

    def test_partial_generation_leaves_only_enumerated_files_and_fixed_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "surface.headers").write_bytes(b"existing-private-marker")
            error = StringIO()
            with redirect_stderr(error):
                self.assertEqual(fixture.main(["generate", str(root), "partial-fixture"]), 1)
            self.assertEqual(error.getvalue(), "Secrets smoke fixture failed\n")
            self.assertEqual({path.name for path in root.iterdir()}, {"control.json", "surface.headers"})
            self.assertEqual((root / "surface.headers").read_bytes(), b"existing-private-marker")


if __name__ == "__main__":
    unittest.main()
