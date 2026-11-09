"""Installed installer identity and normal pure CLI routes, never apply/prepare."""
import copy
from dataclasses import replace
import importlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

from grandparent_image_check import distribution, files, verified_git_files
from bootstrap_driver_imports import REQUIRED_IMPORTS

if not __debug__:
    raise SystemExit("bootstrap driver verification requires enabled checks")

PUBLIC = Path("/usr/share/cpk-bootstrap-driver")
BUILD = Path("/opt/cpk-bootstrap-driver-build")
PACKAGES = {
    "core": ("control-plane-kit-core", "control_plane_kit_core", "control-plane-kit-core/src/control_plane_kit_core/"),
    "operations": ("control-plane-kit-operations", "control_plane_kit_operations", "control-plane-kit-operations/src/control_plane_kit_operations/"),
    "interpreters": ("control-plane-kit-interpreters", "control_plane_kit_interpreters", "src/control_plane_kit_interpreters/"),
    "secrets": ("control-plane-kit-secrets", "control_plane_kit_secrets", "src/control_plane_kit_secrets/"),
}


def seal():
    expected = {}
    for role, (dist, module, prefix) in PACKAGES.items():
        expected[module] = {"distribution": dist, "role": role, "files": verified_git_files(
            BUILD / role / "src" / module, prefix, (BUILD / (role + ".git-tree")).read_text().splitlines())}
    project = tomllib.loads((BUILD / "servers/pyproject.toml").read_text())
    tree = (BUILD / "servers.git-tree").read_text().splitlines()
    for where in project["tool"]["setuptools"]["packages"]["find"]["where"]:
        for root in (BUILD / "servers" / where).iterdir():
            if not (root / "__init__.py").is_file():
                continue
            prefix = where + "/" + root.name + "/"
            selected = [line for line in tree if line.split("\t", 1)[1].startswith(prefix)]
            expected[root.name] = {"distribution": "control-plane-kit-servers", "role": "servers",
                                   "files": verified_git_files(root, prefix, selected)}
    assert "control_plane_kit_servers_cpk_server" in expected
    (PUBLIC / "source-files.json").write_text(json.dumps(expected, sort_keys=True) + "\n")
    (PUBLIC / "source-objects.json").write_bytes((BUILD / "source-objects.json").read_bytes())


def verify():
    cohort = json.loads((PUBLIC / "cohort.json").read_text())
    objects = json.loads((PUBLIC / "source-objects.json").read_text())
    expected = json.loads((PUBLIC / "source-files.json").read_text())
    result = {"cohort": cohort, "source_objects": objects, "modules": {}, "distributions": {}}
    for module, spec in expected.items():
        imported = importlib.import_module(module)
        root = Path(imported.__file__).resolve().parent
        assert root == Path(metadata.distribution(spec["distribution"]).locate_file(module)).resolve()
        assert files(root) == spec["files"]
        assert objects[spec["role"]]["commit"] == cohort[spec["role"]]
        result["modules"][module] = {"import_path": str(imported.__file__), "source_files_verified": len(spec["files"])}
        if spec["distribution"] not in result["distributions"]:
            detail = distribution(spec["distribution"])
            assert detail["direct_url"]["url"] == "file:///opt/cpk-bootstrap-driver-build/" + spec["role"]
            result["distributions"][spec["distribution"]] = detail
    sql = [path for path in expected["control_plane_kit_operations"]["files"] if path.endswith(".sql")]
    assert len(sql) == 7
    result["sql_resources_verified"] = sorted(sql)
    for role, name, module, repository in (
            ("sdk", "control-plane-kit-server-sdk", "control_plane_kit_server_sdk", "control-plane-kit-server-sdk"),):
        detail = distribution(name)
        assert detail["direct_url"]["url"] == "https://github.com/OpenJ92/" + repository + "/archive/" + cohort[role] + ".zip"
        imported = importlib.import_module(module)
        assert Path(imported.__file__).resolve().parent == Path(metadata.distribution(name).locate_file(module)).resolve()
        detail["import_path"] = str(imported.__file__)
        result["distributions"][name] = detail
    result["required_imports"] = {name: importlib.import_module(name).__file__ for name in REQUIRED_IMPORTS}
    core_url = "https://github.com/OpenJ92/control-plane-kit/archive/" + cohort["declared_core"] + ".zip#subdirectory=control-plane-kit-core"
    sdk_url = "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/" + cohort["sdk"] + ".zip"
    required_urls = {
        "control-plane-kit-interpreters": {"control-plane-kit-core": core_url},
        "control-plane-kit-server-sdk": {"control-plane-kit-core": core_url},
        "control-plane-kit-secrets": {"control-plane-kit-core": core_url, "control-plane-kit-server-sdk": sdk_url},
        "control-plane-kit-servers": {
            "control-plane-kit-core": core_url,
            "control-plane-kit-operations": core_url.replace("subdirectory=control-plane-kit-core", "subdirectory=control-plane-kit-operations"),
            "control-plane-kit-server-sdk": sdk_url,
            "control-plane-kit-secrets": "https://github.com/OpenJ92/control-plane-kit-secrets/archive/" + cohort["declared_secrets"] + ".zip",
            "control-plane-kit-interpreters": "https://github.com/OpenJ92/control-plane-kit-interpreters/archive/" + cohort["declared_interpreters"] + ".zip",
        },
    }
    result["declared_urls_verified"] = {}
    for name, required in required_urls.items():
        observed = {item.split("@", 1)[0].strip().split("[", 1)[0]: item.split("@", 1)[1].strip()
                    for item in result["distributions"][name]["requires_dist"] if "@" in item}
        assert all(observed.get(dependency) == url for dependency, url in required.items())
        result["declared_urls_verified"][name] = required
    assert subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True).returncode == 0
    result.update(pip_check="passed-version-consistency-only", effective_uid=os.geteuid(),
                  explicit_selected_cohort=True, older_declared_dependency_urls_preserved=True)
    result["cryptography_version"] = metadata.version("cryptography")
    return result


