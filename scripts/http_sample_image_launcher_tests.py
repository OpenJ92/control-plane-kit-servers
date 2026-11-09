"""Real launcher refusal with explicit Git/Docker CLI doubles, no real daemon."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = "sha256:" + "a" * 64


class ImageInputLauncherTests(unittest.TestCase):
    def test_ordinary_launchers_refuse_bad_full_inputs_before_build_network_or_postgres(self):
        with TemporaryDirectory(prefix="cpk163-launcher-law-") as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text("#!" + sys.executable + "\n" + '''
import json,os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ["CPK_LAUNCH_CALLS"],"a") as stream: stream.write(json.dumps(args)+"\\n")
if args[:2]==["image","inspect"]:
    print(os.environ["CPK_SOURCE_IMAGE_VALIDATOR"])
    raise SystemExit(0)
if args and args[0]=="run" and args[-1]=="/source/scripts/http_sample_image_inputs.py":
    if "none" not in args or "--read-only" not in args or "never" not in args: raise SystemExit(98)
    raise SystemExit(subprocess.run([sys.executable,str(Path(os.environ["CPK_LAUNCH_ROOT"])/"scripts/http_sample_image_inputs.py")]).returncode)
raise SystemExit(99)
''')
            git = root / "git"
            # Archive transport double only. The fake validation controller runs
            # the actual shared codec with the outer gate's pinned Core imports.
            git.write_text("#!" + sys.executable + "\nimport sys,tarfile\n"
                "if 'archive' not in sys.argv: raise SystemExit(99)\n"
                "with tarfile.open(fileobj=sys.stdout.buffer,mode='w|'): pass\n")
            docker.chmod(0o700)
            git.chmod(0o700)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                CPK_SOURCE_IMAGE_VALIDATOR=VALIDATOR, CPK_LAUNCH_ROOT=str(ROOT),
                CPK_LAUNCH_CALLS=str(root / "calls"))
            commands = (
                ["sh", str(ROOT / "test.sh"), "--http-sample-source-registrations", "/core", "/ops", "/interpreters", "/secrets", "1" * 40],
                ["sh", str(ROOT / "scripts/http_sample_source_assembly.sh"), "unused-controller", "/core", "/ops", "/interpreters", "registrations", "/secrets", "1" * 40])
            for command in commands:
                for full, legacy in (("{}", None), ('{"gateway":null}', None), ('{"gateway":1,"gateway":2}', None), ("{}", "{}")):
                    with self.subTest(launcher=Path(command[1]).name, conflicting=legacy is not None):
                        (root / "calls").unlink(missing_ok=True)
                        selected = dict(env, CPK_SOURCE_ASSEMBLY_IMAGES=full)
                        selected.pop("CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE", None)
                        if legacy is not None:
                            selected["CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE"] = legacy
                        result = subprocess.run(command, env=selected, capture_output=True, timeout=20, check=False)
                        self.assertEqual(result.returncode, 2)
                        calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
                        self.assertEqual([value[:2] for value in calls], [["image","inspect"],["run","--pull"]])
                        self.assertTrue(calls[-1][-1] == "/source/scripts/http_sample_image_inputs.py")
                        self.assertIn(b"source assembly image input refused", result.stderr)
