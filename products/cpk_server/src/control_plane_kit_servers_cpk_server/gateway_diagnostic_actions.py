"""Finite #221 setup composition. Live calls require the reviewed operator packet.

This is a diagnostic entrypoint, not a reusable deployment or recovery engine.
Independent provider/Operations commits are never described as one transaction.
"""
import copy
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
import os
from pathlib import Path
import secrets
import stat
import time
from urllib.parse import urlsplit, urlunsplit
import uuid
from hashlib import sha256

import httpx
import rfc8785
import control_plane_kit_core as core
from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import SecretReference, SecretProviderId, SecretProviderEndpointReference, health_signing_intent_for
from control_plane_kit_interpreters.secret_provider import canonical_provider_secret_id
from control_plane_kit_operations.cpk_server import RouteAuthorizationPolicy
from control_plane_kit_operations.workspaces import CreateWorkspace, WorkspaceCommandService
from control_plane_kit_operations.workflows import IdempotencyKey
from control_plane_kit_operations.secret_providers import (
    RegisterSecretProviderCommand, RegisterSecretReferenceCommand,
    SecretProviderKind, SecretProviderRegistrationService,
)
from control_plane_kit_operations.delegation_signing_keys import (
    RegisterDelegationSigningKeyCommand, ActivateDelegationSigningKeyCommand,
    DelegationSigningKeyRegistrationService,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .authentication import (
    authenticate_bearer_credential, StaticDevelopmentMultiCredentialVerifier,
    StaticDevelopmentPrincipalCredential,
)
from ._gateway_diagnostic_bootstrap import read_file
from ._gateway_diagnostic_input import bounded_json, closed

WORKSPACE = "cpk221-self-health-r1"
HOSTNAME = "cpk-bootstrap-grandparent.openj92.dev"
PROVIDER_URL = "http://cpk221-self-health-r1-secrets:8081"
SETUP_SCOPES = (PolicyScope.HUB_INSTANCE_CREATE, PolicyScope.SECRET_PROVIDER_REGISTER,
                PolicyScope.DELEGATION_KEY_REGISTER, PolicyScope.DELEGATION_KEY_ACTIVATE)


class SetupHold(ValueError):
    def __init__(self):
        super().__init__("diagnostic setup held; preserve private receipts")


def bounded_failure(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            failure = SetupHold()
        raise failure from None
    return call


def private_root(root):
    root = Path(root)
    info = root.lstat()
    if not root.is_absolute() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise SetupHold
    return root


def write_private(path, value, *, replace=False):
    """Exclusive first claim; durable same-directory atomic receipt replacement."""
    path = Path(path)
    private_root(path.parent)
    raw = value if isinstance(value, bytes) else rfc8785.dumps(value)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex) if replace else path
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
        if replace:
            os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        os.close(descriptor)


def read_json(path):
    return bounded_json(read_file(path, 65536, protected=True))


def generation_actions():
    result = []
    for family, purpose in (("transit", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT),
                            ("workload", core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)):
        reference = f"secret://{WORKSPACE}/keys/{family}-health"
        result.append(dict(workspace_id=WORKSPACE, reference=reference,
            intent=health_signing_intent_for(purpose).value,
            path=f"/v1/workspaces/{WORKSPACE}/delegation-keys/{canonical_provider_secret_id(SecretReference(reference))}/generate",
            body=dict(purpose=purpose.value, issuer="cpk221-" + family,
                caller_subject="cpk221-setup-operator", correlation_id=f"{WORKSPACE}:generate:{family}",
                secret_reference=reference)))
    return tuple(result)


@bounded_failure
def validate_generated_key(action, payload):
    if action not in generation_actions(): raise SetupHold
    closed(payload, {"outcome", "secret_reference", "metadata", "purpose", "issuer", "correlation_id",
        "replayed", "key_id", "algorithm", "public_key_pem", "fingerprint_sha256"})
    body = action["body"]
    if (payload["outcome"] != "generated" or payload["replayed"] is not False
            or payload["secret_reference"] != action["reference"]
            or any(payload[name] != body[name] for name in ("purpose", "issuer", "correlation_id"))
            or payload["algorithm"] != "ed25519"):
        raise SetupHold
    meta = closed(payload["metadata"], {"workspace_id", "secret_id", "version_id", "version_number", "status",
        "algorithm", "key_fingerprint", "key_version", "created_at", "revoked_at", "labels"})
    if (meta["workspace_id"] != WORKSPACE or meta["secret_id"] != canonical_provider_secret_id(SecretReference(action["reference"]))
            or meta["status"] != "active" or meta["revoked_at"] is not None
            or type(meta["version_number"]) is not int or meta["version_number"] != 1
            or meta["algorithm"] != "AES-256-GCM"):
        raise SetupHold
    labels = closed(meta["labels"], {"intent", "purpose", "issuer", "key_id"})
    if labels != dict(intent=action["intent"], purpose=body["purpose"], issuer=body["issuer"], key_id=payload["key_id"]):
        raise SetupHold
    for name in ("version_id", "key_fingerprint", "key_version", "created_at"):
        if type(meta[name]) is not str or not 1 <= len(meta[name]) <= 256: raise SetupHold
    key = core.DelegationPublicKey(payload["key_id"], core.DelegationKeyAlgorithm.ED25519, payload["public_key_pem"])
    if not isinstance(serialization.load_pem_public_key(key.public_key_pem.encode()), Ed25519PublicKey): raise SetupHold
    if key.fingerprint_sha256 != payload["fingerprint_sha256"]: raise SetupHold
    return key


@bounded_failure
def generate_health_keys(root, *, transport=None):
    root = private_root(root)
    receipt = {"status": "pending", "completed": [], "pending": None}
    write_private(root / "generation-receipt.json", receipt)
    token = read_file(root / "provider-generate.token", 4096, protected=True).decode("ascii")
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False, transport=transport) as client:
        for family, action in zip(("transit", "workload"), generation_actions()):
            receipt["pending"] = family
            write_private(root / "generation-receipt.json", receipt, replace=True)
            deadline = time.monotonic() + 20
            with client.stream("POST", PROVIDER_URL + action["path"], json=action["body"],
                    headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity": raise SetupHold
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if len(raw) + len(chunk) > 65536 or time.monotonic() > deadline: raise SetupHold
                    raw.extend(chunk)
                if time.monotonic() > deadline: raise SetupHold
                payload = bounded_json(bytes(raw))
                validate_generated_key(action, payload)
                receipt["completed"].append(payload)
                receipt["pending"] = None
                write_private(root / "generation-receipt.json", receipt, replace=True)
    receipt["status"] = "complete"
    write_private(root / "generation-receipt.json", receipt, replace=True)
    return receipt["completed"]


def generated_keys(root):
    value = read_json(root / "generation-receipt.json")
    if value["status"] != "complete" or value["pending"] is not None or len(value["completed"]) != 2: raise SetupHold
    return tuple(validate_generated_key(action, payload) for action, payload in zip(generation_actions(), value["completed"]))


def setup_context(root):
    bindings = []
    for family, scopes in (("setup", SETUP_SCOPES), ("runner", (PolicyScope.SECRET_PROVIDER_USE,))):
        principal = AuthenticatedPrincipal(PrincipalIdentity("urn:cpk221:diagnostic", "cpk221-" + family + "-operator", PrincipalKind.OPERATOR),
            (WorkspaceGrant(WORKSPACE, scopes),))
        bindings.append(StaticDevelopmentPrincipalCredential(read_file(root / (family + "-binding.token"), 4096, protected=True), principal))
    presented = read_file(root / "setup-operator.token", 4096, protected=True).decode("ascii")
    principal = authenticate_bearer_credential({"Authorization": "Bearer " + presented}, StaticDevelopmentMultiCredentialVerifier(tuple(bindings)))
    context = principal.command_context(WORKSPACE)
    RouteAuthorizationPolicy(required_scopes=SETUP_SCOPES).authorize(context)
    return context


@bounded_failure
def initialize_operations(root, *, schema_initializer=None, uow_factory=None):
    root = private_root(root)
    if (root / "operations-receipt.json").exists(): raise SetupHold
    context = setup_context(root)
    publics = generated_keys(root)
    if schema_initializer is None or uow_factory is None:
        schema_initializer, uow_factory = postgres_setup(root)
    receipt = {"status": "pending", "pending": "schema", "keys": []}
    write_private(root / "operations-receipt.json", receipt)
    def pending(name):
        receipt["pending"] = name
        write_private(root / "operations-receipt.json", receipt, replace=True)
    stamp = lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    schema_initializer()
    pending("workspace")
    workspace = WorkspaceCommandService(uow_factory, clock=stamp, id_factory=lambda: uuid.uuid4().hex).create(
        CreateWorkspace(WORKSPACE, "Gateway self-health diagnostic", context.actor_id, IdempotencyKey(WORKSPACE + ":workspace")))
    if workspace.replayed: raise SetupHold
    receipt["graph_id"] = workspace.current_graph.graph_id
    pending("provider")
    providers = SecretProviderRegistrationService(uow_factory)
    admitted = dict(admitted_by=context.actor_id, admitted_at=stamp(), actor_scopes=context.granted_scopes)
    actions = generation_actions()
    provider = providers.register_provider(RegisterSecretProviderCommand(
        workspace_id=WORKSPACE, provider_id=SecretProviderId(WORKSPACE), provider_kind=SecretProviderKind.CONTROL_PLANE_KIT_SECRETS,
        display_name="Gateway diagnostic custody", endpoint_reference=SecretProviderEndpointReference("cpk221-secrets"),
        credential_reference=SecretReference(f"secret://bootstrap/{WORKSPACE}/resolve"),
        allowed_reference_prefixes=tuple(SecretReference(action["reference"]) for action in actions),
        allowed_intents=tuple(health_signing_intent_for(core.DelegationKeyPurpose(action["body"]["purpose"])) for action in actions), **admitted))
    receipt["provider_registration_id"] = provider.registration_id
    keys = DelegationSigningKeyRegistrationService(uow_factory)
    for family, action, public in zip(("transit", "workload"), actions, publics):
        pending("register-" + family + "-reference")
        purpose = core.DelegationKeyPurpose(action["body"]["purpose"])
        reference = providers.register_reference(RegisterSecretReferenceCommand(WORKSPACE, SecretReference(action["reference"]),
            provider.registration_id, (health_signing_intent_for(purpose),), **admitted))
        entry = {"reference_registration_id": reference.registration_id}
        receipt["keys"].append(entry)
        pending("register-" + family + "-key")
        registered = keys.register(RegisterDelegationSigningKeyCommand(WORKSPACE, purpose, action["body"]["issuer"],
            public, SecretReference(action["reference"]), **admitted))
        entry["registration_id"] = registered.registration_id
        pending("activate-" + family + "-key")
        active = keys.activate(ActivateDelegationSigningKeyCommand(WORKSPACE, purpose, action["body"]["issuer"],
            registered.public_key.key_id, context.actor_id, stamp(), context.granted_scopes))
        if active.registration_id != registered.registration_id or active.public_key != public: raise SetupHold
        entry["activated"] = True
    receipt.update(status="complete", pending=None)
    write_private(root / "operations-receipt.json", receipt, replace=True)
    return receipt


def postgres_setup(root):
    import psycopg
    from control_plane_kit_operations.postgres import PostgresUnitOfWork
    from control_plane_kit_operations.postgres.schema import install_schema
    dsn = read_file(root / "database.dsn", 4096, protected=True).decode()
    connect = lambda: psycopg.connect(dsn, connect_timeout=10, options="-c statement_timeout=10000 -c lock_timeout=5000")
    def initialize():
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone() != ("cpk221_self_health_r1",): raise SetupHold
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                if cursor.fetchone() != (0,): raise SetupHold
            install_schema(connection)
    return initialize, lambda: PostgresUnitOfWork(connect)


def target(node, graph):
    roles = core.NodeControlGraphReferenceRole
    return core.NodeControlTarget(*(core.NodeControlGraphReference(role, value) for role, value in (
        (roles.WORKSPACE, WORKSPACE), (roles.GRAPH_REVISION, graph), (roles.NODE, node), (roles.PROVIDER_SOCKET, "control"))))


def public_record(key):
    return dict(key_id=key.key_id, algorithm=key.algorithm.value, public_key_pem=key.public_key_pem, fingerprint=key.fingerprint_sha256)


def public_from_record(value):
    closed(value, {"key_id", "algorithm", "public_key_pem", "fingerprint"})
    key = core.DelegationPublicKey(value["key_id"], core.DelegationKeyAlgorithm(value["algorithm"]), value["public_key_pem"])
    if key.fingerprint_sha256 != value["fingerprint"]: raise SetupHold
    return key


@bounded_failure
def prepare_private_material(root):
    from control_plane_kit_server_sdk.verifier_keys import WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet
    from control_plane_kit_secrets.control import SecretsControlConfiguration, secrets_control_declaration, encode_secrets_control_configuration
    from control_plane_kit_secrets.crypto import encode_master_key_for_file
    root = Path(root)
    if not root.is_absolute(): raise SetupHold
    root.mkdir(mode=0o700)
    private_root(root)
    tokens = {name: secrets.token_urlsafe(32) for name in ("provider-generate", "provider-resolve", "setup-operator", "runner-operator")}
    for name, token in tokens.items(): write_private(root / (name + ".token"), token.encode())
    for family in ("setup", "runner"):
        write_private(root / (family + "-binding.token"), tokens[family + "-operator"].encode())
    write_private(root / "master.key", encode_master_key_for_file(secrets.token_bytes(32)).encode())
    password = secrets.token_urlsafe(32)
    write_private(root / "postgres-password", password.encode())
    write_private(root / "database.dsn",
        f"postgresql://cpk221:{password}@{WORKSPACE}-postgres:5432/cpk221_self_health_r1".encode())
    credentials = []
    for family, action in (("generate", "secret.generate-delegation-key"), ("resolve", "secret.resolve")):
        credentials.append(dict(subject="cpk221-" + family, token=tokens["provider-" + family],
            grants=[dict(action=action, workspace_id=WORKSPACE, intents=[item["intent"] for item in generation_actions()])]))
    write_private(root / "provider-credentials.json", credentials)
    public = []
    for name in ("gateway-surface", "secrets-surface", "secrets-health"):
        # Private halves are never serialized. Python does not promise memory erasure.
        key = Ed25519PrivateKey.generate().public_key()
        public.append(core.DelegationPublicKey("cpk221-" + name, core.DelegationKeyAlgorithm.ED25519,
            key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()))
    write_private(root / "bootstrap-public.json", [public_record(key) for key in public])
    config = SecretsControlConfiguration(target=target("secrets", "cpk221-bootstrap-config"),
        runtime_id=core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.RUNTIME, WORKSPACE),
        declaration=secrets_control_declaration(), surface_issuer="cpk221-secrets-surface",
        surface_keys=WorkloadNodeControlSurfaceReadVerifierKeySet(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (public[1],)),
        health_issuer="cpk221-secrets-health",
        health_keys=WorkloadNodeHealthReadVerifierKeySet(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (public[2],)))
    write_private(root / "secrets-control.json", encode_secrets_control_configuration(config))
    return {"status": "private-material-prepared"}


