"""New retained-image orchestration laws; these do not qualify a real image."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


class RetainedQualificationTests(unittest.TestCase):
    def policy(self):
        return runpy.run_path(str(ROOT / 'products/cloudflared_connector/retained_qualification.py'))

    def test_only_reviewed_actual_executor_is_admitted(self):
        p = self.policy()
        good = {'Version': '28.0.4', 'GitCommit': '6430e49'}
        info = {'ID': 'test-daemon', 'OSType': 'linux', 'Architecture': 'x86_64'}
        self.assertEqual(p['executor'](info, good)['version'], '28.0.4')
        for bad in ({'Version': '29.7.2', 'GitCommit': '6430e49'},
                    {'Version': '28.0.4', 'GitCommit': '6430e4'},
                    {'Version': '28.0.4', 'GitCommit': 'wrong-build'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p['executor'](info, bad)

    def test_reference_local_id_and_source_are_independently_bound(self):
        p = self.policy()
        image = {'Id': 'sha256:' + 'a' * 64, 'RepoDigests': [p['REFERENCE']],
                 'Os': 'linux', 'Architecture': 'amd64',
                 'Config': {'Labels': {'org.opencontainers.image.revision': p['SOURCE']}}}
        self.assertEqual(p['association'](image), image['Id'])
        for change in ({'RepoDigests': []}, {'Id': 'latest'}, {'Architecture': 'arm64'},
                       {'Config': {'Labels': {'org.opencontainers.image.revision': 'b' * 40}}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                p['association'](dict(image, **change))

    def test_primary_failure_survives_projection_failure(self):
        p = self.policy()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def fail_write(*args):
                raise OSError('private canary')
            with patch.dict(p['finish'].__globals__, {'save': fail_write}):
                self.assertEqual(p['finish'](root, {}, 73), 73)
                self.assertEqual(p['finish'](root, {}, 0), 1)

    def test_projection_does_not_copy_unknown_private_receipt_fields(self):
        p = self.policy()
        candidate = 'sha256:' + 'a' * 64
        value = {'schema': 'cpk.cloudflared-managed-qualification.v1',
                 'candidate_id': candidate, 'source_commit': p['SOURCE'],
                 'status': 'fail', 'cleanup': 'unverified', 'candidate_retained': True,
                 'private': 'SECRET_CANARY', 'created_containers': ['SECRET_CANARY']}
        result = p['qualification_fields'](value, candidate)
        self.assertEqual(result['cleanup'], 'unverified')
        self.assertNotIn('SECRET_CANARY', json.dumps(result))
        for field, bad in [('candidate_id', 'sha256:' + 'b' * 64),
                           ('cleanup', 'SECRET_CANARY'), ('candidate_retained', 1)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                p['qualification_fields'](dict(value, **{field: bad}), candidate)

    def test_failed_or_missing_cleanup_cannot_pass(self):
        p = self.policy()
        value = {'status': 'pass', 'cleanup': 'verified', 'candidate_retained': True}
        p['require_success'](value)
        for change in ({'status': 'fail'}, {'cleanup': 'unverified'},
                       {'candidate_retained': False}, {'cleanup': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                p['require_success'](dict(value, **change))
