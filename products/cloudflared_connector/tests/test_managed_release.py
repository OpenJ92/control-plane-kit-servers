"""Release orchestration laws; command doubles do not qualify an OCI artifact."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ManagedReleaseRoutingTests(unittest.TestCase):
    def run_owner(self, arguments, ignored=False, unsupported=None):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            calls = home / 'calls'
            docker = home / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nexit 91\n')
            docker.chmod(0o755)
            if ignored:
                import json
                git = home / 'git'
                ignored_path = 'products/.coverage' if ignored == 'cache' else 'products/cloudflared_connector/src/__pycache__/untracked.pyc'
                git.write_text('#!/bin/sh\ncase "$*" in *--ignored*) echo ' + ignored_path + ';; esac\n')
                git.chmod(0o755)
                (home/'controller.json').write_text(json.dumps(dict(
                    schema='cpk.cloudflared-controller-acquisition.v1',image_id='sha256:'+'a'*64,
                    source_commit='b'*40,source_tree='c'*40,dockerfile_sha256='d'*64,
                    build_exit=0,build_log_sha256='e'*64)))
            if unsupported:
                git = home / 'git'
                git.write_text('#!/bin/sh\ncase "$1" in\n'
                    'rev-parse) echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;\n'
                    + ('ls-tree) echo "160000 commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa submodule";;\n'
                       if unsupported == 'submodule' else 'cat-file) exit 1;;\n')
                    + 'esac\n')
                git.chmod(0o755)
            replacements = {'@receipts':str(home/'new-receipts'), '@controller-receipt':str(home/'controller.json')}
            arguments = [replacements.get(item,item) for item in arguments]
            environment = dict(os.environ, PATH=str(home) + os.pathsep + os.environ['PATH'], CALLS=str(calls))
            result = subprocess.run(['sh', str(ROOT / 'test.sh'), *arguments], cwd=ROOT,
                                    env=environment, capture_output=True, text=True, timeout=10)
            return result, calls.read_text() if calls.exists() else ''

    def test_missing_candidate_arguments_refuse_before_any_docker_call(self):
        result, calls = self.run_owner(['--managed-connector-candidate'])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, '')

    def test_ignored_bytecode_refuses_before_controller_or_source_import(self):
        result, calls = self.run_owner([
            '--managed-connector-release-tests', '--controller-image-id', 'sha256:'+'a'*64,
            '--controller-receipt', '@controller-receipt', '--receipt-dir', '@receipts'], ignored=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, '')

    def test_incomplete_or_submodule_context_refuses_before_build(self):
        for unsupported in ('submodule', 'missing-input'):
            with self.subTest(unsupported=unsupported):
                result, calls = self.run_owner([
                    '--managed-connector-controller', '--receipt-dir', '@receipts'], unsupported=unsupported)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(calls, '')

    def test_non_executable_ignored_report_does_not_block_source_mount(self):
        result, calls = self.run_owner([
            '--managed-connector-release-tests', '--controller-image-id', 'sha256:'+'a'*64,
            '--controller-receipt', '@controller-receipt', '--receipt-dir', '@receipts'], ignored='cache')
        # The Docker double deliberately refuses inspection; admission reached it.
        self.assertNotEqual(result.returncode, 2)
        self.assertIn('image inspect', calls)

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


class ManagedCandidateOwnershipTests(unittest.TestCase):
    def test_success_and_failure_retain_borrowed_image_and_receipt(self):
        import json
        import runpy
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import packaged_managed_witness as witness
        policy = runpy.run_path(str(ROOT / 'products/cloudflared_connector/release.py'))
        candidate = 'sha256:'+'a'*64
        controller = 'sha256:'+'b'*64
        source = 'c'*40
        tree = 'd'*40
        for failed, close_failed in ((False, False), (True, False), (True, True)):
            with self.subTest(failed=failed, close_failed=close_failed), tempfile.TemporaryDirectory() as directory:
                evidence = Path(directory)
                (evidence/'fixtures').mkdir()
                record = dict(schema='cpk.cloudflared-controller-acquisition.v1',source_commit=source,
                              source_tree=tree,image_id=controller,build_exit=0,build_log_sha256='e'*64,
                              dockerfile_sha256=policy['digest_file'](ROOT/'Dockerfile.test'))
                (evidence/'controller.json').write_text(json.dumps(record))
                image = SimpleNamespace(id=candidate, attrs={'Os':'linux','Architecture':'amd64',
                    'Config':{'Labels':{'org.opencontainers.image.revision':source}}})
                client = Mock()
                client.images.get.return_value = image
                client.containers.list.return_value = []
                if close_failed:
                    client.close.side_effect = RuntimeError('close failed')
                env = dict(CPK_MANAGED_IMAGE=candidate,CPK_MANAGED_SOURCE=source,
                           CPK_MANAGED_TEST_RUN='owned-test',CPK_RELEASE_CONTROLLER=controller,
                           CPK_RELEASE_TREE=tree)
                with patch.dict(os.environ,env), patch('docker.from_env',return_value=client), \
                     patch.object(witness,'verify_image'), patch.object(witness,'controller',
                         side_effect=RuntimeError('private detail must not escape') if failed else None):
                    if failed:
                        with self.assertRaises(ValueError):
                            policy['qualify'](ROOT,evidence)
                    else:
                        policy['qualify'](ROOT,evidence)
                final = json.loads((evidence/'qualification.json').read_text())
                self.assertEqual(final['status'], 'fail' if failed else 'pass')
                self.assertEqual(final['cleanup'], 'unverified' if close_failed else 'verified')
                self.assertTrue(final['candidate_retained'])
                self.assertEqual((evidence/'fixtures').exists(), close_failed)
                self.assertNotIn('private detail', (evidence/'qualification.json').read_text())
                client.images.remove.assert_not_called()
                client.images.build.assert_not_called()
                client.images.pull.assert_not_called()


class ManagedProducerOrderingTests(unittest.TestCase):
    def producer(self, fail_qualification=False, substitute=False):
        import json
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            shutil.copy(ROOT/'scripts/cloudflared_managed_publish.sh', root/'scripts')
            binary = root/'bin'
            binary.mkdir()
            calls = root/'calls'
            source = 'a'*40
            candidate = 'sha256:'+'b'*64
            controller = 'sha256:'+'c'*64
            (binary/'git').write_text('#!/bin/sh\ncase "$1" in status|ls-files|ls-tree|cat-file) exit 0;; archive) echo exact-source-context;; rev-parse) printf "%s\\n" "$SOURCE";; *) exit 92;; esac\n')
            (binary/'gh').write_text('#!/bin/sh\ncase "$*" in *versions*) echo "[[]]";; *) echo \'{"name":"control-plane-kit-servers/cloudflared-connector","package_type":"container","visibility":"private"}\';; esac\n')
            (binary/'tar').write_text('#!/bin/sh\nexit 0\n')
            (root/'test.sh').write_text('''#!/bin/sh
printf 'test %s\n' "$1" >> "$CALLS"
case "$1" in
 --managed-connector-controller)
   mkdir -p "$3"
   printf '%s\n' "$CONTROLLER" > "$3/image.id"
   echo '{}' > "$3/controller.json";;
 --managed-connector-candidate) exit "$QUALIFICATION_EXIT";;
 *) exit 93;;
esac
''')
            (binary/'docker').write_text('''#!/bin/sh
printf 'docker %s\n' "$*" >> "$CALLS"
case "$1 $2" in
 'buildx build')
  shift 2
  while [ "$#" -gt 0 ]; do
   case "$1" in --iidfile) printf '%s\n' "$CANDIDATE" > "$2"; shift;;
   --metadata-file) echo '{}' > "$2"; shift;; esac
   shift
  done;;
 'image inspect')
   case "$*" in *revision*) printf '%s\n' "$SOURCE";;
   *) if [ "$SUBSTITUTE" = 1 ] && [ -f "$CASE_ROOT/tagged" ]; then echo 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'; else printf '%s\n' "$CANDIDATE"; fi;; esac;;
 'tag '*) touch "$CASE_ROOT/tagged";;
 'run '*) exit 0;;
 'push '*) exit 94;;
 *) exit 95;;
esac
''')
            for path in [*binary.iterdir(), root/'test.sh']:
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(binary)+os.pathsep+os.environ['PATH'],
                       SOURCE=source,CANDIDATE=candidate,CONTROLLER=controller,CALLS=str(calls),
                       CASE_ROOT=str(root),SUBSTITUTE='1' if substitute else '0',
                       QUALIFICATION_EXIT='7' if fail_qualification else '0',
                       CPK_MANAGED_RELEASE_RECEIPTS=str(root/'evidence'))
            result = subprocess.run(['sh',str(root/'scripts/cloudflared_managed_publish.sh'),'managed-'+source],
                                    cwd=root,env=env,capture_output=True,text=True,timeout=10)
            return result, calls.read_text()

    def test_qualification_failure_never_tags_or_pushes(self):
        result, calls = self.producer(fail_qualification=True)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('test --managed-connector-candidate', calls)
        self.assertNotIn('docker tag ', calls)
        self.assertNotIn('docker push ', calls)
        self.assertEqual(calls.count('docker buildx build '), 1)

    def test_tag_substitution_refuses_without_push_or_rebuild(self):
        result, calls = self.producer(substitute=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('docker tag ', calls)
        self.assertNotIn('docker push ', calls)
        self.assertEqual(calls.count('docker buildx build '), 1)


class ManagedCleanupOwnershipTests(unittest.TestCase):
    def test_unrecorded_same_label_is_never_removed_even_on_failure(self):
        import runpy
        from unittest.mock import Mock
        cleanup = runpy.run_path(str(ROOT/'products/cloudflared_connector/release.py'))['cleanup_owned']
        foreign = Mock(id='b'*64)
        client = Mock()
        client.containers.list.return_value = [foreign]
        with self.assertRaises(ValueError):
            cleanup(client, 'collision', ['a'*64])
        foreign.remove.assert_not_called()
        client.containers.get.assert_not_called()

    def test_recorded_id_with_changed_label_is_not_removed(self):
        import runpy
        from unittest.mock import Mock
        cleanup = runpy.run_path(str(ROOT/'products/cloudflared_connector/release.py'))['cleanup_owned']
        container = Mock(id='a'*64)
        container.attrs = {'Config':{'Labels':{'org.openj92.cpk.test-run':'another-run'}}}
        client = Mock()
        client.containers.list.return_value = []
        client.containers.get.return_value = container
        with self.assertRaises(ValueError):
            cleanup(client, 'owned-run', ['a'*64])
        container.remove.assert_not_called()
