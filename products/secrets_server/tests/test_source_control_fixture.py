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
            self.assertEqual((first.target, first.runtime_id, first.declaration),
                             (second.target, second.runtime_id, second.declaration))
            self.assertNotEqual(first.surface_keys, second.surface_keys)
            self.assertNotEqual(first.health_keys, second.health_keys)

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
