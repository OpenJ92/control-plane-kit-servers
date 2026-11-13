"""Actual owning wrapper stop behavior with a nonzero fake buildx child.

All Docker/Git facts are finite external doubles; no artifact is qualified here.
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
RUN = "cpk399-grandparent-artifact-20261113-01"
PLAN = "cpk399-grandparent-dependency-plan-20261113-01"
DOCKER = r'''
import json,os,pathlib,sys
a=sys.argv[1:]
with open(os.environ["BUILD_CALLS"],"a") as out: out.write(json.dumps(a)+"\n")
if a[:2]==["context","show"]: print("fixture-local")
elif a[:2]==["context","inspect"]: print("unix:///fixture.sock")
elif a[0]=="info": print("d23d00aa-b281-448d-bc95-c8e47efeeea2")
elif a[:2]==["image","inspect"]: print(a[2] if a[2].startswith("sha256:") else a[2].split("@",1)[1])
elif a[:2]==["image","save"]: sys.stdout.buffer.write(b"bounded synthetic Docker export")
elif a[:2]==["buildx","build"]: sys.exit(int(os.environ["BUILD_EXIT"]))
elif a[0]=="run":
    pathlib.Path(a[a.index("--cidfile")+1]).write_text("c"*64)
    mount=next(a[i+1] for i,value in enumerate(a) if value=="--mount" and a[i+1].endswith("target=/layout"))
    source=mount.split("source=",1)[1].split(",",1)[0]
    pathlib.Path(source,"public-scratch").write_text("external validator double")
    print('{"all_blob_digests_verified":true}')
elif a[0] in ("image","ps","volume","network"): sys.exit(0)
else: sys.exit(99)
'''
GIT = r'''
import sys,tarfile
a=sys.argv[1:]
while a and a[0] in ("-C", "-c"): a=a[2:]
if a[0]=="rev-parse":
    value=a[1]
    print(value.removesuffix("^{commit}") if value.endswith("^{commit}") else
          "97507ed009a5e5c8aa81d280288a2f81ce807835" if value.endswith(":src/control_plane_kit_interpreters") else "e"*40)
elif a[0]=="archive":
    with tarfile.open(fileobj=sys.stdout.buffer,mode="w|") as out:
        item=tarfile.TarInfo("products/cpk_server")
        item.type=tarfile.DIRTYPE
        item.mode=0o755
        out.addfile(item)
elif a[0]=="get-tar-commit-id": print("e438f6e522ad0a23a7acef460be08690f48b2e17")
elif a[0] in ("hash-object","write-tree"): print("e"*40)
elif a[0] in ("status","ls-tree","init","update-index"): pass
else: sys.exit(98)
'''
SHASUM = r'''
import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[-1])
digest="af15d9261cde91e387b2659b489712abbc5579f09ba67ca51350c802552c22e0" if p.name=="interpreters.tar" else hashlib.sha256(p.read_bytes()).hexdigest()
print(digest+"  "+str(p))
'''
DF = 'print("Filesystem 1024-blocks Used Available Capacity Mounted-on\\nfixture 2097152 0 2097152 0% /tmp")\n'


class BuildTerminationTests(unittest.TestCase):
    def test_nonzero_buildx_child_retains_scratch_without_parent_signal_or_retry(self):
        records = Path("/tmp").resolve() / RUN
        plan_records = Path("/tmp").resolve() / PLAN
        for code in (1, 137):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as name:
                self.assertFalse(records.exists())
                self.assertFalse(plan_records.exists())
                root = Path(name)
                work = root / "work"
                (work / "scripts").mkdir(parents=True)
                (work / "products/cpk_server").mkdir(parents=True)
                for filename in ("grandparent_image_build.sh", "gateway_packaged_owner.sh", "docker_witness_daemon.sh"):
                    shutil.copy2(ROOT / "scripts" / filename, work / "scripts" / filename)
                for filename in ("grandparent-cohort.json", "mcp-grandparent-public-lock.json"):
                    shutil.copy2(ROOT / "products/cpk_server" / filename, work / "products/cpk_server")
                # Finite Git/archive facts are external doubles in this stop law;
                # they do not qualify source bytes or a deployable artifact.
                import io, tarfile, hashlib
                archive = root / "interpreters.tar"
                with tarfile.open(archive, "w") as out:
                    data = b"fixture = True\n"
                    item = tarfile.TarInfo("src/control_plane_kit_interpreters/__init__.py")
                    item.size = len(data)
                    out.addfile(item, io.BytesIO(data))
                plan_records.mkdir()
                (plan_records / "result.json").write_text(json.dumps(dict(mode="plan", source="e"*40,
                    base="localhost/control-plane-kit-servers/cpk-server@sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28",
                    exit_code=0, cleanup="verified", dependency_inventory_verified=True)))
                lock_hash = hashlib.sha256((work / "products/cpk_server/mcp-grandparent-public-lock.json").read_bytes()).hexdigest()
                (plan_records / "base-public.json").write_text(json.dumps(dict(status="ready-no-version-changes",
                    public_lock_sha256=lock_hash)))
                for binary, source in (("docker", DOCKER), ("git", GIT), ("df", DF), ("shasum", SHASUM)):
                    path = root / binary
                    path.write_text("#!" + sys.executable + "\n" + source.lstrip())
                    path.chmod(0o700)
                env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                       "BUILD_EXIT": str(code), "BUILD_CALLS": str(root / "calls")}
                for key in ("DOCKER_HOST", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
                    env.pop(key, None)
                try:
                    result = subprocess.run(["sh", "scripts/grandparent_image_build.sh", "--grandparent-image-build",
                                             str(work), str(work), str(archive), str(work)], cwd=work, env=env,
                                            capture_output=True, check=False, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    receipt = json.loads((records / "result.json").read_text())
                    self.assertTrue(receipt["build_attempted"], result.stderr[-1024:])
                    self.assertEqual(receipt["cleanup"], "unverified")
                    self.assertEqual(receipt["retention"], "unverified")
                    self.assertFalse(receipt["installed_cohort_verified"])
                    self.assertTrue((records / "context").is_dir())
                    self.assertTrue((records / "base-layout/public-scratch").is_file())
                    calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
                    self.assertEqual(sum(a[:2] == ["buildx", "build"] for a in calls), 1)
                    self.assertFalse(any(a[0] == "pull" for a in calls))
                finally:
                    if records.exists():
                        shutil.rmtree(records)
                    if plan_records.exists():
                        shutil.rmtree(plan_records)
