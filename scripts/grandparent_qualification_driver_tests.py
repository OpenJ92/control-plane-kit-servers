"""Actual shell admission with finite Docker/Git facts; never runtime proof.

The external Docker double checks mount availability, then deliberately stops
at the first admitted helper. No witness Python, credential or service runs.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILT = "2cf6cba37b2e951c4c51b2bb211c4bf10a7dd033"
IMAGE = "sha256:" + "a" * 64
POSTGRES = "sha256:" + "b" * 64
REFERENCE = "localhost/control-plane-kit-servers/cpk-grandparent@" + IMAGE
RUN = "cpk399-mcp-qualification-driver-tests"

DOCKER = r'''
import json,os,pathlib,sys
a=sys.argv[1:]
with open(os.environ["QUAL_CALLS"],"a") as stream: stream.write(json.dumps(a)+"\n")
if a[:2]==["context","show"]: print("fixture-local")
elif a[:2]==["context","inspect"]: print("unix:///fixture.sock")
elif a[0]=="info": print("d23d00aa-b281-448d-bc95-c8e47efeeea2")
elif a[:2]==["image","inspect"]:
    if a[a.index("--format")+1]=="{{.Id}}":
        print(os.environ["QUAL_IMAGE"] if a[2]==os.environ["QUAL_REFERENCE"] else a[2])
    else: print('10001|0|["python","-m","control_plane_kit_servers_cpk_server.server"]|linux|amd64')
elif a[0]=="run":
    mounts=[]
    for i,value in enumerate(a):
        if value=="--mount":
            fields=dict(item.split("=",1) if "=" in item else (item,True) for item in a[i+1].split(","))
            mounts.append(fields)
    # Finite runc prerequisite: an absent target cannot be created beneath an
    # already read-only parent bind. This is the original observed defect only.
    for child in mounts:
        for parent in mounts:
            prefix=parent["target"].rstrip("/")+"/"
            if parent.get("readonly") and child["target"].startswith(prefix):
                target=pathlib.Path(parent["source"])/child["target"][len(prefix):]
                if not target.exists():
                    print("synthetic missing target below read-only bind",file=sys.stderr)
                    sys.exit(125)
    witness=next(pathlib.Path(item["source"]) for item in mounts if item["target"]=="/witness")
    for name in ("grandparent_artifact_fixture.py","cpk_http_host_fixtures.py",
                 "receiver_acceptance_material.py","managed_native_material.py","postgres.json"):
        if not (witness/name).is_file(): sys.exit(125)
    pathlib.Path(os.environ["QUAL_ADMITTED"]).write_text("first helper admitted")
    sys.exit(86) # deliberate stop; no application or credential generation
elif a[0] in ("ps","volume","network"): sys.exit(0)
else: sys.exit(99)
'''
GIT = r'''
import os,sys
a=sys.argv[1:]
if a==["rev-parse","HEAD"]: print(os.environ["QUAL_DRIVER"])
elif a==["status","--porcelain"]: sys.exit(0)
else: sys.exit(98)
'''


class QualificationDriverTests(unittest.TestCase):
    def invoke(self, *, driver, producer=BUILT):
        records = Path("/tmp").resolve() / RUN
        self.assertFalse(records.exists())
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            work = root / "work"
            (work / "scripts").mkdir(parents=True)
            for filename in ("cpk_server_image_smoke.sh", "docker_witness_daemon.sh", "gateway_packaged_owner.sh"):
                shutil.copy2(ROOT / "scripts" / filename, work / "scripts" / filename)
            # Public fixture bytes are external launch inputs, never executed.
            (work / "scripts/grandparent_artifact_fixture.py").write_text("public witness fixture\n")
            fixture_root = work / "products/cpk_server/tests"
            fixture_root.mkdir(parents=True)
            for filename in ("cpk_http_host_fixtures.py", "receiver_acceptance_material.py", "managed_native_material.py"):
                (fixture_root / filename).write_text("public typed fixture\n")
            descriptor = work / "products/postgres_server/product.cpk.json"
            descriptor.parent.mkdir(parents=True)
            descriptor.write_text("{}\n")
            receipt = root / "build.json"
            receipt.write_text(json.dumps(dict(mode="build", source=producer,
                product_source="0610e9454dd9a75a6e6bf5e89fe281c8631cccaa", exit_code=0,
                installed_cohort_verified=True, derived_base_layers_verified=True,
                cleanup="verified", retention="verified", base_retained="verified",
                approved_deployment=False, image=REFERENCE)))
            for binary, source in (("docker", DOCKER), ("git", GIT)):
                path = root / binary
                path.write_text("#!" + sys.executable + "\n" + source.lstrip())
                path.chmod(0o700)
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "QUAL_DRIVER": driver, "QUAL_IMAGE": IMAGE, "QUAL_REFERENCE": REFERENCE,
                "QUAL_CALLS": str(root / "calls"), "QUAL_ADMITTED": str(root / "admitted"),
                "CPK_SERVER_SMOKE_PROFILE": "grandparent-artifact", "CPK_SERVER_BUILD_IMAGE": "0"}
            for key in ("DOCKER_HOST", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONTEXT"):
                env.pop(key, None)
            try:
                result = subprocess.run(["sh", "scripts/cpk_server_image_smoke.sh", IMAGE,
                    str(receipt), POSTGRES, RUN], cwd=work, env=env, capture_output=True,
                    check=False, timeout=20)
                calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
                final = json.loads((records / "result.json").read_text()) if (records / "result.json").exists() else None
                return dict(result=result, admitted=(root / "admitted").exists(), calls=calls,
                    final=final, private_absent=not (records / "private").exists(),
                    witness_absent=not (records / "witness").exists())
            finally:
                if records.exists():
                    shutil.rmtree(records)

    def test_first_helper_has_readable_mounts_and_keeps_driver_and_producer_distinct(self):
        for driver in (BUILT, "d" * 40):
            with self.subTest(driver=driver):
                observed = self.invoke(driver=driver)
                self.assertTrue(observed["admitted"], observed["result"].stderr[-1024:])
                self.assertEqual(observed["result"].returncode, 86)
                self.assertEqual(observed["final"]["source"], driver)
                self.assertEqual(observed["final"]["driver_source"], driver)
                self.assertEqual(observed["final"]["built_source"], BUILT)
                self.assertEqual(observed["final"]["cleanup"], "verified")
                self.assertFalse(observed["final"]["isolated_process_verified"])
                self.assertTrue(observed["private_absent"] and observed["witness_absent"])
                self.assertFalse(any(a[:2] in (["network", "create"], ["volume", "create"])
                    for a in observed["calls"]))

    def test_different_producer_refuses_before_helper_launch(self):
        observed = self.invoke(driver="d" * 40, producer="e" * 40)
        self.assertNotEqual(observed["result"].returncode, 0)
        self.assertFalse(observed["admitted"])
        self.assertFalse(any(a[0] == "run" for a in observed["calls"]))