@bounded_failure
def build_artifacts(root, *, gateway_image_digest, runtime_id, private_hostname):
    from control_plane_kit_server_sdk.verifier_keys import WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet
    from control_plane_kit_servers_cpk_local_gateway import control_configuration as control
    from control_plane_kit_servers_cpk_local_gateway import health_transit_configuration as transit
    from control_plane_kit_servers_cpk_local_gateway import health_relay_configuration as relay
    from control_plane_kit_core.products import ContainerServerProduct, ProductIdentity, ProductDescriptorCodec, OciImageReference
    root = private_root(root)
    public = generated_keys(root)
    operations = read_json(root / "operations-receipt.json")
    if operations["status"] != "complete" or len(operations["keys"]) != 2: raise SetupHold
    bootstrap = tuple(public_from_record(item) for item in read_json(root / "bootstrap-public.json"))
    if len(bootstrap) != 3: raise SetupHold
    receiver = target("gateway", operations["graph_id"])
    runtime = core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.RUNTIME, runtime_id)
    configured = control.GatewayControlConfiguration(target=receiver, runtime_id=runtime, declaration=control.gateway_control_declaration(),
        surface_issuer="cpk221-gateway-surface",
        surface_keys=WorkloadNodeControlSurfaceReadVerifierKeySet(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, (bootstrap[0],)),
        health_issuer="cpk221-workload", health_keys=WorkloadNodeHealthReadVerifierKeySet(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, (public[1],)))
    trust = transit.GatewayHealthTransitConfiguration(receiver.workspace_id, receiver.node_id, runtime,
        "cpk221-transit", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (public[0],))
    targets = relay.GatewayHealthRelayConfiguration(receiver.workspace_id, receiver.node_id, runtime, ())
    artifacts = {"control": control.gateway_control_configuration_artifact(configured),
        "transit": transit.gateway_health_transit_configuration_artifact(trust),
        "targets": relay.gateway_health_relay_configuration_artifact(targets)}
    contract = relay.gateway_health_source_runtime_contract(artifacts["transit"], artifacts["targets"], artifacts["control"])
    binding = relay.gateway_health_target_binding(target_id="cpk221-gateway-self", target=receiver, runtime_id=runtime,
        runtime_contract=contract, hostname=private_hostname)
    artifacts["targets"] = relay.gateway_health_relay_configuration_artifact(replace(targets, targets=(binding,)))
    contract = relay.gateway_health_source_runtime_contract(artifacts["transit"], artifacts["targets"], artifacts["control"])
    # Explicit local source coordinate; this does not assert a published registry manifest.
    document = ProductDescriptorCodec().encode_document(ContainerServerProduct(ProductIdentity("diagnostic-local", "cpk221-gateway", 1),
        OciImageReference("localhost", "cpk221/source-gateway", gateway_image_digest), contract))
    ProductDescriptorCodec().decode_document(document.content)
    destination = root / "artifacts"
    destination.mkdir(mode=0o700)
    for name, artifact in artifacts.items(): write_private(destination / (name + ".json"), artifact.content.encode())
    write_private(destination / "product.json", document.content)
    return {"status": "artifacts-prepared"}


