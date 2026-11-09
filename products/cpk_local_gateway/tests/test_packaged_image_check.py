"""Public log evidence cannot include private seed or compact credential bytes."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from packaged_image_check import logs, main, readiness


class PackagedImageCheckTests(unittest.TestCase):
    def test_readiness_records_transient_transport_failure_then_recovery(self):
        cpk_attempts=[]
        pauses=[]
        def reply(request):
            if request.url.host=="cpk-source":
                cpk_attempts.append(True)
                if len(cpk_attempts)==1:
                    raise httpx.ConnectError("private-transport-marker",request=request)
            status=401 if request.url.host=="gateway-source" else 200
            return httpx.Response(status,json={"status":"ready"})
        clock=iter((0,1))
        result=readiness(transport=httpx.MockTransport(reply),clock=lambda:next(clock),pause=pauses.append)
        self.assertTrue(result["complete"])
        self.assertFalse(result["deadline_exceeded"])
        self.assertEqual(result["pending_roles"],[])
        self.assertEqual(result["readiness"]["cpk"]["status"],200)
        self.assertEqual(result["observations"]["cpk"]["observation"],"ready")
        self.assertTrue(result["observations"]["cpk"]["transport_unavailable_seen"])
        self.assertNotIn("private-transport-marker",json.dumps(result))

    def test_partial_readiness_deadline_is_emitted_with_nonzero_cli_result(self):
        def reply(request):
            if request.url.host=="gateway-source":
                raise httpx.ConnectError("private-transport-marker",request=request)
            return httpx.Response(200,json={"status":"ready"})
        clock=iter((0,31))
        def probe():
            return readiness(transport=httpx.MockTransport(reply),clock=lambda:next(clock),
                pause=lambda delay:self.fail("deadline must stop readiness waiting"))
        output,error=StringIO(),StringIO()
        with patch("packaged_image_check.readiness",side_effect=probe), \
                patch.object(sys,"argv",["check","readiness"]), \
                patch("packaged_image_check.signal.signal"),patch("packaged_image_check.signal.alarm"), \
                redirect_stdout(output),redirect_stderr(error):
            status=main()
        result=json.loads(output.getvalue())
        self.assertEqual(status,1)
        self.assertEqual(result["exit_code"],1)
        self.assertFalse(result["complete"])
        self.assertTrue(result["deadline_exceeded"])
        self.assertEqual(result["pending_roles"],["gateway"])
        self.assertEqual(set(result["readiness"]),{"cpk","secrets"})
        self.assertEqual(result["observations"]["gateway"]["observation"],"transport-unavailable")
        self.assertNotIn("private-transport-marker",output.getvalue()+error.getvalue())
        self.assertNotIn("http://",output.getvalue()+error.getvalue())

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
