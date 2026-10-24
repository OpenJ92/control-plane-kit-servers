"""Current Hello/gateway artifact checks in the existing owned Docker fixture.

The same socket checks accept source IDs or genuine cached published digests.
No registry login/pull, CPK orchestration, provider mutation or synthetic health.
"""
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4

import docker
import httpx
import control_plane_kit_core as core
from control_plane_kit_interpreters.docker import DockerSdkConfigurationMount
from control_plane_kit_interpreters.docker.sdk import matches_image_reference
from products.cpk_server.tests.docker_image_update_identity import (
    FIXED, fixed_manifest_bytes, qualify_fixed_image,
)
from control_plane_kit_servers_hello_server.configuration import (
    hello_control_configuration_artifact, hello_control_declaration, hello_source_runtime_contract,
)
from control_plane_kit_servers_cpk_local_gateway import control_configuration as gateway_control
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_source_runtime_contract
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from gateway_control_fixtures import fixture, credential
from health_relay_fixtures import World


ATTRIBUTION = b"<p>Served by Control Plane Kit Hello.</p>"


def _require_hello_provenance(installed, *, mode):
    """Source builds follow canonical inputs; the published family stays fixed."""
    assert mode in ("source-built", "published-digest")
    if mode == "source-built":
        upstreams = json.loads((Path(__file__).resolve().parents[3] /
            "coordinates/server-products.json").read_text())["upstreams"]
        core_commit = upstreams["control_plane_kit_core_commit"]
        sdk_commit = upstreams["control_plane_kit_server_sdk_commit"]
    else:
        core_commit = "9861e536e79314005499ae07379f627bfb1599a2"
        sdk_commit = "d4e7c4d91c054f139e2971774ae5e37fc741262d"
    assert installed == {
        "control-plane-kit-core": f"https://github.com/OpenJ92/control-plane-kit/archive/{core_commit}.zip",
        "control-plane-kit-server-sdk": f"https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/{sdk_commit}.zip",
    }, "Hello installed provenance differs from its artifact mode"


def _read(method, origin, path, *, token=None, body=None):
    headers = {} if token is None else {"Authorization": "Bearer " + token}
    with httpx.stream(method, origin + path, headers=headers, json=body,
                      timeout=5, trust_env=False, follow_redirects=False) as response:
        content = bytearray()
        for chunk in response.iter_bytes(chunk_size=4096):
            assert len(content) + len(chunk) <= 65536, "artifact response exceeds bound"
            content.extend(chunk)
        return response.status_code, bytes(content)


def _controls(origin, value, sensitive):
    static_token = None
    for static, kind, path in (
            (True, core.NodeHealthReadKind.READINESS, "/__control/capabilities"),
            *((False, kind, "/__control/health/" + kind.value)
              for kind in value.config.declaration.surface.health_reads)):
        now = int(time.time())
        request, token = credential(value, static=static, kind=kind, issued=now - 1, expires=now + 60)
        sensitive.append(token)
        status, body = _read("GET", origin, path, token=token)
        assert status == 200, "artifact protected read failed"
        if static:
            static_token = token
            expected = core.ReceiverControlSurfaceReadResultCodec(request, value.config.declaration).capabilities_result()
            assert body == expected.canonical_bytes(), "artifact capabilities differ"
        else:
            result = core.ReceiverHealthReadResultCodec(request, value.config.declaration).decode(json.loads(body))
            assert result.outcome is core.NodeHealthReadOutcome.HEALTHY
            assert _read("GET", origin, path, token=static_token)[0] == 401
        assert _read("GET", origin, path)[0] == 401, "artifact accepted missing credential"
    assert _read("GET", origin, "/__control/health/readiness", token=static_token)[0] == 401
    wrong = replace(value.config.target, receiver_id="f" * 32)
    _, denied = credential(value, request_changes={"target": wrong}, issued=now - 1, expires=now + 60)
    sensitive.append(denied)
    assert _read("GET", origin, "/__control/health/readiness", token=denied)[0] == 401
    if core.NodeHealthReadKind.LIVENESS not in value.config.declaration.surface.health_reads:
        _, undeclared = credential(value, kind=core.NodeHealthReadKind.LIVENESS,
            issued=now - 1, expires=now + 60)
        sensitive.append(undeclared)
        assert _read("GET", origin, "/__control/health/liveness", token=undeclared)[0] == 401