@bounded_failure
def seal_packet(root, *, controller_image_digest, resource_plan, now):
    from control_plane_kit_servers_cpk_local_gateway.control_configuration import decode_gateway_control_configuration
    from control_plane_kit_core.public_ingress import NamedPublicIngress, IngressAuthorityReference, PublicIngressTarget
    from ._gateway_diagnostic_input import prepare_packet
    root = private_root(root)
    if (root / "packet.json").exists(): raise SetupHold
    artifacts = {name: read_file(root / "artifacts" / (name + ".json"), 1048576, protected=True)
                 for name in ("control", "transit", "targets", "product")}
    configured = decode_gateway_control_configuration(artifacts["control"])
    public = generated_keys(root)
    operations = read_json(root / "operations-receipt.json")
    if operations["status"] != "complete": raise SetupHold
    request = core.NodeHealthReadRequest(configured.target, configured.runtime_id, core.NodeHealthReadKind.READINESS,
        configured.declaration.identity(), WORKSPACE + "-request")
    common = dict(canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1, target=request.target,
        runtime_id=request.runtime_id, kind=request.kind, declaration_identity=request.declaration_identity,
        request_id=request.request_id, request_digest=request.canonical_digest(), issued_at=now, not_before=now, expires_at=now + 300)
    transit = core.DelegatedGatewayNodeHealthReadTransitGrant(profile=core.DelegatedGatewayNodeHealthReadTransitGrantProfile.V1,
        purpose=core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, issuer="cpk221-transit", key_id=public[0].key_id,
        gateway_node_id=request.target.node_id, attempt_id=WORKSPACE + "-attempt", jti=WORKSPACE + "-transit", **common)
    workload = core.DelegatedWorkloadNodeHealthReadGrant(profile=core.DelegatedWorkloadNodeHealthReadGrantProfile.V1,
        purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, issuer="cpk221-workload", key_id=public[1].key_id,
        audience=core.workload_node_control_audience(request.target), jti=WORKSPACE + "-workload", **common)
    ingress = NamedPublicIngress("management", IngressAuthorityReference("cpk221-retained-tunnel"),
        PublicIngressTarget("gateway", "control"), "cpk221-connector", HOSTNAME)
    packet = dict(profile="gateway-self-health-diagnostic.v1", attempt_id=WORKSPACE + "-attempt", request=request.descriptor(),
        ingress=ingress.descriptor(), target_id="cpk221-gateway-self", transit_socket="control",
        source_commit="369b3a3e2ad497ac4ab75e0c51ad11cb68dc1c0e", image_digest=controller_image_digest,
        resource_plan=resource_plan, artifacts={name: sha256(raw).hexdigest() for name, raw in artifacts.items()},
        transit_grant=transit.descriptor(), workload_grant=workload.descriptor(), keys=[])
    for key, record, action in zip(public, operations["keys"], generation_actions()):
        packet["keys"].append(dict(registration_id=record["registration_id"], key_id=key.key_id, fingerprint=key.fingerprint_sha256,
            private_reference=action["reference"], reference_registration_id=record["reference_registration_id"],
            provider_registration_id=operations["provider_registration_id"], endpoint_reference="cpk221-secrets",
            credential_reference=f"secret://bootstrap/{WORKSPACE}/resolve"))
    raw = rfc8785.dumps(packet)
    prepare_packet(raw, artifacts)
    write_private(root / "packet.json", raw)
    return raw