def qualify(driver):
    verify()
    return normal_cli_plans(driver, PUBLIC / "fixtures")


def normal_cli_plans(driver, fixture):
    assert driver.startswith("sha256:") and len(driver) == 71
    sys.path[:0] = [str(fixture / "scripts"), str(fixture / "products/cpk_server/tests")]
    import root_material_preparation_tests as maintained
    maintained.DRIVER = driver
    case = maintained.RootMaterialPreparationTests()
    case.setUp()
    try:
        from control_plane_kit_core.configuration import ConfigurationArtifact
        from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfigurationCodec
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_servers_website_server.managed import control_declaration, control_configuration_artifact
        from test_frontend_deployment import FrontendDeploymentTests
        document = copy.deepcopy(case.document)
        commissioning = document.pop("commissioning")
        public = json.loads(commissioning["public_utf8"])
        selected = ConfigurationArtifact.from_descriptor(public["artifacts"]["secrets"])
        codec = ReceiverNodeControlConfigurationCodec()
        control = codec.decode_bytes(selected.content.encode())
        website = replace(control, target=replace(control.target,
            node_id=replace(control.target.node_id, value="root-a-website"), receiver_id="e" * 32),
            declaration=control_declaration())
        website_artifact = control_configuration_artifact(website)
        document["bootstrap_input"]["installation"]["website"] = {
            "image": FrontendDeploymentTests().image().descriptor(), "external_endpoint": "https://website.example.test",
            "host_binding": {"address": "127.0.0.1", "port": 18081},
            "managed_control_configuration": website_artifact.descriptor()}
        http_intents = ["gateway.http-verification-sample-transit-signing-key", "workload.http-verification-sample-signing-key"]
        document["provider_grants"].extend({"action": action,
            "workspace_id": document["bootstrap_input"]["installation"]["workspace_id"], "intents": http_intents}
            for action in ("secret.write", "secret.resolve"))
        def write(name, value):
            path = case.root / name
            path.write_bytes(value if type(value) is bytes else json.dumps(value).encode())
            return str(path)
        arguments = ["plan", "--input", write("input.json", document),
                     "--commission-plan", write("commission-plan.json", commissioning["plan"]),
                     "--commission-public", write("public.json", commissioning["public_utf8"].encode()),
                     "--commission-complete", write("complete.json", commissioning["completion"]),
                     "--public-sha256", commissioning["public_sha256"],
                     "--commissioning-digest", commissioning["intent_digest"], "--driver", driver]
        first = subprocess.run([sys.executable, "-m", "control_plane_kit_servers_cpk_server.root_material_preparation",
                                *arguments], capture_output=True, timeout=60)
        assert first.returncode == 0 and len(first.stdout) <= 1048576
        material = json.loads(first.stdout)
        second = subprocess.run([sys.executable, "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli", "plan",
                                 "--input", write("bootstrap-input.json", material["bootstrap_plan"]["input"]),
                                 "--driver", driver], capture_output=True, timeout=60)
        assert second.returncode == 0 and len(second.stdout) <= 1048576
        bootstrap = json.loads(second.stdout)
        assert bootstrap == material["bootstrap_plan"] and bootstrap["driver_image_id"] == driver
        graph = GraphDescriptorCodec().decode(bootstrap["graph"])
        assert graph.node("root-a-website").configuration_artifacts == (website_artifact,)
        assert not case.state.exists()
        assert "PRIVATE KEY" not in first.stdout.decode() + second.stdout.decode()
        bad = copy.deepcopy(document)
        bad["provider_grants"].append({"action": "secret.generate-delegation-key",
            "workspace_id": document["bootstrap_input"]["installation"]["workspace_id"], "intents": http_intents})
        refused_arguments = list(arguments)
        refused_arguments[refused_arguments.index("--input") + 1] = write("denied-http-generation.json", bad)
        refused = subprocess.run([sys.executable, "-m", "control_plane_kit_servers_cpk_server.root_material_preparation",
                                  *refused_arguments], capture_output=True, timeout=60)
        assert refused.returncode == 2 and refused.stdout == b""
        assert refused.stderr == b"root material preparation plan is invalid\n" and not case.state.exists()
        from root_material_provider_policy_tests import ProviderPreparationTests
        optional_fixture = ProviderPreparationTests()
        optional_fixture.fixture = case
        optional_document = optional_fixture.document()
        optional_document.pop("commissioning")
        optional_document["bootstrap_input"] = copy.deepcopy(document["bootstrap_input"])
        optional_arguments = list(arguments)
        optional_arguments[optional_arguments.index("--input") + 1] = write("optional-input.json", optional_document)
        optional_process = subprocess.run([sys.executable, "-m", "control_plane_kit_servers_cpk_server.root_material_preparation",
                                           *optional_arguments], capture_output=True, timeout=60)
        assert optional_process.returncode == 0 and len(optional_process.stdout) <= 1048576
        optional_plan = json.loads(optional_process.stdout)
        assert optional_plan["outputs"] == material["outputs"] + ["external-provisioner.token"]
        optional_bootstrap = subprocess.run([sys.executable, "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli", "plan",
            "--input", write("optional-bootstrap-input.json", optional_plan["bootstrap_plan"]["input"]), "--driver", driver],
            capture_output=True, timeout=60)
        assert optional_bootstrap.returncode == 0 and len(optional_bootstrap.stdout) <= 1048576
        assert json.loads(optional_bootstrap.stdout) == optional_plan["bootstrap_plan"] and not case.state.exists()
        return {"driver_image_id": driver, "material_plan_digest": material["digest"],
                "bootstrap_plan_digest": bootstrap["digest"], "normal_cli_routes": ["root_material_preparation plan", "bootstrap_cli plan"],
                "fixture": "synthetic-public-only-read-trust-no-customer-input", "managed_website_included": True,
                "material_contract": "reviewed-bfed7ab-default-and-optional-pure-plans-only",
                "optional_material_plan_digest": optional_plan["digest"],
                "optional_bootstrap_plan_digest": optional_plan["bootstrap_plan"]["digest"],
                "extra_credential_planned_not_created": True,
                "http_import_policy_plan_passed": True, "http_generation_policy_plan_refused": True,
                "real_material_prepared": False, "apply_executed": False, "live_service_started": False}
    finally:
        case.doCleanups()


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["seal"]:
            seal()
        elif sys.argv[1:] == ["verify"]:
            print(json.dumps(verify(), sort_keys=True))
        elif len(sys.argv) == 3 and sys.argv[1] == "qualify":
            print(json.dumps(qualify(sys.argv[2]), sort_keys=True))
        else:
            raise ValueError
    except Exception:
        print("bootstrap driver verification failed", file=sys.stderr)
        raise SystemExit(1) from None
