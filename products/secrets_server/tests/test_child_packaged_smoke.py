"""CLI refusal and cleanup ownership before Secrets image effects."""
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]
DOCKER = r'''
import json,os,sys
a=sys.argv[1:]
with open(os.environ["CHILD_CALLS"],"a") as stream: stream.write(json.dumps(a)+"\n")
if a[:2]==["context","show"]: print("fixture-local")
elif a[:2]==["context","inspect"]: print("unix:///var/run/docker.sock")
elif a[0]=="info": print("fixture-daemon")
elif a[:2]==["image","inspect"]: print("sha256:"+"f"*64)
elif a[:2]==["image","ls"]: pass
elif a[:2]==["ps","-aq"]:
    if os.environ["CHILD_CASE"]=="inventory-failed": sys.exit(31)
    print("foreign-container")
else: sys.exit(97)
'''
GIT = r'''
import sys
if sys.argv[1]=="rev-parse": print("e"*40)
elif sys.argv[1] not in ("status","diff"): sys.exit(98)
'''
OWNERSHIP_DOCKER = r'''
import json,os,sys
a=sys.argv[1:]
with open(os.environ["CHILD_CALLS"],"a") as stream: stream.write(json.dumps(a)+"\n")
run=os.environ["CHILD_FIXED_RUN"]
volume=run+"-provider-bootstrap"
if a[0]=="info": print("fixture-daemon")
elif a[:2]==["volume","create"]: print(a[-1])
elif a[:2]==["volume","inspect"]: print(volume+"|local|local|"+run+"|"+"b"*64+"|0")
elif a[:2]==["volume","ls"]:
    if os.environ["CHILD_CASE"]=="wrong-owner": print(volume)
elif a[:2]==["network","ls"]: pass
elif a[:1]==["ps"]:
    if os.environ["CHILD_CASE"]=="unexpected-label": print("c"*64)
else: sys.exit(99)
'''


class ChildPackagedSmokeTests(unittest.TestCase):
    def admission(self, scenario, *, existing=False):
        run = "cpk-secrets-image-smoke-cpk163-" + uuid4().hex
        records = Path("/tmp").resolve() / run
        if existing:
            records.mkdir()
            (records / "result.json").write_text("existing-receipt")
        try:
            with TemporaryDirectory() as directory:
                root = Path(directory)
                for name, source in (("docker", DOCKER), ("git", GIT)):
                    binary = root / name
                    binary.write_text("#!" + sys.executable + "\n" + source.lstrip())
                    binary.chmod(0o700)
                environment = {**os.environ,"PATH":str(root)+os.pathsep+os.environ["PATH"],
                    "CHILD_CALLS":str(root/"calls"),"CHILD_CASE":scenario,
                    "CPK_SECRETS_SMOKE_PROFILE":"wrapped-child","CPK_SECRETS_BUILD_IMAGE":"1",
                    "CPK_SECRETS_BUILD_CONTROLLER":"0","CPK_SERVERS_TEST_IMAGE":"sha256:"+"f"*64,
                    "CPK_SECRETS_IMAGE":"localhost/control-plane-kit-servers/secrets-server:cpk163-fixture",
                    "CPK_RECEIVER_DAEMON_ID":"fixture-daemon","CPK_SECRETS_CHILD_RUN":run,
                    "CPK_SECRETS_CHILD_RECORDS":str(records)}
                for key in ("DOCKER_HOST","DOCKER_TLS","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"):
                    environment.pop(key,None)
                result = subprocess.run(["sh","scripts/secrets_server_image_smoke.sh"],cwd=ROOT,
                    env=environment,text=True,capture_output=True,timeout=15,check=False)
                calls = [json.loads(line) for line in (root/"calls").read_text().splitlines()] if (root/"calls").exists() else []
                receipt = (records/"result.json").read_text() if (records/"result.json").exists() else None
                return result.returncode,calls,receipt,records.exists()
        finally:
            if existing:
                (records/"result.json").unlink()
                records.rmdir()

    def test_existing_receipt_is_untouched_before_docker(self):
        status,calls,receipt,_ = self.admission("collision",existing=True)
        self.assertNotEqual(status,0)
        self.assertEqual(calls,[])
        self.assertEqual(receipt,"existing-receipt")

    def test_collision_and_failed_inventory_cannot_build_or_clean_foreign_state(self):
        for scenario in ("collision","inventory-failed"):
            with self.subTest(scenario=scenario):
                status,calls,receipt,exists = self.admission(scenario)
                self.assertNotEqual(status,0)
                self.assertFalse(exists)
                self.assertIsNone(receipt)
                self.assertFalse(any("rm" in call or call[0] in ("build","buildx","pull") for call in calls))

    def test_same_run_other_reservation_and_unexpected_label_cannot_bootstrap_or_delete(self):
        source = (ROOT/"scripts/secrets_server_image_smoke.sh").read_text()
        prefix = source.split('if [ "$BUILD_IMAGE" = "1" ]; then',1)[0]
        for scenario in ("wrong-owner","unexpected-label"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as directory:
                root = Path(directory)
                docker = root/"docker"
                docker.write_text("#!"+sys.executable+"\n"+OWNERSHIP_DOCKER.lstrip())
                docker.chmod(0o700)
                records = root/"records"
                records.mkdir()
                run = "cpk-secrets-image-smoke-cpk163-owned-fixture"
                environment = {**os.environ,"PATH":str(root)+os.pathsep+os.environ["PATH"],
                    "CPK_SECRETS_SMOKE_PROFILE":"published-baseline","CPK_SECRETS_BUILD_IMAGE":"0",
                    "CPK_SECRETS_BUILD_CONTROLLER":"0","CPK_SECRETS_IMAGE":"repo@sha256:"+"d"*64,
                    "CPK_RECEIVER_DAEMON_ID":"fixture-daemon","CHILD_CALLS":str(root/"calls"),
                    "CHILD_CASE":scenario,"CHILD_FIXED_RUN":run}
                shell = prefix + "\nCHILD_PROFILE=1\nCHILD_RESERVED=1\nCHILD_OWNER="+"a"*64+"\n"
                shell += "CPK_SECRETS_CHILD_RECORDS="+shlex.quote(str(records))+"\nRUN_ID="+run+"\n"
                shell += 'PROVIDER_BOOTSTRAP="$RUN_ID-provider-bootstrap"\nCLIENT_BOOTSTRAP="$RUN_ID-client-bootstrap"\nDATA_VOLUME="$RUN_ID-data"\nNETWORK="$RUN_ID-network"\n'
                if scenario == "wrong-owner":
                    shell += 'child_create_volume "$PROVIDER_BOOTSTRAP"\nsmoke_run bootstrap --rm fixture-image\n'
                shell += "exit 0\n"
                result = subprocess.run(["sh","-c",shell],cwd=ROOT,env=environment,
                    text=True,capture_output=True,timeout=15,check=False)
                calls = [json.loads(line) for line in (root/"calls").read_text().splitlines()]
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(any("rm" in call or call[0]=="run" for call in calls))
                self.assertEqual(json.loads((records/"result.json").read_text())["cleanup"],"unverified")
