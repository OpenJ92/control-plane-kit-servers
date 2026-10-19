"""One-shot source-image witness; invoked only by the repository Docker gate."""
from __future__ import annotations

import os
from pathlib import Path
import time

import docker

from postgres_control_fixtures import fixture, readiness_only
from control_plane_kit_servers_postgres_server.configuration import postgres_control_configuration_artifact


RUN = os.environ["CPK_POSTGRES_TEST_RUN"]
HOST_RECORDS = Path(os.environ["CPK_POSTGRES_HOST_RECORDS"])
RECORDS = Path("/witness")
LABELS = {"org.openj92.cpk.test-run": RUN, "org.openj92.project": "control-plane-kit-servers"}
PASSWORD = "postgres-source-witness-password"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prepare_files() -> None:
    artifact = postgres_control_configuration_artifact(readiness_only(fixture().config))
    control = RECORDS / "control.json"
    secret = RECORDS / "password"
    init = RECORDS / "10-witness.sql"
    control.write_text(artifact.content, encoding="utf-8")
    control.chmod(0o444)
    secret.write_text(PASSWORD + "\n", encoding="utf-8")
    secret.chmod(0o400)
    os.chown(secret, 70, 70)
    init.write_text(
        "SELECT pg_sleep(2); CREATE TABLE cpk_witness(value text NOT NULL); "
        "INSERT INTO cpk_witness VALUES ('retained-row');\n",
        encoding="utf-8",
    )
    init.chmod(0o444)


