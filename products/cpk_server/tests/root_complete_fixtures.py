"""Public-only complete-root fixtures; image identities are not qualified."""
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.products import ProductDescriptorCodec
from test_frontend_deployment import FrontendDeploymentTests
from test_root_bootstrap import DRIVER, installation_input


def complete_input():
    document = installation_input()
    commissioning = importlib.import_module("control_plane_kit_servers_cpk_server.root_commissioning")
    cpk = importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
    secrets = importlib.import_module("control_plane_kit_servers_secrets_server.configuration")
    with TemporaryDirectory(dir=Path.cwd()) as directory:
        state = Path(directory)
        intent = {"schema": "cpk.root-commissioning.intent.v1", "installation_id": "root-a",
            "workspace_id": "root-workspace", "profile": "operator-offline-read-trust",
            "custody": {"host_directory": str(state), "uid": os.geteuid(), "gid": os.getegid()}}
        plan = commissioning.plan_root_commissioning(intent, preparer_image_id=DRIVER)
        public = commissioning.prepare_root_commissioning(plan, expected_digest=plan["digest"],
            preparer_image_id=DRIVER, state_directory=state)
    codec = ProductDescriptorCodec()
    for role in ("cpk", "secrets"):
        artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
        # Noncanonical whitespace/source metadata must survive admission.
        artifact = replace(artifact, content=json.dumps(json.loads(artifact.content), indent=2),
            source_digest="b" * 64)
        contract = (cpk.cpk_source_runtime_contract(cpk.CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
            if role == "cpk" else secrets.secrets_source_runtime_contract(artifact))
        original = codec.decode_document(document["installation"]["products"][role])
        document["installation"]["products"][role] = json.loads(codec.encode_document(
            replace(original.product, runtime_contract=contract)).content)
    document["installation"]["website"] = {
        "image": FrontendDeploymentTests().image().descriptor(),
        "external_endpoint": "https://web.example.test",
        "host_binding": {"address": "127.0.0.1", "port": 18081}}
    return document


def contract(document, role):
    return document["installation"]["products"][role]["product"]["runtime_contract"]


def replace_artifact_content(document, role, change):
    selected = contract(document, role)["configuration_artifacts"][0]
    artifact = ConfigurationArtifact.from_descriptor(selected)
    content = json.loads(artifact.content)
    change(content)
    contract(document, role)["configuration_artifacts"][0] = replace(
        artifact, content=json.dumps(content)).descriptor()
