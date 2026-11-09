"""Gateway image admission and exact-owned cleanup, using finite fake CLI replies."""
import json
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[3]
DAEMON="d23d00aa-b281-448d-bc95-c8e47efeeea2"
CONTROLLER="sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba"
SECRETS="localhost/control-plane-kit-servers/secrets-server@sha256:"+"b"*64
FAKE=r'''
import json,os,pathlib,sys
a=sys.argv[1:]; mode=os.environ["GW_CASE"]; run=os.environ["GW_FIXED_RUN"]
with open(os.environ["GW_CALLS"],"a") as stream: stream.write(json.dumps(a)+"\n")
if a[:2]==["context","show"]: print("fixture-local")
elif a[:2]==["context","inspect"]: print("unix:///var/run/docker.sock")
elif a[0]=="info": print("wrong-daemon" if mode=="daemon" else "d23d00aa-b281-448d-bc95-c8e47efeeea2")
elif a[:2]==["image","inspect"]:
    ref=a[2]; source="c04f060fd063b407d858c8a55fe85a247be086cf"
    role="controller" if ref.startswith("sha256:") else "postgres" if "postgres@" in ref else "secrets" if "secrets-server@" in ref else "cpk"
    if role=="secrets": source="1182fccdaed6e8d8410f7ec2b5de697ab8236c4b"
    # These cached images have no Labels map. Reading Config on those roles
    # models Docker's missing-property failure rather than fabricating labels.
    if role in ("postgres","controller") and "Config" in a[-1]: sys.exit(34)
    if role=="postgres" and mode=="inspect-failure":
        print("PRIVATE_CONFIG_MARKER",file=sys.stderr); sys.exit(35)
    identity=ref if ref.startswith("sha256:") else "sha256:"+ref.rsplit("sha256:",1)[1]
    digest=ref
    if role=="postgres" and mode!="pg-canonical": digest=ref.removeprefix("docker.io/library/")
    if role=="postgres" and mode=="pg-wrong-digest": digest=digest.rsplit("sha256:",1)[0]+"sha256:"+"0"*64
    attrs={"id":identity,"digests":[] if mode=="image" else [digest],"os":"linux","architecture":"amd64"}
    if role in ("cpk","secrets"):
        attrs["source"]=None if mode==role+"-missing" else {} if mode==role+"-malformed" else "0"*40 if mode==role+"-source" else source
    if role=="secrets":
        attrs.update(run=None if mode=="secrets-missing" else "foreign" if mode=="secrets-run" else os.environ.get("GW_SECRETS_RUN"),
            owner=None if mode=="secrets-missing" else "c"*64 if mode=="secrets-owner" else "a"*64)
    print(json.dumps(attrs))
elif a[:2]==["image","ls"]:
    if mode in ("metadata-ok","pg-canonical"): print("existing-gateway-tag")
elif a[:2]==["volume","create"]: print(a[-1])
elif a[:2]==["volume","inspect"]: print(a[2]+"|local|local|"+run+"|"+"b"*64+"|0")
elif a[:2]==["volume","ls"]:
    if mode=="owner": print(run+"-secrets-bootstrap")
    elif mode=="collision" and any(x.startswith("name=") for x in a): print(a[-1].removeprefix("name="))
elif a[:2]==["network","ls"]: pass
elif a[0]=="ps":
    if mode=="readback" and any(x.startswith("name=") for x in a): print("c"*64)
    elif mode=="readback" and any(x.startswith("id=") for x in a): sys.exit(31)
elif a[0]=="inspect":
    if mode=="helper": print("exited|1")
    else: print("/"+run+"-gateway|"+run+"|"+"a"*64)
elif a[0]=="rm": pass
else: sys.exit(99)
'''
GIT=r'''
import os,pathlib,sys
if sys.argv[1]=="rev-parse": print("e"*40)
elif sys.argv[1]=="show": print(pathlib.Path(os.environ["GW_PIN_FIXTURE"]).read_text(),end="")
elif sys.argv[1]=="status" and os.environ["GW_CASE"]=="git-read": sys.exit(32)
elif sys.argv[1] not in ("status","diff"): sys.exit(98)
'''


