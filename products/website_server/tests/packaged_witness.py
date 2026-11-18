"""Explicit Docker witness for #190. No provider or authenticated API request.

Run with host Python: packaged_witness.py IMAGE FIXTURE_DIRECTORY
Owns only newly created labeled containers. Retains image and input fixture.
"""
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
import time

IMAGE, DIRECTORY, *outcomes = sys.argv[1:]
EXPECTED = outcomes[0] if outcomes else "healthy"
assert EXPECTED in ("healthy", "unhealthy")
OWNER = "rowan-website190"


def docker(*arguments):
    return subprocess.check_output(["docker", "--context", "desktop-linux", *arguments], text=True).strip()


def request(port, path, credential=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path, headers={} if credential is None else {"Authorization": "Bearer " + credential})
        response = connection.getresponse()
        body = response.read(5 * 1048576 + 1)
        assert len(body) <= 5 * 1048576
        return response.status, response.getheader("Content-Type"), body
    finally:
        connection.close()


def observed(container):
    return json.loads(docker("inspect", container))[0]


def wait_exit(container):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = observed(container)["State"]
        if not state["Running"]:
            return state
        time.sleep(0.1)
    raise AssertionError("Owned entrypoint did not exit")


for suffix, action in (("term", "term"), ("node-exit", "node-exit"), ("replacement", "term")):
    name = "cpk-website190-" + suffix
    container = None
    try:
        container = docker(
            "run", "--detach", "--name", name, "--label", "cpk.witness.owner=" + OWNER,
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--restart", "no", "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
            "--mount", "type=bind,src=" + str(Path(DIRECTORY).resolve() / "control.json") +
            ",dst=/etc/cpk/website/control.json,readonly",
            "--env", "CPK_WEB_UPSTREAM=https://child.example.invalid",
            "--publish", "127.0.0.1::8080", "--publish", "127.0.0.1::8000", IMAGE)
        item = observed(container)
        ports = item["NetworkSettings"]["Ports"]
        visitor = int(ports["8080/tcp"][0]["HostPort"])
        management = int(ports["8000/tcp"][0]["HostPort"])
        deadline = time.monotonic() + 15
        while True:
            try:
                status, mime, page = request(visitor, "/index.html")
                assert status == 200 and mime == "text/html; charset=utf-8"
                break
            except (OSError, http.client.HTTPException):
                assert time.monotonic() < deadline
                time.sleep(0.1)
        assert b'<div id="root"></div>' in page
        entry = re.search(rb'src="(/assets/[^"]+\.js)"', page)
        assert entry is not None
        status, mime, asset = request(visitor, entry.group(1).decode())
        assert status == 200 and mime == "text/javascript; charset=utf-8" and len(asset) > 100
        assert request(management, "/__control/health/readiness")[0] == 401
        credential = (Path(DIRECTORY) / "synthetic-health.jwt").read_text()
        status, _, body = request(management, "/__control/health/readiness", credential)
        assert status == 200
        outcome = json.loads(body)
        deadline = time.monotonic() + 5
        while outcome["outcome"] == "unknown" and time.monotonic() < deadline:
            time.sleep(0.05)
            status, _, body = request(management, "/__control/health/readiness", credential)
            assert status == 200
            outcome = json.loads(body)
        assert outcome["outcome"] == EXPECTED
        assert outcome["request_id"] == "health-request"
        assert request(management, "/index.html")[0] == 404
        # Visitor surface cannot return the protected management read.
        assert request(visitor, "/__control/health/readiness")[0] == 404
        if action == "node-exit":
            # Signal only the direct Node child of the owned PID1 wrapper.
            docker("exec", container, "/opt/cpk-website/bin/python", "-c",
                   "import os,signal; p=open('/proc/1/task/1/children').read().split();"
                   "assert len(p)==1; os.kill(int(p[0]),signal.SIGTERM)")
        else:
            docker("kill", "--signal", "TERM", container)
        state = wait_exit(container)
        assert state["ExitCode"] == (1 if action == "node-exit" else 0)
        print(json.dumps({"case": suffix, "website": "served", "management": "protected",
                          "exit": state["ExitCode"], "readiness": outcome["outcome"]}))
    finally:
        if container is not None:
            item = observed(container)
            assert item["Config"]["Labels"]["cpk.witness.owner"] == OWNER
            assert item["Name"] == "/" + name
            if item["State"]["Running"]:
                docker("stop", "--time", "12", container)
            docker("rm", container)
