"""Protected synthetic inputs for the existing root/real-Postgres witnesses."""
import hashlib
import importlib
import json

from test_dynamic_root_bootstrap import DynamicRootBootstrapTests, TOKEN


def initialization_inputs(test, *, multiple=True):
    fixture = DynamicRootBootstrapTests()
    fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    document, policy, private = fixture.inputs(multiple=multiple)
    plan = fixture.plan(document)
    index, _ = fixture.material(plan, policy, private)
    runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
    credentials, intent = runtime._material(plan, index)
    root = fixture.root / "helper"
    root.mkdir(mode=0o700)
    module = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_initialization")
    target = initialization_target(plan)
    private = {**private, "plan_digest": plan["digest"],
        "policy": {"file": "workspace-authority.json", "sha256": hashlib.sha256(policy).hexdigest()}}
    values = {"plan.json": fixture.api.canonical(plan), "workspace-intent.json": fixture.api.canonical(private),
        "workspace-authority.json": policy, "credential": TOKEN.encode(),
        "database-password": credentials[document["installation"]["references"]["postgres_password"]].encode(),
        "acquisition.json": fixture.api.canonical(target)}
    if multiple:
        values["principals.json"] = credentials[document["installation"]["control_auth"]["principals_document"]].encode()
    for name, value in values.items():
        fixture.private_write(root / name, value)
    return fixture, module, plan, index, root, target, intent


def initialization_target(plan):
    """Synthetic controller coordinates, with the actual installed schema owner."""
    module = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_initialization")
    pg = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["postgres_node_id"])
    return {"schema": "cpk.root-bootstrap.initialization-target.v1", "plan_digest": plan["digest"],
        "driver_image_id": plan["driver_image_id"], "installation_id": plan["input"]["installation"]["installation_id"],
        "engine_id": "synthetic-daemon", "postgres_container_id": "a" * 64,
        "postgres_image_id": "sha256:" + "b" * 64,
        "labels": {**plan["resources"]["labels"], "org.openj92.cpk.acquisition": "c" * 32},
        "data_volumes": [{**entry, "id": entry["name"]} for entry in pg["data_volumes"]],
        "database": pg["environment"]["POSTGRES_DB"], "username": pg["environment"]["POSTGRES_USER"],
        "namespace": "public", **module.package_correlation()}


def read_progress(directory):
    return json.loads((directory / "progress.json").read_bytes())
