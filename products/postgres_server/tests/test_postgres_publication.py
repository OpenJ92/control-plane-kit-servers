"""Managed PostgreSQL artifact contracts; no database or registry effects."""
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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


if __name__=='__main__':unittest.main()
