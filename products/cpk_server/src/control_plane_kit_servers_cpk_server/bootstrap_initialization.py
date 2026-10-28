"""Socket-free explicit workspace initialization and read-only receipt inspection."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distribution
from importlib.resources import files
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from psycopg import connect
from psycopg.pq import TransactionStatus
from control_plane_kit_operations.postgres import PostgresUnitOfWork, install_schema
from control_plane_kit_operations.workspace_permissions import (
    WorkspacePermissionCommandService, WorkspacePermissionInitializationReceipt,
    WorkspacePermissionNotFound, WorkspacePermissionReadService,
)

from .bootstrap import RootBootstrapError, RootBootstrapHold, canonical, decode_document, verified_plan
from .bootstrap_runtime import private_read
from .bootstrap_workspace import admit_workspace_intent


PROGRESS_VOLUME_PATH = "/cpk-initialization"
PROGRESS_PATH = PROGRESS_VOLUME_PATH + "/private/progress/progress.json"
PROGRESS_SCHEMA = "cpk.root-bootstrap.initialization-progress.v1"
TARGET_SCHEMA = "cpk.root-bootstrap.initialization-target.v1"
_STORES = ("CPK_WORKPLACE_DATABASE_URL", "CPK_ACTIVITY_HISTORY_DATABASE_URL",
    "CPK_OBSERVER_STATE_DATABASE_URL", "CPK_GRAPH_TOPOLOGY_DATABASE_URL")


@dataclass(frozen=True, repr=False)
class _Inputs:
    plan: dict = field(repr=False)
    intent: object = field(repr=False)
    target: dict = field(repr=False)
    password: str = field(repr=False)


def package_correlation():
    """Identify the installed owner in this exact driver, never a migration input."""
    direct = json.loads(distribution("control-plane-kit-operations").read_text("direct_url.json"))
    match = re.fullmatch(r"https://github\.com/OpenJ92/control-plane-kit/archive/([0-9a-f]{40})\.zip",
        direct["url"])
    if match is None or direct.get("subdirectory") != "control-plane-kit-operations":
        raise RootBootstrapError("bootstrap installed schema owner could not be verified")
    schema = files("control_plane_kit_operations.postgres").joinpath("current_schema.sql").read_bytes()
    return {"operations_commit": match[1], "schema_sha256": hashlib.sha256(schema).hexdigest()}


def database_target(plan):
    """The verified graph's four stores select one product-owned database."""
    pg = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["postgres_node_id"])
    cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
    database, username = pg["environment"]["POSTGRES_DB"], pg["environment"]["POSTGRES_USER"]
    if (cpk["environment"].get("PGDATABASE") != database
            or cpk["environment"].get("PGUSER") != username):
        raise ValueError("database identity differs")
    for name in _STORES:
        endpoint = urlsplit(cpk["environment"][name])
        if (endpoint.scheme != "postgresql" or endpoint.hostname != plan["postgres_node_id"]
                or endpoint.port != 5432 or endpoint.username is not None or endpoint.password is not None
                or endpoint.path not in ("", "/" + database) or endpoint.query or endpoint.fragment):
            raise ValueError("database endpoint differs")
    return {"database": database, "username": username, "namespace": "public"}


def helper_input_bytes(plan, intent, material, target):
    """Project the admitted immutable intent into only this helper's private files."""
    installation = plan["input"]["installation"]
    private = {"plan_digest": plan["digest"],
        "policy": {"file": "workspace-authority.json", "sha256": hashlib.sha256(intent.policy_bytes).hexdigest()},
        "installer": intent.installer.identity.descriptor(),
        "initialization_idempotency_key": intent.initialization_key.value,
        "administration": decode_document(intent.administration_bytes)}
    result = {"plan.json": canonical(plan), "workspace-intent.json": canonical(private),
        "workspace-authority.json": intent.policy_bytes,
        "credential": material[installation["references"]["control_credential"]].encode("utf-8"),
        "database-password": material[installation["references"]["postgres_password"]].encode("utf-8"),
        "acquisition.json": canonical(target)}
    auth = installation.get("control_auth", {"kind": "single-operator"})
    if auth["kind"] == "multi-principal":
        result["principals.json"] = material[auth["principals_document"]].encode("utf-8")
    return result