def route_copy(config, expected_origin):
    if type(config) is not dict or set(config) - {"ingress", "originRequest", "warp-routing"}: raise SetupHold
    if config.get("originRequest", {}) != {} or config.get("warp-routing", {"enabled": False}) != {"enabled": False}: raise SetupHold
    rules = config.get("ingress")
    if type(rules) is not list or len(rules) != 2 or rules[1] != {"service": "http_status:404"}: raise SetupHold
    rule = rules[0]
    if (type(rule) is not dict or set(rule) - {"hostname", "service", "originRequest"}
            or rule.get("hostname") != HOSTNAME or rule.get("service") != expected_origin or rule.get("originRequest", {}) != {}): raise SetupHold
    origin = urlsplit(expected_origin)
    if (origin.scheme != "http" or not origin.hostname or origin.port != 8080 or origin.username is not None
            or origin.password is not None or origin.path not in ("", "/") or origin.query or origin.fragment
            or any(char.isspace() for char in expected_origin) or "\\" in expected_origin): raise SetupHold
    changed = copy.deepcopy(config)
    changed["ingress"][0]["service"] = urlunsplit(("http", origin.netloc.rsplit(":", 1)[0] + ":8000", origin.path, "", ""))
    return changed


def route_evidence(status, original, changed, previous=None, provider=None):
    history = [] if previous is None else list(previous["history"])
    history.append(dict(status=status, observed_at=datetime.now(timezone.utc).isoformat()))
    return dict(status=status, original_sha256=sha256(rfc8785.dumps(original)).hexdigest(),
        temporary_sha256=sha256(rfc8785.dumps(changed)).hexdigest(), history=history,
        provider_observations=copy.deepcopy(getattr(provider, "observations", [])))


