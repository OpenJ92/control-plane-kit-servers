"""CPK recipient proof within the owning numeric bootstrap Docker fixture."""

from __future__ import annotations

import hashlib
import json
import secrets
from uuid import uuid4

from control_plane_kit_core.secrets import SecretFileMode, SecretValue
from control_plane_kit_interpreters.docker import DockerSdkSecretMount


def exercise_cpk_file(*, engine, sdk, resources, labels, image_id, network_id):
    """Use the actual image default user; fixture owns exact-resource cleanup."""
    assert engine.images.get(image_id).labels.get("org.openj92.cpk.test-run") == labels[
        "org.openj92.cpk.test-run"
    ]
    image = sdk.inspect_image(image_id)
    assert image is not None and image.image_id == image_id
    uid = image.secret_file_owner_uid()
    assert uid == 10001, "CPK image must advertise numeric UID10001"
    value = secrets.token_urlsafe(48)
    digest = hashlib.sha256(value.encode()).hexdigest()
    target = "/run/secrets/cpk-installation/provider-client"
    volume = engine.volumes.create(name=f"cpk-client-file-{uuid4().hex}", labels=labels)
    resources.append((engine.volumes, volume.name))
    sdk.materialize_secret_file(volume.name, SecretValue(value),
                                SecretFileMode.OWNER_READ_ONLY, owner_uid=uid)
    evidence = sdk.inspect_secret_file(volume.name)
    assert evidence is not None
    assert evidence.uid == uid and evidence.mode == 0o400 and evidence.regular_file
    assert evidence.content_digest == digest, "CPK client material mismatch"
    # Installer-private policy uses the same protected staging owner, not a
    # public configuration artifact. This is component evidence, not root apply.
    identity = {"issuer": "urn:fixture", "subject_id": "private-policy-" + uuid4().hex, "kind": "operator"}
    policy = json.dumps({"schema": "cpk-server.workspace-authority.v1", "installation_id": "numeric-fixture",
        "administrators": [identity], "known_identities": [identity], "capabilities": []}).encode()
    policy_digest = hashlib.sha256(policy).hexdigest()
    policy_target = "/etc/cpk/cpk-server/workspace-authority.json"
    policy_volume = engine.volumes.create(name=f"cpk-policy-file-{uuid4().hex}", labels=labels)
    resources.append((engine.volumes, policy_volume.name))
    sdk.materialize_secret_file(policy_volume.name, SecretValue(policy.decode()),
                                SecretFileMode.OWNER_READ_ONLY, owner_uid=uid)
    policy_evidence = sdk.inspect_secret_file(policy_volume.name)
    assert policy_evidence is not None and policy_evidence.regular_file
    assert policy_evidence.uid == uid and policy_evidence.mode == 0o400
    assert policy_evidence.content_digest == policy_digest
    probe = f'''
import hashlib, os, pathlib, pwd, stat
account = pwd.getpwnam("cpk")
assert os.getuid() == account.pw_uid == 10001
assert os.getgid() == account.pw_gid
assert os.environ["HOME"] == account.pw_dir
assert os.access(account.pw_dir, os.R_OK | os.X_OK)
file = pathlib.Path({target!r})
info = file.stat()
assert stat.S_ISREG(info.st_mode) and info.st_uid == 10001
assert stat.S_IMODE(info.st_mode) == 0o400
assert hashlib.sha256(file.read_bytes()).hexdigest() == {digest!r}
try:
    file.write_bytes(b"forbidden")
except OSError:
    pass
else:
    raise AssertionError("CPK bootstrap file writable")
from control_plane_kit_servers_cpk_server.workspace_authority_configuration import read_workspace_authority_configuration
policy_file = pathlib.Path({policy_target!r})
info = policy_file.stat()
assert stat.S_ISREG(info.st_mode) and info.st_uid == 10001
assert stat.S_IMODE(info.st_mode) == 0o400
assert hashlib.sha256(policy_file.read_bytes()).hexdigest() == {policy_digest!r}
decoded = read_workspace_authority_configuration(str(policy_file))
assert decoded.administration_policy.installation_id == "numeric-fixture"
assert len(decoded.administration_policy.administrators) == 1
try:
    policy_file.write_bytes(b"forbidden")
except OSError:
    pass
else:
    raise AssertionError("CPK policy file writable")
'''
    name = f"cpk-client-recipient-{uuid4().hex}"
    mount = DockerSdkSecretMount(target, volume.name)
    policy_mount = DockerSdkSecretMount(policy_target, policy_volume.name)
    sdk.create_container(name=name, image=image_id, environment={}, labels=labels,
                         volumes={}, secret_mounts=(mount, policy_mount), network=network_id,
                         aliases=(name,), command=("python", "-B", "-c", probe))
    recipient = engine.containers.get(name)
    resources.append((engine.containers, recipient.id))
    observed = sdk.inspect_container(name)
    assert observed is not None and observed.image_id == image_id
    assert observed.configured_user == "10001"
    assert set(observed.readonly_secret_mounts) == {mount, policy_mount}
    sdk.start_container(name)
    result = recipient.wait(timeout=30)
    output = recipient.logs(tail=30)
    assert value.encode() not in output, "CPK recipient material leaked"
    assert policy not in output and identity["subject_id"].encode() not in output, "CPK private policy leaked"
    assert result.get("StatusCode") == 0, "CPK UID/account/HOME/protected-file law failed"
    # Restart the same exact recipient with its retained policy mount.
    sdk.start_container(name)
    result = recipient.wait(timeout=30)
    assert result.get("StatusCode") == 0, "CPK retained policy restart failed"
    observed = sdk.inspect_container(name)
    assert observed is not None and set(observed.readonly_secret_mounts) == {mount, policy_mount}
    assert sdk.inspect_secret_file(policy_volume.name).content_digest == policy_digest
    output = recipient.logs(tail=30)
    assert value.encode() not in output and identity["subject_id"].encode() not in output
    print("CPK numeric private policy staging, decoder and retained-mount restart PASS; root apply unverified")