def exercise_wrapper_artifacts(*, engine, sdk, resources, labels, network_id,
                               hello_reference, gateway_reference, mode, expected_attribution, expected_source=None,
                               hello_health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS),
                               expected_execution_ids=None):
    """Caller owns the existing exact cleanup ledger, daemon and internal network."""
    assert mode in ("source-built", "published-digest")
    assert hello_health_reads in ((core.NodeHealthReadKind.READINESS,),
        (core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS))
    images = {}
    for name, reference in (("hello", hello_reference), ("gateway", gateway_reference)):
        # Read only: missing/evicted cache is a failed prerequisite, never a pull.
        observed = sdk.inspect_image(reference)
        assert observed is not None, "artifact image is absent from selected daemon"
        raw = engine.images.get(reference)
        assert raw.id == observed.image_id and raw.attrs["Os"] == "linux"
        if mode == "published-digest":
            product = "hello-server" if name == "hello" else "cpk-local-gateway"
            assert reference.startswith("ghcr.io/openj92/control-plane-kit-servers/" + product + "@sha256:")
            assert matches_image_reference(reference, observed.repo_digests)
            assert raw.attrs["Architecture"] == "amd64", "published tuple platform differs"
            fixed_role = next((role for role, selected in FIXED.items()
                               if selected["reference"] == reference), None)
            if fixed_role is not None:
                qualify_fixed_image(fixed_role, reference=reference,
                    manifest_bytes=fixed_manifest_bytes(fixed_role), image_attrs=raw.attrs,
                    interpreter_image_id=observed.image_id)
        else:
            assert reference == observed.image_id
            assert raw.labels.get("org.openj92.cpk.test-run") == labels["org.openj92.cpk.test-run"]
        assert observed.configured_user in ({"hello", "10002"} if name == "hello" else {"gateway", "10005"})
        if name == "hello" and expected_source is not None:
            assert raw.labels.get("org.opencontainers.image.revision") == expected_source
        if expected_execution_ids is not None:
            assert set(expected_execution_ids) == {"hello", "gateway"}
            assert observed.image_id == expected_execution_ids[name], "admitted image identity changed"
        images[name] = (observed.image_id, raw.attrs["Architecture"])

    world = World()
    world.target = replace(world.target, provider_socket_name=core.NodeControlGraphReference(
        core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"))
    default = hello_control_declaration()
    world.declaration = replace(default, surface=replace(default.surface, health_reads=hello_health_reads))
    hello_config = core.ReceiverNodeControlConfiguration(world.target, world.declaration, (
        NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            "surface-issuer", (world.static_key,)),
        NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
            "workload-issuer", (world.key,))))
    hello_artifact = hello_control_configuration_artifact(hello_config)
    world.contract = hello_source_runtime_contract(hello_artifact)
    hello = SimpleNamespace(config=hello_config, world=world)
    gateway = fixture(gateway_control, world)
    gateway_contract = gateway_health_source_runtime_contract(*gateway.artifacts)
    sensitive, containers = [], []

    def launch(name, artifacts, environment, alias):
        mounts = []
        for artifact in artifacts:
            volume = engine.volumes.create(name="cpk-wrapper-public-" + uuid4().hex, labels=labels)
            resources.append((engine.volumes, volume.name))
            sdk.materialize_configuration_artifact(volume.name, artifact)
            assert sdk.configuration_artifact_digest(volume.name) == artifact.content_digest
            mounts.append(dict(DockerSdkConfigurationMount(artifact, volume.name).docker_mount()))
        container = engine.containers.create(images[name][0], name="cpk-wrapper-" + uuid4().hex,
            labels=labels, environment=environment, mounts=mounts, network=network_id,
            networking_config={network_id: engine.api.create_endpoint_config(aliases=[alias])},
            cap_drop=["ALL"], security_opt=["no-new-privileges"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}))
        resources.append((engine.containers, container.id))
        containers.append(container)
        container.start()
        container.reload()
        assert container.attrs["Image"] == images[name][0]
        assert not container.attrs["HostConfig"]["PortBindings"]
        actual = {item["Destination"]: item for item in container.attrs["Mounts"]}
        for mount in mounts:
            assert actual[mount["Target"]]["Name"] == mount["Source"]
            assert actual[mount["Target"]]["RW"] is False
        return container

    def environment(contract):
        return {item.name: item.value for item in contract.public_environment}

    try:
        hello_process = launch("hello", (hello_artifact,), environment(world.contract), "wrapped-db")
        gateway_process = launch("gateway", gateway.artifacts, environment(gateway_contract), "wrapped-gateway")
        for process, origin in ((hello_process, "http://wrapped-db:8000"),
                                (gateway_process, "http://wrapped-gateway:8000")):
            readiness = "not-observed"
            for _ in range(30):
                process.reload()
                assert process.status == "running", "artifact exited before serving"
                try:
                    # Read-only readiness polling; no mutation is retried.
                    readiness = str(_read("GET", origin, "/__control/capabilities")[0])
                    if readiness == "401":
                        break
                except httpx.TransportError:
                    readiness = "transport-unavailable"
                time.sleep(0.2)
            else:
                raise AssertionError("artifact listener did not become available: " + readiness)
        status, body = _read("GET", "http://wrapped-db:8000", "/")
        assert status == 200 and b"<h1>Hello, world!</h1>" in body
        assert (ATTRIBUTION in body) is expected_attribution, "artifact business response differs"
        _controls("http://wrapped-db:8000", hello, sensitive)
        _controls("http://wrapped-gateway:8000", gateway, sensitive)
        now = int(time.time())
        if world.declaration != default:
            _, prior = credential(hello, request_changes={"declaration_identity": default.identity()},
                issued=now - 1, expires=now + 60)
            sensitive.append(prior)
            assert _read("GET", "http://wrapped-db:8000", "/__control/health/readiness", token=prior)[0] == 401
        request, workload_token = credential(hello, issued=now - 1, expires=now + 60)
        transit = world.transit.token(world.transit.grant(request, issued_at=now - 1,
            not_before=now - 1, expires_at=now + 60)).decode()
        sensitive.extend((workload_token, transit))
        envelope = {"profile": "cpk-gateway-health-relay-request.v2", "target_id": "database-management",
            "attempt_id": "attempt-a", "request": request.descriptor(), "workload_credential": workload_token}
        status, body = _read("POST", "http://wrapped-gateway:8000", "/cpk/health/readiness",
            token=transit, body=envelope)
        assert status == 200, "artifact signed gateway transit failed"
        result = core.ReceiverHealthReadResultCodec(request, world.declaration).decode(json.loads(body))
        assert result.outcome is core.NodeHealthReadOutcome.HEALTHY
        assert _read("POST", "http://wrapped-gateway:8000", "/cpk/health/readiness",
            token=workload_token, body=envelope)[0] == 401
        assert _read("POST", "http://wrapped-gateway:8000", "/cpk/health/readiness",
            token=transit, body={**envelope, "target_id": "not-installed"})[0] == 403
        for name in ("hello", "gateway"):
            refused = launch(name, (), {}, "unconfigured-" + uuid4().hex)
            assert refused.wait(timeout=20)["StatusCode"] != 0, "artifact accepted absent configuration"
            artifacts = (hello_artifact,) if name == "hello" else gateway.artifacts
            malformed = (*artifacts[:-1], replace(artifacts[-1], content="{}", source_digest=None))
            refused = launch(name, malformed, {}, "malformed-" + uuid4().hex)
            assert refused.wait(timeout=20)["StatusCode"] != 0, "artifact accepted malformed configuration"
        for process, uid in ((hello_process, 10002), (gateway_process, 10005)):
            observed = process.exec_run(["python", "-B", "-c", "import os; print(os.getuid())"])
            assert observed.exit_code == 0 and observed.output.strip() == str(uid).encode()
        installed_provenance = None
        if mode == "source-built" or expected_source is not None:
            provenance = hello_process.exec_run(["python", "-B", "-c",
                "import importlib.metadata as m,json; print(json.dumps({n:json.loads(m.distribution(n).read_text('direct_url.json'))['url'] for n in ('control-plane-kit-core','control-plane-kit-server-sdk')},sort_keys=True))"])
            assert provenance.exit_code == 0
            installed_provenance = json.loads(provenance.output)
            _require_hello_provenance(installed_provenance, mode=mode)
        for container in containers:
            output = container.logs(tail=100)
            assert len(output) <= 1024 * 1024
            assert not any(value.encode() in output for value in sensitive), "artifact logged credentials"
        observation = {"wrapper_artifacts": "passed", "mode": mode,
            "hello_reference": hello_reference, "gateway_reference": gateway_reference,
            "engine_id": engine.info().get("ID"),
            "hello_image_id": images["hello"][0], "gateway_image_id": images["gateway"][0],
            "hello_platform": "linux/" + images["hello"][1], "gateway_platform": "linux/" + images["gateway"][1],
            "hello_health_reads": [kind.value for kind in hello_health_reads],
            "hello_configuration_digest": hello_artifact.content_digest,
            "hello_attribution": expected_attribution, "signed_v2_sockets": True,
            "hello_source_revision": engine.images.get(hello_reference).labels.get("org.opencontainers.image.revision"),
            "hello_runtime_uid": 10002, "hello_installed_provenance": installed_provenance}
        print(json.dumps(observation), flush=True)
        return observation
    finally:
        # Retire aliases before another pair; the outer ledger verifies exact absence
        # and removes all recorded public volumes even if this cleanup is interrupted.
        for container in reversed(containers):
            container.reload()
            assert container.labels.get("org.openj92.cpk.test-run") == labels["org.openj92.cpk.test-run"]
            container.remove(force=True)
