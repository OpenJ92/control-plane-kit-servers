"""Same-push manifest anchor laws; synthetic inputs, no registry effects."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE, TREE = 'a'*40, 'b'*40
CANDIDATE, DIGEST = 'sha256:'+'c'*64, 'sha256:'+'d'*64
DESTINATION = 'ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector:managed-'+SOURCE
LINE = f'managed-{SOURCE}: digest: {DIGEST} size: 123\n'.encode()
VERSION = dict(Version='28.0.4', GitCommit='6430e49', Os='linux', Arch='amd64')
INFO = dict(ID='test-daemon', ServerVersion='28.0.4', OSType='linux', Driver='overlay2',
            DriverStatus=[['Backing Filesystem','extfs']])


class SamePushAnchorTests(unittest.TestCase):
    def owner(self, name):
        api=runpy.run_path(str(ROOT/'products/cloudflared_connector/release.py'))
        self.assertTrue(name in api, 'Same-push integrity owner is not implemented')
        return api[name]

    def test_exact_terminal_result_binds_source_candidate_destination_and_bytes(self):
        parse=self.owner('push_receipt')
        raw=b'The push refers to repository [ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector]\n0123456789ab: Pushed\n'+LINE
        value=parse(raw,0,SOURCE,TREE,CANDIDATE,DESTINATION)
        self.assertEqual(value,dict(schema='cpk.cloudflared-managed-push.v1',
            source_commit=SOURCE,source_tree=TREE,candidate_id=CANDIDATE,destination=DESTINATION,
            manifest_digest=DIGEST,manifest_size=123,transcript_sha256=hashlib.sha256(raw).hexdigest()))

    def test_ambiguous_malformed_nonterminal_and_unbounded_output_refuses(self):
        parse=self.owner('push_receipt')
        cases=[b'', LINE*2, LINE+b'extra\n', LINE.replace(b'managed-',b'wrong-'),
               LINE.replace(b'123',b'0'),LINE.replace(b'123',b'0123'),
               LINE.replace(b'123',b'1048577'),LINE.replace(b'\n',b'\r\n'),
               b'\x1b[0m'+LINE, b'bad: digest: nope size: 1\n'+LINE,
               b'x'*1048577, LINE[:-1]]
        for raw in cases:
            with self.subTest(raw=raw[:80]), self.assertRaisesRegex(ValueError,'^Managed release evidence is invalid$'):
                parse(raw,0,SOURCE,TREE,CANDIDATE,DESTINATION)
        for code in (None,True,1,255):
            with self.subTest(code=code), self.assertRaises(ValueError):
                parse(LINE,code,SOURCE,TREE,CANDIDATE,DESTINATION)
        with self.assertRaises(ValueError):parse(LINE,0,'f'*40,TREE,CANDIDATE,DESTINATION)

    def test_only_reviewed_classic_producer_path_is_supported(self):
        profile=self.owner('producer_profile')
        profile(VERSION,INFO)
        for version,info in [(dict(VERSION,Version='29.0.0'),INFO),
                             (dict(VERSION,GitCommit='unknown'),INFO),
                             (dict(VERSION,Arch='arm64'),INFO),
                             (VERSION,dict(INFO,Driver='overlayfs')),
                             (VERSION,dict(INFO,DriverStatus=[['driver-type','io.containerd.snapshotter.v1']])),
                             (VERSION,dict(INFO,ServerVersion='28.5.1')),
                             (VERSION,dict(INFO,DriverStatus=None))]:
            with self.subTest(version=version,info=info),self.assertRaises(ValueError):profile(version,info)

    def test_private_reader_refuses_symlinks_and_oversize(self):
        read=self.owner('read_push_bytes')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'push.log';path.write_bytes(LINE)
            self.assertEqual(read(path),LINE)
            link=root/'link';link.symlink_to(path)
            with self.assertRaises((ValueError,OSError)):read(link)
            nested=root/'nested';nested.symlink_to(root,target_is_directory=True)
            with self.assertRaises((ValueError,OSError)):read(nested/'push.log')
            path.write_bytes(b'x'*1048577)
            with self.assertRaises(ValueError):read(path)

    def test_reader_refuses_file_changed_during_read(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import os
        read=self.owner('read_push_bytes')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'push.log';path.write_bytes(LINE)
            before=path.stat()
            after=SimpleNamespace(st_size=before.st_size,st_mtime_ns=before.st_mtime_ns+1,
                                  st_ctime_ns=before.st_ctime_ns)
            with patch.object(os,'fstat',side_effect=[before,after]),self.assertRaises(ValueError):read(path)


if __name__ == '__main__':unittest.main()
