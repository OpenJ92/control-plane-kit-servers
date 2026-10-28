"""Docker-only root launcher commands and socket-free authenticated setup."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

from .bootstrap import (
    RootBootstrapError, RootBootstrapHold, apply_root_bootstrap, canonical, decode_document,
    inspect_root_bootstrap, inspect_root_initialization, plan_root_bootstrap, verified_plan, bootstrap_failure,
)


def public_setup(plan, credential):
    plan = verified_plan(plan, plan["digest"], plan["driver_image_id"])
    if "workspace_authority" not in plan["input"]["installation"]:
        return _public_setup(plan, credential)
    try:
        from .bootstrap_workspace import load_workspace_helper_intent
        if credential.name != "credential":
            raise ValueError("fixed setup credential required")
        intent = load_workspace_helper_intent(plan, credential.parent)
        return _public_setup(plan, credential, intent=intent)
    except Exception:
        failure = RootBootstrapHold("bootstrap public setup outcome requires investigation")
    # Never retain a private identity, policy or transport exception as context.
    raise failure


def _public_setup(plan, credential, *, intent=None):
    from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
    from control_plane_kit_core.runtime_effects import ImagePullAuthority
    from .client.profile import ClientProfile
    from .client.transport import PublicHttpTransport

    installation = plan["input"]["installation"]
    setup = plan["input"]["setup"]
    workspace = installation["workspace_id"]
    profile = ClientProfile("http://127.0.0.1:8080", workspace,
        {role: credential for role in ("operator", "approver", "worker")}, Path("/tmp/bootstrap-client"))
    transport = PublicHttpTransport(profile, timeout_seconds=15)
    progress = {"schema": "cpk.root-bootstrap.setup-progress.v1", "plan_digest": plan["digest"],
                "workspace_id": workspace, "status": "in-progress", "pending": None, "commands": [], "reads": []}
    progress_directory = Path("/tmp/cpk-bootstrap-progress")
    progress_directory.mkdir(mode=0o700, exist_ok=False)

    def checkpoint():
        raw = canonical(progress)
        if len(raw) > 65_536:
            raise RootBootstrapError("bootstrap public progress exceeds its bound")
        temporary = progress_directory / "progress.new"
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, progress_directory / "progress.json")
        descriptor = os.open(progress_directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    checkpoint()
    # Only read-only socket readiness is polled. Every public mutation is sent once.
    for attempt in range(90):
        try:
            with socket.create_connection(("127.0.0.1", 8080), timeout=1):
                break
        except OSError:
            if attempt == 89:
                raise RootBootstrapError("bootstrap public server did not become reachable") from None
            time.sleep(1)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    commands = progress["commands"]
    reads = progress["reads"]

    def call(route, payload, *, coordinates=None):
        paths = {} if route == "command.workspace-administration.create" else {"workspace_id": workspace, **(coordinates or {})}
        return transport.call(route, path_parameters=paths,
                              payload=payload, credential_role="operator")

    def command(route, payload, *, explicit=False):
        if len(commands) >= len(plan["setup_routes"]) or plan["setup_routes"][len(commands)] != route:
            raise RootBootstrapError("bootstrap setup sequence differs from reviewed plan")
        progress["pending"] = route
        checkpoint()
        result = call(route, payload if explicit else {"workspace_id": workspace,
            "idempotency_key": "root-" + plan["digest"][:32] + "-" + str(len(commands)), **payload})
        # Save only bounded returned coordinates, before later validation or the
        # next command can fail. Never persist a raw response or error body.
        entry = {"route": route}
        source = result.get("workspace", {}) if route == "command.workspace.create" else result
        if explicit:
            source = result.get("receipt", {})
        if isinstance(source, dict):
            for key in ("workspace_id", "current_graph_id", "desired_graph_id", "registration_id", "delivery_id", "authority_id",
                    "receipt_id", "observed_current_graph_id"):
                value = source.get(key)
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value):
                    entry[key] = value
            assignment = source.get("resulting_assignment", source)
            if isinstance(assignment, dict):
                if type(assignment.get("revision")) is int and assignment["revision"] >= 0:
                    entry["revision"] = assignment["revision"]
                if assignment.get("status") in ("active", "revoked"):
                    entry["status"] = assignment["status"]
                for key in ("assignment_id", "registration_id"):
                    value = assignment.get(key)
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value):
                        entry[key] = value
        commands.append(entry)
        progress["pending"] = None
        checkpoint()
        return result

    def read(route, *, query=None, **coordinates):
        result = call(route, {} if query is None else query, coordinates=coordinates)
        reads.append(route)
        checkpoint()
        return result

    def identity(value, key):
        result = value.get(key)
        if not isinstance(result, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", result):
            raise RootBootstrapError("bootstrap command identity could not be verified")
        commands[-1][key] = result
        checkpoint()
        return result

    def detail(route, field, key, expected, **coordinates):
        result = read(route, **coordinates)
        if result.get("workspace_id") != workspace or result.get(field, {}).get(key) != expected:
            raise RootBootstrapError("bootstrap registration readback differs from command result")
        return result[field]

    if intent is None:
        created = command("command.workspace.create", {"name": setup["workspace_name"], "metadata": {}})
        if created.get("workspace", {}).get("workspace_id") != workspace or created.get("replayed") is not False:
            raise RootBootstrapError("bootstrap new workspace could not be verified")
        current_graph = created["workspace"]["current_graph_id"]
    else:
        from .bootstrap_enrollment import (creation_receipt, permission_receipt, verify_permission_read,
            verify_runtime_registration, management_receipt)
        administration = decode_document(intent.administration_bytes)
        key = administration["workspace_creation_idempotency_key"]
        created = command("command.workspace-administration.create", {"workspace_id": workspace,
            "name": setup["workspace_name"], "metadata": {}, "idempotency_key": key}, explicit=True)
        current_graph = creation_receipt(created, intent, workspace, key).observed_current_graph_id
        for grant in administration["permission_grants"]:
            result = command("command.workspace-permission.grant", grant, explicit=True)
            receipt = permission_receipt(result, intent, workspace, grant)
            observed = read("read.workspace-permission", query={"target": grant["target"]})
            verify_permission_read(observed, receipt)
    provider = command("command.secret-provider.register", {
        **setup["provider"], "provider_kind": "control-plane-kit-secrets", "display_name": "Root secrets provider",
        "endpoint_reference": installation["provider_endpoint_ref"],
        "credential_reference": installation["references"]["provider_bootstrap_credential_ref"],
        "admitted_at": stamp, "metadata": {},
    })
    provider_id = identity(provider, "registration_id")
    detail("read.secret-provider-detail", "secret_provider", "registration_id", provider_id,
           provider_id=setup["provider"]["provider_id"])
    for reference in setup["secret_references"]:
        result = command("command.secret-reference.register", {
            **reference, "provider_registration_id": provider_id, "admitted_at": stamp, "metadata": {}})
        registration = identity(result, "registration_id")
        detail("read.secret-reference-detail", "secret_reference", "registration_id", registration, registration_id=registration)
    authority_ref = installation["runtime_access"]["authority_ref"]["reference_id"]
    registered = command("command.runtime-authority.register", {"authority_ref": authority_ref, "runtime_kind": "docker",
        "authority": {"kind": "local-docker-socket"}, "admitted_at": stamp})
    registration = identity(registered, "registration_id")
    authority_read = detail("read.runtime-authority-detail", "runtime_authority", "registration_id", registration, authority_ref=authority_ref)
    if intent is not None and administration["management_grant"] is not None:
        grant = administration["management_grant"]
        for value in (registered, authority_read):
            verify_runtime_registration(value, workspace, authority_ref, registration)
        payload = {key: value for key, value in grant.items() if key != "registration_from"}
        result = command("command.managed-runtime-access.grant", {**payload, "registration_id": registration}, explicit=True)
        receipt = management_receipt(result, intent, workspace, grant, registration)
        observed = read("read.managed-runtime-assignment", query={"runtime_id": grant["runtime_id"], "authority_ref": authority_ref})
        if (observed != receipt.resulting_assignment.descriptor() or type(observed.get("revision")) is not int):
            raise ValueError("management readback differs from receipt")
    delivered = command("command.runtime-authority-delivery.register", {"delivery": installation["runtime_access"], "admitted_at": stamp})
    delivery_id = identity(delivered, "delivery_id")
    detail("read.runtime-authority-delivery-detail", "runtime_authority_delivery", "delivery_id", delivery_id, authority_ref=authority_ref)
    products = plan["setup_products"] if "setup_products" in plan else installation["products"].values()
    for product in products:
        result = command("command.product.import", {"descriptor_document": product, "imported_at": stamp})
        identity(result, "registration_id")
        expected = ProductReference.from_document(ProductDescriptorCodec().decode_document(product)).descriptor()
        if result.get("reference") != expected or result.get("workspace_id") != workspace or result.get("status") != "active":
            raise RootBootstrapError("bootstrap imported product identity differs from selected descriptor")
        commands[-1]["reference"] = expected
        checkpoint()
    for authority in setup["image_pull_authorities"]:
        result = command("command.image-pull-authority.register", {**authority, "admitted_at": stamp})
        identity(result, "authority_id")
        expected = ImagePullAuthority(authority["registry"], authority.get("repository"), authority["credential_reference"]).descriptor()
        if result.get("authority") != expected or result.get("workspace_id") != workspace:
            raise RootBootstrapError("bootstrap pull authority differs from selected scope")
    for authority in setup["ingress_authorities"]:
        from control_plane_kit_operations.ingress_authorities import CloudflareZoneIngressAuthorityCodec
        effective = {**authority["authority"], "generated_secret_provider_registration_id": provider_id}
        expected = CloudflareZoneIngressAuthorityCodec().decode(effective).descriptor()
        registered = command("command.ingress-authority.register", {
            "authority_ref": authority["authority_ref"], "authority": effective, "admitted_at": stamp})
        registration = identity(registered, "registration_id")
        observed_authority = read("read.ingress-authority-detail", authority_ref=authority["authority_ref"])
        detail_value = observed_authority.get("ingress_authority", {})
        # The existing public read projection redacts these three reference
        # fields. The command proves their exact values; its registration ID
        # ties the readback's public projection to that confirmed result.
        public_expected = {**expected, "api_token_ref": "<redacted>",
            "generated_secret_provider_registration_id": "<redacted>",
            "generated_secret_reference_prefix": "<redacted>"}
        for value, expected_authority in ((registered, expected), (detail_value, public_expected)):
            if (value.get("registration_id") != registration or value.get("workspace_id") != workspace
                    or value.get("authority_ref") != authority["authority_ref"]
                    or value.get("status") != "active" or value.get("authority") != expected_authority):
                raise RootBootstrapError("bootstrap ingress authority differs from approved effective scope")
        if observed_authority.get("workspace_id") != workspace:
            raise RootBootstrapError("bootstrap ingress readback workspace differs")
    observed = read("read.workspace")
    if observed.get("workspace", {}).get("workspace_id") != workspace:
        raise RootBootstrapError("bootstrap workspace readback could not be verified")
    current = read("read.current-graph")
    desired = read("read.desired-graph")
    expected_desired = observed["workspace"].get("desired_graph_id") if intent is not None else created["workspace"]["desired_graph_id"]
    if (current.get("graph_id") != current_graph
            or current.get("assigned") is not True
            or (intent is not None and observed["workspace"].get("current_graph_id") != current_graph)
            or not isinstance(expected_desired, str) or desired.get("graph_id") != expected_desired):
        raise RootBootstrapError("bootstrap initial graph readback differs from workspace creation")
    progress["status"] = "complete"
    checkpoint()
    return {"status": "authenticated-local-setup", "workspace_id": workspace,
            "commands": commands, "reads": reads, "external_endpoint": "unverified"}


def main():
    parser = argparse.ArgumentParser(description="Explicit Docker root acquisition")
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--input", type=Path, required=True)
    plan_parser.add_argument("--driver", required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument("--driver", required=True)
    apply_parser.add_argument("--digest", required=True)
    apply_parser.add_argument("--index", type=Path, required=True)
    apply_parser.add_argument("--state", type=Path, required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--state", type=Path, required=True)
    initialization_parser = sub.add_parser("inspect-initialization")
    initialization_parser.add_argument("--plan", type=Path, required=True)
    initialization_parser.add_argument("--driver", required=True)
    initialization_parser.add_argument("--digest", required=True)
    initialization_parser.add_argument("--index", type=Path, required=True)
    initialization_parser.add_argument("--state", type=Path, required=True)
    sub.add_parser("initialize-workspace")
    sub.add_parser("inspect-workspace-initialization")
    sub.add_parser("setup")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            with args.input.open("rb") as stream:
                document = decode_document(stream.read(1_048_577))
            result = plan_root_bootstrap(document, driver_image_id=args.driver)
        elif args.command == "apply":
            with args.plan.open("rb") as stream:
                plan = decode_document(stream.read(1_048_577))
            result = apply_root_bootstrap(plan, expected_digest=args.digest, driver_image_id=args.driver,
                                          index_path=args.index, state_directory=args.state)
        elif args.command == "inspect":
            result = inspect_root_bootstrap(state_directory=args.state)
        elif args.command == "inspect-initialization":
            with args.plan.open("rb") as stream:
                plan = decode_document(stream.read(1_048_577))
            result = inspect_root_initialization(plan, expected_digest=args.digest, driver_image_id=args.driver,
                index_path=args.index, state_directory=args.state)
        elif args.command in ("initialize-workspace", "inspect-workspace-initialization"):
            from .bootstrap_initialization import run_workspace_initialization
            result = run_workspace_initialization(inspect_only=args.command == "inspect-workspace-initialization")
        else:
            from .bootstrap_runtime import private_read
            result = public_setup(decode_document(private_read(Path("/bootstrap/plan.json"))), Path("/bootstrap/credential"))
        print(canonical(result).decode())
        return 0
    except Exception as error:
        # Never print SDK exceptions, request payloads, provider bodies or traces.
        print(json.dumps(bootstrap_failure(error)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
