"""#191 closed optional selection and actual-artifact metadata laws."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = "1" * 40
REFERENCES = {
    "cpk-server": "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "a" * 64,
    "secrets-server": "ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:" + "b" * 64,
}


class RootArtifactAdmissionTests(unittest.TestCase):
    def owner(self):
        path = ROOT / "scripts/root_artifact_inputs.py"
        self.assertTrue(path.is_file(), "closed current-root artifact admission is missing")
        spec = importlib.util.spec_from_file_location("root_artifact_inputs", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def environment(self):
        return {"CPK_ROOT_ARTIFACT_MODE": "published-digest",
                "CPK_ROOT_CPK_IMAGE": REFERENCES["cpk-server"],
                "CPK_ROOT_SECRETS_IMAGE": REFERENCES["secrets-server"],
                "CPK_ROOT_SOURCE_REVISION": SOURCE}

    def attrs(self, role):
        return {"Id": "sha256:" + "c" * 64, "RepoDigests": [REFERENCES[role]],
                "Os": "linux", "Architecture": "amd64",
                "Config": {"User": "10001" if role == "cpk-server" else "10006",
                           "Labels": {"org.opencontainers.image.revision": SOURCE}}}

    def provenance(self, role):
        pins = json.loads((ROOT / "coordinates/server-products.json").read_text())["upstreams"]
        archive = "https://github.com/OpenJ92/"
        result = {
            "control-plane-kit-core": {"url": archive + "control-plane-kit/archive/" +
                pins["control_plane_kit_core_commit"] + ".zip", "subdirectory": "control-plane-kit-core"},
            "control-plane-kit-server-sdk": {"url": archive + "control-plane-kit-server-sdk/archive/" +
                pins["control_plane_kit_server_sdk_commit"] + ".zip"},
        }
        if role == "cpk-server":
            result["control-plane-kit-operations"] = {"url": archive + "control-plane-kit/archive/" +
                pins["control_plane_kit_operations_commit"] + ".zip", "subdirectory": "control-plane-kit-operations"}
            result["control-plane-kit-interpreters"] = {"url": archive + "control-plane-kit-interpreters/archive/" +
                pins["control_plane_kit_interpreters_commit"] + ".zip"}
        else:
            result["control-plane-kit-secrets"] = {"url": archive + "control-plane-kit-secrets/archive/" +
                pins["control_plane_kit_secrets_commit"] + ".zip"}
        return pins, result

    def rejected(self, module, action):
        with self.assertRaises(module.RootArtifactError) as caught:
            action()
        self.assertEqual(str(caught.exception), "current root artifact input is invalid")
        self.assertNotIn("private-marker", repr(caught.exception))

    def test_default_is_empty_and_explicit_pair_preserves_role_source_and_references(self):
        owner = self.owner()
        for env in ({}, {"CPK_ROOT_ARTIFACT_MODE": "source-built"},
                    {"CPK_ROOT_ARTIFACT_MODE": "source-built", "CPK_ROOT_CPK_IMAGE": "",
                     "CPK_ROOT_SECRETS_IMAGE": "", "CPK_ROOT_SOURCE_REVISION": "", "PATH": "/unrelated"}):
            self.assertIsNone(owner.select_root_artifacts(env))
        self.assertEqual(owner.select_root_artifacts(self.environment()), {
            "mode": "published-digest", "source_revision": SOURCE, "images": REFERENCES})

    def test_partial_unknown_cross_role_tag_or_noncanonical_selection_refuses(self):
        owner = self.owner()
        env = self.environment()
        cases = [{**env, "CPK_ROOT_ARTIFACT_MODE": value}
                 for value in ("", "private-marker", "source-built")]
        cases += [{key: value for key, value in env.items() if key != missing}
                  for missing in env]
        for field in ("CPK_ROOT_CPK_IMAGE", "CPK_ROOT_SECRETS_IMAGE"):
            for value in ("", "private-marker", "sha256:" + "a" * 64,
                          "ghcr.io/foreign/product@sha256:" + "a" * 64,
                          env[field].replace("@sha256:", ":tag@sha256:"),
                          env[field][:-1], env[field] + "\n",
                          env[field].replace("sha256:", "sha256:A"),
                          REFERENCES["secrets-server" if field == "CPK_ROOT_CPK_IMAGE" else "cpk-server"]):
                cases.append({**env, field: value})
        cases += [{**env, "CPK_ROOT_SOURCE_REVISION": value}
                  for value in ("", "develop", "A" * 40, "1" * 39, SOURCE + "\n")]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                self.rejected(owner, lambda: owner.select_root_artifacts(candidate))

    def test_reference_and_execution_identity_remain_distinct_and_stable(self):
        owner = self.owner()
        for role in REFERENCES:
            attrs = self.attrs(role)
            original = deepcopy(attrs)
            proof = owner.qualify_root_artifact(role=role, reference=REFERENCES[role],
                source_revision=SOURCE, image_attrs=attrs)
            self.assertEqual(proof, {"role": role, "reference": REFERENCES[role],
                "source_revision": SOURCE, "execution_id": attrs["Id"], "platform": "linux/amd64"})
            self.assertNotEqual(proof["execution_id"], REFERENCES[role].split("@")[1])
            self.assertEqual(attrs, original)
            self.assertEqual(owner.qualify_root_artifact(role=role, reference=REFERENCES[role],
                source_revision=SOURCE, image_attrs=attrs, expected_execution_id=proof["execution_id"]), proof)
            changed = {**attrs, "Id": "sha256:" + "d" * 64}
            self.rejected(owner, lambda: owner.qualify_root_artifact(role=role,
                reference=REFERENCES[role], source_revision=SOURCE, image_attrs=changed,
                expected_execution_id=proof["execution_id"]))

    def test_absent_wrong_role_platform_user_digest_revision_or_identity_refuses(self):
        owner = self.owner()
        for role in REFERENCES:
            attrs = self.attrs(role)
            candidates = [None, {}, {**attrs, "Id": "private-marker"},
                {**attrs, "RepoDigests": []}, {**attrs, "RepoDigests": [REFERENCES[
                    "secrets-server" if role == "cpk-server" else "cpk-server"]]},
                {**attrs, "Os": "windows"}, {**attrs, "Architecture": "arm64"},
                {**attrs, "Config": {**attrs["Config"], "User": "0"}},
                {**attrs, "Config": {**attrs["Config"], "Labels": {}}},
                {**attrs, "Config": {**attrs["Config"], "Labels": {
                    "org.opencontainers.image.revision": "2" * 40}}}]
            for candidate in candidates:
                with self.subTest(role=role, candidate=candidate):
                    self.rejected(owner, lambda: owner.qualify_root_artifact(role=role,
                        reference=REFERENCES[role], source_revision=SOURCE, image_attrs=candidate))

    def test_actual_container_image_must_equal_the_admitted_execution_identity(self):
        owner = self.owner()
        for role in REFERENCES:
            proof = owner.qualify_root_artifact(role=role, reference=REFERENCES[role],
                source_revision=SOURCE, image_attrs=self.attrs(role))
            owner.require_root_artifact_execution(proof=proof, observed_image_id=proof["execution_id"])
            for observed in (None, "", "sha256:" + "d" * 64, REFERENCES[role],
                             REFERENCES[role].split("@")[1]):
                with self.subTest(role=role, observed=observed):
                    self.rejected(owner, lambda: owner.require_root_artifact_execution(
                        proof=proof, observed_image_id=observed))

    def test_actual_installed_archive_and_subdirectory_match_gate_selected_cohort(self):
        owner = self.owner()
        for role in REFERENCES:
            pins, installed = self.provenance(role)
            owner.require_root_artifact_provenance(role=role, installed=installed, upstreams=pins)
            # Archive hashes are legitimate extra direct_url metadata, not a new source selector.
            with_hash = deepcopy(installed)
            with_hash["control-plane-kit-core"]["archive_info"] = {"hashes": {"sha256": "e" * 64}}
            owner.require_root_artifact_provenance(role=role, installed=with_hash, upstreams=pins)
            cases = [{}]
            for name, metadata in installed.items():
                cases.append({key: value for key, value in installed.items() if key != name})
                for invalid in ({"url": "file:///private-marker"},
                        {**metadata, "url": metadata["url"].replace(".zip", "-wrong.zip")},
                        {**metadata, "subdirectory": "wrong"},
                        {**metadata, "dir_info": {"editable": True}},
                        {**metadata, "vcs_info": {"vcs": "git", "commit_id": SOURCE}}):
                    cases.append({**installed, name: invalid})
                if "subdirectory" in metadata:
                    cases.append({**installed, name: {"url": metadata["url"]}})
            for candidate in cases:
                with self.subTest(role=role, candidate=candidate):
                    self.rejected(owner, lambda: owner.require_root_artifact_provenance(
                        role=role, installed=candidate, upstreams=pins))

    def test_new_gate_cohort_does_not_silently_accept_old_artifact_metadata(self):
        owner = self.owner()
        for role in REFERENCES:
            pins, installed = self.provenance(role)
            changed = {**pins, "control_plane_kit_core_commit": "9" * 40}
            self.rejected(owner, lambda: owner.require_root_artifact_provenance(
                role=role, installed=installed, upstreams=changed))
