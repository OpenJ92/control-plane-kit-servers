"""Release orchestration laws; command doubles do not qualify an OCI artifact."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ManagedReleaseRoutingTests(unittest.TestCase):
    def run_owner(self, arguments):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            calls = home / 'calls'
            docker = home / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nexit 91\n')
            docker.chmod(0o755)
            environment = dict(os.environ, PATH=str(home) + os.pathsep + os.environ['PATH'], CALLS=str(calls))
            result = subprocess.run(['sh', str(ROOT / 'test.sh'), *arguments], cwd=ROOT,
                                    env=environment, capture_output=True, text=True, timeout=10)
            return result, calls.read_text() if calls.exists() else ''

    def test_missing_candidate_arguments_refuse_before_any_docker_call(self):
        result, calls = self.run_owner(['--managed-connector-candidate'])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, '')

    def test_mutable_candidate_refuses_before_any_docker_call(self):
        result, calls = self.run_owner([
            '--managed-connector-candidate', '--image-id', 'candidate:latest',
            '--source', 'a' * 40, '--controller-image-id', 'sha256:' + 'b' * 64,
            '--controller-receipt', '/missing/receipt.json', '--receipt-dir', '/missing/new'])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, '')

    def test_duplicate_options_refuse_before_any_docker_call(self):
        result, calls = self.run_owner([
            '--managed-connector-candidate', '--image-id', 'sha256:' + 'a' * 64,
            '--image-id', 'sha256:' + 'b' * 64])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, '')