def _load_inputs(root):
    plan = decode_document(private_read(root / "plan.json"))
    plan = verified_plan(plan, plan["digest"], plan["driver_image_id"])
    installation = plan["input"]["installation"]
    if "workspace_authority" not in installation:
        raise ValueError("dynamic installation required")
    private = decode_document(private_read(root / "workspace-intent.json"))
    policy = private_read(root / "workspace-authority.json")
    credentials = {installation["references"]["control_credential"]:
        private_read(root / "credential").decode("utf-8")}
    auth = installation.get("control_auth", {"kind": "single-operator"})
    if auth["kind"] == "multi-principal":
        credentials[auth["principals_document"]] = private_read(root / "principals.json").decode("utf-8")
    intent = admit_workspace_intent(plan, private, policy, credentials)
    target = decode_document(private_read(root / "acquisition.json"))
    if set(target) != {"schema", "plan_digest", "driver_image_id", "installation_id", "engine_id",
            "postgres_container_id", "postgres_image_id", "labels", "data_volumes", "database", "username",
            "namespace", "operations_commit", "schema_sha256"}:
        raise ValueError("target fields differ")
    expected = {"schema": TARGET_SCHEMA, "plan_digest": plan["digest"],
        "driver_image_id": plan["driver_image_id"], "installation_id": installation["installation_id"],
        **database_target(plan), **package_correlation()}
    if any(target[key] != value for key, value in expected.items()):
        raise ValueError("target differs")
    if (type(target["engine_id"]) is not str or not 1 <= len(target["engine_id"]) <= 256
            or re.fullmatch(r"[0-9a-f]{64}", target["postgres_container_id"]) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", target["postgres_image_id"]) is None):
        raise ValueError("target identity differs")
    labels = target["labels"]
    if (type(labels) is not dict or set(labels) != set(plan["resources"]["labels"]) | {"org.openj92.cpk.acquisition"}
            or any(labels[key] != value for key, value in plan["resources"]["labels"].items())
            or re.fullmatch(r"[0-9a-f]{32}", labels["org.openj92.cpk.acquisition"]) is None):
        raise ValueError("target custody differs")
    pg = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["postgres_node_id"])
    if target["data_volumes"] != [{**entry, "id": entry["name"]} for entry in pg["data_volumes"]]:
        raise ValueError("data volumes differ")
    password = private_read(root / "database-password").decode("utf-8")
    if "\x00" in password or password.endswith("\n"):
        raise ValueError("password bytes differ")
    # No ambient libpq routing/authentication/options may affect this privileged
    # fixed-input command. All effective connection inputs are supplied below.
    if any(name.startswith("PG") for name in os.environ):
        raise ValueError("ambient database settings are unsupported")
    return _Inputs(plan, intent, target, password)


def _connection(inputs, *, autocommit=False, read_only=False):
    connection = connect(host="127.0.0.1", hostaddr="127.0.0.1", port=5432,
        dbname=inputs.target["database"], user=inputs.target["username"], password=inputs.password,
        autocommit=autocommit, connect_timeout=5, sslmode="disable", gssencmode="disable",
        options="-csearch_path=public -cstatement_timeout=15000 -clock_timeout=10000"
            + (" -cdefault_transaction_read_only=on" if read_only else ""))
    try:
        if connection.info.transaction_status != TransactionStatus.IDLE or connection.autocommit is not autocommit:
            raise ValueError("connection is not fresh")
        return connection
    except BaseException:
        connection.close()
        raise


def _checkpoint(directory, progress):
    raw = canonical(progress)
    if len(raw) > 4096:
        raise ValueError("progress bound")
    temporary = directory / "progress.new"
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, directory / "progress.json")
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_receipt(inputs):
    factory = lambda: PostgresUnitOfWork(lambda: _connection(inputs, read_only=True))
    service = WorkspacePermissionReadService(factory,
        administration_policy=inputs.intent.authority.administration_policy)
    try:
        receipt = service.installation(inputs.intent.installer)
    except WorkspacePermissionNotFound:
        return "missing", None
    if (type(receipt) is not WorkspacePermissionInitializationReceipt
            or receipt.installation_id != inputs.intent.installer.installation_id
            or receipt.actor != inputs.intent.installer.identity
            or receipt.idempotency_key != inputs.intent.initialization_key.value):
        return "conflict", None
    return "matching", receipt


def _utc_now():
    value = datetime.now(timezone.utc)
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def run_workspace_initialization(*, input_directory=Path("/bootstrap"),
        progress_directory=Path(PROGRESS_PATH).parent, inspect_only=False):
    """Fixed helper commands; directory seams are only for trusted composition tests."""
    try:
        if type(inspect_only) is not bool:
            raise ValueError("inspection mode")
        inputs = _load_inputs(input_directory)
        progress_directory.mkdir(mode=0o700, exist_ok=False)
        progress = {"schema": PROGRESS_SCHEMA, "plan_digest": inputs.plan["digest"],
            "installation_id": inputs.intent.installer.installation_id,
            "operations_commit": inputs.target["operations_commit"], "schema_sha256": inputs.target["schema_sha256"],
            "schema_acknowledged": False, "initialization": "unknown", "occurred_at": None,
            "pending": "inspection" if inspect_only else "schema"}
        _checkpoint(progress_directory, progress)
        if inspect_only:
            status, receipt = _read_receipt(inputs)
        else:
            # The fresh autocommit connection makes the owner's explicit
            # transaction top-level. Its context must return and close before
            # any schema acknowledgement or separate initialization connection.
            with _connection(inputs, autocommit=True) as connection:
                install_schema(connection, require_empty=True)
                # A transaction context can return without COMMIT if its
                # transport was already closed. That is not an acknowledgement.
                if (connection.closed or connection.autocommit is not True
                        or connection.info.transaction_status != TransactionStatus.IDLE):
                    raise ValueError("schema completion is unverified")
            progress.update(schema_acknowledged=True, pending=None)
            _checkpoint(progress_directory, progress)
            progress["pending"] = "initialization"
            _checkpoint(progress_directory, progress)
            factory = lambda: PostgresUnitOfWork(lambda: _connection(inputs))
            commands = WorkspacePermissionCommandService(factory,
                administration_policy=inputs.intent.authority.administration_policy,
                clock=_utc_now,
                id_factory=lambda: uuid4().hex)
            result = commands.initialize(inputs.intent.installer, idempotency_key=inputs.intent.initialization_key)
            status, receipt = _read_receipt(inputs)
            if result.replayed is not False or status != "matching" or receipt != result.receipt:
                raise ValueError("initialization acknowledgement differs")
        progress.update(initialization=status, pending=None,
            occurred_at=None if receipt is None else receipt.occurred_at)
        _checkpoint(progress_directory, progress)
        return progress
    except Exception:
        failure = RootBootstrapHold("bootstrap workspace initialization requires investigation")
    # Drop private parser/provider/DB exception context, including on admission.
    raise failure