def wait_running(container, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        container.reload()
        if container.status == "running":
            return
        if container.status in {"exited", "dead"}:
            raise AssertionError("PostgreSQL source container exited before running")
        time.sleep(0.1)
    raise AssertionError("PostgreSQL source container did not run")


def wait_query(container, seconds: float = 45.0) -> None:
    deadline = time.monotonic() + seconds
    command = ("/usr/local/bin/psql", "-X", "-U", "cpk", "-d", "cpk", "-tA", "-c",
               "SELECT value FROM cpk_witness;")
    while time.monotonic() < deadline:
        container.reload()
        if container.status != "running":
            raise AssertionError("PostgreSQL source container exited before readiness")
        result = container.exec_run(command, stdin=False, demux=True)
        stdout, stderr = result.output
        if result.exit_code == 0 and stdout == b"retained-row\n":
            require(not stderr, "successful retained query wrote stderr")
            return
        time.sleep(0.25)
    raise AssertionError("PostgreSQL retained row was not queryable")


def wait_exit(container, expected: int, seconds: float = 15.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        container.reload()
        if container.status == "exited":
            require(container.attrs["State"]["ExitCode"] == expected, "unexpected container exit")
            return
        time.sleep(0.1)
    raise AssertionError("PostgreSQL source container did not exit")


def mounts(volume_name: str, *, init: bool) -> dict[str, dict[str, str]]:
    values = {
        volume_name: {"bind": "/var/lib/postgresql/data", "mode": "rw"},
        str(HOST_RECORDS / "control.json"): {"bind": "/etc/cpk/postgres/control.json", "mode": "ro"},
        str(HOST_RECORDS / "password"): {"bind": "/run/secrets/postgres/password", "mode": "ro"},
    }
    if init:
        values[str(HOST_RECORDS / "10-witness.sql")] = {
            "bind": "/docker-entrypoint-initdb.d/10-witness.sql", "mode": "ro"
        }
    return values


def create(client, image_id: str, network_name: str, volume_name: str, suffix: str, *, init: bool = False):
    return client.containers.create(
        image_id,
        name=f"{RUN}-{suffix}",
        labels=LABELS,
        network=network_name,
        volumes=mounts(volume_name, init=init),
    )


def main() -> int:
    client = docker.from_env()
    image = None
    network = None
    volumes = []
    containers = []
    tag = f"control-plane-kit-postgres-source:{RUN}"
    try:
        prepare_files()
        image, _ = client.images.build(
            path="/source", dockerfile="products/postgres_server/Dockerfile", tag=tag,
            labels=LABELS, rm=True,
        )
        image.reload()
        require(image.attrs["Config"]["User"] == "70:70", "image is not uid/gid 70")
        require(image.attrs["Config"]["Entrypoint"] in (None, []), "upstream entrypoint remains active")
        require("5432/tcp" in image.attrs["Config"]["ExposedPorts"], "native port missing")
        require("8000/tcp" in image.attrs["Config"]["ExposedPorts"], "management port missing")

        network = client.networks.create(f"{RUN}-network", internal=True, labels=LABELS)
        data = client.volumes.create(name=f"{RUN}-data", labels=LABELS)
        volumes.append(data)

        first = create(client, image.id, network.name, data.name, "first", init=True)
        containers.append(first)
        first.start()
        wait_running(first)
        wait_query(first)
        require(first.attrs["HostConfig"]["Binds"] is not None, "expected fixed mounts")
        require("docker.sock" not in repr(first.attrs["Mounts"]), "Docker socket reached product")
        first.stop(timeout=10)
        wait_exit(first, 0)
        require(PASSWORD.encode() not in first.logs(stdout=True, stderr=True), "password reached logs")
        first.remove()
        containers.remove(first)

        restarted = create(client, image.id, network.name, data.name, "restart")
        containers.append(restarted)
        restarted.start()
        wait_running(restarted)
        wait_query(restarted)
        restarted.exec_run(("python3", "-c", "import os; os.kill(int(open('/var/lib/postgresql/data/postmaster.pid').readline()), 15)"))
        wait_exit(restarted, 1)
        require(PASSWORD.encode() not in restarted.logs(stdout=True, stderr=True), "password reached failure logs")
        restarted.remove()
        containers.remove(restarted)

        recovery = create(client, image.id, network.name, data.name, "recovery")
        containers.append(recovery)
        recovery.start()
        wait_running(recovery)
        wait_query(recovery)
        recovery.kill(signal="KILL")
        wait_exit(recovery, 137)
        recovery.remove()
        containers.remove(recovery)

        recovered = create(client, image.id, network.name, data.name, "recovered")
        containers.append(recovered)
        recovered.start()
        wait_running(recovered)
        wait_query(recovered)
        recovered.stop(timeout=10)
        wait_exit(recovered, 0)
        recovered.remove()
        containers.remove(recovered)

        wrong = client.volumes.create(name=f"{RUN}-wrong-owner", labels=LABELS)
        volumes.append(wrong)
        owner = client.containers.run(
            image.id, ("sh", "-c", "chown 0:0 /var/lib/postgresql/data"), user="0:0",
            volumes={wrong.name: {"bind": "/var/lib/postgresql/data", "mode": "rw"}}, remove=True,
        )
        require(owner == b"", "owner setup returned output")
        refused = create(client, image.id, network.name, wrong.name, "wrong-owner")
        containers.append(refused)
        refused.start()
        wait_exit(refused, 1)
        require(PASSWORD.encode() not in refused.logs(stdout=True, stderr=True), "password reached refusal logs")
        return 0
    finally:
        for container in reversed(containers):
            container.reload()
            require(container.labels.get("org.openj92.cpk.test-run") == RUN, "foreign container cleanup refused")
            container.remove(force=True)
        for volume in reversed(volumes):
            volume.reload()
            require(volume.attrs["Labels"].get("org.openj92.cpk.test-run") == RUN, "foreign volume cleanup refused")
            volume.remove(force=True)
        if network is not None:
            network.reload()
            require(network.attrs["Labels"].get("org.openj92.cpk.test-run") == RUN, "foreign network cleanup refused")
            network.remove()
        if image is not None:
            image.reload()
            require(image.labels.get("org.openj92.cpk.test-run") == RUN, "foreign image cleanup refused")
            client.images.remove(tag, force=True)


if __name__ == "__main__":
    raise SystemExit(main())