@bounded_failure
def change_route(root, expected_origin, provider):
    root = private_root(root)
    if (root / "route-action.json").exists() or (root / "route-original.json").exists(): raise SetupHold
    original = provider.get_config()
    changed = route_copy(original, expected_origin)
    if provider.get_connections() != []: raise SetupHold
    write_private(root / "route-original.json", original)
    pending = route_evidence("pending-update", original, changed, provider=provider)
    write_private(root / "route-action.json", pending)
    if provider.put_config(changed) != changed: raise SetupHold
    if provider.get_config() != changed: raise SetupHold
    result = route_evidence("route-updated", original, changed, pending, provider)
    write_private(root / "route-action.json", result, replace=True)
    return result


@bounded_failure
def restore_route(root, provider):
    root = private_root(root)
    if (root / "route-restore.json").exists(): raise SetupHold
    if read_json(root / "route-action.json")["status"] != "route-updated": raise SetupHold
    original = read_json(root / "route-original.json")
    changed = route_copy(original, original["ingress"][0]["service"])
    if provider.get_config() != changed or provider.get_connections() != []: raise SetupHold
    pending = route_evidence("pending-restore", original, changed, provider=provider)
    write_private(root / "route-restore.json", pending)
    if provider.put_config(original) != original: raise SetupHold
    if provider.get_config() != original: raise SetupHold
    result = route_evidence("route-restored", original, changed, pending, provider)
    write_private(root / "route-restore.json", result, replace=True)
    return result


