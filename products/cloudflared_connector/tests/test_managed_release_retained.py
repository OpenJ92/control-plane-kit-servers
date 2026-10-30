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
                 'source_tree': p['TREE'], 'controller_id': 'sha256:' + 'b' * 64,
                 'run': 'cpk-managed-release-run.123456789abc', 'platform': 'linux/amd64',
                 'recipe_sha256': 'c' * 64, 'witness_sha256': 'd' * 64,
                 'controller_receipt_sha256': 'e' * 64,
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

    def test_pull_failure_stops_before_controller_and_preserves_intent_and_exit(self):
        p = self.policy()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'executor': {'daemon_id': 'test'}, 'status': 'running'}
            calls = []
            def fail_pull(command, owner, receipts, name):
                calls.append(command)
                intent = json.loads((root / 'result.json').read_text())
                self.assertEqual(intent['stage'], 'pull')
                return 47
            with patch.dict(p['run'].__globals__, {
                    'preflight': lambda owner: report['executor'], 'effect': fail_pull}):
                self.assertEqual(p['run'](root, root, report), 47)
            self.assertEqual(calls, [['docker', 'pull', '--platform', 'linux/amd64', p['REFERENCE']]])
            self.assertEqual(json.loads((root / 'result.json').read_text())['primary_exit'], 47)

    def test_executor_drift_stops_before_any_acquisition(self):
        p = self.policy()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'executor': {'daemon_id': 'old'}, 'status': 'running'}
            with patch.dict(p['run'].__globals__, {
                    'preflight': lambda owner: {'daemon_id': 'changed'},
                    'effect': lambda *args: self.fail('Acquisition after executor drift')}):
                self.assertEqual(p['run'](root, root, report), 1)

    def test_success_uses_only_existing_owners_and_postchecks_exact_image(self):
        p = self.policy()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, controller_id = 'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64
            report = {'executor': {'daemon_id': 'test'}, 'status': 'running'}
            commands = []
            def effects(command, owner, receipts, name):
                commands.append(command)
                if name == 'controller-acquisition':
                    target = root / 'controller'
                    target.mkdir()
                    (target / 'controller.json').write_text(json.dumps({
                        'schema': 'cpk.cloudflared-controller-acquisition.v1',
                        'source_commit': p['SOURCE'], 'source_tree': p['TREE'],
                        'dockerfile_sha256': p['INPUT_HASHES']['Dockerfile.test'],
                        'image_id': controller_id, 'build_exit': 0, 'build_log_sha256': 'c' * 64}))
                if name == 'qualification':
                    target = root / 'qualification'
                    target.mkdir()
                    (target / 'qualification.json').write_text(json.dumps({
                        'schema': 'cpk.cloudflared-managed-qualification.v1',
                        'candidate_id': candidate, 'source_commit': p['SOURCE'],
                        'source_tree': p['TREE'], 'controller_id': controller_id,
                        'run': 'cpk-managed-release-run.123456789abc', 'platform': 'linux/amd64',
                        'controller_receipt_sha256': report['controller_receipt_sha256'],
                        'recipe_sha256': p['INPUT_HASHES']['products/cloudflared_connector/Dockerfile.managed'],
                        'witness_sha256': p['INPUT_HASHES']['products/cloudflared_connector/tests/packaged_managed_witness.py'],
                        'status': 'pass', 'cleanup': 'verified', 'candidate_retained': True}))
                return 0
            with patch.dict(p['run'].__globals__, {
                    'preflight': lambda owner: report['executor'],
                    'daemon': lambda owner: report['executor'],
                    'observe': lambda owner: candidate, 'effect': effects}):
                self.assertEqual(p['run'](root, root, report), 0)
            self.assertEqual(len(commands), 3)
            self.assertEqual(commands[1][:2], ['./test.sh', '--managed-connector-controller'])
            self.assertEqual(commands[2][:4], ['./test.sh', '--managed-connector-candidate', '--image-id', candidate])
            result = json.loads((root / 'result.json').read_text())
            self.assertTrue(result['association_after'])
            self.assertEqual(result['cleanup'], 'verified')
            self.assertEqual(result['controller']['image_id'], controller_id)
            self.assertEqual(result['qualification']['candidate_id'], candidate)

    def test_unsupported_executor_observation_is_sanitized_and_retained(self):
        p = self.policy()
        observed = p['observed_executor'](
            {'ID': 'test-daemon', 'OSType': 'linux', 'Architecture': 'x86_64', 'Secrets': 'CANARY'},
            {'Version': '29.7.2', 'GitCommit': 'abcdef1234', 'Private': 'CANARY'})
        self.assertEqual(observed['version'], '29.7.2')
        self.assertEqual(observed['commit'], 'abcdef1234')
        self.assertNotIn('CANARY', json.dumps(observed))
        with self.assertRaises(ValueError):
            p['executor']({'ID': observed['daemon_id'], 'OSType': 'linux', 'Architecture': 'amd64'},
                          {'Version': observed['version'], 'GitCommit': observed['commit']})
