"""Temporary access-only branch: execute the actual inline probe with I/O doubles."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
ENDPOINT = 'https://api.github.com/users/OpenJ92/packages/container/control-plane-kit-servers%2Fcloudflared-connector'
CANARY = 'PRIVATE-PROBE-CANARY'


class ManagedAccessProbeTests(unittest.TestCase):
    def observe(self, *, status=200, admission_failure=False, cleanup_failure=False,
                transport=False, token=True, root='/tmp', workspace='/source'):
        workflow=(ROOT/'.github/workflows/publish-product-image.yml').read_text()
        script=textwrap.dedent(workflow.split("python3 - <<'PY'\n",1)[1].rsplit('          PY',1)[0])
        temporary=MagicMock()
        if cleanup_failure:temporary.cleanup.side_effect=OSError(CANARY)
        response=MagicMock();response.status=status
        response.__enter__.return_value=response
        opener=MagicMock()
        if transport:opener.open.side_effect=urllib.error.URLError(CANARY)
        elif status!=200:
            opener.open.side_effect=urllib.error.HTTPError(ENDPOINT,status,CANARY,{},io.BytesIO(CANARY.encode()))
        else:opener.open.return_value=response
        with patch.dict(os.environ,{'RUNNER_TEMP':root,'GITHUB_WORKSPACE':workspace,'GH_TOKEN':CANARY if token else ''}), \
             patch.object(tempfile,'TemporaryDirectory',side_effect=OSError(CANARY) if admission_failure else None,return_value=temporary) as create, \
             patch.object(urllib.request,'build_opener',return_value=opener) as build, \
             contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as finished:
                exec(compile(script,'inline-access-probe','exec'),{'__name__':'__main__'})
        self.assertEqual(err.getvalue(),'')
        self.assertNotIn(CANARY,out.getvalue())
        self.assertEqual(len(out.getvalue().splitlines()),1)
        value=json.loads(out.getvalue())
        self.assertEqual(set(value),{'schema','local_temp','package_get','http_status'})
        self.assertEqual(value['schema'],'cpk.managed-package-access-probe.v1')
        response.read.assert_not_called()
        if opener.open.called:
            opener.open.assert_called_once()
            request=opener.open.call_args.args[0]
            self.assertEqual(request.full_url,ENDPOINT)
            self.assertEqual(request.get_method(),'GET')
            self.assertEqual(request.get_header('Authorization'),'Bearer '+CANARY)
            self.assertEqual(opener.open.call_args.kwargs,{'timeout':20})
            handler=build.call_args.args[0]
            self.assertIsNone(handler.redirect_request(request,None,302,CANARY,{},'https://other.invalid/'))
        return value,finished.exception.code,opener,temporary,create

    def test_exact_get_success_without_body_or_secret_output(self):
        value,code,opener,temporary,create=self.observe()
        self.assertEqual((value['local_temp'],value['package_get'],value['http_status'],code),('success','http-response',200,0))
        temporary.cleanup.assert_called_once_with()
        create.assert_called_once_with(prefix='cpk-package-access-',dir='/tmp')

    def test_http_denials_and_redirect_are_status_only_without_retry(self):
        for status in (301,302,403,404,500):
            with self.subTest(status=status):
                value,code,opener,temporary,_=self.observe(status=status)
                self.assertEqual((value['package_get'],value['http_status'],code),('http-response',status,1))
                opener.open.assert_called_once()
                temporary.cleanup.assert_called_once_with()

    def test_admission_failure_never_requests_package(self):
        value,code,opener,temporary,_=self.observe(admission_failure=True)
        self.assertEqual((value['local_temp'],value['package_get'],value['http_status'],code),('failure','not-attempted',None,1))
        opener.open.assert_not_called();temporary.cleanup.assert_not_called()

    def test_invalid_temp_locations_refuse_before_creation_or_request(self):
        for root in ('relative','/tmp/../tmp','/source','/source/nested'):
            with self.subTest(root=root):
                value,code,opener,temporary,create=self.observe(root=root)
                self.assertEqual((value['local_temp'],code),('failure',1))
                create.assert_not_called();opener.open.assert_not_called()

    def test_transport_failure_never_exposes_reason_or_retries(self):
        value,code,opener,temporary,_=self.observe(transport=True)
        self.assertEqual((value['package_get'],value['http_status'],code),('transport-failure',None,1))
        opener.open.assert_called_once();temporary.cleanup.assert_called_once_with()

    def test_missing_token_is_local_failure_without_request(self):
        value,code,opener,temporary,_=self.observe(token=False)
        self.assertEqual((value['package_get'],value['http_status'],code),('local-request-failure',None,1))
        opener.open.assert_not_called();temporary.cleanup.assert_called_once_with()

    def test_cleanup_failure_preserves_observed_http_status(self):
        value,code,opener,temporary,_=self.observe(cleanup_failure=True)
        self.assertEqual((value['local_temp'],value['package_get'],value['http_status'],code),('cleanup-failure','http-response',200,1))
        temporary.cleanup.assert_called_once_with()
