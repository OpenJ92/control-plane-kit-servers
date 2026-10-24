"""Synthetic receipt projection laws, never image/registry qualification."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE, TREE = 'a' * 40, 'b' * 40
CANDIDATE, CONTROLLER = 'sha256:' + 'c' * 64, 'sha256:' + 'd' * 64
CONFIG = 'sha256:' + 'e' * 64
REPOSITORY = 'ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector'
CANARY = 'PRIVATE-OWNER-CANARY'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def fixture(root):
    context = dict(schema='cpk.managed-release-context.v1', source_commit=SOURCE,
                   source_tree=TREE, run_id='123', attempt='1')
    controller = dict(schema='cpk.cloudflared-controller-acquisition.v1', source_commit=SOURCE,
        source_tree=TREE, dockerfile_sha256=digest(ROOT/'Dockerfile.test'), image_id=CONTROLLER,
        build_exit=0, build_log_sha256='f'*64)
    controller_path = put(root, 'controller/controller.json', controller)
    put(root, 'qualification/controller.json', controller)
    profile = dict(stage='stop_profile_inputs', container_id='1'*64, engine_id=CANARY,
        engine_version='28.0.4', engine_commit='6430e49', platform='linux', docker_sdk='7.2.0',
        configured_signal='SIGTERM', configured_timeout=None)
    witness = dict(stage='managed_cloudflared_controller', outcome='package_pass', live_qualification='pending',
        profile_container_id='1'*64, docker_sdk='7.2.0', engine_id=CANARY, engine_version='28.0.4',
        engine_commit='6430e49', stop_timeout=10, configured_stop_timeout=None,
        reviewed_engine_source='6430e49a55babd9b8f4d08e70ecb2b68900770fe', timeout_origin='engine_fixed_default',
        stop_signal='SIGTERM', term_time_ns=1000000000, kill_time_ns=11000000000, die_time_ns=11000000001,
        native_version='2026.6.1', installed={CANARY:'1.0'})
    log = root/'qualification/witness.log'
    log.write_text(json.dumps(profile)+'\n'+json.dumps(witness)+'\n')
    qualification = dict(schema='cpk.cloudflared-managed-qualification.v1', candidate_id=CANDIDATE,
        source_commit=SOURCE, status='pass', cleanup='verified', candidate_retained=True, run=CANARY,
        controller_id=CONTROLLER, source_tree=TREE,
        recipe_sha256=digest(ROOT/'products/cloudflared_connector/Dockerfile.managed'),
        witness_sha256=digest(ROOT/'products/cloudflared_connector/tests/packaged_managed_witness.py'),
        controller_receipt_sha256=digest(controller_path), platform='linux/amd64',
        created_containers=['1'*64], witness_log_sha256=digest(log))
    qpath = put(root, 'qualification/qualification.json', qualification)
    platform = dict(schemaVersion=2,mediaType='application/vnd.oci.image.manifest.v1+json',
        config={'mediaType':'application/vnd.oci.image.config.v1+json','digest':CONFIG,'size':10},layers=[])
    manifest = put(root,'remote-platform.json',platform)
    index = 'sha256:'+digest(manifest)
    (root/'remote-index.json').write_bytes(manifest.read_bytes())
    put(root,'remote-config.json',dict(os='linux',architecture='amd64',config={'Labels':{'org.opencontainers.image.revision':SOURCE}}))
    put(root,'build-metadata.json',{'containerimage.digest':index,'containerimage.config.digest':CONFIG,'buildx.build.ref':CANARY})
    for phase in ['preflight','before-push','published']:
        put(root,phase+'/validated.json',dict(package_id=3,visibility='private',tag='managed-'+SOURCE,
            digest=index if phase=='published' else None,version_id=4 if phase=='published' else None))
    put(root,'publication.json',dict(schema='cpk.cloudflared-managed-publication.v1',reference=REPOSITORY+'@'+index,
        candidate_id=CANDIDATE,source_commit=SOURCE,platform_manifest=index,config_digest=CONFIG,
        qualification_sha256=digest(qpath),visibility='private',status='verified'))
    (root/'candidate.id').write_text(CANDIDATE+'\n')
    for path in ['build.exit','push.exit','qualification/controller.exit']:
        (root/path).write_text('0\n')
    return context


class ManagedEvidenceTests(unittest.TestCase):
    def implementation(self):
        path=ROOT/'products/cloudflared_connector/release_evidence.py'
        self.assertTrue(path.is_file(), 'Closed managed evidence projection is not implemented')
        return runpy.run_path(str(path))

    def test_complete_projection_excludes_private_inputs_and_retains_actual_facts(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); context=fixture(root)
            value=project(root,ROOT,context,0)
            self.assertEqual(value['outcomes']['remote_publication'],'verified')
            self.assertEqual(value['outcomes']['projection'],'complete')
            self.assertEqual(value['outcomes']['retention'],'pending-upload')
            self.assertEqual(value['artifacts']['candidate_id'],CANDIDATE)
            self.assertEqual(value['stop']['term_to_kill_ns'],10000000000)
            self.assertEqual(value['stop']['kill_to_die_ns'],1)
            self.assertNotIn(CANARY,json.dumps(value))
            self.assertNotIn('created_containers',json.dumps(value))
            self.assertNotIn('engine_id',json.dumps(value))

    def test_later_producer_failure_and_push_exit_absence_do_not_erase_proved_publication(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); context=fixture(root)
            (root/'push.exit').unlink()
            value=project(root,ROOT,context,7)
            self.assertEqual(value['outcomes']['remote_publication'],'verified')
            self.assertEqual(value['outcomes']['producer_exit'],7)
            self.assertIsNone(value['outcomes']['push_command_exit'])

    def test_missing_or_nonzero_push_without_remote_proof_remains_unknown(self):
        project=self.implementation()['project']
        for exit_value in [None,'7\n']:
            with self.subTest(exit=exit_value),tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root);(root/'publication.json').unlink()
                if exit_value is None:(root/'push.exit').unlink()
                else:(root/'push.exit').write_text(exit_value)
                value=project(root,ROOT,context,None)
                self.assertEqual(value['outcomes']['remote_publication'],'unknown')
                self.assertEqual(value['outcomes']['cleanup'],'verified')
                self.assertEqual(value['outcomes']['projection'],'incomplete')

    def test_contradictory_receipts_cannot_establish_publication(self):
        project=self.implementation()['project']
        for name,key,bad in [('publication.json','candidate_id',CONTROLLER),
                             ('controller/controller.json','source_tree','9'*40),
                             ('qualification/qualification.json','cleanup','unverified'),
                             ('build-metadata.json','containerimage.config.digest',CONTROLLER),
                             ('published/validated.json','visibility','public')]:
            with self.subTest(file=name),tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root);v=json.loads((root/name).read_text());v[key]=bad;put(root,name,v)
                value=project(root,ROOT,context,0)
                self.assertEqual(value['outcomes']['remote_publication'],'unknown')
                self.assertNotEqual(value['outcomes']['projection'],'complete')

    def test_unknown_fields_duplicates_and_truncation_are_categorical(self):
        project=self.implementation()['project']
        for raw in ['{"schema":', '{"x":1,"x":2}',None]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root)
                if raw is None:
                    value=json.loads((root/'publication.json').read_text());value[CANARY]=CANARY;put(root,'publication.json',value)
                else:(root/'publication.json').write_text(raw)
                value=project(root,ROOT,context,0)
                self.assertEqual(value['outcomes']['projection'],'invalid')
                self.assertEqual(value['failure'],'invalid-evidence')
                self.assertNotIn(CANARY,json.dumps(value))

    def test_witness_duplicate_or_private_identity_conflict_refuses(self):
        project=self.implementation()['project']
        for conflict in [False,True]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root);p=root/'qualification/witness.log';lines=p.read_text().splitlines()
                if conflict:
                    final=json.loads(lines[1]);final['engine_id']='different';lines[1]=json.dumps(final)
                else:lines.append(lines[1])
                p.write_text('\n'.join(lines)+'\n')
                q=json.loads((root/'qualification/qualification.json').read_text());q['witness_log_sha256']=digest(p);qpath=put(root,'qualification/qualification.json',q)
                pub=json.loads((root/'publication.json').read_text());pub['qualification_sha256']=digest(qpath);put(root,'publication.json',pub)
                value=project(root,ROOT,context,0)
                self.assertEqual(value['outcomes']['remote_publication'],'unknown')
                self.assertIsNone(value['stop'])

    def test_symlink_ancestor_and_boolean_context_fail_without_echo(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);root=home/'real';root.mkdir();context=fixture(root);link=home/'link';link.symlink_to(root,target_is_directory=True)
            for receipts,c in [(link,context),(root,dict(context,attempt=True))]:
                with self.assertRaisesRegex(ValueError,'^Invalid release evidence$'):
                    project(receipts,ROOT,c,0)

    def test_oversized_and_symlinked_receipt_is_invalid_not_read_or_exported(self):
        project=self.implementation()['project']
        for mode in ['symlink','oversize']:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root);p=root/'publication.json';p.unlink()
                if mode=='symlink':p.symlink_to(root/'qualification/qualification.json')
                else:p.write_text('x'*65537)
                value=project(root,ROOT,context,0)
                self.assertEqual(value['outcomes']['projection'],'invalid')
                self.assertEqual(value['outcomes']['remote_publication'],'unknown')

    def test_output_keysets_are_closed(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);value=project(root,ROOT,fixture(root),0)
            self.assertEqual(set(value),{'schema','source','workflow','outcomes','artifacts',
                'controller_receipt_sha256','qualification_receipt_sha256','stop','native_version','package_checks','failure'})
            self.assertEqual(set(value['outcomes']),{'producer_exit','push_command_exit','remote_publication',
                'qualification','cleanup','candidate_retained_before_runner_disposal','projection','retention'})
            self.assertEqual(set(value['stop']),{'engine_version','engine_commit','reviewed_engine_source','docker_sdk',
                'platform','configured_timeout','effective_timeout','timeout_origin','signal','term_to_kill_ns','kill_to_die_ns','owner_witness'})

    def test_index_manifest_links_to_selected_platform(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);context=fixture(root)
            platform='sha256:'+digest(root/'remote-platform.json')
            index=put(root,'remote-index.json',dict(schemaVersion=2,mediaType='application/vnd.oci.image.index.v1+json',
                manifests=[dict(mediaType='application/vnd.oci.image.manifest.v1+json',digest=platform,size=10,
                                platform=dict(os='linux',architecture='amd64'))]))
            index_digest='sha256:'+digest(index)
            meta=json.loads((root/'build-metadata.json').read_text());meta['containerimage.digest']=index_digest;put(root,'build-metadata.json',meta)
            pub=json.loads((root/'publication.json').read_text());pub['reference']=REPOSITORY+'@'+index_digest;put(root,'publication.json',pub)
            pkg=json.loads((root/'published/validated.json').read_text());pkg['digest']=index_digest;put(root,'published/validated.json',pkg)
            result=project(root,ROOT,context,0)
            self.assertEqual(result['outcomes']['remote_publication'],'verified')
            self.assertEqual(result['artifacts']['platform_manifest'],platform)

    def test_explicit_timeout_does_not_bypass_typed_profile_or_timing(self):
        project=self.implementation()['project']
        for defect in [None,'version','timeout','timing']:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root);log=root/'qualification/witness.log';p,w=map(json.loads,log.read_text().splitlines())
                p['configured_timeout']=10;w.update(configured_stop_timeout=10,timeout_origin='container',reviewed_engine_source=None)
                if defect=='version':p['engine_version']=w['engine_version']=CANARY
                if defect=='timeout':p['configured_timeout']=w['configured_stop_timeout']=True
                if defect=='timing':w['kill_time_ns']=w['term_time_ns']+1
                log.write_text(json.dumps(p)+'\n'+json.dumps(w)+'\n')
                q=json.loads((root/'qualification/qualification.json').read_text());q['witness_log_sha256']=digest(log);qpath=put(root,'qualification/qualification.json',q)
                pub=json.loads((root/'publication.json').read_text());pub['qualification_sha256']=digest(qpath);put(root,'publication.json',pub)
                result=project(root,ROOT,context,0)
                self.assertEqual(result['outcomes']['remote_publication'],'verified' if defect is None else 'unknown')
                self.assertNotIn(CANARY,json.dumps(result))

    def test_recursive_bounds_and_remote_revision_mismatch(self):
        project=self.implementation()['project']
        for defect in ['depth','count','string','revision']:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                root=Path(d);context=fixture(root)
                meta=json.loads((root/'build-metadata.json').read_text())
                if defect=='depth':
                    deep=None
                    for _ in range(32):deep=[deep]
                    meta['buildx.build.provenance']=deep
                elif defect=='count':meta['buildx.build.provenance']=[0]*20001
                elif defect=='string':meta['buildx.build.ref']='x'*8193
                else:put(root,'remote-config.json',dict(os='linux',architecture='amd64',config={'Labels':{'org.opencontainers.image.revision':'f'*40}}))
                put(root,'build-metadata.json',meta)
                result=project(root,ROOT,context,0)
                self.assertEqual(result['outcomes']['remote_publication'],'unknown')
                self.assertEqual(result['outcomes']['projection'],'invalid')

    def test_wrapper_captures_once_and_exports_only_fixed_file_without_echo(self):
        import contextlib
        import io
        import subprocess
        from unittest.mock import patch
        api=self.implementation()
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);source=home/'source';source.mkdir();(source/'scripts').mkdir()
            (source/'scripts/publish_product_image.sh').write_text('#!/bin/sh\nprintf "'+CANARY+'\\n"\nprintf "'+CANARY+'\\n" >&2\nexit 7\n')
            real_run=subprocess.run
            def recorded_run(args,**kwargs):
                if args[0]=='git':
                    self.assertEqual(kwargs['cwd'],source)
                    output={('status','--porcelain'):'',('rev-parse','HEAD'):SOURCE,
                            ('rev-parse','HEAD^{tree}'):TREE}[tuple(args[1:])]
                    return subprocess.CompletedProcess(args,0,output+'\n','')
                return real_run(args,**kwargs)
            with patch.object(subprocess,'run',side_effect=recorded_run):
                attempt=api['prepare'](source,home,'123','1')
                with contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(api['run_attempt'](attempt,source),7)
                    with self.assertRaisesRegex(ValueError,'^Invalid release evidence$'):api['run_attempt'](attempt,source)
            self.assertNotIn(CANARY,out.getvalue()+err.getvalue())
            self.assertIn(CANARY,(attempt/'producer.log').read_text())
            # Export uses actual owner source in separate fixture case; no release invoked.
            receipts=home/'receipts';receipts.mkdir();context=fixture(receipts)
            export=home/'public'
            result=api['export'](receipts,ROOT,context,7,export)
            self.assertEqual([p.name for p in export.iterdir()],['managed-release-evidence.json'])
            self.assertEqual(result['outcomes']['remote_publication'],'verified')
            self.assertNotIn(CANARY,(export/'managed-release-evidence.json').read_text())
            with self.assertRaisesRegex(ValueError,'^Invalid release evidence$'):api['export'](receipts,ROOT,context,7,export)

    def test_known_owner_failure_is_incomplete_and_keeps_cleanup_observation(self):
        project=self.implementation()['project']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);context=fixture(root)
            records=[dict(stage='managed_cloudflared_helper',mode='contents',exit_code=1,result='valid_error',reason='native_version'),
                dict(stage='managed_cloudflared_controller_failure',outcome='unqualified',role='primary',phase='artifact',operation='result_read',helper_mode='contents'),
                dict(stage='managed_cloudflared_controller',outcome='unqualified',reason='package_inspection_failed',states=[])]
            log=root/'qualification/witness.log';log.write_text(''.join(json.dumps(r)+'\n' for r in records))
            q=json.loads((root/'qualification/qualification.json').read_text())
            q.update(status='fail',witness_log_sha256=digest(log));put(root,'qualification/qualification.json',q)
            (root/'publication.json').unlink()
            value=project(root,ROOT,context,1)
            self.assertEqual(value['outcomes']['projection'],'incomplete')
            self.assertEqual(value['outcomes']['qualification'],'fail')
            self.assertEqual(value['outcomes']['cleanup'],'verified')
            self.assertIsNone(value['stop'])
            self.assertIsNone(value['native_version'])
            self.assertNotIn('package_inspection_failed',json.dumps(value))

    def test_cli_malformed_exit_keeps_proved_publication_in_closed_artifact(self):
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        for raw in ['', 'PRIVATE-OWNER-CANARY', '2x\n']:
            with self.subTest(raw=raw),tempfile.TemporaryDirectory() as d:
                home=Path(d);receipts=home/'receipts';receipts.mkdir();context=fixture(receipts)
                put(home,'context.json',context);(home/'producer.exit').write_text(raw)
                api=self.implementation();main=api['main']
                with patch.dict(main.__globals__,clean_context=lambda *args:context),patch.object(sys,'argv',['evidence','export','--attempt',str(home)]),contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(main(),1)
                artifact=home/'public/managed-release-evidence.json'
                self.assertTrue(artifact.is_file(),'Malformed optional exit must not suppress proved publication')
                value=json.loads(artifact.read_text())
                self.assertEqual(value['outcomes']['remote_publication'],'verified')
                self.assertEqual(value['outcomes']['projection'],'invalid')
                self.assertIsNone(value['outcomes']['producer_exit'])
                self.assertNotIn(CANARY,artifact.read_text()+err.getvalue())

    def test_workflow_selectors_and_upload_contract(self):
        # Inspect the small authored mapping, not runner execution or upload success.
        workflow=(ROOT/'.github/workflows/publish-product-image.yml').read_text()
        steps={}
        for chunk in workflow.split('      - name: ')[1:]:
            lines=chunk.splitlines();steps[lines[0]]='\n'.join(lines[1:])
        ordinary=steps['Publish product image']
        self.assertIn("if: inputs.product_id != 'cloudflared-connector-managed'",ordinary)
        self.assertIn('run: sh scripts/publish_product_image.sh "$PRODUCT_ID" "$IMAGE_TAG"',ordinary)
        managed="inputs.product_id == 'cloudflared-connector-managed'"
        for name in ['Prepare managed release evidence','Publish selected managed product']:
            self.assertIn('if: '+managed,steps[name])
        condition="if: always() && "+managed+" && steps.managed-evidence.outcome == 'success'"
        for name in ['Project managed release evidence','Retain closed managed release evidence']:
            self.assertIn(condition,steps[name])
        upload=steps['Retain closed managed release evidence']
        self.assertIn('uses: actions/upload-artifact@v4',upload)
        paths=[line.strip() for line in upload.splitlines() if line.strip().startswith('path:')]
        self.assertEqual(paths,['path: ${{ steps.managed-evidence.outputs.attempt }}/public/managed-release-evidence.json'])
        self.assertIn('retention-days: 30',upload)
        self.assertIn('if-no-files-found: error',upload)
        self.assertNotIn('continue-on-error',workflow)

    def test_prepare_refuses_temp_inside_checkout_before_creating_attempt(self):
        from unittest.mock import patch
        prepare=self.implementation()['prepare']
        with tempfile.TemporaryDirectory() as d:
            source=Path(d);nested=source/'ignored-temp';nested.mkdir()
            context=dict(schema='cpk.managed-release-context.v1',source_commit=SOURCE,source_tree=TREE,run_id='123',attempt='1')
            with patch.dict(prepare.__globals__,clean_context=lambda *args:context):
                for temp in (source,nested):
                    with self.subTest(temp=temp),self.assertRaisesRegex(ValueError,'^Invalid release evidence$'):
                        prepare(source,temp,'123','1')
            self.assertEqual(list(nested.iterdir()),[])
