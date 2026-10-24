"""Command-boundary laws for the existing product-local owning shell."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
IMAGE = 'sha256:' + 'a' * 64
NETWORK = 'b' * 64
CONTAINER = 'c' * 64

# This seam observes shell effects; ordinary CI proves real network attachment.
DOCKER = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a=sys.argv[1:]; root=pathlib.Path(os.environ['FAKE_STATE'])
p=root/'state.json'; s=json.loads(p.read_text()) if p.exists() else {}
with (root/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\n')
failure=os.environ.get('FAKE_FAILURE','')
image='sha256:'+'a'*64; net='b'*64; cid='c'*64
def save(): p.write_text(json.dumps(s))
def opt(key): return a[a.index(key)+1]
def labels(): return dict(a[i+1].split('=',1) for i,x in enumerate(a) if x=='--label')
if a[:2]==['image','inspect']: print(image)
elif a[:2]==['network','ls']:
    if failure=='collision': print('foreign')
elif a[:2]==['network','create']:
    s['network']={'name':a[-1], 'labels':labels(), 'internal':'--internal' in a}; save()
    if failure=='ambiguous-create': sys.exit(1)
    print(net)
elif a[:2]==['network','inspect']:
    n=s['network']; endpoints=1 if failure=='foreign-endpoint' else int('container' in s)
    owner=n['labels'].get('org.openj92.cpk.controller-run','')
    if failure=='foreign-owner': owner='foreign'
    print(net+'|'+n['name']+'|'+str(n['internal']).lower()+'|'+owner+'|'+str(endpoints))
elif a[:2]==['network','rm']:
    if failure=='cleanup': sys.exit(1)
    s.pop('network'); save()
elif a[0]=='create':
    assert opt('--network')==net
    assert '--pull' in a and opt('--pull')=='never'
    env=dict(a[i+1].split('=',1) for i,x in enumerate(a) if x=='-e' and '=' in a[i+1])
    run=env['CPK_POSTGRES_TEST_RUN']; n=s['network']
    assert run not in n['name']
    assert n['labels'].get('org.openj92.cpk.test-run')!=run
    s['container']={'name':opt('--name'),'labels':labels(),'image':image}; save()
    pathlib.Path(opt('--cidfile')).write_text(cid)
    print(cid)
elif a[0]=='start':
    if failure=='interrupt': os.kill(os.getppid(),15)
    sys.exit(7 if failure=='controller' else 0)
elif a[0]=='ps':
    if 'container' in s: print(cid)
elif a[:2]==['container','inspect']:
    c=s['container']; print(cid+'|/'+c['name']+'|'+c['labels']['org.openj92.cpk.controller-run']+'|'+c['image'])
elif a[:2]==['container','rm']:
    s.pop('container'); save()
elif a[0]=='run':
    assert opt('--network')=='none'
else: raise AssertionError(a)
'''


class PostgresArtifactShellTests(unittest.TestCase):
    def invoke(self, mode='published', failure='', extra=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root/'bin').mkdir()
        for name, text in [('docker', DOCKER), ('git', '#!/bin/sh\nprintf "%s\\n" checkpoint\n')]:
            path=root/'bin'/name; path.write_text(text); path.chmod(0o755)
        env=dict(os.environ, PATH=str(root/'bin')+':'+os.environ['PATH'], FAKE_STATE=str(root), FAKE_FAILURE=failure)
        for key in ('CPK_POSTGRES_ARTIFACT_MODE','CPK_POSTGRES_IMAGE','CPK_POSTGRES_SOURCE_REVISION','CPK_POSTGRES_RECIPE_SHA256'):
            env.pop(key, None)
        if mode=='published':
            env.update(CPK_POSTGRES_ARTIFACT_MODE='published-digest', CPK_POSTGRES_IMAGE='repository@sha256:'+'d'*64,
                       CPK_POSTGRES_SOURCE_REVISION='e'*40, CPK_POSTGRES_RECIPE_SHA256='f'*64)
        env.update(extra or {})
        selector={'published':'--postgres-published-image','source':'--postgres-source-image','unit':'--postgres-release-tests'}[mode]
        receipt=root/'receipt'
        result=subprocess.run(['sh',str(ROOT/'scripts/postgres_artifact_shell.sh'),selector,
                               '--controller-image-id',IMAGE,'--receipt-dir',str(receipt)],
                              env=env,capture_output=True,text=True,timeout=15)
        calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()] if (root/'calls.jsonl').exists() else []
        state=json.loads((root/'state.json').read_text()) if (root/'state.json').exists() else {}
        return result, receipt, calls, state

    def test_effectful_modes_share_internal_launch_and_exact_cleanup(self):
        for mode in ('source','published'):
            with self.subTest(mode=mode):
                result, receipt, calls, state=self.invoke(mode)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(state,{})
                self.assertFalse((receipt/'fixtures').exists())
                self.assertEqual((receipt/'qualification.exit').read_text().strip(),'0')
                create=next(c for c in calls if c[0]=='create')
                self.assertEqual(create[create.index('--network')+1],NETWORK)
                self.assertNotIn('build',[c[0] for c in calls]); self.assertNotIn('pull',[c[0] for c in calls])
                self.assertLess(next(i for i,c in enumerate(calls) if c[:2]==['container','rm']),
                                next(i for i,c in enumerate(calls) if c[:2]==['network','rm']))
                self.assertIn('CPK_POSTGRES_ARTIFACT_MODE='+('source-built' if mode=='source' else 'published-digest'),create)

    def test_failure_and_interruption_keep_failure_and_cleanup_owned_resources(self):
        for failure in ('controller','interrupt'):
            with self.subTest(failure=failure):
                result, receipt, calls, state=self.invoke(failure=failure)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(state,{})
                self.assertNotEqual((receipt/'qualification.exit').read_text().strip(),'0')

    def test_uncertain_or_foreign_resources_are_not_force_cleaned(self):
        for failure in ('collision','ambiguous-create','foreign-owner','foreign-endpoint','cleanup'):
            with self.subTest(failure=failure):
                result, receipt, calls, state=self.invoke(failure=failure)
                self.assertNotEqual(result.returncode,0)
                if failure!='cleanup': self.assertFalse(any(c[:2]==['network','rm'] for c in calls))
                if failure in ('collision','ambiguous-create','foreign-owner','foreign-endpoint'):
                    self.assertFalse(any(c[0]=='start' for c in calls))

    def test_source_rejects_published_inputs_before_effects(self):
        result, _, calls, _=self.invoke('source',extra={'CPK_POSTGRES_IMAGE':'borrowed'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])

    def test_unit_mode_remains_daemon_free_and_network_none(self):
        result, _, calls, _=self.invoke('unit')
        self.assertEqual(result.returncode,0,result.stderr)
        run=next(c for c in calls if c[0]=='run')
        self.assertEqual(run[run.index('--network')+1],'none')
        self.assertFalse(any('docker.sock' in arg for arg in run))
        self.assertFalse(any(c[0] in ('network','create','start') for c in calls))