# G extends this existing process-delivery owner; the numeric witness above stays
# independent. No workspace or runtime permissions are created by this fixture.
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import tempfile
import time


@dataclass(repr=False)
class PublicEnrollmentFixture:
    base_url: str
    workspace_ids: tuple[str, str]
    profiles: dict
    administrator_profiles: dict
    provider_administrator_profiles: dict
    identities: dict
    administrator_identity: dict
    provider_administrator_identity: dict
    runtime_id: str
    authority_ref: str
    capability_id: str
    logical_provider_id: str
    provider_id: str
    provider_subject: str
    provider_endpoint_reference: str
    provider_credential_reference: str
    engine_id: str
    image_ids: dict
    docs: dict
    state_dir: Path
    _engine: object = field(repr=False)
    _services: dict = field(repr=False)
    _mounts: dict = field(repr=False)
    _controller_id: str = field(repr=False)
    _controller_started_at: str = field(repr=False)
    _restarted: bool = False

    def process_identity(self):
        """Observe each real service's PID1, never the namespace owner's PID."""
        from scripts.cpk_server_source_live_report import SourceLiveInvariantError
        if self._engine.info().get("ID") != self.engine_id:
            raise SourceLiveInvariantError("enrollment-daemon-changed")
        holder = self._engine.containers.get(self._controller_id)
        holder.reload()
        if (holder.attrs["Image"] != self.image_ids["controller"]
                or holder.attrs["State"]["Status"] != "running"
                or holder.attrs["State"]["StartedAt"] != self._controller_started_at
                or holder.attrs["HostConfig"]["PortBindings"]):
            raise SourceLiveInvariantError("enrollment-namespace-holder-changed")
        result = {}
        probe = ('import json,pathlib; s=pathlib.Path("/proc/1/stat").read_text(); '
                 'u=next(x for x in pathlib.Path("/proc/1/status").read_text().splitlines() '
                 'if x.startswith("Uid:")); '
                 'print(json.dumps({"start_ticks":s.rsplit(")",1)[1].split()[19],'
                 '"effective_uid":int(u.split()[2])}))')
        for role, container in self._services.items():
            container.reload()
            attrs = container.attrs
            if (attrs["State"]["Status"] != "running"
                    or attrs["Image"] != self.image_ids[role]
                    or attrs["Mounts"] != self._mounts[role]):
                raise SourceLiveInvariantError("enrollment-service-identity-changed")
            observed = container.exec_run(["python", "-B", "-c", probe])
            if observed.exit_code != 0 or len(observed.output) > 512:
                raise SourceLiveInvariantError("enrollment-process-observation-failed")
            value = json.loads(observed.output)
            expected_uid = 10001 if role == "cpk" else 10006
            if (set(value) != {"start_ticks", "effective_uid"}
                    or value["effective_uid"] != expected_uid
                    or not re.fullmatch(r"[0-9]{1,24}", value["start_ticks"])):
                raise SourceLiveInvariantError("enrollment-process-observation-invalid")
            result[role] = {"container_id": container.id, "image_id": attrs["Image"],
                "started_at": attrs["State"]["StartedAt"], "restart_count": attrs["RestartCount"],
                **value}
        return result

    def restart_after_enrollment(self):
        """Explicit one-time durability phase; never called by readiness/enter."""
        from scripts.cpk_server_source_live_report import SourceLiveInvariantError
        if self._restarted:
            raise SourceLiveInvariantError("enrollment-restart-already-attempted")
        before = self.process_identity()
        self._restarted = True
        for role in ("secrets", "cpk"):
            self._services[role].restart(timeout=10)
            _enrollment_ready(self._services[role],
                "http://g-secrets:8081/health/ready" if role == "secrets"
                else self.base_url + "/health/live")
        after = self.process_identity()
        if any(after[role]["started_at"] == before[role]["started_at"] for role in after):
            raise SourceLiveInvariantError("enrollment-restart-not-observed")
        return after