class CloudflareRouteProvider:
    """Existing provider client; exact retained-tunnel config/connections only."""
    def __init__(self, credentials, *, transport=None):
        from control_plane_kit_interpreters.cloudflare.client import CloudflareApiClient, CloudflareZoneAuthority
        from .gateway_ingress_admission import BASE, EXPECTED_TUNNEL, Credentials
        if type(credentials) is not Credentials: raise SetupHold
        self.root = f"/accounts/{credentials.account}/cfd_tunnel/{EXPECTED_TUNNEL}"
        self.observations = []
        authority = CloudflareZoneAuthority(credentials.account, credentials.zone, "openj92.dev",
            SecretReference("secret://bootstrap/cpk221/cloudflare-api"), HOSTNAME)
        self.client = CloudflareApiClient(authority, credentials.token,
            RouteTransport(BASE + self.root, transport=transport))

    def get_config(self):
        response = self.client._request("GET", self.root + "/configurations")
        observed = dict(observed_at=datetime.now(timezone.utc).isoformat())
        version = response["result"].get("version")
        if type(version) is int and version >= 0: observed["version"] = version
        self.observations.append(observed)
        return response["result"]["config"]

    def get_connections(self):
        response = self.client._request("GET", self.root + "/connections")
        value = response["result"]
        if type(value) is not list: raise SetupHold
        return value

    def put_config(self, value):
        response = self.client._request("PUT", self.root + "/configurations", json={"config": value})
        result = response["result"]["config"]
        if result != value: raise SetupHold
        return result


