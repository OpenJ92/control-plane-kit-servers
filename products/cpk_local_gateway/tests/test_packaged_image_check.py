"""Public log evidence cannot include private seed or compact credential bytes."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from packaged_image_check import logs


class PackagedImageCheckTests(unittest.TestCase):
    def test_log_scan_accepts_bounded_clean_data_and_refuses_credentials_silently(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            provider,client,captured=(root/name for name in ("provider","client","logs"))
            for path in (provider,client,captured): path.mkdir()
            (provider/"credentials.json").write_text(json.dumps([{"token":"fixture-private-token"}]))
            (provider/"master.key").write_bytes(b"fixture-private-master")
            (client/"provider-token").write_bytes(b"fixture-private-token")
            (client/"application-value").write_bytes(b"fixture-private-value")
            for role in ("postgres","cpk","secrets","gateway","signer"):
                (captured/(role+".status")).write_bytes(b"0\n")
                (captured/(role+".log")).write_bytes(b"ordinary process output")
            self.assertTrue(logs(captured,provider,client)["logs_redacted"])
            for value in (b"fixture-private-master",b"Bearer synthetic",b"eyJabc.e30.signature"):
                with self.subTest(kind=value.split(b" ",1)[0][:3]):
                    (captured/"gateway.log").write_bytes(value)
                    output,error=StringIO(),StringIO()
                    with redirect_stdout(output),redirect_stderr(error),self.assertRaises(ValueError):
                        logs(captured,provider,client)
                    self.assertEqual(output.getvalue()+error.getvalue(),"")

    def test_failed_log_retrieval_cannot_become_empty_clean_log(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            provider,client,captured=(root/name for name in ("provider","client","logs"))
            for path in (provider,client,captured): path.mkdir()
            (provider/"credentials.json").write_text("[]")
            (provider/"master.key").write_bytes(b"fixture-master")
            (client/"provider-token").write_bytes(b"fixture-token")
            (client/"application-value").write_bytes(b"fixture-value")
            (captured/"postgres.status").write_bytes(b"1\n")
            (captured/"postgres.log").write_bytes(b"")
            with self.assertRaises(ValueError): logs(captured,provider,client)