class PackagedImageOwnerTests(unittest.TestCase):
    def environment(self,root,mode,run):
        for name,source in (("docker",FAKE),("git",GIT)):
            binary=root/name
            binary.write_text("#!"+sys.executable+"\n"+source.lstrip())
            binary.chmod(0o700)
        env={**os.environ,"PATH":str(root)+os.pathsep+os.environ["PATH"],"GW_CASE":mode,
            "GW_FIXED_RUN":run,"GW_CALLS":str(root/"calls"),"CPK_GATEWAY_IMAGE_RUN":run,
            "CPK_GATEWAY_IMAGE_TAG":"localhost/control-plane-kit-servers/cpk-local-gateway:cpk163-unit"}
        for key in ("DOCKER_HOST","DOCKER_TLS","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"):
            env.pop(key,None)
        return env

    def admission(self,mode):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            run="cpk-gateway-image-smoke-cpk163-"+uuid4().hex
            records=Path("/tmp").resolve()/run
            receipt_dir=Path("/tmp").resolve()/("cpk-secrets-image-smoke-cpk163-"+uuid4().hex)
            receipt_dir.mkdir()
            receipt={"source":"1182fccdaed6e8d8410f7ec2b5de697ab8236c4b","exit_code":0,
                "run":receipt_dir.name,"owner_nonce":"a"*64,
                "daemon_id":DAEMON,"controller_id":CONTROLLER,
                "product_source_base":"85b193bbdc777376c5104029a5ee04e74627cf71",
                "candidate_reference":SECRETS,"cleanup":"verified","candidate_retention":"verified",
                **{key:True for key in ("installed_provenance_verified","initial_custody_verified",
                    "retained_restart_verified","revocation_persistence_verified","signed_pair_verified",
                    "initial_signed_pair_verified","restart_signed_pair_verified","logs_redacted_verified")}}
            if mode=="unqualified": receipt["retained_restart_verified"]=False
            (receipt_dir/"result.json").write_text(json.dumps(receipt))
            if mode=="stream":
                with (receipt_dir/"result.json").open("a") as output: output.write(json.dumps(receipt))
            pin={"schema":"cpk163.gateway-secrets-acceptance.v1",
                "source":"1182fccdaed6e8d8410f7ec2b5de697ab8236c4b","reference":SECRETS,
                "url":"https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-1",
                "run":receipt_dir.name,"receipt_sha256":hashlib.sha256((receipt_dir/"result.json").read_bytes()).hexdigest()}
            if mode=="unbuildable": pin.update(reference=None,url=None,run=None,receipt_sha256=None)
            pin_path=root/"pin.json"
            pin_path.write_text(json.dumps(pin))
            if mode=="receipt-substitution":
                (receipt_dir/"result.json").write_text(json.dumps(receipt|{"owner_nonce":"c"*64}))
            inputs={"schema":"cpk163.gateway-image-inputs.v1","secrets_reference":SECRETS,
                "secrets_receipt":str(receipt_dir/"result.json"),
                "secrets_acceptance":"https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-1"}
            if mode=="substituted": inputs["secrets_reference"]=SECRETS.replace("b"*64,"a"*64)
            if mode=="unrelated": inputs["secrets_acceptance"]=inputs["secrets_acceptance"].replace("-1","-2")
            path=root/"inputs.json"
            if mode!="missing": path.write_text(json.dumps(inputs))
            work=root/"work"
            (work/"scripts").mkdir(parents=True)
            for name in ("gateway_packaged_image.sh","gateway_packaged_owner.sh","docker_witness_daemon.sh"):
                shutil.copy2(ROOT/"scripts"/name,work/"scripts"/name)
            environment=self.environment(root,mode,run)
            environment.update(GW_PIN_FIXTURE=str(pin_path),GW_SECRETS_RUN=receipt_dir.name)
            try:
                result=subprocess.run(["sh","scripts/gateway_packaged_image.sh",str(path)],cwd=work,
                    env=environment,capture_output=True,text=True,timeout=15,check=False)
                self.assertNotIn("PRIVATE_CONFIG_MARKER",result.stdout+result.stderr)
                if mode=="inspect-failure":
                    self.assertEqual(result.stderr.strip(),"gateway borrowed image inspection failed: postgres")
                calls=[json.loads(line) for line in (root/"calls").read_text().splitlines()] if (root/"calls").exists() else []
                return result.returncode,calls,records.exists()
            finally:
                shutil.rmtree(receipt_dir)
                if records.exists(): shutil.rmtree(records)

    def test_unqualified_missing_and_substituted_input_have_no_docker_effect(self):
        for mode in ("missing","unqualified","substituted","unrelated","receipt-substitution","stream","unbuildable"):
            with self.subTest(mode=mode):
                status,calls,exists=self.admission(mode)
                self.assertNotEqual(status,0)
                self.assertEqual(calls,[])
                self.assertFalse(exists)

    def test_daemon_image_and_volume_collision_have_zero_build_or_allocation(self):
        for mode in ("daemon","image","collision","git-read","pg-wrong-digest","inspect-failure"):
            with self.subTest(mode=mode):
                status,calls,exists=self.admission(mode)
                self.assertNotEqual(status,0)
                self.assertFalse(exists)
                self.assertTrue(calls)
                self.assertFalse(any(a[0] in ("run","build","buildx","rm","pull") or
                    a[:2] in (["volume","create"],["network","create"]) for a in calls))

    def test_label_free_pg_and_controller_and_exact_pg_digest_spellings_pass_metadata_admission(self):
        for mode in ("metadata-ok","pg-canonical"):
            with self.subTest(mode=mode):
                status,calls,exists=self.admission(mode)
                # Stop safely at the later tag collision, after all four images.
                self.assertNotEqual(status,0)
                self.assertFalse(exists)
                self.assertEqual(len([a for a in calls if a[:2]==["image","inspect"]]),4)
                self.assertTrue(any(a[:2]==["image","ls"] for a in calls))
                self.assertFalse(any(a[0] in ("run","build","buildx","rm","pull") or
                    a[:2] in (["volume","create"],["network","create"]) for a in calls))

    def test_missing_malformed_or_mismatched_protected_labels_stop_before_reservation(self):
        for mode in ("cpk-missing","cpk-malformed","cpk-source","secrets-missing",
                     "secrets-malformed","secrets-source","secrets-run","secrets-owner"):
            with self.subTest(mode=mode):
                status,calls,exists=self.admission(mode)
                self.assertNotEqual(status,0)
                self.assertFalse(exists)
                self.assertTrue(any(a[:2]==["image","inspect"] for a in calls))
                self.assertFalse(any(a[0] in ("run","build","buildx","rm","pull") or
                    a[:2] in (["image","ls"],["volume","create"],["network","create"]) for a in calls))

    def test_foreign_reservation_helper_failure_and_failed_readback_stay_failed(self):
        for mode in ("owner","helper","readback"):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root=Path(directory)
                run="cpk-gateway-image-smoke-cpk163-owned-unit"
                records=root/"records"
                records.mkdir()
                shell='set -eu\n. ./scripts/gateway_packaged_owner.sh\n'
                shell+='GW_RUN='+run+'\nGW_RECORDS='+shlex.quote(str(records))+'\n'
                shell+='GW_OWNER='+"a"*64+'\nGW_DAEMON='+DAEMON+'\nGW_RESERVED=1\nGW_VOLUMES=""\n'
                if mode=="owner":
                    shell+='GW_VOLUMES="$GW_RUN-secrets-bootstrap"\n'
                    shell+='if gw_volume_create "$GW_RUN-secrets-bootstrap"; then gw_run bootstrap fixture; fi\ngw_cleanup\n'
                elif mode=="helper":
                    (records/"signer.cid").write_text("c"*64)
                    shell+='gw_wait_signer\n'
                else:
                    (records/"gateway.attempt").touch()
                    (records/"gateway.cid").write_text("c"*64)
                    shell+='gw_cleanup\n'
                result=subprocess.run(["sh","-c",shell],cwd=ROOT,env=self.environment(root,mode,run),
                    capture_output=True,text=True,timeout=15,check=False)
                calls=[json.loads(line) for line in (root/"calls").read_text().splitlines()]
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(any(a[0]=="run" for a in calls))
                if mode=="owner": self.assertFalse(any(a[:2]==["volume","rm"] for a in calls))