class RouteTransport:
    def __init__(self, root, *, transport=None):
        self.root, self.transport = root, transport

    @bounded_failure
    def request(self, method, url, *, headers, json=None, params=None):
        from control_plane_kit_interpreters.cloudflare.client import CloudflareHttpResponse
        if params is not None or (method, url) not in (
                ("GET", self.root + "/connections"), ("GET", self.root + "/configurations"),
                ("PUT", self.root + "/configurations")):
            raise SetupHold
        if method == "GET" and json is not None: raise SetupHold
        if method == "PUT":
            closed(json, {"config"})
            if len(rfc8785.dumps(json)) > 65536: raise SetupHold
        deadline = time.monotonic() + 20
        with httpx.Client(timeout=10, verify=True, follow_redirects=False, trust_env=False, transport=self.transport) as client:
            with client.stream(method, url, headers={**headers, "Accept-Encoding": "identity"}, json=json) as response:
                if not 200 <= response.status_code < 300 or response.headers.get("content-encoding", "identity") != "identity": raise SetupHold
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 65536 or time.monotonic() > deadline: raise SetupHold
                    body.extend(chunk)
                if time.monotonic() > deadline: raise SetupHold
                value = bounded_json(bytes(body))
                if type(value) is not dict or value.get("success") is not True: raise SetupHold
                return CloudflareHttpResponse(response.status_code, value)


