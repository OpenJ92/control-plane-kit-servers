"""One child installation through existing authenticated public clients.

This module composes product/client contracts. It does not execute Docker, own
Operations state, mint material, or recover an uncertain public mutation.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.public_ingress import NamedPublicIngress
from control_plane_kit_core.secrets import SecretReference, SecretUseIntent
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph

from ..installation import DockerCpkInstallation, compose_docker_cpk_installation
from .workflow import MAXIMUM_DESIRED_BYTES, TopologyClient


class ChildInstallationError(ValueError):
    """Fixed public input refusal, without provider response or credential text."""


class ChildInstallationHold(ChildInstallationError):
    """Inspect prior public coordinates; automatic redispatch is unavailable."""


_COORDINATE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_SETUP_SCOPES = frozenset({
    PolicyScope.HUB_INSTANCE_CREATE, PolicyScope.INSTANCE_WORKSPACE_READ,
    PolicyScope.INSTANCE_WORKSPACE_EDIT, PolicyScope.SECRET_PROVIDER_REGISTER,
    PolicyScope.SECRET_PROVIDER_READ, PolicyScope.RUNTIME_AUTHORITY_REGISTER,
    PolicyScope.RUNTIME_AUTHORITY_READ, PolicyScope.RUNTIME_AUTHORITY_DELIVERY_REGISTER,
    PolicyScope.RUNTIME_AUTHORITY_DELIVERY_READ,
})


def _json(value, *, maximum=1_048_576):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > maximum:
        raise ChildInstallationError("child installation document exceeds its bound")
    return raw


def _identity(value):
    if not isinstance(value, str) or not _COORDINATE.fullmatch(value):
        raise ChildInstallationError("child installation coordinate is invalid")
    return value


def child_installation_document(installation: DockerCpkInstallation, *, child_workspace_id: str) -> dict:
    """Project the shared composer into exact parent imports and child target."""
    try:
        _identity(child_workspace_id)
        if not isinstance(installation, DockerCpkInstallation) or not isinstance(installation.ingress, NamedPublicIngress):
            raise ValueError()
        if not any(grant.workspace_id == child_workspace_id for grant in installation.workspace_grants):
            raise ValueError()
        topology = compose_docker_cpk_installation(installation)
        graph = compile_topology(topology)
        if not validate_graph(graph).valid:
            raise ValueError()
        encoded = GraphDescriptorCodec().encode(graph)
        _json(encoded, maximum=MAXIMUM_DESIRED_BYTES)
        products = [json.loads(child.implementation.document.content)
                    for child in topology.root.children if hasattr(child, "block_id")]
        document = {"schema": "cpk.child-installation.v1", "parent_workspace_id": installation.workspace_id,
                    "child_workspace_id": child_workspace_id,
                    "child_endpoint": f"https://{installation.ingress.hostname}",
                    "installation_id": installation.installation_id, "graph": encoded, "products": products}
        _json(document)
        return document
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ChildInstallationError("child installation input could not be verified") from None


class _Progress:
    """Exclusive, bounded command coordinates for this recipe; never replay."""

    def __init__(self, state, target, phase):
        if not isinstance(state, Path) or not state.is_absolute():
            raise ChildInstallationError("child progress directory must be absolute")
        if any(path.is_symlink() for path in (state, *state.parents)):
            raise ChildInstallationHold("child progress path requires investigation")
        try:
            # Exclusive mkdir also arbitrates concurrent first invocations. An
            # existing directory, even after failure/completion, never redispatches.
            state.mkdir(mode=0o700, parents=False, exist_ok=False)
        except OSError:
            raise ChildInstallationHold("child progress already exists or is unavailable") from None
        self.state = state
        self.value = {"schema": "cpk.child-installation-progress.v1", "target": target,
                      "phase": phase, "pending": None, "commands": [], "reads": []}
        self.save()

    def write(self, name, raw):
        temporary = self.state / (name + ".new")
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state / name)
        descriptor = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def save(self):
        self.write("progress.json", _json(self.value))

    def command(self, client, route, payload):
        if len(self.value["commands"]) >= 64:
            raise ChildInstallationHold("child setup command bound exceeded")
        key = str(uuid4())
        self.value["pending"] = {"route": route, "idempotency_key": key}
        self.save()
        result = client.transport.call(route,
            path_parameters={"workspace_id": client.profile.workspace_id},
            payload={**payload, "workspace_id": client.profile.workspace_id, "idempotency_key": key},
            credential_role="operator")
        # Persist only known bounded returned coordinates, before later validation.
        source = result.get("workspace", {}) if route == "command.workspace.create" else result
        coordinates = {key: value for key, value in source.items()
                       if key in {"workspace_id", "registration_id", "delivery_id", "current_graph_id", "desired_graph_id"}
                       and isinstance(value, str) and _COORDINATE.fullmatch(value)}
        self.value["commands"].append({"route": route, "coordinates": coordinates})
        self.save()
        if source.get("workspace_id") != client.profile.workspace_id:
            raise ChildInstallationHold("child command workspace differs")
        return result

    def confirmed(self):
        self.value["pending"] = None
        self.save()

    def read(self, client, route, **coordinates):
        if len(self.value["reads"]) >= 128:
            raise ChildInstallationHold("child setup read bound exceeded")
        result = client.transport.call(route,
            path_parameters={"workspace_id": client.profile.workspace_id, **coordinates}, payload={}, credential_role="operator")
        self.value["reads"].append(route)
        self.save()
        return result

    def detail(self, client, route, field, key, expected, **coordinates):
        result = self.read(client, route, **coordinates)
        if result.get("workspace_id") != client.profile.workspace_id or result.get(field, {}).get(key) != expected:
            raise ChildInstallationHold("child registration readback differs")

    def finish(self, result):
        self.value.update(phase="complete", pending=None, result=result)
        self.save()


def _target(document, profile, phase, setup=None):
    return {"endpoint": profile.endpoint, "workspace_id": profile.workspace_id,
            "installation_sha256": hashlib.sha256(_json(document)).hexdigest(),
            "setup_sha256": None if setup is None else hashlib.sha256(_json(setup)).hexdigest(), "operation": phase}


def _import_products(client, progress, products, stamp):
    for document in products:
        expected = ProductReference.from_document(ProductDescriptorCodec().decode_document(document)).descriptor()
        result = progress.command(client, "command.product.import", {"descriptor_document": document, "imported_at": stamp})
        _identity(result.get("registration_id"))
        if (result.get("workspace_id") != client.profile.workspace_id or result.get("status") != "active"
                or result.get("reference") != expected):
            raise ChildInstallationHold("child product import identity differs")
        progress.confirmed()


def prepare_child_installation(installation: DockerCpkInstallation, *, parent: TopologyClient,
                               child_workspace_id: str, state_directory: Path):
    """Import exact composed variants, then use the existing public planner.

    The caller inspects and separately approves/applies the returned plan through
    TopologyClient. This function does not execute it or initialize the child.
    """
    document = child_installation_document(installation, child_workspace_id=child_workspace_id)
    if parent.profile.workspace_id != document["parent_workspace_id"]:
        raise ChildInstallationError("parent workspace does not match installation")
    try:
        progress = _Progress(state_directory, _target(document, parent.profile, "prepare"), "preparing")
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        _import_products(parent, progress, document["products"], stamp)
        progress.write("desired.json", _json(document["graph"], maximum=MAXIMUM_DESIRED_BYTES))
        progress.value["pending"] = "client.plan"
        progress.save()
        result = parent.plan(state_directory / "desired.json", title="Deploy child installation")
        progress.finish(result.descriptor())
        return result
    except Exception:
        raise ChildInstallationHold("child preparation could not be verified; inspect private progress") from None


def _validate_setup(installation, child, setup):
    try:
        document = child_installation_document(installation, child_workspace_id=child.profile.workspace_id)
        if child.profile.endpoint != document["child_endpoint"]:
            raise ValueError()
        grant = next(value for value in installation.workspace_grants if value.workspace_id == child.profile.workspace_id)
        if not _SETUP_SCOPES <= set(grant.scopes):
            raise ValueError()
        if not isinstance(setup, dict) or set(setup) != {"workspace_name", "provider", "secret_references"}:
            raise ValueError()
        if not isinstance(setup["workspace_name"], str) or not 1 <= len(setup["workspace_name"]) <= 512:
            raise ValueError()
        provider = setup["provider"]
        if not isinstance(provider, dict) or set(provider) != {"provider_id", "allowed_reference_prefixes", "allowed_intents"}:
            raise ValueError()
        _identity(provider["provider_id"])
        prefixes, intents = provider["allowed_reference_prefixes"], provider["allowed_intents"]
        if (not isinstance(prefixes, list) or not 1 <= len(prefixes) <= 32
                or not isinstance(intents, list) or not 1 <= len(intents) <= 32):
            raise ValueError()
        for prefix in prefixes:
            SecretReference(prefix)
        for intent in intents:
            SecretUseIntent(intent)
        references = setup["secret_references"]
        if not isinstance(references, list) or len(references) > 16:
            raise ValueError()
        for reference in references:
            if not isinstance(reference, dict) or set(reference) != {"reference", "allowed_intents"}:
                raise ValueError()
            SecretReference(reference["reference"])
            if not any(reference["reference"] == prefix or reference["reference"].startswith(prefix.rstrip("/") + "/") for prefix in prefixes):
                raise ValueError()
            if (not isinstance(reference["allowed_intents"], list) or not reference["allowed_intents"]
                    or not set(reference["allowed_intents"]) <= set(intents)):
                raise ValueError()
        _json(setup, maximum=65_536)
        return document
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration):
        raise ChildInstallationError("child setup target or declared setup scope is invalid") from None


def initialize_child_workspace(installation: DockerCpkInstallation, *, child: TopologyClient,
                               setup: dict, state_directory: Path) -> dict:
    """Initialize the declared child via public commands after parent convergence.

    The joined recipe must verify its parent operation before calling this explicit
    mutation. Each invocation is exclusive and never automatically repeated.
    """
    document = _validate_setup(installation, child, setup)
    workspace = child.profile.workspace_id
    try:
        progress = _Progress(state_directory, _target(document, child.profile, "initialize", setup), "initializing")
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        created = progress.command(child, "command.workspace.create", {"name": setup["workspace_name"], "metadata": {}})
        value = created.get("workspace", {})
        if value.get("workspace_id") != workspace or created.get("replayed") is not False:
            raise ChildInstallationHold("child workspace creation differs")
        current = _identity(value.get("current_graph_id"))
        desired = value.get("desired_graph_id")
        if desired is not None:
            _identity(desired)
        progress.confirmed()
        provider = progress.command(child, "command.secret-provider.register", {
            **setup["provider"], "provider_kind": "control-plane-kit-secrets", "display_name": "Child secrets provider",
            "endpoint_reference": installation.provider_endpoint_ref.reference_id,
            "credential_reference": installation.provider_bootstrap_credential_ref.reference_id,
            "admitted_at": stamp, "metadata": {}})
        registration = _identity(provider.get("registration_id"))
        progress.detail(child, "read.secret-provider-detail", "secret_provider", "registration_id", registration,
                        provider_id=setup["provider"]["provider_id"])
        progress.confirmed()
        for reference in setup["secret_references"]:
            result = progress.command(child, "command.secret-reference.register", {
                **reference, "provider_registration_id": registration, "admitted_at": stamp, "metadata": {}})
            identity = _identity(result.get("registration_id"))
            progress.detail(child, "read.secret-reference-detail", "secret_reference", "registration_id", identity,
                            registration_id=identity)
            progress.confirmed()
        authority = installation.runtime_access.authority_ref.reference_id
        result = progress.command(child, "command.runtime-authority.register", {
            "authority_ref": authority, "runtime_kind": "docker", "authority": {"kind": "local-docker-socket"}, "admitted_at": stamp})
        identity = _identity(result.get("registration_id"))
        progress.detail(child, "read.runtime-authority-detail", "runtime_authority", "registration_id", identity, authority_ref=authority)
        progress.confirmed()
        result = progress.command(child, "command.runtime-authority-delivery.register", {
            "delivery": installation.runtime_access.descriptor(), "admitted_at": stamp})
        identity = _identity(result.get("delivery_id"))
        progress.detail(child, "read.runtime-authority-delivery-detail", "runtime_authority_delivery", "delivery_id", identity, authority_ref=authority)
        progress.confirmed()
        observed = progress.read(child, "read.workspace").get("workspace", {})
        observed_current = progress.read(child, "read.current-graph")
        observed_desired = progress.read(child, "read.desired-graph")
        if (observed.get("workspace_id") != workspace or observed.get("current_graph_id") != current
                or observed.get("desired_graph_id") != desired or observed_current.get("graph_id") != current
                or observed_current.get("assigned") is not True or observed_desired.get("graph_id") != desired):
            raise ChildInstallationHold("child workspace readback differs")
        result = {"status": "child-initialized", "workspace_id": workspace, "endpoint": child.profile.endpoint,
                  "current_graph_id": current, "desired_graph_id": desired, "provider_registration_id": registration}
        progress.finish(result)
        return result
    except Exception:
        raise ChildInstallationHold("child initialization could not be verified; inspect private progress") from None
