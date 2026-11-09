"""Bounded image inspection/readiness/log checks for the owning gateway action."""
from importlib import import_module, metadata
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def provenance(coordinates):
    origins = {}
    for name in ("core", "server-sdk"):
        distribution = "control-plane-kit-" + name
        commit = coordinates["upstreams"]["control_plane_kit_" + name.replace("-", "_") + "_commit"]
        repository = "control-plane-kit" if name == "core" else distribution
        url = "https://github.com/OpenJ92/" + repository + "/archive/" + commit + ".zip"
        installed = json.loads(metadata.distribution(distribution).read_text("direct_url.json"))
        if installed.get("url") != url or installed.get("subdirectory") != (
                distribution if name == "core" else None):
            raise ValueError
        origins[distribution] = {"url":url,"subdirectory":installed.get("subdirectory")}
    module = import_module("control_plane_kit_servers_cpk_local_gateway.server")
    if not Path(module.__file__).resolve().is_relative_to(Path("/app/products/cpk_local_gateway/src")):
        raise ValueError
    checked = subprocess.run([sys.executable,"-m","pip","check"],capture_output=True,timeout=30,check=False)
    if checked.returncode:
        raise ValueError
    return {"installed_origins":origins,"pip_check":"passed","gateway_import":"passed"}


def readiness():
    import httpx
    pending = {"cpk":("http://cpk-source:8080/health/ready",200),
        "secrets":("http://secrets-provider:8081/health/ready",200),
        "gateway":("http://gateway-source:8000/__control/capabilities",401)}
    results = {}
    deadline = time.monotonic()+30
    with httpx.Client(timeout=1,trust_env=False,follow_redirects=False) as client:
        while pending:
            for role,(url,expected) in tuple(pending.items()):
                try:
                    with client.stream("GET",url) as response:
                        body = bytearray()
                        for chunk in response.iter_bytes(chunk_size=4096):
                            if len(body)+len(chunk)>65_536:
                                raise ValueError
                            body.extend(chunk)
                        if response.status_code != expected:
                            continue
                        if role != "gateway" and json.loads(body).get("status") != "ready":
                            raise ValueError
                        results[role] = {"status":expected,"transport":"owned-network"}
                        del pending[role]
                except httpx.HTTPError:
                    pass
            if pending:
                if time.monotonic()>=deadline:
                    raise ValueError
                time.sleep(0.25)
    return {"readiness":results,"gateway_observation":"unsigned protected route refuses401"}


def bounded(path,limit,*,empty=False):
    with path.open("rb") as stream:
        raw=stream.read(limit+1)
    if len(raw)>limit or (not raw and not empty):
        raise ValueError
    return raw


def logs(directory,provider,client):
    # These are test-owned private seed files; only the Boolean result escapes.
    credentials=json.loads(bounded(provider/"credentials.json",16_384))
    forbidden=[b"Bearer ",b"PRIVATE KEY",b"valid-token",b"postgresql://",b"postgres://"]
    forbidden.extend(item["token"].encode("ascii") for item in credentials)
    forbidden.extend((bounded(provider/"master.key",4096),
        bounded(client/"provider-token",4096),bounded(client/"application-value",4096)))
    jwt=re.compile(rb"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
    for role in ("postgres","cpk","secrets","gateway","signer"):
        if bounded(directory/(role+".status"),32)!=b"0\n":
            raise ValueError
        content=bounded(directory/(role+".log"),1_048_576,empty=True)
        if any(value in content for value in forbidden) or jwt.search(content):
            raise ValueError
    return {"logs_redacted":True,"roles":["postgres","cpk","secrets","gateway","signer"]}


def main():
    def timed_out(*args):
        raise TimeoutError
    signal.signal(signal.SIGALRM,timed_out)
    signal.alarm(60)
    try:
        if len(sys.argv)==3 and sys.argv[1]=="provenance":
            result=provenance(json.loads(Path(sys.argv[2]).read_text()))
        elif len(sys.argv)==2 and sys.argv[1]=="readiness":
            result=readiness()
        elif len(sys.argv)==3 and sys.argv[1]=="logs":
            result=logs(Path(sys.argv[2]),Path("/provider"),Path("/client"))
        else:
            raise ValueError
    except Exception:
        print("gateway packaged inspection failed",file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
