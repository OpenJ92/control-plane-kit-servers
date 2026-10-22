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


class ManagedReleasePolicyTests(unittest.TestCase):
    def policy(self):
        import runpy
        path = ROOT / 'products/cloudflared_connector/release.py'
        self.assertTrue(path.is_file(), 'Managed release policy is not implemented')
        return runpy.run_path(str(path))

    def test_destination_is_closed_and_source_bound(self):
        policy = self.policy()
        destination = policy['destination']
        source = 'a' * 40
        self.assertEqual(destination(source, 'managed-' + source),
                         'ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector:managed-' + source)
        for bad_source, tag in [('a'*7, 'managed-'+'a'*7), (source, 'latest'),
                                (source, 'managed-' + source + '\n')]:
            with self.assertRaises(ValueError):
                destination(bad_source, tag)

    def test_controller_receipt_requires_exact_typed_identity(self):
        policy = self.policy()
        receipt = dict(schema='cpk.cloudflared-controller-acquisition.v1',
                       source_commit='a'*40, source_tree='b'*40, dockerfile_sha256='c'*64,
                       image_id='sha256:'+'d'*64, build_exit=0, build_log_sha256='e'*64)
        validate = policy['controller_receipt']
        self.assertEqual(validate(receipt, receipt['image_id']), receipt)
        for field, value in [('build_exit', False), ('image_id', 'latest'),
                             ('source_commit', 'short'), ('schema', 'other')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(dict(receipt, **{field:value}), receipt['image_id'])
        with self.assertRaises(ValueError):
            validate(receipt, 'sha256:'+'f'*64)

    def test_package_checks_complete_pages_and_exact_tag_digest(self):
        policy = self.policy()
        source = 'a'*40
        tag = 'managed-' + source
        digest = 'sha256:' + 'b'*64
        package = dict(id=1, name='control-plane-kit-servers/cloudflared-connector',
                       package_type='container', visibility='private')
        version = dict(id=2, name=digest, metadata={'container':{'tags':[tag]}})
        validate = policy['package_evidence']
        validate(package, [[]], source)
        validate(package, [[version]], source, digest)
        for bad in [dict(package, visibility='public'), dict(package, name='elsewhere')]:
            with self.assertRaises(ValueError):
                validate(bad, [[]], source)
        for pages in [[], [[version]], [[], [version]], [None]]:
            with self.assertRaises(ValueError):
                validate(package, pages, source)
        with self.assertRaises(ValueError):
            validate(package, [[version], [version]], source, digest)
        with self.assertRaises(ValueError):
            validate(package, [[version]], source, 'sha256:'+'c'*64)

    def test_same_candidate_is_required_after_qualification(self):
        policy = self.policy()
        check = policy['qualified_candidate']
        candidate = 'sha256:'+'a'*64
        receipt = dict(schema='cpk.cloudflared-managed-qualification.v1',
                       candidate_id=candidate, source_commit='b'*40,
                       status='pass', cleanup='verified', candidate_retained=True)
        check(receipt, candidate, 'b'*40)
        for field, value in [('status','fail'),('cleanup','unverified'),
                             ('candidate_retained',False),('candidate_id','sha256:'+'c'*64),
                             ('source_commit','d'*40)]:
            with self.assertRaises(ValueError):
                check(dict(receipt, **{field:value}), candidate, 'b'*40)
