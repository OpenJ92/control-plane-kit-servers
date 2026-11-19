"""Normal pinned interpreter stop path, restricted to this witness container."""
import sys
import docker
from control_plane_kit_interpreters.docker.sdk import DockerSdkClient

identity, case = sys.argv[1:]
client = docker.from_env(timeout=30)
item = client.containers.get(identity)
item.reload()
assert item.id == identity
assert item.attrs["Name"] == "/cpk-website190-drain-" + case
assert item.attrs["Config"]["Labels"]["cpk.witness.owner"] == "rowan-website190-drain"
assert item.attrs["Config"].get("StopTimeout") in (None, 10)
# No timeout argument: this is the ordinary selected StopNode provider method.
DockerSdkClient(client=client).stop_container(identity)
