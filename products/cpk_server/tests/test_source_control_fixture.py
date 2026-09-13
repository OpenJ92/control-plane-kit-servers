"""The owning source smoke's ephemeral public file and private grants."""
import importlib
import json
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import unittest

import jwt
import control_plane_kit_core as core
from control_plane_kit_server_sdk.verification import Ed25519WorkloadNodeHealthReadVerifier
from control_plane_kit_server_sdk.verifier_keys import AtomicWorkloadNodeHealthReadVerifierKeySet


class SourceControlFixtureTests(unittest.TestCase):
    def setUp(self):
        self.product=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(self.product/"src"))
        self.config=importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
        self.source=importlib.import_module("source_control_fixture")

    def tearDown(self):
        sys.path.remove(str(self.product/"src"))

    def test_generated_public_config_private_headers_and_bounded_actual_health_grant(self):
        with TemporaryDirectory() as temporary:
            directory=Path(temporary)
            self.source.generate(directory)
            self.assertEqual({path.name for path in directory.iterdir()}, {"control.json","surface.headers","health.headers"})
            control=self.config.decode_cpk_control_configuration((directory/"control.json").read_bytes())
            for name,mode in (("control.json",0o444),("surface.headers",0o600),("health.headers",0o600)):
                self.assertEqual(stat.S_IMODE((directory/name).stat().st_mode),mode)
                self.assertNotIn(b"PRIVATE KEY",(directory/name).read_bytes())
            credential=(directory/"health.headers").read_text().removeprefix("Authorization: Bearer ").strip()
            self.assertLess(len(credential),4096)
            untrusted=jwt.decode(credential,options={"verify_signature":False})
            self.assertEqual(untrusted["exp"]-untrusted["iat"],240)
            verifier=Ed25519WorkloadNodeHealthReadVerifier(
                AtomicWorkloadNodeHealthReadVerifierKeySet(control.health_keys),
                expected_issuer=control.health_issuer,expected_audience=core.workload_node_control_audience(control.target),clock=lambda:untrusted["iat"]+1,
            )
            request=verifier.admit(credential.encode(),route_kind=core.NodeHealthReadKind.LIVENESS,candidate=None,expected_target=control.target,expected_runtime_id=control.runtime_id,expected_declaration=control.declaration)
            self.assertEqual(request.runtime_id,control.runtime_id)
            with self.assertRaises(FileExistsError):
                self.source.generate(directory)

    def test_source_and_published_profiles_are_explicit_and_cleanup_names_every_new_file(self):
        root=self.product.parents[1]
        smoke=(root/"scripts/cpk_server_image_smoke.sh").read_text()
        published=(root/"scripts/cpk_server_published_image_smoke.sh").read_text()
        gate=(root/"test.sh").read_text()
        self.assertIn("CPK_SERVER_SMOKE_PROFILE=wrapped-source",gate)
        self.assertIn("CPK_SERVER_SMOKE_PROFILE=published-baseline",published)
        self.assertIn("--network none",smoke)
        self.assertIn("source_control_fixture.py generate /fixture",smoke)
        self.assertIn("source_control_fixture.py verify /fixture",smoke)
        self.assertIn("target=/etc/cpk/cpk-server/control.json,readonly",smoke)
        self.assertIn("--max-time 3 --max-filesize 65536",smoke)
        self.assertIn('chmod 700 "$CONTROL_RECORDS"',smoke)
        self.assertIn("umask 077",smoke)
        cleanup=smoke.split("cleanup_control_fixture() {",1)[1].split("\ncleanup()",1)[0]
        for name in ("control.json","surface.headers","health.headers","surface.json","health.json","denied.json"):
            self.assertIn("$CONTROL_RECORDS/"+name,cleanup)
        self.assertIn('rmdir "$CONTROL_RECORDS" || return 1',cleanup)
        self.assertIn('cleanup_control_fixture || status=1',smoke)
