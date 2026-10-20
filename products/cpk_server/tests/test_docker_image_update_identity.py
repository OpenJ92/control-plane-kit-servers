"""#191 fixed-artifact identity proofs; pure observations, never Docker I/O."""
from dataclasses import replace
import hashlib
import importlib
import json
import unittest
from unittest.mock import Mock

from image_identity_test_material import FIXED, clients, manifest_bytes, observations, qualified_images


class FixedArtifactIdentityTests(unittest.TestCase):
    def qualify(self, attrs, *, role="hello_family", raw=None, reference=None, interpreter_id=None):
        module = importlib.import_module("docker_image_update_identity")
        return module.qualify_fixed_image(role,
            reference=FIXED[role]["reference"] if reference is None else reference,
            manifest_bytes=manifest_bytes(role) if raw is None else raw,
            image_attrs=attrs, interpreter_image_id=interpreter_id)

    def test_original_five_manifests_bind_reference_to_unchanged_config(self):
        for role, selected in FIXED.items():
            with self.subTest(role=role):
                raw = manifest_bytes(role)
                self.assertEqual("sha256:" + hashlib.sha256(raw).hexdigest(),
                                 selected["reference"].split("@")[1])
                manifest = json.loads(raw)
                self.assertEqual(manifest["schemaVersion"], 2)
                self.assertNotIn("manifests", manifest)
                self.assertEqual(manifest["config"]["digest"], selected["image_id"])

    def test_config_identity_allows_omitted_null_or_coherent_descriptor(self):
        for descriptor in ("omitted", None, observations()["hello_family"]["Descriptor"]):
            with self.subTest(descriptor=descriptor):
                attrs = observations("config-valued")["hello_family"]
                if descriptor != "omitted":
                    attrs["Descriptor"] = descriptor
                proof = self.qualify(attrs, interpreter_id=attrs["Id"])
                self.assertEqual(proof.config_digest, FIXED["hello_family"]["image_id"])
                self.assertEqual(proof.execution_id, proof.config_digest)
                self.assertEqual(proof.manifest_digest, FIXED["hello_family"]["reference"].split("@")[1])
                self.assertEqual(proof.proof_form, "config-valued")
                self.assertEqual(proof.platform, "linux/amd64")

    def test_manifest_identity_requires_and_retains_distinct_linked_identities(self):
        for role, attrs in observations().items():
            with self.subTest(role=role):
                proof = self.qualify(attrs, role=role, interpreter_id=attrs["Id"])
                self.assertEqual(proof.reference, FIXED[role]["reference"])
                self.assertEqual(proof.execution_id, proof.manifest_digest)
                self.assertEqual(proof.config_digest, FIXED[role]["image_id"])
                self.assertNotEqual(proof.execution_id, proof.config_digest)
                self.assertEqual(proof.proof_form, "manifest-valued")

    def test_manifest_identity_refuses_omitted_or_null_descriptor(self):
        for descriptor in ("omitted", None):
            attrs = observations()["hello_family"]
            if descriptor == "omitted":
                attrs.pop("Descriptor")
            else:
                attrs["Descriptor"] = None
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                self.qualify(attrs)

    def test_nonnull_descriptor_contradictions_never_fall_back(self):
        original = observations()["hello_family"]["Descriptor"]
        invalid = [{}, [], "manifest", {**original, "digest": FIXED["hello_family"]["image_id"]},
                   {**original, "mediaType": "application/vnd.oci.image.index.v1+json"},
                   {**original, "size": original["size"] + 1},
                   {**original, "size": True},
                   {**original, "platform": {"os": "linux", "architecture": "arm64"}}]
        for form in ("config-valued", "manifest-valued"):
            for descriptor in invalid:
                with self.subTest(form=form, descriptor=descriptor):
                    attrs = observations(form)["hello_family"]
                    attrs["Descriptor"] = descriptor
                    with self.assertRaises(ValueError):
                        self.qualify(attrs)

    def test_fixed_selection_rejects_missing_tampered_or_foreign_linkage(self):
        attrs = observations()["hello_family"]
        raw = manifest_bytes("hello_family")
        changed = json.loads(raw)
        changed["config"]["digest"] = FIXED["hello_a"]["image_id"]
        for candidate in (b"", raw + b"\n", manifest_bytes("hello_a"),
                          json.dumps(changed).encode(), b'{"manifests": []}'):
            with self.subTest(raw_size=len(candidate)), self.assertRaises(ValueError):
                self.qualify(attrs, raw=candidate)
        for reference in (FIXED["hello_a"]["reference"], "unreviewed.invalid/image:latest"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.qualify(attrs, reference=reference)
        module = importlib.import_module("docker_image_update_identity")
        with self.assertRaises(ValueError):
            module.qualify_fixed_image("optional-extra", reference=FIXED["hello_family"]["reference"],
                manifest_bytes=raw, image_attrs=attrs)

    def test_local_metadata_and_interpreter_must_agree_with_fixed_artifact(self):
        for field, wrong in (("Id", "sha256:" + "f" * 64), ("RepoDigests", []),
                             ("RepoDigests", [FIXED["hello_a"]["reference"]]),
                             ("Os", "windows"), ("Architecture", "arm64")):
            attrs = observations()["hello_family"]
            attrs[field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                self.qualify(attrs)
        for change in ("user", "source"):
            attrs = observations()["hello_family"]
            if change == "user":
                attrs["Config"]["User"] = "root"
            else:
                attrs["Config"]["Labels"]["org.opencontainers.image.revision"] = "foreign"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.qualify(attrs)
        connector = observations()["connector"]
        connector["Config"]["Entrypoint"] = ["/bin/sh"]
        with self.assertRaises(ValueError):
            self.qualify(connector, role="connector")
        with self.assertRaises(ValueError):
            self.qualify(observations()["hello_family"], interpreter_id="sha256:" + "f" * 64)

    def test_admission_refuses_absent_or_disagreeing_interpreter_without_effects(self):
        from live_docker_image_update import inspect_inputs
        for selected in (None, type("Inspection", (), {"image_id": "sha256:" + "f" * 64})()):
            engine, sdk = clients()
            sdk.inspect_image = lambda reference: selected
            engine.containers = Mock()
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                inspect_inputs(engine, sdk)
            engine.containers.create.assert_not_called()

    def test_bound_complete_map_copies_input_and_freezes_proof_values(self):
        module = importlib.import_module("docker_image_update_identity")
        initial = qualified_images("manifest-valued")
        mutable = dict(initial.images)
        bound = module.bind_fixed_images("daemon-a", mutable)
        mutable.clear()
        self.assertEqual(set(bound.images), set(FIXED))
        self.assertEqual(bound.daemon_id, "daemon-a")
        with self.assertRaises(TypeError):
            bound.images["hello_a"] = bound.images["hello_b"]
        with self.assertRaises(AttributeError):
            bound.images["hello_a"].execution_id = "sha256:" + "f" * 64
        encoded = bound.descriptor()
        self.assertEqual(encoded["daemon_id"], "daemon-a")
        self.assertEqual(set(encoded["images"]), set(FIXED))
        for role, proof in bound.images.items():
            self.assertEqual(encoded["images"][role], {
                "role": role, "reference": proof.reference, "manifest_digest": proof.manifest_digest,
                "config_digest": proof.config_digest, "execution_id": proof.execution_id,
                "proof_form": proof.proof_form, "platform": "linux/amd64"})
        encoded["images"]["hello_a"]["execution_id"] = "foreign"
        self.assertNotEqual(bound.images["hello_a"].execution_id, "foreign")

    def test_binding_refuses_missing_conflicting_or_foreign_expectations(self):
        module = importlib.import_module("docker_image_update_identity")
        good = qualified_images()
        missing = dict(good.images)
        missing.pop("gateway")
        conflict = {**good.images, "hello_a": good.images["hello_b"]}
        extra = {**good.images, "optional-extra": good.images["hello_a"]}
        for proofs in (missing, conflict, extra):
            with self.subTest(roles=list(proofs)), self.assertRaises(ValueError):
                module.bind_fixed_images("daemon-a", proofs)
        with self.assertRaises(ValueError):
            module.bind_fixed_images("", good.images)
        with self.assertRaises(ValueError):
            altered = replace(good.images["hello_a"], execution_id="sha256:" + "f" * 64)
            module.bind_fixed_images("daemon-a", {**good.images, "hello_a": altered})
