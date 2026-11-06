"""Explicit fixture-only late-response witness for the real supervisor."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time

image, directory, case = sys.argv[1:]
assert case in ("fast", "slow")
owner = "rowan-website190-drain"
name = "cpk-website190-drain-" + case


def docker(*args):
    return subprocess.check_output(["docker", "--context", "desktop-linux", *args], text=True).strip()


container = None
response_result = []
try:
    container = docker("run", "--detach", "--name", name, "--label", "cpk.witness.owner=" + owner,
                       "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                       "--restart", "no", "--tmpfs", "/run/witness:rw,mode=1777",
                       "--mount", "type=bind,src=" + str(Path(directory).resolve() / "control.json") +
                       ",dst=/etc/cpk/website/control.json,readonly",
                       "--env", "CPK_WEB_UPSTREAM=https://synthetic.example.invalid",
                       "--publish", "127.0.0.1::8080", image)
    info = json.loads(docker("inspect", container))[0]
    port = int(info["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"])
    deadline = time.monotonic() + 15
    while True:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/index.html")
            assert connection.getresponse().status == 200
            connection.close()
            break
        except OSError:
            assert time.monotonic() < deadline
            time.sleep(0.1)

    def request():
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        try:
            body = json.dumps({"session_id":"synthetic-session","decision":"approved",
                               "idempotency_key":"synthetic-once"})
            connection.request("POST", "/api/workspaces/" + case + "/approvals/synthetic/decision",
                               body=body, headers={"Authorization":"Bearer synthetic-test-only",
                                                   "Content-Type":"application/json"})
            response = connection.getresponse()
            response_result.append((response.status, response.read()))
        except Exception:
            response_result.append(("failed", b""))
        finally:
            connection.close()

    reader = Thread(target=request)
    reader.start()
    while docker("exec", container, "/usr/local/bin/node", "-e",
                 "process.stdout.write(String(require('fs').existsSync('/run/witness/admitted')))") != "true":
        assert time.monotonic() < deadline
        time.sleep(0.1)
    source = str(Path(__file__).resolve().parents[3])
    docker("run", "--rm", "--network", "none",
           "--volume", "/var/run/docker.sock:/var/run/docker.sock",
           "--volume", source + ":/source:ro",
           "--env", "PYTHONDONTWRITEBYTECODE=1",
           "control-plane-kit-servers-test:379-trace-red", "python",
           "/source/products/website_server/tests/stop_owned.py", container, case)
    reader.join(2)
    assert not reader.is_alive()
    expected = (200, b'{"recorded":true}') if case == "fast" else (504, b'{"error":"upstream_timeout"}')
    assert response_result == [expected], response_result
    info = json.loads(docker("inspect", container))[0]
    assert info["State"]["ExitCode"] == 0
    print(json.dumps({"case":case,"response":expected[0],"supervisor_exit":0,"stop_path":"ordinary-sdk-default"}))
finally:
    if container is not None:
        info = json.loads(docker("inspect", container))[0]
        assert info["Name"] == "/" + name
        assert info["Config"]["Labels"]["cpk.witness.owner"] == owner
        if info["State"]["Running"]:
            docker("stop", "--time", "10", container)
        docker("rm", container)
