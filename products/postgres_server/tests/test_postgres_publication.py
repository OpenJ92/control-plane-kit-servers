"""Managed PostgreSQL artifact contracts; no database or registry effects."""
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import io
from contextlib import redirect_stdout
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
SOURCE='a'*40
RECIPE='b'*64
ID='sha256:'+'c'*64
REFERENCE='ghcr.io/openj92/control-plane-kit-servers/postgres-server@sha256:'+'d'*64


def attrs():
    return dict(Id=ID,RepoDigests=[REFERENCE],Os='linux',Architecture='amd64',
        Config=dict(User='70:70',Entrypoint=[],Cmd=['python3','-m','control_plane_kit_servers_postgres_server.process'],
                    Labels={'org.opencontainers.image.revision':SOURCE,'org.openj92.cpk.recipe.sha256':RECIPE}))


class PostgresPublicationTests(unittest.TestCase):
    def policy(self):
        path=ROOT/'products/postgres_server/release.py'
        self.assertTrue(path.is_file(),'Managed PostgreSQL publication policy is missing')
        return runpy.run_path(str(path))

    def test_destination_is_explicit_and_source_bound(self):
        select=self.policy()['publication_destination']
        self.assertEqual(select('openj92','control-plane-kit-servers','managed-'+SOURCE,SOURCE),REFERENCE.split('@')[0]+':managed-'+SOURCE)
        for owner,package,tag in [('other','control-plane-kit-servers','managed-'+SOURCE),
                                  ('openj92','other','managed-'+SOURCE),('openj92','control-plane-kit-servers','latest')]:
            with self.assertRaises(ValueError):select(owner,package,tag,SOURCE)

    def test_private_package_and_absent_tag_are_required(self):
        check=self.policy()['package_check']
        package=dict(id=7,name='control-plane-kit-servers/postgres-server',package_type='container',visibility='private')
        check(package,[[]],SOURCE)
        version=dict(id=8,name=REFERENCE.split('@')[1],metadata={'container':{'tags':['managed-'+SOURCE]}})
        with self.assertRaises(ValueError):check(package,[[version]],SOURCE)
        check(package,[[version]],SOURCE,REFERENCE)
        for value in (None,dict(package,visibility='public'),dict(package,name='other')):
            with self.assertRaises(ValueError):check(value,[[]],SOURCE)

    def test_first_publication_requires_exact_not_found_response_and_failed_http_exit(self):
        policy=self.policy()
        self.assertIn('first_publication_check',policy)
        check=policy['first_publication_check']
        raw=b'HTTP/2.0 404 Not Found\r\nContent-Type: application/json\r\n\r\n{"message":"Package not found.","status":"404"}'
        check(raw,'1')
        for body,status in ((raw,'0'),(raw,'2'),(raw.replace(b'404 Not Found',b'200 OK'),'1'),
                            (raw.replace(b'404 Not Found',b'403 Forbidden'),'1'),
                            (raw.replace(b'404 Not Found',b'500 Server Error'),'1'),
                            (raw.replace(b'"status":"404"',b'"status":"404","status":"404"'),'1'),
                            (b'{"message":"Package not found.","status":"404"}','1'),
                            (raw+b'not json','1'),(b'x'*65537,'1')):
            with self.subTest(status=status,body=body[:30]):
                with self.assertRaises(ValueError):check(body,status)

    def test_first_publication_postcheck_requires_owning_repository(self):
        policy=self.policy()
        self.assertIn('first_published_package',policy)
        check=policy['first_published_package']
        package=dict(id=7,name='control-plane-kit-servers/postgres-server',package_type='container',visibility='private',
                     repository={'full_name':'OpenJ92/control-plane-kit-servers'})
        version=dict(id=8,name=REFERENCE.split('@')[1],metadata={'container':{'tags':['managed-'+SOURCE]}})
        check(package,[[version]],SOURCE,REFERENCE)
        for repository in (None,{}, {'full_name':'OpenJ92/other'}):
            with self.assertRaises(ValueError):check(dict(package,repository=repository),[[version]],SOURCE,REFERENCE)

    def test_published_identity_requires_exact_repository_source_recipe_platform_and_user(self):
        check=self.policy()['published_image']
        self.assertEqual(check(attrs(),REFERENCE,SOURCE,RECIPE),ID)
        for key,bad in [('RepoDigests',['other@'+REFERENCE.split('@')[1]]),('Architecture','arm64')]:
            value=attrs();value[key]=bad
            with self.assertRaises(ValueError):check(value,REFERENCE,SOURCE,RECIPE)
        for key,bad in [('User','postgres'),('Entrypoint',['docker-entrypoint.sh']),('Cmd',['postgres'])]:
            value=attrs();value['Config'][key]=bad
            with self.assertRaises(ValueError):check(value,REFERENCE,SOURCE,RECIPE)
        with self.assertRaises(ValueError):check(attrs(),REFERENCE,'f'*40,RECIPE)
        with self.assertRaises(ValueError):check(attrs(),REFERENCE,SOURCE,'f'*64)

    def witness(self):
        with patch.dict(os.environ,CPK_POSTGRES_TEST_RUN='unit',CPK_POSTGRES_HOST_RECORDS='/tmp/unit'):
            import live_postgres_image
        return live_postgres_image

    def test_published_mode_borrows_exact_image_without_build_or_image_removal(self):
        witness=self.witness()
        self.assertTrue(hasattr(witness,'select_image'),'Published PostgreSQL witness selection is missing')
        image=Mock(id=ID,attrs=attrs());client=Mock();client.images.get.return_value=image
        env=dict(CPK_POSTGRES_ARTIFACT_MODE='published-digest',CPK_POSTGRES_IMAGE=REFERENCE,
                 CPK_POSTGRES_SOURCE_REVISION=SOURCE,CPK_POSTGRES_RECIPE_SHA256=RECIPE)
        with patch.dict(os.environ,env):
            selected,owned=witness.select_image(client,'owned-test-tag')
        self.assertIs(selected,image);self.assertFalse(owned)
        client.images.get.assert_called_once_with(REFERENCE);client.images.build.assert_not_called()
        witness.cleanup_image(client,image,'owned-test-tag',owned)
        client.images.remove.assert_not_called()

    def test_identity_failure_precedes_fixtures_and_never_builds_or_deletes(self):
        witness=self.witness();client=Mock()
        value=attrs();value['Config']['User']='0'
        client.images.get.return_value=Mock(id=ID,attrs=value)
        env=dict(CPK_POSTGRES_ARTIFACT_MODE='published-digest',CPK_POSTGRES_IMAGE=REFERENCE,
                 CPK_POSTGRES_SOURCE_REVISION=SOURCE,CPK_POSTGRES_RECIPE_SHA256=RECIPE)
        with patch.dict(os.environ,env), patch.object(witness.docker,'from_env',return_value=client), \
                patch.object(witness,'prepare_files') as prepare:
            with self.assertRaises(ValueError):witness.main()
        prepare.assert_not_called();client.images.build.assert_not_called()
        client.images.remove.assert_not_called();client.images.pull.assert_not_called()

    def test_borrowed_success_is_reported_only_after_resource_and_fixture_cleanup(self):
        witness=self.witness()
        env=dict(CPK_POSTGRES_ARTIFACT_MODE='published-digest',CPK_POSTGRES_IMAGE=REFERENCE,
                 CPK_POSTGRES_SOURCE_REVISION=SOURCE,CPK_POSTGRES_RECIPE_SHA256=RECIPE)
        for failure in (None,'exercise','fixtures'):
            with self.subTest(failure=failure):
                client=Mock();client.images.get.return_value=Mock(id=ID,attrs=attrs())
                output=io.StringIO();order=[]
                def exercise(*args):
                    order.append('resource cleanup')
                    self.assertEqual(output.getvalue(),'')
                    if failure=='exercise':raise RuntimeError('resource cleanup failed')
                def cleanup():
                    order.append('fixture cleanup')
                    self.assertEqual(output.getvalue(),'')
                    if failure=='fixtures':raise RuntimeError('fixture cleanup failed')
                with patch.dict(os.environ,env), patch.object(witness.docker,'from_env',return_value=client), \
                        patch.object(witness,'exercise',side_effect=exercise), \
                        patch.object(witness,'cleanup_files',side_effect=cleanup), redirect_stdout(output):
                    if failure:
                        with self.assertRaises(RuntimeError):witness.main()
                    else:self.assertEqual(witness.main(),0)
                self.assertEqual(order,['resource cleanup','fixture cleanup'])
                if failure:self.assertEqual(output.getvalue(),'')
                else:self.assertIn('"owned_cleanup": "VERIFIED"',output.getvalue())
                client.images.remove.assert_not_called();client.images.pull.assert_not_called()
                client.images.build.assert_not_called()

    def test_missing_borrowed_image_and_mixed_modes_have_no_fallback(self):
        witness=self.witness();client=Mock();client.images.get.side_effect=RuntimeError('missing')
        env=dict(CPK_POSTGRES_ARTIFACT_MODE='published-digest',CPK_POSTGRES_IMAGE=REFERENCE,
                 CPK_POSTGRES_SOURCE_REVISION=SOURCE,CPK_POSTGRES_RECIPE_SHA256=RECIPE)
        with patch.dict(os.environ,env):
            with self.assertRaises(RuntimeError):witness.select_image(client,'tag')
        for mode in ('source-built','unknown'):
            with patch.dict(os.environ,dict(env,CPK_POSTGRES_ARTIFACT_MODE=mode)):
                with self.assertRaises(AssertionError):witness.select_image(client,'tag')
        client.images.build.assert_not_called();client.images.pull.assert_not_called()
        client.images.remove.assert_not_called()

    def test_publisher_stops_before_push_on_preflight_or_build_failure(self):
        """Run the real publisher with command fakes; never contact Docker/GH."""
        fake = '''import json, os, pathlib, subprocess, sys
name=pathlib.Path(sys.argv[0]).name;args=sys.argv[1:]
root=pathlib.Path(os.environ['FAKE_ROOT']);log=root/'calls'
with log.open('a') as out:out.write(name+' '+ ' '.join(args)+'\\n')
calls=log.read_text();fail=os.environ['FAIL_AT'];source='a'*40
repo='ghcr.io/openj92/control-plane-kit-servers/postgres-server'
if name=='git':
    if args==['rev-parse','HEAD']:print(source)
    elif args[0]=='archive':sys.stdout.write('fake tracked archive')
elif name=='gh':
    pushed='docker push ' in calls
    if '--include' in args:
        assert args[-1]=='users/OpenJ92/packages/container/control-plane-kit-servers%2Fpostgres-server'
        if fail=='transport':sys.exit(1)
        status=404
        if fail in ('existing','public','used') or (fail=='appeared' and calls.count('gh api --include')==2):status=200
        if fail in ('401','403','500'):status=int(fail)
        print('HTTP/2.0 '+str(status)+' '+('Not Found' if status==404 else 'Other'))
        print('Content-Type: application/json');print()
        print('broken json' if fail=='malformed' else json.dumps({'message':'Package not found.','status':str(status)}))
        sys.exit(0 if fail=='zero-exit-404' or status==200 else 1)
    if fail=='absent':sys.exit(1)
    if '--paginate' in args:
        if fail=='versions-404':sys.exit(1)
        version=dict(id=8,name='sha256:'+('e' if fail=='post-digest' else 'd')*64,
                     metadata={'container':{'tags':[] if fail=='post-tag' else ['managed-'+source]}})
        print(json.dumps([[version]] if pushed or fail=='used' else [[]]))
    else:
        print(json.dumps(dict(id=7,name='control-plane-kit-servers/postgres-server',package_type='container',
            repository={'full_name':'OpenJ92/other' if fail=='post-repository' else 'OpenJ92/control-plane-kit-servers'},
            visibility='public' if fail=='public' or (pushed and fail=='post-private') else 'private')))
elif name=='docker':
    if '/policy/release.py' in args:
        mounts=[a for a in args if ':/evidence:ro' in a]
        evidence=mounts[0].split(':/evidence:ro')[0]
        tail=args[args.index('/policy/release.py')+1:]
        tail=[evidence if a=='/evidence' else a for a in tail]
        sys.exit(subprocess.run([sys.executable,str(root/'products/postgres_server/release.py'),*tail]).returncode)
    elif args[0] in ('build','push'):
        if args[0]=='build':sys.stdin.read()
        if fail==args[0]:sys.exit(1)
    elif args[:2]==['image','inspect']:
        fmt=args[args.index('--format')+1]
        if fmt=='{{.Id}}':print('sha256:'+('e' if fail=='post-image' and 'docker push ' in calls else 'c')*64)
        elif fmt=='{{.Os}}/{{.Architecture}}':print('linux/amd64')
        elif fmt=='{{.Config.User}}':print('70:70')
        elif 'revision' in fmt:print(source)
        elif 'image.source' in fmt:print('https://github.com/OpenJ92/control-plane-kit-servers')
        elif 'recipe.sha256' in fmt:
            import hashlib
            print(hashlib.sha256((root/'products/postgres_server/Dockerfile').read_bytes()).hexdigest())
        elif 'RepoDigests' in fmt:print(repo+'@sha256:'+'d'*64)
        else:sys.exit(2)
else:sys.exit(2)
'''
        cases=[('postgres-server-managed',failure) for failure in ('none','public','absent','used','build','push','post-private')]
        cases += [('postgres-server-managed-first',failure) for failure in (
            'none','existing','public','used','appeared','401','403','500','transport','malformed','zero-exit-404',
            'build','push','post-private','post-repository','post-digest','post-tag','post-image','versions-404')]
        for product,failure in cases:
            with self.subTest(product=product,failure=failure), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'bin').mkdir();(root/'scripts').mkdir()
                (root/'products/postgres_server').mkdir(parents=True)
                for relative in ('scripts/publish_product_image.sh','scripts/select_repository_digest.sh',
                                 'products/postgres_server/release.py','products/postgres_server/Dockerfile'):
                    shutil.copyfile(ROOT/relative,root/relative)
                for command in ('git','gh','docker'):
                    path=root/'bin'/command
                    path.write_text('#!'+sys.executable+'\n'+fake);path.chmod(0o755)
                env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],FAKE_ROOT=str(root),FAIL_AT=failure,
                         GHCR_OWNER='openj92',GHCR_PACKAGE='control-plane-kit-servers')
                result=subprocess.run(['sh',str(root/'scripts/publish_product_image.sh'),
                                       product,'managed-'+SOURCE],env=env,capture_output=True,text=True)
                calls=(root/'calls').read_text()
                self.assertEqual(result.returncode==0,failure=='none',result.stderr)
                pushed=failure in ('none','push','post-private','post-repository','post-digest','post-tag','post-image','versions-404')
                self.assertEqual(calls.count('docker push '),int(pushed))
                if product.endswith('-first'):
                    self.assertEqual(calls.count('gh api --include'),2 if pushed or failure=='appeared' else 1)
                    self.assertEqual(calls.count('docker build '),int(pushed or failure in ('appeared','build')))
                if failure=='none':self.assertIn('reference='+REFERENCE,result.stdout)
                else:self.assertNotIn('postgres-server-managed reference=',result.stdout)

    def test_existing_named_or_labelled_resources_refuse_without_adoption_or_cleanup(self):
        witness=self.witness()
        for kind in ('containers','volumes','networks'):
            for matched_by in ('label','name'):
                with self.subTest(kind=kind,matched_by=matched_by):
                    client=Mock();existing=Mock()
                    for collection in ('containers','volumes','networks'):
                        getattr(client,collection).list.return_value=[]
                    getattr(client,kind).list.side_effect=lambda **kw: [existing] if matched_by in kw['filters'] else []
                    with patch.object(witness,'prepare_files') as prepare:
                        with self.assertRaises(AssertionError):witness.exercise(client,Mock())
                    prepare.assert_not_called();existing.remove.assert_not_called()
                    for collection in ('containers','volumes','networks'):
                        getattr(client,collection).create.assert_not_called()

    def test_same_basename_receipts_get_distinct_random_run_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir()
            docker=root/'bin/docker'
            docker.write_text('#!/bin/sh\nif [ "$1" = image ]; then printf "%s\\n" "'+ID+'"; fi\n')
            docker.chmod(0o755)
            git=root/'bin/git'
            git.write_text('#!/bin/sh\nif [ "$1" = rev-parse ]; then printf "%s\\n" "'+SOURCE+'"; fi\n')
            git.chmod(0o755)
            env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],
                     CPK_POSTGRES_ARTIFACT_MODE='published-digest',CPK_POSTGRES_IMAGE=REFERENCE,
                     CPK_POSTGRES_SOURCE_REVISION=SOURCE,CPK_POSTGRES_RECIPE_SHA256=RECIPE)
            identities=[]
            for parent in ('a','b'):
                (root/parent).mkdir();receipt=root/parent/'receipts'
                result=subprocess.run(['sh',str(ROOT/'scripts/postgres_artifact_shell.sh'),
                    '--postgres-published-image','--controller-image-id',ID,'--receipt-dir',str(receipt)],
                    env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                identities.append((receipt/'run.id').read_text().strip())
            self.assertNotEqual(*identities)


if __name__=='__main__':unittest.main()
