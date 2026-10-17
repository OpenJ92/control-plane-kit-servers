"""One source-built generic SDK image under two declarations, in the owner ledger."""
from dataclasses import replace
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import docker
import httpx
import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from control_plane_kit_interpreters.docker import DockerSdkConfigurationMount
from gateway_control_fixtures import credential
from health_relay_fixtures import World
from live_wrapper_artifacts import _read


def exercise_counter_artifact(*, engine, sdk, resources, labels, network_id, image_id):
    """Reuse the existing controller/network/cleanup; no orchestration or OCI claim."""
    image = engine.images.get(image_id)
    assert image.id == image_id
    assert image.labels.get("org.openj92.cpk.test-run") == labels["org.openj92.cpk.test-run"]
    assert (image.attrs["Os"], image.attrs["Architecture"]) == ("linux", "amd64")
    assert image.attrs["Config"]["User"] == "10008"
    world = World()
    target = replace(world.target, provider_socket_name=core.NodeControlGraphReference(
        core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"))
    families = (
        NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            "surface-issuer", (world.static_key,)),
        NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
            "workload-issuer", (world.key,)),
    )
    containers, sensitive, observations = [], [], []
    try:
        for kinds in ((core.NodeHealthReadKind.READINESS,),
                (core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)):
            declaration = core.WorkloadNodeControlSurfaceDeclaration(
                core.WorkloadNodeControlSurfaceDescriptor(target.provider_socket_name, (), health_reads=kinds),
                profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
            config = core.ReceiverNodeControlConfiguration(target, declaration, families)
            value = SimpleNamespace(config=config, world=world)
            artifact = ConfigurationArtifact("counter-control", "/etc/cpk/counter/control.json",
                ConfigurationMediaType.JSON, core.ReceiverNodeControlConfigurationCodec().encode_bytes(config).decode())
            volume = engine.volumes.create(name="cpk-counter-public-" + uuid4().hex, labels=labels)
            resources.append((engine.volumes, volume.name))
            sdk.materialize_configuration_artifact(volume.name, artifact)
            assert sdk.configuration_artifact_digest(volume.name) == artifact.content_digest
            mount = dict(DockerSdkConfigurationMount(artifact, volume.name).docker_mount())
            alias = "counter-" + uuid4().hex
            process = engine.containers.create(image_id, name="cpk-counter-" + uuid4().hex,
                labels=labels, mounts=[mount], network=network_id,
                networking_config={network_id: engine.api.create_endpoint_config(aliases=[alias])},
                cap_drop=["ALL"], security_opt=["no-new-privileges"],
                log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}))
            resources.append((engine.containers, process.id))
            containers.append(process)
            process.start()
            origin = "http://" + alias + ":8000"
            readiness = "not-observed"
            for _ in range(30):
                process.reload()
                assert process.status == "running", "counter exited before serving"
                try:
                    readiness = str(_read("GET", origin, "/__control/capabilities")[0])
                    if readiness == "401":
                        break
                except httpx.TransportError:
                    readiness = "transport-unavailable"
                time.sleep(0.2)
            else:
                raise AssertionError("counter listener did not become available: " + readiness)
            assert process.attrs["Image"] == image_id
            assert not process.attrs["HostConfig"]["PortBindings"]
            actual, = process.attrs["Mounts"]
            assert actual["Destination"] == artifact.target_path
            assert actual["Name"] == volume.name and actual["RW"] is False
            assert _read("GET", origin, "/count") == (200, b"1")
            assert _read("GET", origin, "/count") == (200, b"2")
            now = int(time.time())
            static_request, static_token = credential(value, static=True, issued=now - 1, expires=now + 60)
            sensitive.append(static_token)
            expected = core.ReceiverControlSurfaceReadResultCodec(static_request, declaration).capabilities_result()
            assert _read("GET", origin, "/__control/capabilities", token=static_token) == (200, expected.canonical_bytes())
            for kind in kinds:
                request, token = credential(value, kind=kind, issued=now - 1, expires=now + 60)
                sensitive.append(token)
                path = "/__control/health/" + kind.value
                status, body = _read("GET", origin, path, token=token)
                assert status == 200
                result = core.ReceiverHealthReadResultCodec(request, declaration).decode(json.loads(body))
                assert result.outcome is core.NodeHealthReadOutcome.HEALTHY
                assert _read("GET", origin, path)[0] == 401
                assert _read("GET", origin, path, token=static_token)[0] == 401
            _, wrong = credential(value, request_changes={"target": replace(target, receiver_id="f" * 32)},
                issued=now - 1, expires=now + 60)
            sensitive.append(wrong)
            assert _read("GET", origin, "/__control/health/readiness", token=wrong)[0] == 401
            if core.NodeHealthReadKind.LIVENESS not in kinds:
                _, undeclared = credential(value, kind=core.NodeHealthReadKind.LIVENESS,
                    issued=now - 1, expires=now + 60)
                sensitive.append(undeclared)
                assert _read("GET", origin, "/__control/health/liveness", token=undeclared)[0] == 401
            observed = process.exec_run(["python", "-B", "-c", "import os; print(os.getuid())"])
            assert observed.exit_code == 0 and observed.output.strip() == b"10008"
            provenance = process.exec_run(["python", "-B", "-c",
                "import importlib.metadata as m,json; print(json.dumps({n:json.loads(m.distribution(n).read_text('direct_url.json'))['url'] for n in ('control-plane-kit-core','control-plane-kit-server-sdk')},sort_keys=True))"])
            assert provenance.exit_code == 0
            assert json.loads(provenance.output) == {
                "control-plane-kit-core": "https://github.com/OpenJ92/control-plane-kit/archive/9861e536e79314005499ae07379f627bfb1599a2.zip",
                "control-plane-kit-server-sdk": "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/d4e7c4d91c054f139e2971774ae5e37fc741262d.zip",
            }
            output = process.logs(tail=100)
            assert len(output) <= 1024 * 1024 and not any(token.encode() in output for token in sensitive)
            observations.append({"health_reads": [kind.value for kind in kinds],
                "configuration_digest": artifact.content_digest, "protected_reads": True})
        print(json.dumps({"counter_artifact": "passed", "mode": "source-built", "image_id": image_id,
            "platform": "linux/amd64", "uid": 10008, "declarations": observations,
            "same_image": True, "sdk_commit": "d4e7c4d91c054f139e2971774ae5e37fc741262d",
            "core_commit": "9861e536e79314005499ae07379f627bfb1599a2"}), flush=True)
    finally:
        for process in reversed(containers):
            process.reload()
            assert process.labels.get("org.openj92.cpk.test-run") == labels["org.openj92.cpk.test-run"]
            process.remove(force=True)
