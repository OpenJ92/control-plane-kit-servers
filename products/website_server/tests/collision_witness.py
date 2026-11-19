"""Foreign identical index must never give the owned child positive readiness."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import time

image, directory = sys.argv[1:]
name, owner = "cpk-website190-collision", "rowan-website190-collision"


def docker(*args):
    return subprocess.check_output(["docker","--context","desktop-linux",*args],text=True).strip()


def get(port,path,credential=None):
    connection = http.client.HTTPConnection("127.0.0.1",port,timeout=1)
    try:
        connection.request("GET",path,headers={} if credential is None else {"Authorization":"Bearer "+credential})
        response = connection.getresponse()
        return response.status,response.read(5*1048576)
    finally:
        connection.close()


container = None
try:
    container = docker("run","--detach","--name",name,"--label","cpk.witness.owner="+owner,
                       "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                       "--restart","no","--env","CPK_WEB_UPSTREAM=https://child.example.invalid",
                       "--mount","type=bind,src="+str(Path(directory).resolve()/"control.json")+
                       ",dst=/etc/cpk/website/control.json,readonly",
                       "--publish","127.0.0.1::8080","--publish","127.0.0.1::8000",image)
    info = json.loads(docker("inspect",container))[0]
    ports = info["NetworkSettings"]["Ports"]
    visitor, management = (int(ports[key][0]["HostPort"]) for key in ("8080/tcp","8000/tcp"))
    credential = (Path(directory)/"synthetic-health.jwt").read_text()
    deadline = time.monotonic()+15
    responses = 0
    saw_page = False
    while time.monotonic() < deadline:
        info = json.loads(docker("inspect",container))[0]
        if not info["State"]["Running"]:
            break
        try:
            status,body = get(visitor,"/index.html")
            saw_page = saw_page or status == 200 and b'<div id="root"></div>' in body
            status,body = get(management,"/__control/health/readiness",credential)
            assert status == 200
            assert json.loads(body)["outcome"] == "unknown"
            responses += 1
        except (OSError,http.client.HTTPException):
            time.sleep(0.05)
    assert not info["State"]["Running"]
    assert info["State"]["ExitCode"] == 1
    assert saw_page and responses > 0
    print(json.dumps({"foreign_page":"identical","authorized_reads":responses,"outcome":"unknown","exit":1}))
finally:
    if container is not None:
        info = json.loads(docker("inspect",container))[0]
        assert info["Name"] == "/"+name
        assert info["Config"]["Labels"]["cpk.witness.owner"] == owner
        if info["State"]["Running"]:
            docker("stop","--time","10",container)
        docker("rm",container)
