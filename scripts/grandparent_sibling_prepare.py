"""Public-only inputs for the reviewed #399 local sibling; no runtime effects.

Run in the pinned installer. Commissioning/material generation and Docker
create/start remain separate approved owner commands. No private file is read.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

IDENTITY = "cpk399-sibling-20261114-01"
DRIVER = "sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80"
CPK = "sha256:49ae1044c73f5fb94cce229f736be5fa1ee3d1a0fcbe4e423d54b2831d2986a7"
SECRETS = "sha256:bbcaff85024db94cf4f39269fd91a42acdef74bb0fa6e2049b8d019225603c0a"
WEBSITE = "sha256:93627bde9fb49973f6c8f5368c133c510fc6f7ec039ad66b50851ed1adc19a26"
ENV_ROOT = "/Users/jacobvartuli/Software/self/control-plane-kit-servers/env/" + IDENTITY
PUBLIC_PATH = "/private/tmp/" + IDENTITY + "-public/website-control.json"
LAUNCH_PATH = "/private/tmp/" + IDENTITY + "-launch"
UPSTREAM = "http://" + IDENTITY + "-cpk:8080"
HUMAN_SCOPES = ["instance:workspace:read", "runtime-authority:read",
    "runtime-authority-delivery:read", "ingress-authority:read", "secret-provider:read",
    "delegation-key:read", "node-control:read"]
SETUP_SCOPES = ["instance:workspace:read", "instance:workspace:edit", "secret-provider:register",
    "secret-provider:read", "runtime-authority:register", "runtime-authority:read",
    "runtime-authority-delivery:register", "runtime-authority-delivery:read"]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def require(condition):
    if not condition:
        raise ValueError("sibling public preparation refused")


def root_volume_names(plan):
    return [entry["name"] for node in plan["resources"]["nodes"]
        for field in ("data_volumes", "secret_files", "configuration_files", "installer_files")
        for entry in node.get(field, [])]


def commissioning_intent():
    return dict(schema="cpk.root-commissioning.intent.v1", installation_id=IDENTITY,
        workspace_id=IDENTITY, profile="operator-offline-read-trust",
        custody=dict(host_directory=ENV_ROOT + "-commissioned", uid=501, gid=20))


def material_template(postgres_document):
    """Deliberately not executable until fresh public products are bound."""
    installation = dict(installation_id=IDENTITY, workspace_id=IDENTITY,
        runtime_authority=IDENTITY + "-docker-access",
        runtime_access=dict(authority_ref=dict(reference_id=IDENTITY + "-docker-access"),
            delivery_kind="local-docker-socket-mount", secret_references=[]),
        products=dict(cpk=None, postgres=deepcopy(postgres_document), secrets=None),
        references={name: "secret://bootstrap/" + IDENTITY + "/" + suffix for name, suffix in (
            ("control_credential", "control"), ("postgres_password", "postgres"),
            ("custody_root_key", "custody"), ("provider_credentials_document", "grants"),
            ("provider_client_credential", "client"))}, workspace_grants=[],
        control_auth=dict(kind="multi-principal", principals_document="secret://bootstrap/" + IDENTITY + "/principals"),
        provider_endpoint_ref=IDENTITY + "-secrets", external_endpoint="https://cpk399-sibling-api.invalid")
    installation["references"]["provider_bootstrap_credential_ref"] = "secret://control-plane-kit/" + IDENTITY + "/bootstrap-client"
    return dict(schema="cpk.root-material.intent.v1",
        bootstrap_input=dict(schema="cpk.root-bootstrap.input.v1", installation=installation,
            host_binding=dict(address="127.0.0.1", port=18263),
            setup=dict(workspace_name="Local sibling " + IDENTITY,
                provider=dict(provider_id="control-plane-kit", allowed_reference_prefixes=["secret://control-plane-kit/" + IDENTITY],
                    allowed_intents=["postgres.password", "application.control-token"]),
                secret_references=[], image_pull_authorities=[], ingress_authorities=[])),
        principals={role: dict(issuer="urn:control-plane-kit:static-development",
            subject_id=IDENTITY + "-" + role, kind="worker" if role == "worker" else "operator")
            for role in ("human", "setup", "worker")},
        permissions=dict(human=list(HUMAN_SCOPES), setup=list(SETUP_SCOPES), worker=["instance:workspace:read"]),
        capabilities=[], management=None,
        provider_grants=[dict(action="secret.resolve", workspace_id=IDENTITY,
            intents=["postgres.password", "application.control-token"])],
        custody=dict(host_directory=ENV_ROOT + "-prepared/material", uid=501, gid=20))


def bind_material(template, commission_plan, public_raw, completion):
    """Pure product framing, then validation by the selected material owner."""
    from control_plane_kit_core.configuration import ConfigurationArtifact
    from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
    from control_plane_kit_core.products import ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity
    from control_plane_kit_servers_cpk_server.control_configuration import CpkSourceVariant, cpk_source_runtime_contract
    from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract
    from control_plane_kit_servers_cpk_server.root_material_preparation import plan_root_material_preparation
    require(commission_plan["input"] == commissioning_intent() and commission_plan["preparer_image_id"] == DRIVER)
    require(template == material_template(template["bootstrap_input"]["installation"]["products"]["postgres"]))
    public = json.loads(public_raw)
    value = deepcopy(template)
    products = value["bootstrap_input"]["installation"]["products"]
    for role, digest, factory in (("cpk", CPK, lambda a: cpk_source_runtime_contract(CpkSourceVariant.DOCKER_CLOUDFLARE, a)),
                                  ("secrets", SECRETS, secrets_source_runtime_contract)):
        artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
        contract = factory(artifact)
        if role == "cpk":
            contract = replace(contract, public_environment=(*contract.public_environment,
                PublicStaticEnvironmentBinding("CPK_MCP_PROFILE", "grandparent-read-only-v1")))
        product = ContainerServerProduct(ProductIdentity("control-plane-kit",
            "cpk-server-docker-cloudflare" if role == "cpk" else "secrets-server", 1),
            OciImageReference("localhost", "control-plane-kit-servers/" + ("cpk-grandparent" if role == "cpk" else "secrets-server"), digest),
            contract)
        products[role] = json.loads(ProductDescriptorCodec().encode_document(product).content)
    value["commissioning"] = dict(plan=commission_plan, intent_digest=commission_plan["digest"],
        public_utf8=public_raw.decode(), public_sha256=sha256(public_raw).hexdigest(), completion=completion)
    plan = plan_root_material_preparation(value, driver_image_id=DRIVER)
    volumes = root_volume_names(plan["bootstrap_plan"])
    require(len(volumes) <= 10 and len(set(volumes)) == len(volumes))
    # Keep the CLI input public and unprojected; the existing launcher attaches
    # its separately pinned commissioning snapshot again during material-plan.
    del value["commissioning"]
    return value, plan


def website_artifact(public_raw, receiver_id):
    import control_plane_kit_core as core
    # Only the existing public product factory is loaded for offline rendering;
    # no server process or installed product module is replaced.
    sys.path.insert(0, "/source/products/website_server/src")
    from control_plane_kit_servers_website_server.managed import control_configuration_artifact, control_declaration
    public = json.loads(public_raw)
    require(public["schema"] == "cpk.root-commissioning.public.v1")
    require(re.fullmatch(r"[0-9a-f]{32}", receiver_id) and receiver_id not in public["receiver_ids"].values())
    config = core.ReceiverNodeControlConfigurationCodec().decode_bytes(public["artifacts"]["cpk"]["content"].encode())
    target = config.target.descriptor()
    require(target == dict(workspace_id=IDENTITY, runtime_id=IDENTITY + "-docker", node_id=IDENTITY + "-cpk",
        provider_socket_name="http-api", receiver_id=public["receiver_ids"]["cpk"]))
    roles = core.NodeControlGraphReferenceRole
    target = core.NodeControlReceiverTarget(*(core.NodeControlGraphReference(role, name) for role, name in (
        (roles.WORKSPACE, IDENTITY), (roles.RUNTIME, IDENTITY + "-docker"),
        (roles.NODE, IDENTITY + "-website"), (roles.PROVIDER_SOCKET, "control"))), receiver_id)
    return control_configuration_artifact(replace(config, target=target, declaration=control_declaration()))


def website_action(plan, result, artifact):
    """Freeze native create/start argv from a completed NEW bootstrap receipt.

    This function has no Docker client. Effective network/alias/proxy/image and
    ownership still need authoritative inspection before any human bearer use.
    """
    from control_plane_kit_servers_cpk_server.bootstrap import verified_plan
    import control_plane_kit_core as core
    verified_plan(plan, expected_digest=plan["digest"], driver_image_id=DRIVER)
    require(plan["input"]["installation"]["installation_id"] == IDENTITY
        and "website" not in plan["input"]["installation"])
    target = core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode()).target.descriptor()
    require(target["workspace_id"] == IDENTITY and target["runtime_id"] == IDENTITY + "-docker"
        and target["node_id"] == IDENTITY + "-website" and target["provider_socket_name"] == "control")
    receipt = result["receipt"]
    require(result["status"] == "local-ready" and receipt["phase"] == "complete" and receipt["pending"] is None)
    require(receipt["plan_digest"] == plan["digest"] and receipt["driver_image_id"] == DRIVER)
    require(receipt["setup_workspace_id"] == IDENTITY and receipt["labels"]["org.openj92.cpk.installation"] == IDENTITY)
    network_name = plan["resources"]["network"]["name"]
    require(set(receipt["resources"]["networks"]) == {network_name})
    network = receipt["resources"]["networks"][network_name]["id"]
    cpk = receipt["resources"]["containers"][IDENTITY + "-cpk"]["id"]
    require(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (network, cpk)))
    argv = ["docker", "create", "--pull", "never", "--name", "cpk-" + IDENTITY + "-website",
        "--network", network, "--network-alias", IDENTITY + "-website", "--publish", "127.0.0.1:18264:8080/tcp",
        "--restart", "no", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--log-driver", "none", "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777",
        "--env", "PORT=8080", "--env", "CPK_WEB_UPSTREAM=" + UPSTREAM,
        "--env", "CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/website/control.json",
        "--mount", "type=bind,source=" + PUBLIC_PATH + ",target=/etc/cpk/website/control.json,readonly",
        "--label", "org.openj92.cpk.installation=" + IDENTITY,
        "--label", "org.openj92.cpk.operator-action=" + IDENTITY + "-website-initial",
        "--cidfile", LAUNCH_PATH + "/website.cid", WEBSITE]
    return dict(schema="cpk399.sibling-website-action.v1", approved=False, operator_bootstrap_owned=True,
        bootstrap_plan_digest=plan["digest"], engine_id=receipt["engine_id"], network_id=network,
        cpk_container_id=cpk, website_public_sha256=artifact.content_digest,
        create_argv=argv, start_argv=["docker", "start", "RESULT.NEW_WEBSITE_CID"],
        automatic_retry=False, automatic_cleanup=False, cpk_deployment_acceptance=False)


def main():
    try:
        mode, *args = sys.argv[1:]
        if mode == "commission-intent" and not args:
            result = commissioning_intent()
        elif mode == "material-template" and len(args) == 1:
            result = material_template(json.loads(Path(args[0]).read_bytes()))
        elif mode == "bind-material" and len(args) == 4:
            result, _plan = bind_material(json.loads(Path(args[0]).read_bytes()), json.loads(Path(args[1]).read_bytes()),
                Path(args[2]).read_bytes(), json.loads(Path(args[3]).read_bytes()))
        elif mode == "website-artifact" and len(args) == 2:
            result = website_artifact(Path(args[0]).read_bytes(), args[1]).descriptor()
        elif mode == "website-action" and len(args) == 3:
            from control_plane_kit_core.configuration import ConfigurationArtifact
            result = website_action(json.loads(Path(args[0]).read_bytes()), json.loads(Path(args[1]).read_bytes()),
                ConfigurationArtifact.from_descriptor(json.loads(Path(args[2]).read_bytes())))
        else:
            raise ValueError
        print(canonical(result).decode())
        return 0
    except Exception:
        print('{"status":"HOLD","stage":"public-preparation"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