def _enrollment_ready(container, url):
    import httpx
    from scripts.cpk_server_source_live_report import SourceLiveInvariantError
    for unused in range(40):
        container.reload()
        if container.status != "running":
            raise SourceLiveInvariantError("enrollment-service-exited")
        try:
            with httpx.Client(timeout=1, trust_env=False, follow_redirects=False) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return
        except httpx.TransportError:
            pass
        time.sleep(0.25)
    raise SourceLiveInvariantError("enrollment-readiness-unavailable")


def _enrollment_inputs(environment):
    """Closed nonsecret launch coordinates; validate before resource creation."""
    from scripts.cpk_server_source_live_report import SourceLiveInvariantError
    names = ("RUN", "ENGINE", "NETWORK", "CONTROLLER_IMAGE", "CPK_IMAGE", "SECRETS_IMAGE", "POSTGRES_IMAGE")
    values = {name.lower(): environment.get("CPK_G_" + name, "") for name in names}
    if (not re.fullmatch(r"cpk-enrollment-[A-Za-z0-9._-]{1,80}", values["run"])
            or not re.fullmatch(r"[A-Za-z0-9:._-]{1,128}", values["engine"])
            or not re.fullmatch(r"[0-9a-f]{64}", values["network"])
            or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", values[name.lower()])
                   for name in names if name.endswith("IMAGE"))):
        raise SourceLiveInvariantError("enrollment-launch-input-invalid")
    return values