def approved_inputs(path, phase):
    """Protected operator-authored authority, separately mounted from candidates.

    Filesystem integrity is the trust boundary; this is not a signed approval
    service. The external operator must mount this exact reviewed authorization.
    """
    value = closed(read_json(Path(path)), {"profile", "source_sha256", "root", "expires_at", "phases", "resource_plan",
        "controller_image_digest", "gateway_image_digest", "runtime_id", "ingress_receipt_file", "cloudflare_credentials_file"})
    if (value["profile"] != "cpk221-approved-setup.v1" or type(value["expires_at"]) is not int
            or type(value["phases"]) is not list or not all(type(item) is str for item in value["phases"])
            or value["expires_at"] <= int(time.time()) or phase not in value["phases"]
            or value["source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest()
            or value["root"] != "/private/tmp/cpk221-self-health-r1"):
        raise SetupHold
    root = Path(value["root"])
    if Path(path).resolve().is_relative_to(root): raise SetupHold
    return value, root


def seal_runner_authority(root, approval, packet):
    """Derive the original one-shot runner seal within the approved scope."""
    value = bounded_json(packet)
    bindings = [dict(issuer="urn:cpk221:diagnostic", subject="cpk221-runner-operator", kind="operator",
        workspace_grants=[dict(workspace_id=WORKSPACE, scopes=[PolicyScope.SECRET_PROVIDER_USE.value])],
        credential_file=str(root / "runner-binding.token"))]
    write_private(root / "runner-principals.json", bindings)
    write_private(root / "runner-approval.json", dict(packet_digest=sha256(packet).hexdigest(),
        issuer="urn:cpk221:diagnostic", subject="cpk221-runner-operator", workspace_id=WORKSPACE,
        attempt_id=value["attempt_id"], database_identity="cpk221_self_health_r1",
        expires_at=min(approval["expires_at"], value["workload_grant"]["expires_at"]), reference=approval["resource_plan"]))
    write_private(root / "runner-bootstrap.json", dict(workspace_id=WORKSPACE, database_identity="cpk221_self_health_r1",
        database_dsn_file=str(root / "database.dsn"), operator_credential_file=str(root / "runner-operator.token"),
        principal_bindings_file=str(root / "runner-principals.json"), approval_file=str(root / "runner-approval.json"),
        secret_endpoints={"cpk221-secrets": PROVIDER_URL},
        secret_credentials={f"secret://bootstrap/{WORKSPACE}/resolve": str(root / "provider-resolve.token")}))


@bounded_failure
def seal_approved_packet(root, approval, *, now):
    # Refuse before writing any seal files if the remaining approval cannot
    # contain the original full grant window. Never emit an unusable success.
    if type(approval["expires_at"]) is not int or approval["expires_at"] < now + 300: raise SetupHold
    packet = seal_packet(root, controller_image_digest=approval["controller_image_digest"],
        resource_plan=approval["resource_plan"], now=now)
    seal_runner_authority(root, approval, packet)
    return packet


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Finite approved #221 setup; each phase is single use.")
    parser.add_argument("phase", choices=("prepare", "generate", "operations", "artifacts", "seal", "route-update", "route-restore"))
    parser.add_argument("--approval", required=True)
    args = parser.parse_args(argv)
    try:
        approval, root = approved_inputs(args.approval, args.phase)
        if args.phase == "prepare": prepare_private_material(root)
        elif args.phase == "generate": generate_health_keys(root)
        elif args.phase == "operations": initialize_operations(root)
        elif args.phase == "seal":
            seal_approved_packet(root, approval, now=int(time.time()))
        else:
            from .gateway_ingress_admission import load_credentials, EXPECTED_TUNNEL
            admission = read_json(Path(approval["ingress_receipt_file"]))
            if admission["hostname"] != HOSTNAME or admission["tunnel_id"] != EXPECTED_TUNNEL: raise SetupHold
            origin = admission["origin_service"]
            if args.phase == "artifacts":
                build_artifacts(root, gateway_image_digest=approval["gateway_image_digest"],
                    runtime_id=approval["runtime_id"], private_hostname=urlsplit(origin).hostname)
            else:
                provider = CloudflareRouteProvider(load_credentials(approval["cloudflare_credentials_file"]))
                if args.phase == "route-update": change_route(root, origin, provider)
                else: restore_route(root, provider)
        print(json.dumps({"status": "phase-complete", "phase": args.phase}))
        return 0
    except Exception:
        print(json.dumps({"status": "setup-held", "phase": args.phase}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
