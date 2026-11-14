"""Native metadata runner with finite CLI projections; no runtime/socket access."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "do-not-return-private-path-or-exception-87125"
ENGINE = "d23d00aa-b281-448d-bc95-c8e47efeeea2"
INSTALLATION = "cpk163-gparent-20261109"
GIT = '''import sys
a=sys.argv[1:]
if a==["rev-parse","HEAD"]: print("b"*40)
elif a!=["status","--porcelain"]: sys.exit(99)
'''
DOCKER = '''import json,os,pathlib,sys,time
a=sys.argv[1:]
root=pathlib.Path(os.environ["INVENTORY_FIXTURE"])
data=json.loads((root/"facts.json").read_text())
with (root/"calls.jsonl").open("a") as out: out.write(json.dumps(a)+"\\n")
if a[:2]==["context","show"]: print("desktop-linux")
elif a[:2]==["context","inspect"]: print("unix:///synthetic.sock")
elif a[0]=="info": print(data["engine"])
elif a[:2]==["container","ls"]:
    counter=root/"lists"
    n=int(counter.read_text())+1 if counter.exists() else 1
    counter.write_text(str(n))
    print("\\n".join(data.get("closing_ids",list(data["containers"])) if n>1 else list(data["containers"])))
elif a[:2]==["volume","ls"]:
    for name in data["volumes"]: print(json.dumps(name))
elif a[:2]==["network","ls"]: print(json.dumps(data["network"]["id"]))
elif a[:3]==["inspect","--type","container"]:
    identity=a[3]
    if data.get("query_error")==identity:
        print(data["sentinel"],file=sys.stderr); sys.exit(1)
    print(json.dumps(data["containers"][identity]))
elif a[:2]==["volume","inspect"]: print(json.dumps(data["volumes"][a[2]]))
elif a[:2]==["network","inspect"]: print(json.dumps(data["network"]))
elif a[:2]==["image","inspect"]: print(json.dumps(data["images"][a[2]]))
else: sys.exit(99)
'''
LSOF = '''import json,os,pathlib,sys
d=json.loads((pathlib.Path(os.environ["INVENTORY_FIXTURE"])/"facts.json").read_text())
port=next(a.split(":")[-1] for a in sys.argv if a.startswith("-iTCP:"))
print("p123\\nccom.docker.backend\\nf10u\\nn"+d.get("listener_ip","127.0.0.1")+":"+port)
'''
PS = 'print(" 123 1 /synthetic/com.docker.backend\\n 124 1 /synthetic/cloudflared")\n'
SHASUM = '''import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[-1]);print(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+str(p))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture():
    labels = {"org.openj92.cpk.installation": INSTALLATION,
              "org.openj92.cpk.acquisition": "fixture-acquisition",
              "org.openj92.cpk.bootstrap": "fixture-bootstrap"}
    manifest = dict(schema="cpk399.reset-ownership-manifest.v1", installation_id=INSTALLATION,
                    engine_id=ENGINE, container_candidates=[], volume_candidates=[],
                    network_candidate=dict(id="a"*64, name="fixture-network", expected_ownership=labels))
    facts = dict(engine=ENGINE, containers={}, volumes={}, images={}, sentinel=SENTINEL)
    roles = ["postgres", "secrets", "cpk", "website-active-web65", "website-old", "website-failed", "website-retained"]
    for index, role in enumerate(roles):
        identity = str(index+1)*64
        image = "sha256:"+str(index+1)*64
        name = "fixture-"+role
        required = index < 4
        ports = {"8080/tcp": [dict(HostIp="127.0.0.1", HostPort="18163" if role=="cpk" else "18164")]} if role=="cpk" or role.startswith("website") else {}
        manifest["container_candidates"].append(dict(id=identity, name=name, image=image, role=role,
                                                     presence_required=required, expected_ownership=labels))
        facts["containers"][identity] = dict(id=identity, name="/"+name, image=image,
            state="running" if required else "exited", running=required, paused=False, restarting=False, dead=False,
            stop_signal="SIGTERM", ownership=labels.copy(), network_mode="fixture-network",
            mounts=[], configured_mounts=[], binds=[], volumes_from=[],
            networks=[dict(name="fixture-network", id="a"*64, aliases=[name])],
            configured_ports=ports, ports=ports if required else {})
    for index in range(11):
        name = "fixture-volume-"+str(index)
        manifest["volume_candidates"].append(dict(name=name, expected_ownership=labels))
        facts["volumes"][name] = dict(name=name, driver="local", scope="local", options_empty=True, ownership=labels)
        facts["containers"]["1"*64]["mounts"].append(dict(type="volume", name=name, target="/synthetic/"+str(index), rw=True))
    facts["network"] = dict(id="a"*64, name="fixture-network", driver="bridge", scope="local", internal=False,
        attachable=False, ingress=False, config_only=False, config_from_empty=True, ownership=labels,
        members=list(facts["containers"])[:4])
    images = []
    for index in range(5):
        image = "sha256:"+str(index+1)*64
        reference = "fixture/image@"+image
        images.append(dict(reference=reference, expected_id=image, repo_digest_required=True))
        facts["images"][reference] = dict(id=image, os="linux", architecture="amd64", repo_digests=[reference], user="501", stop_signal="SIGTERM")
    plan = dict(schema="cpk399.reset-inventory-proposal.v1", executable=False, authority=dict(live_queries_approved=False),
        named_volume_scope=dict(can_satisfy_retirement_exclusivity=False),
        ordered_queries=[dict(stage="five-fresh-image-cache-checks", images=images)])
    queries = dict(schema="cpk399.reset-inventory-query-shapes.v1", executable=False,
                   revision=dict(can_satisfy_retirement_exclusivity=False))
    return manifest, plan, queries, facts


class ResetInventoryTests(unittest.TestCase):
    def run_inventory(self, change=None, approved=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root/"work"
            (work/"scripts").mkdir(parents=True)
            for name in ("grandparent_reset_inventory.sh", "grandparent_reset_inventory.jq", "docker_witness_daemon.sh"):
                shutil.copy2(ROOT/"scripts"/name, work/"scripts"/name)
            manifest, plan, queries, facts = fixture()
            if change:
                change(manifest, plan, queries, facts)
            for name, value in (("manifest",manifest),("plan",plan),("queries",queries),("facts",facts)):
                (root/(name+".json")).write_text(json.dumps(value))
            for name, code in (("docker", DOCKER),("git",GIT),("lsof",LSOF),("ps",PS),("shasum",SHASUM)):
                binary = root/name
                binary.write_text("#!"+sys.executable+"\n"+code)
                binary.chmod(0o700)
            destination = Path("/tmp")/("cpk399-reset-inventory-test-"+root.name)
            action = dict(schema="cpk399.reset-inventory-approval.v1", approved=approved, optional_path_comparison=False,
                review_reference="synthetic-only",source_commit="b"*40,output_directory=str(destination),
                runner_sha256=sha(work/"scripts/grandparent_reset_inventory.sh"),
                reducer_sha256=sha(work/"scripts/grandparent_reset_inventory.jq"),
                daemon_sha256=sha(work/"scripts/docker_witness_daemon.sh"))
            for name in ("manifest","plan","queries"):
                action[name]=str(root/(name+".json"))
                action[name+"_sha256"]=sha(root/(name+".json"))
            proposal=root/"action.json"
            proposal.write_text(json.dumps(action))
            env={**os.environ,"PATH":str(root)+os.pathsep+os.environ["PATH"],"DOCKER_CONTEXT":"desktop-linux","INVENTORY_FIXTURE":str(root)}
            for name in ("DOCKER_HOST","DOCKER_TLS","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"):
                env.pop(name,None)
            try:
                result=subprocess.run(["bash","scripts/grandparent_reset_inventory.sh",str(proposal),sha(proposal)],
                    cwd=work,env=env,capture_output=True,timeout=90,check=False)
                calls=[json.loads(line) for line in (root/"calls.jsonl").read_text().splitlines()] if (root/"calls.jsonl").exists() else []
                report=json.loads((destination/"report.json").read_text()) if (destination/"report.json").exists() and (destination/"report.json").stat().st_size else None
                files=sorted(p.name for p in destination.iterdir()) if destination.exists() else []
                combined=result.stdout.decode()+result.stderr.decode()+json.dumps(report)
                self.assertNotIn(SENTINEL,combined)
                self.assertEqual(result.stderr,b"")
                self.assertTrue(all(a[0] in ("context","info","container","volume","network","inspect","image") for a in calls))
                self.assertFalse(any(any(v in a for v in ("run","exec","stop","start","rm","prune","pull","build","connect","disconnect")) for a in calls))
                self.assertLessEqual(len(calls),160)
                self.assertNotIn("query.out",files)
                self.assertNotIn("query.err",files)
                return result,report,calls
            finally:
                if destination.exists(): shutil.rmtree(destination)

    def test_observation_keeps_backing_access_and_external_routing_unresolved(self):
        result,report,_=self.run_inventory()
        self.assertEqual(result.returncode,0,result.stdout[-2048:])
        self.assertEqual(report["status"],"observed")
        self.assertEqual(report["enumeration_counts"],dict(containers=7,target_volumes=11,target_networks=1))
        self.assertEqual(report["backing_path_bind_access"],"unresolved")
        self.assertEqual(report["external_routing"],"unresolved")
        self.assertFalse(report["can_satisfy_retirement_exclusivity"])
        self.assertEqual(len(report["target_containers"]),7)
        self.assertEqual(len(report["image_cache"]),5)

    def foreign(self, facts):
        value=dict(facts["containers"]["5"*64])
        value.update(id="f"*64,name="/foreign",ownership={},network_mode="none",networks=[],configured_ports={},ports={},mounts=[],configured_mounts=[])
        facts["containers"][value["id"]]=value
        return value

    def test_foreign_configured_volume_and_inherited_network_each_hold(self):
        for kind in ("configured-volume","namespace","volumes-from"):
            with self.subTest(kind=kind):
                def change(m,p,q,f):
                    other=self.foreign(f)
                    if kind=="configured-volume": other["configured_mounts"]=[dict(type="volume",name=m["volume_candidates"][0]["name"],target="/foreign")]
                    elif kind=="namespace": other["network_mode"]="container:"+"1"*64
                    else: other["volumes_from"]=["1"*64+":ro"]
                result,report,_=self.run_inventory(change)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(report["status"],"HOLD")

    def test_unnamed_backing_bind_is_not_misreported_as_exclusive(self):
        def change(m,p,q,f):
            other=self.foreign(f)
            other["binds"]=["/private/"+SENTINEL+":/foreign:ro"]
            other["mounts"]=[dict(type="bind",name=None,target="/foreign",rw=False)]
        result,report,_=self.run_inventory(change)
        self.assertEqual(result.returncode,0,result.stdout[-2048:])
        self.assertEqual(report["retirement_volume_exclusivity"],"unproven")
        self.assertFalse(report["can_satisfy_retirement_exclusivity"])

    def test_ownership_and_cached_digest_drift_hold(self):
        for kind in ("ownership","image"):
            with self.subTest(kind=kind):
                def change(m,p,q,f):
                    if kind=="ownership": f["containers"]["1"*64]["ownership"]["org.openj92.cpk.acquisition"]="wrong"
                    else: next(iter(f["images"].values()))["repo_digests"]=[]
                result,report,_=self.run_inventory(change)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(report["status"],"HOLD")

    def test_missing_required_and_oversized_inventory_stop_at_opening(self):
        for kind in ("missing","oversized"):
            with self.subTest(kind=kind):
                def change(m,p,q,f):
                    if kind=="missing": del f["containers"]["1"*64]
                    else:
                        for i in range(129): f["containers"][f"{1000+i:064x}"]={}
                result,report,calls=self.run_inventory(change)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(report["stage"],"opening-sets")
                self.assertFalse(any(a[0]=="inspect" for a in calls))

    def test_stderr_is_closed_failure_without_raw_error_or_further_queries(self):
        result,report,calls=self.run_inventory(lambda m,p,q,f:f.update(query_error="1"*64))
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(report["stage"],"containers")
        self.assertEqual(sum(a[0]=="inspect" for a in calls),1)

    def test_concurrent_id_drift_is_not_an_atomic_observation(self):
        result,report,_=self.run_inventory(lambda m,p,q,f:f.update(closing_ids=list(f["containers"])+["f"*64]))
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(report["status"],"HOLD")

    def test_nonloopback_listener_and_unknown_namespace_hold(self):
        for kind in ("listener","namespace"):
            with self.subTest(kind=kind):
                def change(m,p,q,f):
                    if kind=="listener": f["listener_ip"]="0.0.0.0"
                    else: self.foreign(f)["network_mode"]="container:unresolved"
                result,report,_=self.run_inventory(change)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(report["status"],"HOLD")

    def test_unapproved_action_cannot_read_daemon(self):
        result,report,calls=self.run_inventory(approved=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIsNone(report)
        self.assertEqual(calls,[])