@contextmanager
def public_enrollment_fixture():
    """Fresh real process cohort only; public scenario owns all enrollment."""
    import base64
    import docker
    import psycopg
    from datetime import datetime, timezone
    from psycopg.conninfo import make_conninfo
    from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
    from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkConfigurationMount
    from control_plane_kit_operations.postgres import PostgresUnitOfWork, install_schema
    from control_plane_kit_operations.workflows import IdempotencyKey
    from control_plane_kit_operations.workspace_permissions import (
        WorkspaceAdministrationContext, WorkspacePermissionCommandService, WorkspacePermissionReadService,
    )
    from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
    from control_plane_kit_servers_cpk_server.control_configuration import cpk_control_configuration_artifact
    from control_plane_kit_servers_cpk_server.managed_health_configuration import managed_health_configuration_artifact
    from control_plane_kit_servers_cpk_server.workspace_authority_configuration import decode_workspace_authority_configuration
    from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
    from products.cpk_server.tests.cpk_http_host_fixtures import fixture as control_fixture
    from products.secrets_server.tests.secrets_control_fixtures import SourceControlAuthority
    from scripts.cpk_server_source_live_report import SourceLiveInvariantError, SourceLiveRunFailed

    inputs = _enrollment_inputs(os.environ)
    capability = "g-local-docker"
    try:
        docs = {}
        for role in ("gateway", "native"):
            with Path("/g-inputs/" + role + ".cpk.json").open("rb") as document:
                raw = document.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError
            docs[role] = raw.decode("utf-8")
        managed = managed_health_configuration_artifact(json.dumps({"schema": "cpk-server.managed-health.v2",
            "docker": {"socket_path": "/var/run/docker.sock", "request_timeout": 5.0}, "capability_ids": [capability],
            "gateway_documents": [docs["gateway"]], "native_product_document": docs["native"]}).encode())
    except Exception:
        raise SourceLiveInvariantError("enrollment-product-documents-invalid") from None
    docker_config = Path(os.environ["DOCKER_CONFIG"])
    docker_config.mkdir(mode=0o700)
    (docker_config / "config.json").write_text("{}", encoding="ascii")
    (docker_config / "config.json").chmod(0o600)
    engine = docker.from_env()
    resources = []
    helper_ids = []
    witness = Path("/witness")
    labels = {"org.openj92.cpk.test-run": inputs["run"]}
    primary = None
    cleanup_failed = False
    acquisition_uncertain = False
    sdk = DockerSdkClient(client=engine, configuration_helper_image=inputs["controller_image"])
    directory = tempfile.TemporaryDirectory(prefix="cpk-enrollment-private-")
    root = Path(directory.name)
    root.chmod(0o700)

    def persist():
        (witness / "ownership.json").write_text(json.dumps({"run": inputs["run"],
            "engine": inputs["engine"], "resources": resources, "helpers": helper_ids,
            "acquisition_uncertain": acquisition_uncertain}), encoding="utf-8")
        (witness / "ownership.json").chmod(0o600)

    original_helper = sdk._create_configuration_helper
    def tracked_helper(*args, **kwargs):
        helper = original_helper(*args, **kwargs)
        helper_ids.append(helper.id)
        persist()
        return helper
    sdk._create_configuration_helper = tracked_helper

    def record(kind, resource):
        identity = resource.id if kind == "container" else resource.name
        resources.append((kind, identity))
        persist()
        return resource

    def volume():
        nonlocal acquisition_uncertain
        acquisition_uncertain = True
        persist()
        owned = record("volume", engine.volumes.create(name="cpk-g-" + uuid4().hex, labels=labels))
        acquisition_uncertain = False
        persist()
        return owned

    def private_mount(target, value, uid):
        nonlocal acquisition_uncertain
        owned = volume()
        acquisition_uncertain = True
        persist()
        sdk.materialize_secret_file(owned.name, SecretValue(value), SecretFileMode.OWNER_READ_ONLY, owner_uid=uid)
        observed = sdk.inspect_secret_file(owned.name)
        if (observed is None or not observed.regular_file or observed.uid != uid or observed.mode != 0o400
                or observed.content_digest != hashlib.sha256(value.encode()).hexdigest()):
            raise SourceLiveInvariantError("enrollment-private-delivery-invalid")
        acquisition_uncertain = False
        persist()
        return dict(DockerSdkSecretMount(target, owned.name).docker_mount())

    def public_mount(artifact):
        nonlocal acquisition_uncertain
        owned = volume()
        acquisition_uncertain = True
        persist()
        sdk.materialize_configuration_artifact(owned.name, artifact)
        if sdk.configuration_artifact_digest(owned.name) != artifact.content_digest:
            raise SourceLiveInvariantError("enrollment-public-delivery-invalid")
        acquisition_uncertain = False
        persist()
        return dict(DockerSdkConfigurationMount(artifact, owned.name).docker_mount())

    def create(image, **arguments):
        nonlocal acquisition_uncertain
        acquisition_uncertain = True
        persist()
        arguments.setdefault("cap_drop", ["ALL"])
        owned = record("container", engine.containers.create(image, labels=labels,
            security_opt=["no-new-privileges"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
            **arguments))
        acquisition_uncertain = False
        persist()
        return owned

    try:
        if engine.info().get("ID") != inputs["engine"]:
            raise SourceLiveInvariantError("enrollment-daemon-mismatch")
        controller = engine.containers.get(os.environ["HOSTNAME"])
        controller.reload()
        network = engine.networks.get(inputs["network"])
        if (controller.attrs["Image"] != inputs["controller_image"]
                or controller.labels.get("org.openj92.cpk.test-run") != inputs["run"]
                or controller.attrs["State"]["Status"] != "running"
                or controller.attrs["HostConfig"]["PortBindings"]
                or network.attrs["Labels"].get("org.openj92.cpk.test-run") != inputs["run"]
                or inputs["network"] not in {item["NetworkID"] for item in
                    controller.attrs["NetworkSettings"]["Networks"].values()}):
            raise SourceLiveInvariantError("enrollment-controller-mismatch")
        for role, uid in (("cpk", 10001), ("secrets", 10006)):
            observed = sdk.inspect_image(inputs[role + "_image"])
            if observed is None or observed.secret_file_owner_uid() != uid:
                raise SourceLiveInvariantError("enrollment-image-user-invalid")
        suffix = uuid4().hex
        workspace_ids = ("workspace-g-a-" + suffix, "workspace-g-b-" + suffix)
        installation = "installation-g-" + suffix
        issuer = "urn:control-plane-kit:static-development"
        roles = ("operator", "approver", "worker")
        actor_ids = {workspace: {role: PrincipalIdentity(issuer, workspace + "-" + role,
            PrincipalKind.WORKER if role == "worker" else PrincipalKind.OPERATOR)
            for role in roles} for workspace in workspace_ids}
        administrator = PrincipalIdentity(issuer, "g-installer-" + suffix, PrincipalKind.OPERATOR)
        provider_administrator = PrincipalIdentity(issuer, "g-provider-admin-" + suffix, PrincipalKind.OPERATOR)
        known = [administrator, provider_administrator, *(identity for row in actor_ids.values() for identity in row.values())]
        actor_tokens = {identity.subject_id: secrets.token_urlsafe(48) for identity in known}
        credential_files = {}
        for identity in known:
            file = root / identity.subject_id
            file.write_text(actor_tokens[identity.subject_id], encoding="ascii")
            file.chmod(0o600)
            credential_files[identity.subject_id] = file
        policy_bytes = json.dumps({"schema": "cpk-server.workspace-authority.v1", "installation_id": installation,
            "administrators": [administrator.descriptor()], "known_identities": [identity.descriptor() for identity in known],
            "capabilities": [capability]}).encode()
        policy = decode_workspace_authority_configuration(policy_bytes).administration_policy
        database_password = secrets.token_urlsafe(40)
        database_data = volume()
        postgres = create(inputs["postgres_image"], name="cpk-g-postgres-" + suffix,
            cap_drop=[],  # Preserve the stock PostgreSQL entrypoint's init/chown capabilities.
            network=inputs["network"], networking_config={inputs["network"]:
                engine.api.create_endpoint_config(aliases=["g-postgres"])},
            environment={"POSTGRES_USER": "cpk", "POSTGRES_PASSWORD": database_password, "POSTGRES_DB": "cpk"},
            mounts=[docker.types.Mount("/var/lib/postgresql/data", database_data.name, type="volume")])
        postgres.start()
        database_url = make_conninfo(host="g-postgres", port=5432, dbname="cpk", user="cpk", password=database_password,
                                     connect_timeout=1)
        for unused in range(40):
            postgres.reload()
            if postgres.status != "running":
                raise SourceLiveInvariantError("enrollment-postgres-exited")
            try:
                connection = psycopg.connect(database_url)
                break
            except psycopg.OperationalError:
                time.sleep(0.25)
        else:
            raise SourceLiveInvariantError("enrollment-postgres-unavailable")
        # Readiness retries only connection acquisition. Schema effects execute
        # once; a failed/uncertain transaction is never redispatched here.
        with connection:
            install_schema(connection)
        def unit_of_work():
            return PostgresUnitOfWork(lambda: psycopg.connect(database_url))
        context = WorkspaceAdministrationContext(administrator, installation)
        initialized = WorkspacePermissionCommandService(unit_of_work, administration_policy=policy,
            clock=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            id_factory=lambda: uuid4().hex).initialize(context,
                idempotency_key=IdempotencyKey("initialize-g-" + suffix))
        if initialized.replayed:
            raise SourceLiveInvariantError("enrollment-initialization-replayed")
        WorkspacePermissionReadService(unit_of_work, administration_policy=policy).installation(context)

        provider_id = "g-provider-" + suffix
        provider_subject = "g-ordinary-client"
        provider_token, policy_token = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
        seed = json.dumps([
            {"subject": provider_subject, "token": provider_token, "grants": []},
            {"subject": "g-policy-admin", "token": policy_token, "grants": [], "capabilities": ["secrets.policy-admin"]},
        ])
        secrets_mounts = [private_mount("/run/secrets/cpk-secrets/master.key",
            base64.urlsafe_b64encode(os.urandom(32)).decode(), 10006),
            private_mount("/run/secrets/cpk-secrets/credentials.json", seed, 10006),
            public_mount(secrets_control_configuration_artifact(SourceControlAuthority(suffix).configuration()))]
        secrets_data = volume()
        secrets_mounts.append(docker.types.Mount("/var/lib/cpk-secrets", secrets_data.name, type="volume"))
        provider = create(inputs["secrets_image"], name="cpk-g-secrets-" + suffix,
            network=inputs["network"], networking_config={inputs["network"]:
                engine.api.create_endpoint_config(aliases=["g-secrets"])}, mounts=secrets_mounts,
            environment={"CPK_SECRETS_PROVIDER_ID": provider_id})
        provider.start()
        _enrollment_ready(provider, "http://g-secrets:8081/health/ready")
        provider_reference = "secret://bootstrap/g-provider-client"
        provider_path = "/run/secrets/cpk-installation/provider-client"
        policy_path = "/run/secrets/cpk-installation/provider-policy-admin"
        binding_id = "g-provider-binding-" + suffix
        logical_provider = "g-provider"
        f2 = json.dumps({"schema": "cpk-server.provider-policy-authority.v1", "installation_id": installation,
            "admissions": [{"identity": provider_administrator.descriptor(), "binding_id": binding_id}],
            "bindings": [{"binding_id": binding_id, "logical_provider_id": logical_provider, "provider_id": provider_id,
                "endpoint_reference": "g-provider-policy", "base_url": "http://g-secrets:8081",
                "credential_reference": "secret://bootstrap/g-provider-policy-admin", "credential_file": policy_path}]})
        cpk_mounts = [public_mount(cpk_control_configuration_artifact(control_fixture(suffix).config)),
            public_mount(managed), private_mount("/etc/cpk/cpk-server/workspace-authority.json", policy_bytes.decode(), 10001),
            private_mount("/etc/cpk/cpk-server/provider-policy-authority.json", f2, 10001),
            private_mount(provider_path, provider_token, 10001), private_mount(policy_path, policy_token, 10001),
            docker.types.Mount("/var/run/docker.sock", "/var/run/docker.sock", type="bind")]
        environment = {"CPK_SERVER_MODE": "execution-capable", "CPK_CONTROL_AUTH_CONFIGURED": "true", "CPK_PORT": "8080",
            "CPK_RUNTIME_INTERPRETERS": "docker", "CPK_INGRESS_INTERPRETERS": "none",
            "CPK_CONTROL_AUTH_VERIFIER": "static-development",
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps([{"credential": actor_tokens[identity.subject_id],
                "subject_id": identity.subject_id, "kind": identity.kind.value, "workspace_grants": {}} for identity in known]),
            "CPK_WORKSPACE_AUTHORITY": "dynamic-v1",
            "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": "/etc/cpk/cpk-server/workspace-authority.json",
            "CPK_PROVIDER_POLICY_AUTHORITY": "secrets-v1",
            "CPK_PROVIDER_POLICY_AUTHORITY_CONFIGURATION_FILE": "/etc/cpk/cpk-server/provider-policy-authority.json",
            "CPK_MANAGED_HEALTH": "docker-unix-v1", "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": managed.target_path,
            "CPK_PRODUCT_MATERIAL_RESOLVER": "provider", "CPK_GATEWAY_PROBE_SIGNER": "ed25519",
            "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({logical_provider: "http://g-secrets:8081"}),
            "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": json.dumps({provider_reference: provider_path}),
            **{name: database_url for name in ("CPK_WORKPLACE_DATABASE_URL", "CPK_ACTIVITY_HISTORY_DATABASE_URL",
                "CPK_OBSERVER_STATE_DATABASE_URL", "CPK_GRAPH_TOPOLOGY_DATABASE_URL")}}
        cpk = create(inputs["cpk_image"], name="cpk-g-server-" + suffix, environment=environment,
            network_mode="container:" + controller.id, mounts=cpk_mounts,
            group_add=[str(os.stat("/var/run/docker.sock").st_gid)])
        cpk.start()
        _enrollment_ready(cpk, "http://127.0.0.1:8080/health/live")
        services = {"cpk": cpk, "secrets": provider}
        mounts = {}
        for role, container in services.items():
            container.reload()
            host = container.attrs["HostConfig"]
            if (host["PortBindings"] or host["Privileged"] or host.get("PidMode")
                    or container.attrs["Config"]["User"] != ("10001" if role == "cpk" else "10006")):
                raise SourceLiveInvariantError("enrollment-unexpected-publication")
            expected_image = engine.images.get(inputs[role + "_image"])
            for key in ("Entrypoint", "Cmd"):
                if container.attrs["Config"][key] != expected_image.attrs["Config"][key]:
                    raise SourceLiveInvariantError("enrollment-entrypoint-changed")
            observed_mounts = {item["Destination"]: item for item in container.attrs["Mounts"]}
            for item in cpk_mounts if role == "cpk" else secrets_mounts:
                observed_mount = observed_mounts.get(item["Target"])
                if (observed_mount is None
                        or observed_mount.get("Name", observed_mount.get("Source")) != item["Source"]
                        or observed_mount["RW"] != (not item.get("ReadOnly", False))):
                    raise SourceLiveInvariantError("enrollment-mount-delivery-invalid")
            mounts[role] = container.attrs["Mounts"]
        if cpk.attrs["HostConfig"]["NetworkMode"] != "container:" + controller.id:
            raise SourceLiveInvariantError("enrollment-network-namespace-mismatch")
        def profile(workspace, credentials, label):
            state = root / (workspace + "-" + label)
            state.mkdir(mode=0o700)
            return ClientProfile("http://127.0.0.1:8080", workspace, credentials, state)
        fixture = PublicEnrollmentFixture("http://127.0.0.1:8080", workspace_ids,
            {workspace: profile(workspace, {role: credential_files[identity.subject_id] for role, identity in row.items()}, "ordinary")
             for workspace, row in actor_ids.items()},
            {workspace: profile(workspace, {role: credential_files[administrator.subject_id] for role in roles}, "admin")
             for workspace in workspace_ids},
            {workspace: profile(workspace, {role: credential_files[provider_administrator.subject_id] for role in roles}, "provider-admin")
             for workspace in workspace_ids},
            {workspace: {role: identity.descriptor() for role, identity in row.items()} for workspace, row in actor_ids.items()},
            administrator.descriptor(), provider_administrator.descriptor(), "g-runtime", "g-local-authority", capability,
            logical_provider, provider_id, provider_subject, logical_provider, provider_reference,
            inputs["engine"], {role: inputs[role + "_image"] for role in ("cpk", "secrets", "postgres", "controller")},
            docs, root, engine, services, mounts, controller.id, controller.attrs["State"]["StartedAt"])
        fixture.process_identity()
        yield fixture
    except BaseException as error:
        primary = error
        if isinstance(error, (SourceLiveInvariantError, SourceLiveRunFailed)):
            raise
        raise SourceLiveInvariantError("enrollment-fixture-failed") from None
    finally:
        # Only successful creation identities are cleanup candidates. A failed
        # create can leave unknown effects; never discover-and-delete by name.
        for kind, identity in reversed(resources):
            collection = engine.containers if kind == "container" else engine.volumes
            try:
                resource = collection.get(identity)
                resource.reload()
                observed_labels = resource.labels if kind == "container" else resource.attrs["Labels"]
                if observed_labels.get("org.openj92.cpk.test-run") != inputs["run"]:
                    raise SourceLiveInvariantError("enrollment-cleanup-owner-mismatch")
                resource.remove(force=True) if kind == "container" else resource.remove()
                try:
                    collection.get(identity)
                except docker.errors.NotFound:
                    pass
                else:
                    raise SourceLiveInvariantError("enrollment-cleanup-residue")
            except docker.errors.NotFound:
                pass
            except Exception:
                cleanup_failed = True
        for identity in helper_ids:
            try:
                engine.containers.get(identity)
            except docker.errors.NotFound:
                pass
            except Exception:
                cleanup_failed = True
            else:
                cleanup_failed = True
        try:
            directory.cleanup()
        except Exception:
            cleanup_failed = True
        if acquisition_uncertain:
            cleanup_failed = True
        if not cleanup_failed:
            (witness / "fixture-resources-absent").write_text("verified\n", encoding="ascii")
        try:
            engine.close()
        except Exception:
            cleanup_failed = True
        if cleanup_failed:
            raise SourceLiveRunFailed(getattr(primary, "code", "enrollment-failed") if primary else "enrollment-cleanup-failed",
                                      "enrollment-cleanup-failed") from None
